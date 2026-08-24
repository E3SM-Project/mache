from configparser import ConfigParser

from mache.parallel.login import LoginSystem
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem


def _get_config(parallel_items: dict[str, str]) -> ConfigParser:
    config = ConfigParser()
    config.add_section('build')
    config.set('build', 'compiler', 'gnu')
    config.add_section('parallel')
    for key, value in parallel_items.items():
        config.set('parallel', key, value)
    return config


def test_slurm_default_gpus_per_task_flag(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '16',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=3, ntasks=4
    )

    assert '--gpus-per-task' in args
    index = args.index('--gpus-per-task')
    assert args[index + 1] == '3'


def test_slurm_custom_gpus_per_task_flag(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '16',
            'gpus_per_task_flag': '--gres=gpu',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=1, ntasks=4
    )

    assert '--gres=gpu' in args
    index = args.index('--gres=gpu')
    assert args[index + 1] == '1'


def test_slurm_uses_minimum_nodes_for_single_task(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 6
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=1, ntasks=1
    )

    index = args.index('-N')
    assert args[index + 1] == '1'


def test_slurm_uses_minimum_nodes_for_task_count(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 6
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=17
    )

    index = args.index('-N')
    assert args[index + 1] == '5'


def test_slurm_supports_explicit_distribution(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '16',
            'distribution': 'block:cyclic',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=0, ntasks=4
    )

    index = args.index('-m')
    assert args[index + 1] == 'block:cyclic'


def test_slurm_distribution_overrides_legacy_placement(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '16',
            'distribution': 'block:block',
            'placement': 'plane',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=4
    )

    index = args.index('-m')
    assert args[index + 1] == 'block:block'
    assert 'plane=16' not in args


def test_slurm_legacy_placement_is_still_supported(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '16',
            'placement': 'plane',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=4
    )

    index = args.index('-m')
    assert args[index + 1] == 'plane=16'


def test_pbs_skips_gpu_flag_when_not_configured(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
            'cpus_per_task_flag': '--depth',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=1, ntasks=4
    )

    assert '--gpus-per-task' not in args


def test_pbs_uses_configured_gpu_flag(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
            'cpus_per_task_flag': '--depth',
            'gpus_per_task_flag': '--gpus-per-task',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=2, gpus_per_task=1, ntasks=4
    )

    assert '--gpus-per-task' in args
    index = args.index('--gpus-per-task')
    assert args[index + 1] == '1'


def test_pbs_uses_minimum_nodes_for_single_task(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
            'cpus_per_task_flag': '--depth',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 6
    )

    system = PbsSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=1
    )

    index = args.index('--ppn')
    assert args[index + 1] == '1'


def test_pbs_uses_minimum_nodes_for_task_count(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'max_mpi_tasks_per_node': '4',
            'cpus_per_task_flag': '--depth',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 6
    )

    system = PbsSystem(config)
    args = system._get_parallel_args(
        cpus_per_task=1, gpus_per_task=0, ntasks=17
    )

    index = args.index('--ppn')
    assert args[index + 1] == '4'


def test_pbs_detects_gpus_per_node(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'gpus_per_node': '4',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)

    assert system.gpus_per_node == 4
    assert system.gpus == 8


def test_pbs_reports_no_gpus_as_zero(monkeypatch):
    """A machine or compiler with gpus_per_node = 0 has no GPUs."""
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'gpus_per_node': '0',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)

    # consistent with SlurmSystem and SingleNodeSystem, which also report a
    # known absence of GPUs as 0 rather than as None
    assert system.gpus_per_node == 0
    assert system.gpus == 0


def test_slurm_reports_memory(monkeypatch):
    """A machine's memory is reported per node and for the allocation."""
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
            'memory_per_node': '253000',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)

    assert system.memory_per_node == 253000
    assert system.memory == 506000


def test_slurm_reports_unknown_memory_as_none(monkeypatch):
    """A config without memory_per_node reports no memory, not zero."""
    config = _get_config(
        {
            'parallel_executable': 'srun --label',
            'cores_per_node': '32',
        }
    )

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    system = SlurmSystem(config)

    # zero would read as "this machine has no memory", which is never true
    assert system.memory_per_node is None
    assert system.memory is None


def test_pbs_reports_memory(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
            'memory_per_node': '512000',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)

    assert system.memory_per_node == 512000
    assert system.memory == 1024000


def test_pbs_reports_unknown_memory_as_none(monkeypatch):
    config = _get_config(
        {
            'parallel_executable': 'mpiexec --label',
            'cores_per_node': '32',
        }
    )

    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )

    system = PbsSystem(config)

    assert system.memory_per_node is None
    assert system.memory is None


def test_single_node_reports_memory():
    """One node, so the per-node figure is also the total."""
    config = _get_config(
        {
            'parallel_executable': 'mpirun',
            'cores_per_node': '4',
            'memory_per_node': '16000',
        }
    )

    system = SingleNodeSystem(config)

    assert system.memory_per_node == 16000
    assert system.memory == 16000


def test_login_reports_no_memory():
    """memory_per_node describes a compute node, not a login node."""
    config = _get_config(
        {
            'login_cores': '4',
            'login_gpus': '0',
            'memory_per_node': '253000',
        }
    )

    system = LoginSystem(config)

    assert system.memory_per_node is None
    assert system.memory is None
