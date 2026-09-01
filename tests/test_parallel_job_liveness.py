import subprocess

import pytest

from mache.parallel.slurm import get_slurm_job_state


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
