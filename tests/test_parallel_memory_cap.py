"""
Check the optional memory cap on a launch.

A cap is a limit, not a reservation, and it is only worth anything where the
batch system acts on it: a step allowed 1024 MB and told to take 4 GB is
killed at 960 MB on Perlmutter and Frontier, and runs to completion on
Chrysalis, whose Slurm predates 20.11. So the cap must render where it bites
and render nothing where it does not, since a figure on the command line that
nothing keeps reads as a safety net that is not there.
"""

from configparser import ConfigParser

import pytest

from mache.parallel import MemoryCapSupport, ResourcePlacement
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem

# both eras are in production on machines mache supports and CI will only
# ever have one, so the version is faked
MODERN_SLURM = (25, 11)
LEGACY_SLURM = (20, 2)


def _get_config(parallel_items: dict[str, str]) -> ConfigParser:
    config = ConfigParser()
    config.add_section('build')
    config.set('build', 'compiler', 'gnu')
    config.add_section('parallel')
    for key, value in parallel_items.items():
        config.set('parallel', key, value)
    return config


def _get_slurm_system(monkeypatch, version, **parallel_items) -> SlurmSystem:
    items = {
        'parallel_executable': 'srun --label',
        'cores_per_node': '64',
        'max_mpi_tasks_per_node': '16',
        'memory_per_node': '253000',
    }
    items.update(parallel_items)
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )
    monkeypatch.setattr(
        'mache.parallel.slurm.get_slurm_version', lambda: version
    )
    return SlurmSystem(_get_config(items))


def _get_pbs_system(monkeypatch, **parallel_items) -> PbsSystem:
    items = {
        'parallel_executable': 'mpiexec --label',
        'cores_per_node': '64',
        'max_mpi_tasks_per_node': '16',
        'cpus_per_task_flag': '--depth',
        'memory_per_node': '960000',
    }
    items.update(parallel_items)
    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )
    monkeypatch.setattr(
        'mache.parallel.pbs.is_pals_launcher', lambda executable: True
    )
    return PbsSystem(_get_config(items))


def _get_single_node_system(monkeypatch, **parallel_items):
    items = {'parallel_executable': 'mpirun', 'cores_per_node': '8'}
    items.update(parallel_items)
    monkeypatch.setattr(
        'mache.parallel.single_node.shutil.which', lambda name: '/usr/bin/tsk'
    )
    return SingleNodeSystem(_get_config(items))


def _has_memory_option(command):
    return any(arg.startswith('--mem=') for arg in command)


# --- where the cap is enforced ---------------------------------------------


def test_modern_slurm_renders_the_cap(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, cpus_per_task=2, memory_cap=1024
    )
    assert system.memory_cap_support is MemoryCapSupport.ENFORCED
    assert '--mem=1024M' in command
    assert command[-1] == './run.py'


def test_the_cap_survives_alongside_a_placement(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    placement = ResourcePlacement(nodes=['nid001'], cores=[0, 1, 2, 3])
    command = system.get_parallel_command(
        args=['./run.py'],
        ntasks=2,
        cpus_per_task=2,
        placement=placement,
        memory_cap=4096,
    )
    # a placement says where, and a cap says how much memory; both apply
    assert '--exact' in command
    assert '--mem=4096M' in command


def test_a_cap_above_memory_per_node_is_still_rendered(monkeypatch):
    """memory_per_node is a planning estimate, not a limit to validate on."""
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    assert system.memory_per_node == 253000
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=1, memory_cap=400000
    )
    assert '--mem=400000M' in command


# --- where it is not -------------------------------------------------------


def test_legacy_slurm_renders_no_cap(monkeypatch):
    """Chrysalis accepts --mem on a step and does not act on it."""
    system = _get_slurm_system(monkeypatch, LEGACY_SLURM)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, cpus_per_task=2, memory_cap=1024
    )
    assert system.memory_cap_support is MemoryCapSupport.NONE
    assert not _has_memory_option(command)


def test_slurm_of_unknown_version_renders_no_cap(monkeypatch):
    system = _get_slurm_system(monkeypatch, None)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, memory_cap=1024
    )
    assert system.memory_cap_support is MemoryCapSupport.NONE
    assert not _has_memory_option(command)


def test_pals_renders_no_cap(monkeypatch):
    """PALS has no memory option to give."""
    system = _get_pbs_system(monkeypatch)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, cpus_per_task=2, memory_cap=1024
    )
    assert system.memory_cap_support is MemoryCapSupport.NONE
    assert not _has_memory_option(command)


def test_single_node_renders_no_cap(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, memory_cap=1024
    )
    assert system.memory_cap_support is MemoryCapSupport.NONE
    assert not _has_memory_option(command)


# --- absent by default -----------------------------------------------------


@pytest.mark.parametrize('version', [MODERN_SLURM, LEGACY_SLURM])
def test_no_cap_renders_nothing_about_memory(monkeypatch, version):
    system = _get_slurm_system(monkeypatch, version)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, cpus_per_task=2
    )
    assert not _has_memory_option(command)


@pytest.mark.parametrize('memory_cap', [0, -1])
def test_a_cap_that_means_nothing_is_refused(monkeypatch, memory_cap):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    with pytest.raises(ValueError, match='must be positive'):
        system.get_parallel_command(
            args=['./run.py'], ntasks=2, memory_cap=memory_cap
        )
