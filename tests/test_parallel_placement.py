from configparser import ConfigParser

import pytest

from mache.parallel import PlacementSupport, ResourcePlacement
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem

# a modern Slurm, which reserves what a job step asks for, and a pre-20.11
# one, where the options that do that neither exist nor are accepted.  Both
# are in production on machines mache supports and CI will only ever have one,
# so the version is faked.
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
    }
    items.update(parallel_items)
    config = _get_config(items)

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )
    monkeypatch.setattr(
        'mache.parallel.slurm.get_slurm_version', lambda: version
    )
    return SlurmSystem(config)


def _get_pbs_system(monkeypatch, is_pals=True, **parallel_items) -> PbsSystem:
    items = {
        'parallel_executable': 'mpiexec --label',
        'cores_per_node': '64',
        'max_mpi_tasks_per_node': '16',
        'cpus_per_task_flag': '--depth',
    }
    items.update(parallel_items)
    config = _get_config(items)

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )
    monkeypatch.setattr(
        'mache.parallel.pbs.is_pals_launcher', lambda executable: is_pals
    )
    return PbsSystem(config)


def _get_single_node_system(monkeypatch, **parallel_items):
    items = {'parallel_executable': 'mpirun', 'cores_per_node': '8'}
    items.update(parallel_items)
    monkeypatch.setattr(
        'mache.parallel.single_node.shutil.which', lambda name: '/usr/bin/tsk'
    )
    return SingleNodeSystem(_get_config(items))


def _get_flag_value(args, flag):
    """Get the value of ``--flag=value`` or of ``flag value``."""
    for index, arg in enumerate(args):
        if arg == flag:
            return args[index + 1]
        if arg.startswith(f'{flag}='):
            return arg[len(flag) + 1 :]
    return None


# --- the placement description ---------------------------------------------


def test_placement_requires_cores():
    with pytest.raises(ValueError, match='at least one core'):
        ResourcePlacement(nodes=['nid001'], cores=[])


def test_placement_rejects_duplicate_cores():
    with pytest.raises(ValueError, match='cores must be unique'):
        ResourcePlacement(nodes=['nid001'], cores=[0, 1, 1])


def test_placement_defaults_to_no_gpus():
    placement = ResourcePlacement(nodes=['nid001'], cores=[0, 1])
    assert placement.gpus == 0
    assert placement.gpu_ids is None


def test_placement_gpu_ids_must_match_the_total():
    """A mismatch is a scheduler bug, caught here rather than hours later."""
    with pytest.raises(ValueError, match='lists 1 gpu_ids but asks for 2'):
        ResourcePlacement(nodes=['x1'], cores=[0, 1], gpus=2, gpu_ids=[0])


def test_placement_normalizes_sequences_to_tuples():
    placement = ResourcePlacement(
        nodes=['x1'], cores=[5, 4], gpus=1, gpu_ids=[3]
    )
    assert placement.nodes == ('x1',)
    # core order is preserved, since it is the order tasks are given cores in
    assert placement.cores == (5, 4)
    assert placement.gpu_ids == (3,)


# --- existing behavior is unchanged ----------------------------------------


def test_slurm_without_placement_is_unchanged(monkeypatch):
    system = _get_slurm_system(
        monkeypatch,
        MODERN_SLURM,
        cpu_bind='cores',
        placement='plane',
    )
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=4, cpus_per_task=2
    )
    assert command == [
        'srun',
        '--label',
        '-c',
        '2',
        '-N',
        '1',
        '-n',
        '4',
        '--cpu-bind=cores',
        '-m',
        'plane=16',
        './run.py',
    ]


def test_pbs_without_placement_is_unchanged(monkeypatch):
    system = _get_pbs_system(monkeypatch, cpu_bind='core')
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=4, cpus_per_task=2
    )
    assert command == [
        'mpiexec',
        '--label',
        '-n',
        '4',
        '--ppn',
        '4',
        '--depth',
        '2',
        '--cpu-bind',
        'core',
        './run.py',
    ]


def test_single_node_without_placement_is_unchanged(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=4, cpus_per_task=2
    )
    assert command == ['mpirun', '-n', '4', '-c', '2', './run.py']


