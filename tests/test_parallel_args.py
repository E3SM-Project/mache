from configparser import ConfigParser

from mache.parallel.pbs import PbsSystem
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
