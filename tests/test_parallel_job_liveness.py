import subprocess
from configparser import ConfigParser

import pytest

from mache.parallel import get_parallel_system
from mache.parallel.login import LoginSystem
from mache.parallel.slurm import SlurmSystem, get_slurm_job_state


def _get_config() -> ConfigParser:
    config = ConfigParser()
    config.add_section('build')
    config.set('build', 'compiler', 'gnu')
    config.add_section('parallel')
    config.set('parallel', 'system', 'slurm')
    config.set('parallel', 'parallel_executable', 'srun')
    config.set('parallel', 'cores_per_node', '128')
    config.set('parallel', 'login_cores', '4')
    return config


class _FakeProcess:
    """The parts of ``CompletedProcess`` that the code under test reads."""

    def __init__(self, returncode: int, stdout: str = '', stderr: str = ''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeSqueue:
    """
    Stand-in for ``subprocess.run`` that answers the two squeue calls.

    The job query is the one carrying ``-j``; anything else is the probe
    that asks whether squeue can reach the controller at all.
    """

    def __init__(self, job_result, responsive: bool = True):
        self.job_result = job_result
        self.responsive = responsive
        self.job_args: list[str] = []

    def __call__(self, args, **kwargs):
        if '-j' in args:
            self.job_args = list(args)
            if isinstance(self.job_result, OSError):
                raise self.job_result
            return self.job_result
        if not self.responsive:
            raise subprocess.CalledProcessError(1, args)
        return _FakeProcess(0)


class _NoSqueue:
    """Stand-in for ``subprocess.run`` that fails if it is ever called."""

    def __call__(self, args, **kwargs):
        raise AssertionError(f'squeue should not have been run: {args}')


def _patch_squeue(monkeypatch, fake) -> None:
    monkeypatch.setattr('mache.parallel.slurm.subprocess.run', fake)


def test_job_state_running(monkeypatch):
    fake = _FakeSqueue(_FakeProcess(0, stdout='RUNNING\n'))
    _patch_squeue(monkeypatch, fake)

    assert get_slurm_job_state('12345') == 'RUNNING'
    # the default state filter hides finished jobs, so the query has to ask
    # for all of them or a job that just ended looks like a missing one
    assert '-t' in fake.job_args
    assert 'all' in fake.job_args


def test_job_state_recently_ended(monkeypatch):
    """A job still inside MinJobAge reports the state it ended in."""
    _patch_squeue(monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='TIMEOUT')))

    assert get_slurm_job_state('12345') == 'TIMEOUT'


def test_job_state_empty_listing(monkeypatch):
    _patch_squeue(monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='\n')))

    assert get_slurm_job_state('12345') is None


def test_job_state_het_job_uses_first_row(monkeypatch):
    _patch_squeue(
        monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='RUNNING\nRUNNING\n'))
    )

    assert get_slurm_job_state('12345') == 'RUNNING'


def test_job_state_purged_job_id(monkeypatch):
    """A purged job id is a nonzero exit, but squeue itself is healthy."""
    _patch_squeue(
        monkeypatch,
        _FakeSqueue(
            _FakeProcess(1, stderr='slurm_load_jobs error: Invalid job id'),
            responsive=True,
        ),
    )

    assert get_slurm_job_state('12345') is None


def test_job_state_squeue_unreachable(monkeypatch):
    """An unreachable controller must not be read as a dead job."""
    _patch_squeue(
        monkeypatch,
        _FakeSqueue(
            _FakeProcess(1, stderr='Unable to contact slurm controller'),
            responsive=False,
        ),
    )

    with pytest.raises(RuntimeError, match='Unable to contact'):
        get_slurm_job_state('12345')


def test_job_state_squeue_missing(monkeypatch):
    _patch_squeue(
        monkeypatch, _FakeSqueue(FileNotFoundError('no squeue here'))
    )

    with pytest.raises(RuntimeError, match='Could not run squeue'):
        get_slurm_job_state('12345')


def test_parallel_system_live_allocation(monkeypatch):
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    _patch_squeue(monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='RUNNING')))
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 4
    )

    system = get_parallel_system(_get_config())

    assert isinstance(system, SlurmSystem)
    assert system.nodes == 4


def test_parallel_system_expired_allocation(monkeypatch):
    """This is cbegeman's case: a salloc shell outliving its allocation."""
    monkeypatch.setenv('SLURM_JOB_ID', '1278760')
    _patch_squeue(monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='TIMEOUT')))

    with pytest.warns(UserWarning, match='1278760.*TIMEOUT'):
        system = get_parallel_system(_get_config())

    assert isinstance(system, LoginSystem)
    assert not system.mpi_allowed


def test_parallel_system_purged_allocation(monkeypatch):
    monkeypatch.setenv('SLURM_JOB_ID', '1278760')
    _patch_squeue(
        monkeypatch,
        _FakeSqueue(_FakeProcess(1, stderr='Invalid job id specified')),
    )

    with pytest.warns(UserWarning, match='no record of that job'):
        system = get_parallel_system(_get_config())

    assert isinstance(system, LoginSystem)


def test_parallel_system_squeue_unreachable(monkeypatch):
    """Do not quietly demote a real allocation when squeue cannot answer."""
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    _patch_squeue(
        monkeypatch,
        _FakeSqueue(
            _FakeProcess(1, stderr='Unable to contact slurm controller'),
            responsive=False,
        ),
    )

    with pytest.raises(RuntimeError, match='Unable to contact'):
        get_parallel_system(_get_config())


def test_parallel_system_no_job_id_does_not_ask(monkeypatch):
    monkeypatch.delenv('SLURM_JOB_ID', raising=False)
    _patch_squeue(monkeypatch, _NoSqueue())

    assert isinstance(get_parallel_system(_get_config()), LoginSystem)