# --- Slurm 20.11 and newer -------------------------------------------------


def test_modern_slurm_reports_scheduler_placement(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    assert system.placement_support is PlacementSupport.SCHEDULER


def test_modern_slurm_places_on_one_node(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert args == [
        '-c',
        '2',
        '-N',
        '1',
        '-n',
        '4',
        '-w',
        'nid001',
        '--exact',
        '--gres=none',
    ]


def test_modern_slurm_places_on_several_nodes(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    placement = ResourcePlacement(
        nodes=['nid001', 'nid002'], cores=list(range(8))
    )
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert _get_flag_value(args, '-w') == 'nid001,nid002'
    assert _get_flag_value(args, '-N') == '2'


def test_modern_slurm_asks_for_a_gpu_total(monkeypatch):
    """A per-task count was measured not to confine a launch."""
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    placement = ResourcePlacement(
        nodes=['nid001'], cores=list(range(8)), gpus=2
    )
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=1, ntasks=4, placement=placement
    )
    assert '--gpus=2' in args
    assert '--gres=none' not in args
    assert not any(arg.startswith('--gpus-per-task') for arg in args)


def test_modern_slurm_makes_no_gpus_explicit(monkeypatch):
    """Saying nothing is read as claiming every GPU on the node."""
    system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert '--gres=none' in args


def test_modern_slurm_keeps_a_binding_policy(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM, cpu_bind='cores')
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert '--cpu-bind=cores' in args


def test_modern_slurm_drops_a_binding_that_names_cpus(monkeypatch):
    system = _get_slurm_system(
        monkeypatch, MODERN_SLURM, cpu_bind='list:0-7:8-15'
    )
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert not any(arg.startswith('--cpu-bind') for arg in args)


def test_modern_slurm_drops_gpu_binding_when_no_gpus(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM, gpu_bind='closest')
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert not any(arg.startswith('--gpu-bind') for arg in args)


def test_modern_slurm_keeps_gpu_binding_when_gpus_asked_for(monkeypatch):
    system = _get_slurm_system(monkeypatch, MODERN_SLURM, gpu_bind='closest')
    placement = ResourcePlacement(
        nodes=['nid001'], cores=list(range(8)), gpus=2
    )
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert '--gpu-bind=closest' in args


def test_placement_supersedes_the_distribution(monkeypatch):
    system = _get_slurm_system(
        monkeypatch,
        MODERN_SLURM,
        distribution='block:cyclic',
        placement='plane',
    )
    placement = ResourcePlacement(nodes=['nid001'], cores=list(range(8)))
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4, placement=placement
    )
    assert '-m' not in args


# --- Slurm before 20.11 ----------------------------------------------------


def test_legacy_slurm_reports_cpu_binding(monkeypatch):
    system = _get_slurm_system(monkeypatch, LEGACY_SLURM)
    assert system.placement_support is PlacementSupport.CPU_BINDING


def test_legacy_slurm_places_with_an_explicit_mask(monkeypatch):
    system = _get_slurm_system(monkeypatch, LEGACY_SLURM, cpu_bind='cores')
    placement = ResourcePlacement(nodes=['chr-0493'], cores=[0, 1, 2, 3])
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=2, placement=placement
    )
    # the options that reserve resources do not exist before 20.11 and are an
    # error rather than a no-op there
    assert '--exact' not in args
    assert '--gres=none' not in args
    # one mask per task: cores 0-1 then cores 2-3
    assert args == [
        '-c',
        '2',
        '-N',
        '1',
        '-n',
        '2',
        '-w',
        'chr-0493',
        '--cpu-bind=mask_cpu:0x3,0xc',
    ]


def test_legacy_slurm_masks_non_contiguous_cores(monkeypatch):
    system = _get_slurm_system(monkeypatch, LEGACY_SLURM)
    placement = ResourcePlacement(nodes=['chr-0493'], cores=[1, 65])
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
    )
    expected = 'mask_cpu:0x2,0x20000000000000000'
    assert _get_flag_value(args, '--cpu-bind') == expected


