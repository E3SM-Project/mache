from configparser import ConfigParser

import pytest

from mache.parallel.slurm import SlurmSystem


def _get_slurm_system(monkeypatch, **parallel_items) -> SlurmSystem:
    items = {
        'parallel_executable': 'srun --label',
        'cores_per_node': '64',
        'max_mpi_tasks_per_node': '16',
    }
    items.update(parallel_items)
    config = ConfigParser()
    config.add_section('parallel')
    for key, value in items.items():
        config.set('parallel', key, value)

    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )
    monkeypatch.setattr(
        'mache.parallel.slurm.get_slurm_version', lambda: (25, 11)
    )
    return SlurmSystem(config)


def _command(system: SlurmSystem):
    return system.get_parallel_command(
        args=['./run.py'], ntasks=4, cpus_per_task=1
    )


def test_srun_kills_the_step_on_a_bad_exit(monkeypatch):
    command = _command(_get_slurm_system(monkeypatch))
    assert command[:4] == ['srun', '--label', '--kill-on-bad-exit', '-c']


@pytest.mark.parametrize(
    'executable',
    [
        'srun -l -K --threads-per-core=1',
        'srun --mpi=pmi2 --kill-on-bad-exit',
        'srun --kill-on-bad-exit=0',
        'srun -K1',
    ],
)
def test_flag_already_in_executable_is_not_repeated(monkeypatch, executable):
    command = _command(
        _get_slurm_system(monkeypatch, parallel_executable=executable)
    )
    flags = [
        arg
        for arg in command
        if arg.startswith('--kill-on-bad-exit') or arg.startswith('-K')
    ]
    assert len(flags) == 1


@pytest.mark.parametrize('value', ['False', 'false', 'no', '0'])
def test_machine_can_opt_out(monkeypatch, value):
    command = _command(_get_slurm_system(monkeypatch, kill_on_bad_exit=value))
    assert '--kill-on-bad-exit' not in command


def test_other_launchers_are_left_alone(monkeypatch):
    command = _command(
        _get_slurm_system(monkeypatch, parallel_executable='mpirun')
    )
    assert '--kill-on-bad-exit' not in command


def test_invalid_opt_out_value_raises(monkeypatch):
    system = _get_slurm_system(monkeypatch, kill_on_bad_exit='maybe')
    with pytest.raises(ValueError, match='boolean'):
        _command(system)
