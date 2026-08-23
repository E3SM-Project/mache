"""
Render a placement against every machine config mache ships.

The synthetic configs in ``test_parallel_placement.py`` only cover the option
combinations someone thought to write down. A real config held one that
nobody had: Polaris sets ``cpu_bind = cores``, a binding policy rather than a
list of cores, and the placement's own ``--cpu-bind list:`` was emitted
alongside it. Rendering against the shipped configs is what catches that
class of bug, so it happens here rather than by remembering to run a script
when a machine is added.
"""

from configparser import ConfigParser
from pathlib import Path
from typing import List

import pytest

from mache import MachineInfo
from mache.parallel import PlacementSupport, ResourcePlacement
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem, _get_parallel_configs

REPO_ROOT = Path(__file__).resolve().parents[1]
MACHINES_DIR = REPO_ROOT / 'mache' / 'machines'

# both eras of Slurm, since CI will only ever have one and the two render
# entirely different flag sets
MODERN_SLURM = (25, 11)
LEGACY_SLURM = (20, 2)


def _get_machine_config_names() -> List[str]:
    return sorted(
        path.stem
        for path in MACHINES_DIR.glob('*.cfg')
        if path.stem != 'default'
    )


def _get_compilers(config: ConfigParser) -> List[str]:
    """Get the compilers a machine gives its own parallel options."""
    compilers = [
        section[len('parallel.') :]
        for section in config.sections()
        if section.startswith('parallel.')
    ]
    # a machine with no compiler sections still has its base [parallel]
    return compilers if len(compilers) > 0 else ['']


def _get_config(machine: str, compiler: str) -> ConfigParser:
    config = MachineInfo(machine=machine).config
    if not config.has_section('build'):
        config.add_section('build')
    config.set('build', 'compiler', compiler)
    return config


def _get_system(
    config: ConfigParser, monkeypatch, slurm_version
) -> ParallelSystem | None:
    """
    Build the parallel system a machine's config asks for.

    Returns ``None`` for a machine that defines no parallel system at all --
    Andes and Bebop ship no ``[parallel]`` section, so mache only ever treats
    them as login nodes.
    """
    system_name = config.get('parallel', 'system', fallback=None)
    if system_name is None:
        return None

    if system_name == 'slurm':
        monkeypatch.setenv('SLURM_JOB_ID', '12345')
        monkeypatch.setattr(
            'mache.parallel.slurm._get_subprocess_int', lambda args: 2
        )
        monkeypatch.setattr(
            'mache.parallel.slurm.get_slurm_version', lambda: slurm_version
        )
        return SlurmSystem(config)

    if system_name == 'pbs':
        monkeypatch.setenv('PBS_JOBID', '12345.server')
        monkeypatch.setattr(
            PbsSystem, '_get_node_count_from_qstat', lambda self: 2
        )
        # honor what each machine actually runs: Aurora and Polaris launch
        # with PALS, while Improv's Open MPI mpirun has no placement mechanism
        monkeypatch.setattr(
            'mache.parallel.pbs.is_pals_launcher',
            lambda executable: executable.endswith('mpiexec'),
        )
        return PbsSystem(config)

    if system_name == 'single_node':
        monkeypatch.setattr(
            'mache.parallel.single_node.shutil.which',
            lambda name: '/usr/bin/taskset',
        )
        return SingleNodeSystem(config)

    raise AssertionError(f'unexpected parallel system: {system_name}')


def _get_flags(command: List[str]) -> List[str]:
    """Get the flags in a command, without the values attached to them."""
    return [arg.split('=', 1)[0] for arg in command if arg.startswith('-')]


def _get_duplicates(flags: List[str]) -> List[str]:
    return sorted({flag for flag in flags if flags.count(flag) > 1})


@pytest.mark.parametrize('machine', _get_machine_config_names())
@pytest.mark.parametrize('slurm_version', [MODERN_SLURM, LEGACY_SLURM])
def test_machine_configs_render_each_flag_once(
    monkeypatch, machine, slurm_version
):
    """No machine's own binding config collides with a placement's."""
    checked = 0
    for compiler in _get_compilers(MachineInfo(machine=machine).config):
        config = _get_config(machine, compiler)
        system = _get_system(config, monkeypatch, slurm_version)
        if system is None:
            continue

        if system.placement_support is PlacementSupport.NONE:
            continue

        parallel_configs = _get_parallel_configs(config)
        max_tasks = int(parallel_configs.get('max_mpi_tasks_per_node', 0))
        if max_tasks < 1:
            continue

        ntasks = min(2, max_tasks)
        cpus_per_task = 2
        # start at core 1: Aurora reserves core 0, so a real placement there
        # would not use it
        cores = list(range(1, ntasks * cpus_per_task + 1))

        for placement in _get_placements(system, config, cores):
            command = system.get_parallel_command(
                args=['./run.py'],
                ntasks=ntasks,
                cpus_per_task=cpus_per_task,
                placement=placement,
            )
            duplicates = _get_duplicates(_get_flags(command))
            assert duplicates == [], (
                f'{machine} ({compiler or "no compiler section"}, '
                f'slurm {slurm_version}, gpus={placement.gpus}) renders '
                f'{duplicates} more than once: {" ".join(command)}'
            )

            # guard against the check passing because nothing was placed
            if system.placement_support is PlacementSupport.SCHEDULER:
                assert '--exact' in command
            else:
                assert (
                    any(arg.startswith('--cpu-bind') for arg in command)
                    or command[0] == 'taskset'
                )

            checked += 1

    if checked == 0:
        pytest.skip(f'{machine} cannot place a launch')


def _get_placements(
    system: ParallelSystem, config: ConfigParser, cores: List[int]
) -> List[ResourcePlacement]:
    """Get the placements worth rendering on a machine."""
    placements = [ResourcePlacement(nodes=['node0'], cores=cores)]

    parallel_configs = _get_parallel_configs(config)
    gpus_per_node = int(parallel_configs.get('gpus_per_node', 0))
    if gpus_per_node < 1:
        return placements

    if system.placement_support is PlacementSupport.SCHEDULER:
        # the scheduler assigns the GPUs, so only a total is given
        placements.append(
            ResourcePlacement(nodes=['node0'], cores=cores, gpus=1)
        )
    elif parallel_configs.get('gpu_visible_devices_var'):
        # PALS has no scheduler to assign them, so the caller names them
        placements.append(
            ResourcePlacement(
                nodes=['node0'], cores=cores, gpus=1, gpu_ids=[0]
            )
        )

    return placements


@pytest.mark.parametrize('machine', _get_machine_config_names())
def test_machine_configs_are_unchanged_without_a_placement(
    monkeypatch, machine
):
    """Every shipped config still renders its command as it always has."""
    for compiler in _get_compilers(MachineInfo(machine=machine).config):
        config = _get_config(machine, compiler)
        system = _get_system(config, monkeypatch, MODERN_SLURM)
        if system is None:
            continue

        parallel_configs = _get_parallel_configs(config)
        max_tasks = int(parallel_configs.get('max_mpi_tasks_per_node', 0))
        if max_tasks < 1:
            continue

        command = system.get_parallel_command(
            args=['./run.py'], ntasks=min(2, max_tasks), cpus_per_task=2
        )
        assert command[-1] == './run.py'
        assert '--exact' not in command
        assert '--gres=none' not in command
        assert not any(arg.startswith('--env-remove') for arg in command)