def test_legacy_slurm_refuses_to_place_gpus(monkeypatch):
    system = _get_slurm_system(monkeypatch, LEGACY_SLURM)
    placement = ResourcePlacement(
        nodes=['chr-0493'], cores=[0, 1], gpus=1, gpu_ids=[0]
    )
    with pytest.raises(ValueError, match='20.11 or newer'):
        system._get_parallel_args(
            cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
        )


# --- an unknown launcher ---------------------------------------------------


def test_slurm_of_unknown_version_reports_no_placement(monkeypatch):
    system = _get_slurm_system(monkeypatch, None)
    assert system.placement_support is PlacementSupport.NONE


def test_placement_on_an_unplaceable_machine_raises(monkeypatch):
    system = _get_slurm_system(monkeypatch, None)
    placement = ResourcePlacement(nodes=['nid001'], cores=[0, 1])
    with pytest.raises(ValueError, match='cannot place a launch'):
        system._get_parallel_args(
            cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
        )


def test_pbs_without_pals_reports_no_placement(monkeypatch):
    system = _get_pbs_system(
        monkeypatch, is_pals=False, parallel_executable='mpirun --tag-output'
    )
    assert system.placement_support is PlacementSupport.NONE


# --- PBS with PALS ---------------------------------------------------------


def test_pals_reports_cpu_binding(monkeypatch):
    system = _get_pbs_system(monkeypatch)
    assert system.placement_support is PlacementSupport.CPU_BINDING


def test_pals_names_hosts_and_cores(monkeypatch):
    system = _get_pbs_system(monkeypatch)
    placement = ResourcePlacement(nodes=['x4401c1s0b0n0'], cores=[1, 2, 3, 4])
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert _get_flag_value(args, '--hosts') == 'x4401c1s0b0n0'
    assert _get_flag_value(args, '--cpu-bind') == 'list:1,2:3,4'


def test_pals_places_non_contiguous_cores(monkeypatch):
    """Aurora reserves core 0 and cores 49-52, so the set has gaps."""
    system = _get_pbs_system(monkeypatch)
    placement = ResourcePlacement(nodes=['x1'], cores=[47, 48, 53, 54])
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert _get_flag_value(args, '--cpu-bind') == 'list:47,48:53,54'


def test_pals_renders_the_visible_devices_variable(monkeypatch):
    system = _get_pbs_system(
        monkeypatch,
        gpus_per_node='12',
        gpu_bind='list:0.0:0.1:1.0:1.1:2.0:2.1',
        gpu_visible_devices_var='ZE_AFFINITY_MASK',
    )
    placement = ResourcePlacement(
        nodes=['x1'], cores=[1, 2], gpus=2, gpu_ids=[2, 3]
    )
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
    )
    # a value on the command line cannot leak from the parent, and the remove
    # makes sure an inherited one does not survive
    assert '--env-remove=ZE_AFFINITY_MASK' in args
    assert '--env=ZE_AFFINITY_MASK=1.0,1.1' in args
    assert args.index('--env-remove=ZE_AFFINITY_MASK') < args.index(
        '--env=ZE_AFFINITY_MASK=1.0,1.1'
    )


def test_pals_numbers_devices_from_zero_by_default(monkeypatch):
    system = _get_pbs_system(
        monkeypatch,
        gpus_per_node='4',
        gpu_visible_devices_var='CUDA_VISIBLE_DEVICES',
    )
    placement = ResourcePlacement(
        nodes=['x1'], cores=[1, 2], gpus=1, gpu_ids=[3]
    )
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert '--env=CUDA_VISIBLE_DEVICES=3' in args


def test_pals_makes_no_gpus_explicit(monkeypatch):
    system = _get_pbs_system(
        monkeypatch,
        gpus_per_node='4',
        gpu_visible_devices_var='CUDA_VISIBLE_DEVICES',
    )
    placement = ResourcePlacement(nodes=['x1'], cores=[1, 2])
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert '--env=CUDA_VISIBLE_DEVICES=' in args


