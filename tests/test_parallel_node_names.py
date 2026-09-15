"""
Tests for reading the individual nodes an allocation holds.

A caller placing several launches inside one allocation says which nodes each
may use by name, so the names have to come from somewhere. These check that
they come from the job's own environment wherever it carries them, and that
the batch system is asked only when it does not.
"""

from configparser import ConfigParser

import pytest

from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem


def _get_config(**parallel_items: str) -> ConfigParser:
    config = ConfigParser()
    config.add_section('parallel')
    for key, value in parallel_items.items():
        config.set('parallel', key, value)
    return config


def _get_slurm_system(monkeypatch, **parallel_items) -> SlurmSystem:
    items = {
        'parallel_executable': 'srun --label',
        'cores_per_node': '64',
        'max_mpi_tasks_per_node': '64',
    }
    items.update(parallel_items)
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    return SlurmSystem(_get_config(**items))


def _refuse(*args, **kwargs):
    """Stand in for a batch-system query that should not happen."""
    raise AssertionError('the batch system was asked and should not be')


def test_slurm_takes_the_node_count_from_the_environment(monkeypatch):
    """The job says how many nodes it holds, so squeue is not asked."""
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', '3')
    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_int', _refuse)

    system = _get_slurm_system(monkeypatch)

    assert system.nodes == 3
    assert system.cores == 192


def test_slurm_falls_back_to_squeue_without_the_variable(monkeypatch):
    """An environment carrying the job id and not the count still works."""
    monkeypatch.delenv('SLURM_JOB_NUM_NODES', raising=False)
    monkeypatch.delenv('SLURM_NNODES', raising=False)
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 5
    )

    system = _get_slurm_system(monkeypatch)

    assert system.nodes == 5


def test_slurm_says_so_when_the_variable_is_unusable(monkeypatch):
    """A count that is not a number is worth a warning, not a silent fall."""
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', 'two')
    monkeypatch.delenv('SLURM_NNODES', raising=False)
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_int', lambda args: 2
    )

    with pytest.warns(UserWarning, match='not a node count'):
        system = _get_slurm_system(monkeypatch)

    assert system.nodes == 2


def test_slurm_expands_the_nodelist_it_was_given(monkeypatch):
    """The names come from expanding the job's own hostlist expression."""
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', '4')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'nid[001-003,007]')
    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_int', _refuse)

    seen = []

    def _expand(args):
        seen.append(args)
        return 'nid001\nnid002\nnid003\nnid007'

    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_str', _expand)
    system = _get_slurm_system(monkeypatch)

    assert system.node_names == ['nid001', 'nid002', 'nid003', 'nid007']
    assert seen == [['scontrol', 'show', 'hostnames', 'nid[001-003,007]']]

    # asked again, it is not expanded again
    assert system.node_names == ['nid001', 'nid002', 'nid003', 'nid007']
    assert len(seen) == 1


def test_slurm_names_nothing_without_a_nodelist(monkeypatch):
    """No expression to expand is an answer, not a failure."""
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', '2')
    monkeypatch.delenv('SLURM_JOB_NODELIST', raising=False)
    monkeypatch.delenv('SLURM_NODELIST', raising=False)
    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_int', _refuse)

    system = _get_slurm_system(monkeypatch)

    assert system.node_names is None


def test_a_count_that_disagrees_with_the_names_is_reported(monkeypatch):
    """Placing uses the names, so a disagreeing count has to be visible."""
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', '4')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'nid[001-002]')
    monkeypatch.setattr('mache.parallel.slurm._get_subprocess_int', _refuse)
    monkeypatch.setattr(
        'mache.parallel.slurm._get_subprocess_str',
        lambda args: 'nid001\nnid002',
    )

    system = _get_slurm_system(monkeypatch)

    with pytest.warns(UserWarning, match='names 2 of them'):
        assert system.node_names == ['nid001', 'nid002']


def test_pbs_reads_its_node_file(monkeypatch, tmp_path):
    """PBS writes the names into a file, so nothing has to be asked."""
    node_file = tmp_path / 'nodefile'
    node_file.write_text('x1000c0s0b0n0\nx1000c0s1b0n0\n')
    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setenv('PBS_NODEFILE', str(node_file))
    monkeypatch.setattr(PbsSystem, '_get_node_count_from_qstat', _refuse)

    system = PbsSystem(
        _get_config(
            parallel_executable='mpiexec',
            cores_per_node='96',
            max_mpi_tasks_per_node='96',
        )
    )

    assert system.nodes == 2
    assert system.node_names == ['x1000c0s0b0n0', 'x1000c0s1b0n0']


def test_pbs_counts_each_node_once(monkeypatch, tmp_path):
    """Some sites write one line per rank slot rather than per node."""
    node_file = tmp_path / 'nodefile'
    node_file.write_text('host_a\nhost_a\nhost_b\nhost_b\nhost_a\n')
    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.setenv('PBS_NODEFILE', str(node_file))
    monkeypatch.setattr(PbsSystem, '_get_node_count_from_qstat', _refuse)

    system = PbsSystem(
        _get_config(
            parallel_executable='mpiexec',
            cores_per_node='96',
            max_mpi_tasks_per_node='96',
        )
    )

    assert system.nodes == 2
    assert system.node_names == ['host_a', 'host_b']


def test_pbs_falls_back_to_qstat_without_a_node_file(monkeypatch):
    """A job with no node file behaves exactly as it did before."""
    monkeypatch.setenv('PBS_JOBID', '12345.server')
    monkeypatch.delenv('PBS_NODEFILE', raising=False)
    monkeypatch.setattr(
        PbsSystem, '_get_node_count_from_qstat', lambda self: 3
    )

    system = PbsSystem(
        _get_config(
            parallel_executable='mpiexec',
            cores_per_node='96',
            max_mpi_tasks_per_node='96',
        )
    )

    assert system.nodes == 3
    assert system.node_names is None


def test_a_single_node_system_names_itself(monkeypatch):
    """No batch system to name it, so a caller still gets one name."""
    monkeypatch.setattr(
        'mache.parallel.single_node.platform.node', lambda: 'a'
    )
    system = SingleNodeSystem(
        _get_config(parallel_executable='mpirun', cores_per_node='8')
    )

    assert system.node_names == ['a']


def test_a_system_that_does_not_name_its_nodes_says_so():
    """The base class answers None rather than guessing."""
    assert ParallelSystem(_get_config()).node_names is None
