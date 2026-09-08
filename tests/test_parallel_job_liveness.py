import subprocess
from configparser import ConfigParser

import pytest

from mache.parallel import get_parallel_system
from mache.parallel.login import LoginSystem
from mache.parallel.slurm import (
    SlurmSystem,
    get_slurm_job_state,
    running_on_allocated_node,
)

# every variable that could make a test look as though it were running on
# one of an allocation's nodes
NODE_ENV_VARS = ('SLURMD_NODENAME', 'SLURM_JOB_NODELIST', 'SLURM_NODELIST')


@pytest.fixture(autouse=True)
def off_allocated_nodes(monkeypatch):
    """
    Answer the local fast path with "not on a node" unless a test says so.

    Otherwise a suite run from inside an allocation would take the fast
    path and never reach the squeue behavior these tests are about.
    """
    for variable in NODE_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)


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


def _fake_hostname(monkeypatch, hostname: str) -> None:
    monkeypatch.setattr(
        'mache.parallel.slurm.socket.gethostname', lambda: hostname
    )


def _fake_hostname_expansion(monkeypatch, names: list[str]) -> list[list[str]]:
    """Stand in for ``scontrol show hostnames``, recording what it expanded."""
    expanded: list[list[str]] = []

    def fake(args):
        expanded.append(list(args))
        return '\n'.join(names)

    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_str', fake)
    return expanded


class _NoExpansion:
    """Stand-in for the expansion that fails if it is ever called."""

    def __call__(self, args):
        raise AssertionError(f'scontrol should not have been run: {args}')


def test_on_allocated_node_from_slurmd_nodename(monkeypatch):
    """The node slurmd launched the job on costs nothing to recognize."""
    monkeypatch.setenv('SLURMD_NODENAME', 'chr-0123')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'chr-[0123-0125]')
    _fake_hostname(monkeypatch, 'chr-0123')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_str', _NoExpansion()
    )

    assert running_on_allocated_node()


def test_on_allocated_node_compares_short_names(monkeypatch):
    """An FQDN from the host and a short name from Slurm are the same node."""
    monkeypatch.setenv('SLURMD_NODENAME', 'nid001234')
    _fake_hostname(monkeypatch, 'nid001234.hsn.cm.perlmutter.nersc.gov')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_str', _NoExpansion()
    )

    assert running_on_allocated_node()


def test_on_allocated_node_from_nodelist(monkeypatch):
    """Without SLURMD_NODENAME the node list is expanded and searched."""
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'nid[001234-001236]')
    _fake_hostname(monkeypatch, 'nid001236')
    expanded = _fake_hostname_expansion(
        monkeypatch, ['nid001234', 'nid001235', 'nid001236']
    )

    assert running_on_allocated_node()
    # the expression is passed explicitly, not left to the environment
    assert expanded == [
        ['scontrol', 'show', 'hostnames', 'nid[001234-001236]']
    ]


def test_on_allocated_node_falls_back_to_slurm_nodelist(monkeypatch):
    monkeypatch.setenv('SLURM_NODELIST', 'chr-0123')
    _fake_hostname(monkeypatch, 'chr-0123')
    _fake_hostname_expansion(monkeypatch, ['chr-0123'])

    assert running_on_allocated_node()


def test_off_allocated_node_with_inherited_nodename(monkeypatch):
    """
    A variable inherited on another host must not answer for that host.

    This is the case the check exists to keep working: a shell that carries
    a job's environment but does not run on any of its nodes.
    """
    monkeypatch.setenv('SLURMD_NODENAME', 'chr-0123')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'chr-[0123-0125]')
    _fake_hostname(monkeypatch, 'chrlogin1')
    _fake_hostname_expansion(monkeypatch, ['chr-0123', 'chr-0124', 'chr-0125'])

    assert not running_on_allocated_node()


def test_off_allocated_node_without_a_nodelist(monkeypatch):
    _fake_hostname(monkeypatch, 'chrlogin1')
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_str', _NoExpansion()
    )

    assert not running_on_allocated_node()


def test_off_allocated_node_when_scontrol_is_missing(monkeypatch):
    """An expansion that cannot be run leaves the question to the scheduler."""
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'nid[001234-001236]')
    _fake_hostname(monkeypatch, 'nid001236')

    def fake(args):
        raise FileNotFoundError('no scontrol here')

    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_str', fake)

    assert not running_on_allocated_node()


def test_parallel_system_on_allocated_node_does_not_ask(monkeypatch):
    """A batch job settles its own liveness without a batch-system query."""
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setenv('SLURMD_NODENAME', 'chr-0123')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'chr-[0123-0125]')
    _fake_hostname(monkeypatch, 'chr-0123')
    _patch_squeue(monkeypatch, _NoSqueue())
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 3
    )

    system = get_parallel_system(_get_config())

    assert isinstance(system, SlurmSystem)
    assert system.nodes == 3


def test_parallel_system_off_allocated_node_still_asks(monkeypatch):
    """Off the allocation's nodes, nothing local can answer, so ask."""
    monkeypatch.setenv('SLURM_JOB_ID', '1278760')
    monkeypatch.setenv('SLURMD_NODENAME', 'chr-0123')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'chr-0123')
    _fake_hostname(monkeypatch, 'chrlogin1')
    _fake_hostname_expansion(monkeypatch, ['chr-0123'])
    _patch_squeue(monkeypatch, _FakeSqueue(_FakeProcess(0, stdout='TIMEOUT')))

    with pytest.warns(UserWarning, match='1278760.*TIMEOUT'):
        system = get_parallel_system(_get_config())

    assert isinstance(system, LoginSystem)