def test_pals_refuses_to_choose_gpus(monkeypatch):
    """Only the caller knows about every concurrent launch."""
    system = _get_pbs_system(
        monkeypatch,
        gpus_per_node='4',
        gpu_visible_devices_var='CUDA_VISIBLE_DEVICES',
    )
    placement = ResourcePlacement(nodes=['x1'], cores=[1, 2], gpus=2)
    with pytest.raises(ValueError, match='must set gpu_ids'):
        system._get_parallel_args(
            cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
        )


def test_pals_rejects_a_gpu_the_node_does_not_have(monkeypatch):
    system = _get_pbs_system(
        monkeypatch,
        gpus_per_node='4',
        gpu_visible_devices_var='CUDA_VISIBLE_DEVICES',
    )
    placement = ResourcePlacement(
        nodes=['x1'], cores=[1, 2], gpus=1, gpu_ids=[7]
    )
    with pytest.raises(ValueError, match='asks for GPU 7'):
        system._get_parallel_args(
            cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
        )


def test_pals_renders_only_one_cpu_binding(monkeypatch):
    """The placement's core list replaces the machine's binding policy."""
    system = _get_pbs_system(monkeypatch, cpu_bind='cores')
    placement = ResourcePlacement(nodes=['x1'], cores=[8, 9, 10, 11])
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert args.count('--cpu-bind') == 1
    assert _get_flag_value(args, '--cpu-bind') == 'list:8,9:10,11'


def test_pals_drops_whole_node_binding_lists(monkeypatch):
    system = _get_pbs_system(
        monkeypatch,
        cpu_bind='list:1-8:9-16',
        mem_bind='list:0:0:1:1',
    )
    placement = ResourcePlacement(nodes=['x1'], cores=[1, 2])
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=2, placement=placement
    )
    assert _get_flag_value(args, '--cpu-bind') == 'list:1:2'
    assert '--mem-bind' not in args


# --- single node -----------------------------------------------------------


def test_single_node_reports_cpu_binding(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    assert system.placement_support is PlacementSupport.CPU_BINDING


def test_single_node_without_taskset_reports_no_placement(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    monkeypatch.setattr(
        'mache.parallel.single_node.shutil.which', lambda name: None
    )
    assert system.placement_support is PlacementSupport.NONE


def test_single_node_confines_a_launch_to_its_cores(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    placement = ResourcePlacement(nodes=[], cores=[2, 3, 4, 6])
    command = system.get_parallel_command(
        args=['./run.py'], ntasks=2, cpus_per_task=2, placement=placement
    )
    assert command == [
        'taskset',
        '-c',
        '2-4,6',
        'mpirun',
        '-n',
        '2',
        '-c',
        '2',
        './run.py',
    ]


def test_single_node_rejects_several_nodes(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    placement = ResourcePlacement(nodes=['a', 'b'], cores=[0, 1])
    with pytest.raises(ValueError, match='has only one'):
        system.get_parallel_command(
            args=['./run.py'], ntasks=2, placement=placement
        )


def test_single_node_refuses_to_place_gpus(monkeypatch):
    system = _get_single_node_system(monkeypatch)
    placement = ResourcePlacement(nodes=[], cores=[0, 1], gpus=1, gpu_ids=[0])
    with pytest.raises(ValueError, match='no mechanism'):
        system.get_parallel_command(
            args=['./run.py'], ntasks=2, placement=placement
        )


# --- not enough cores ------------------------------------------------------


@pytest.mark.parametrize('system_name', ['slurm', 'pbs', 'single_node'])
def test_placement_needs_enough_cores(monkeypatch, system_name):
    system: ParallelSystem
    if system_name == 'slurm':
        system = _get_slurm_system(monkeypatch, MODERN_SLURM)
    elif system_name == 'pbs':
        system = _get_pbs_system(monkeypatch)
    else:
        system = _get_single_node_system(monkeypatch)

    placement = ResourcePlacement(nodes=[], cores=[0, 1, 2])
    with pytest.raises(ValueError, match='need 4'):
        system.get_parallel_command(
            args=['./run.py'],
            ntasks=2,
            cpus_per_task=2,
            placement=placement,
        )
