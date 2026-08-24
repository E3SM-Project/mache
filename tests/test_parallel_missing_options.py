"""
Check what a parallel system does when its config omits an option.

``get_config_int`` defaults to ``0``, so a caller that does not ask for
``None`` cannot tell an absent option from one set to zero. Every site that
needs the difference asks for it, and these tests hold that in place: the
consequence of losing it is not an error but a machine that quietly reports
no cores, which reads downstream as a machine with nothing to run on.
"""

from configparser import ConfigParser

import pytest

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


def test_single_node_without_cores_per_node_detects_them(monkeypatch):
    """A config that does not say gets the count from the machine."""
    monkeypatch.setattr('multiprocessing.cpu_count', lambda: 128)
    config = _get_config({'parallel_executable': 'mpirun'})

    system = SingleNodeSystem(config)

    assert system.cores_per_node == 128
    assert system.cores == 128


def test_single_node_with_cores_per_node_takes_the_smaller(monkeypatch):
    """A config that does say cannot claim more than the machine has."""
    monkeypatch.setattr('multiprocessing.cpu_count', lambda: 128)
    config = _get_config(
        {'parallel_executable': 'mpirun', 'cores_per_node': '8'}
    )

    system = SingleNodeSystem(config)

    assert system.cores_per_node == 8
    assert system.cores == 8


def test_slurm_without_cores_per_node_raises(monkeypatch):
    """Slurm cannot detect the count, so an omission has to be an error."""
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    config = _get_config({'parallel_executable': 'srun'})

    with pytest.raises(ValueError, match='cores_per_node must be set'):
        SlurmSystem(config)


def test_pbs_without_cores_per_node_raises(monkeypatch):
    """Neither can PBS."""
    monkeypatch.setenv('PBS_JOBID', '12345')
    config = _get_config({'parallel_executable': 'mpiexec'})

    with pytest.raises(ValueError, match='cores_per_node must be set'):
        PbsSystem(config)


def test_login_without_login_cores_raises():
    """A login node's share is a policy, so only the config can say it."""
    config = _get_config({'parallel_executable': 'mpirun'})

    with pytest.raises(ValueError, match='login_cores must be set'):
        LoginSystem(config)


def test_machine_without_gpus_reports_none_of_them(monkeypatch):
    """
    Silence about GPUs means a machine has none.

    Unlike cores, zero is the right answer here rather than a gap: most
    machines mache ships a config for omit ``gpus_per_node`` because they
    have no GPUs, and a caller doing arithmetic on ``gpus`` would rather
    have that than ``None``.
    """
    monkeypatch.setattr('multiprocessing.cpu_count', lambda: 128)
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )
    config = _get_config(
        {'parallel_executable': 'srun', 'cores_per_node': '32'}
    )

    assert SlurmSystem(config).gpus == 0
    assert SingleNodeSystem(_get_config({})).gpus == 0


def test_slurm_without_max_mpi_tasks_per_node_raises(monkeypatch):
    """
    The same omission, one option along.

    ``max_mpi_tasks_per_node`` is read when a command is rendered rather
    than when the system is built, so a zero here would cap a launch at no
    tasks rather than report a machine with no cores.
    """
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )
    config = _get_config(
        {'parallel_executable': 'srun', 'cores_per_node': '32'}
    )
    system = SlurmSystem(config)

    with pytest.raises(ValueError, match='max_mpi_tasks_per_node must be set'):
        system._get_parallel_args(cpus_per_task=1, gpus_per_task=0, ntasks=4)


def test_pbs_without_max_mpi_tasks_per_node_raises(monkeypatch):
    """And the same on PBS."""
    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 2
    )
    config = _get_config(
        {'parallel_executable': 'mpiexec', 'cores_per_node': '32'}
    )
    system = PbsSystem(config)

    with pytest.raises(ValueError, match='max_mpi_tasks_per_node must be set'):
        system._get_parallel_args(cpus_per_task=1, gpus_per_task=0, ntasks=4)
