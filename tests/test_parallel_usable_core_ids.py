"""
Tests for saying which CPU ids on a node are cores the job may use.

``cores_per_node`` counts a node's cores; it does not say which ids they
are. A caller that numbered them ``range(cores_per_node)`` placed work on
Aurora's held-back core 0, which PALS refused. These check that the ids
come from what the kernel allows the process, one per physical core, held
to the configured count, and that a machine offering fewer cores than the
config counts is reported rather than silently trusted.
"""

import os
import warnings
from configparser import ConfigParser
from contextlib import contextmanager

import pytest

from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem


def _get_config(**parallel_items: str) -> ConfigParser:
    config = ConfigParser()
    config.add_section('parallel')
    for key, value in parallel_items.items():
        config.set('parallel', key, value)
    return config


def _get_slurm_system(monkeypatch, cores_per_node: int) -> SlurmSystem:
    monkeypatch.setenv('SLURM_JOB_ID', '12345')
    monkeypatch.setenv('SLURM_JOB_NUM_NODES', '2')
    config = _get_config(
        parallel_executable='srun',
        cores_per_node=str(cores_per_node),
        max_mpi_tasks_per_node=str(cores_per_node),
    )
    return SlurmSystem(config)


def _fake_node(monkeypatch, allowed, groups):
    """
    Stand in for the kernel: the ids this process may use, and which of
    them share a core. An id in no group is its own core.
    """
    known = {cpu: tuple(sorted(group)) for group in groups for cpu in group}
    monkeypatch.setattr(
        os, 'sched_getaffinity', lambda pid: set(allowed), raising=False
    )
    monkeypatch.setattr(
        'mache.parallel.topology._read_siblings',
        lambda cpu: known.get(cpu, (cpu,)),
    )


@contextmanager
def _no_warning():
    """A context in which any warning is a test failure."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        yield


def test_perlmutter_is_the_first_thread_of_each_core(monkeypatch):
    """256 ids, siblings 128 apart, configured with 128 cores."""
    _fake_node(
        monkeypatch, range(256), [(cpu, cpu + 128) for cpu in range(128)]
    )
    system = _get_slurm_system(monkeypatch, cores_per_node=128)

    with _no_warning():
        assert system.usable_core_ids == tuple(range(128))


def test_aurora_leaves_out_the_held_back_ids(monkeypatch):
    """
    The job may use 1-51 and 53-103 and their siblings 104 apart, with 0
    and 52 and theirs held back, on a node configured with 102 cores.
    Numbering from zero placed work on 0, which PALS refused.
    """
    threads = [cpu for cpu in range(104) if cpu not in (0, 52)]
    allowed = threads + [cpu + 104 for cpu in threads]
    _fake_node(monkeypatch, allowed, [(cpu, cpu + 104) for cpu in range(104)])
    system = _get_slurm_system(monkeypatch, cores_per_node=102)

    with _no_warning():
        ids = system.usable_core_ids

    assert ids == tuple(threads)
    assert 0 not in ids
    assert 52 not in ids


def test_frontier_skips_a_core_in_every_eight(monkeypatch):
    """Ids 0, 8, ..., 56 are held back on a node configured with 56."""
    threads = [cpu for cpu in range(64) if cpu % 8 != 0]
    allowed = threads + [cpu + 64 for cpu in threads]
    _fake_node(monkeypatch, allowed, [(cpu, cpu + 64) for cpu in range(64)])
    system = _get_slurm_system(monkeypatch, cores_per_node=56)

    with _no_warning():
        assert system.usable_core_ids == tuple(threads)


def test_an_interleaved_numbering_is_still_one_per_core(monkeypatch):
    """A machine that numbers siblings side by side is not twice the cores."""
    _fake_node(
        monkeypatch, range(8), [(cpu, cpu + 1) for cpu in range(0, 8, 2)]
    )
    system = _get_slurm_system(monkeypatch, cores_per_node=4)

    with _no_warning():
        assert system.usable_core_ids == (0, 2, 4, 6)


def test_more_cores_than_configured_is_a_cap_and_not_a_complaint(
    monkeypatch,
):
    """A config that counts fewer cores than the node has is honored."""
    _fake_node(monkeypatch, range(64), [])
    system = _get_slurm_system(monkeypatch, cores_per_node=8)

    with _no_warning():
        assert system.usable_core_ids == tuple(range(8))


def test_fewer_cores_than_configured_is_reported(monkeypatch):
    """A placement sized from the config would ask for a missing core."""
    _fake_node(monkeypatch, range(60), [])
    system = _get_slurm_system(monkeypatch, cores_per_node=64)

    with pytest.warns(UserWarning, match='60 cores .* configured with 64'):
        assert system.usable_core_ids == tuple(range(60))


def test_a_reading_of_under_half_the_node_is_not_believed(monkeypatch):
    """
    A process started bound to a corner of the node must not number the
    whole allocation from that corner.
    """
    _fake_node(monkeypatch, range(4), [])
    system = _get_slurm_system(monkeypatch, cores_per_node=64)

    with pytest.warns(UserWarning, match='too few to describe a node'):
        assert system.usable_core_ids == tuple(range(64))


def test_a_platform_without_affinity_numbers_from_zero(monkeypatch):
    monkeypatch.delattr(os, 'sched_getaffinity', raising=False)
    system = _get_slurm_system(monkeypatch, cores_per_node=16)

    with _no_warning():
        assert system.usable_core_ids == tuple(range(16))


def test_the_ids_are_read_once(monkeypatch):
    asked = []

    def _affinity(pid):
        asked.append(pid)
        return set(range(8))

    _fake_node(monkeypatch, range(8), [])
    monkeypatch.setattr(os, 'sched_getaffinity', _affinity)
    system = _get_slurm_system(monkeypatch, cores_per_node=8)

    assert system.usable_core_ids == tuple(range(8))
    assert system.usable_core_ids == tuple(range(8))
    assert asked == [0]


def test_a_system_with_no_core_count_cannot_answer():
    system = ParallelSystem(_get_config(parallel_executable='srun'))

    with pytest.raises(ValueError, match='how many cores'):
        _ = system.usable_core_ids
