"""
Which of a node's CPU ids are the same physical core.

``cores_per_node`` counts physical cores, without hyperthreading, and every
machine mache supports exposes its threads, so the ids the kernel offers a
job are about twice that count.  A caller placing work by core id needs to
know which ids are cores, and the numbering alone does not say.

The kernel does, in ``/sys/devices/system/cpu/cpu<n>/topology/``.  It is
read here rather than assumed: on every machine seen so far thread 0 of
every core is enumerated before any sibling, so "the first
``cores_per_node`` ids" happens to be one thread per core, but nothing
promises that, and a machine that interleaves siblings would place two
tasks on one core with no error.

A node without the topology files -- a container, an unusual kernel --
reads as having no siblings at all, which makes every id its own core.
That is the behavior before this existed, and it is stated rather than
silent.
"""

import os
from typing import Dict, Iterable, List, Set, Tuple

SYSFS_CPU = '/sys/devices/system/cpu'


def thread_siblings(cpu_ids: Iterable[int]) -> Dict[int, Tuple[int, ...]]:
    """
    The ids that share a physical core with each of these, itself included.

    Parameters
    ----------
    cpu_ids : iterable of int
        The ids to look up

    Returns
    -------
    siblings : dict of int to tuple of int
        For each id, every id on the same core in ascending order.  An id
        the kernel says nothing about maps to itself alone.
    """
    return {cpu: _read_siblings(cpu) for cpu in cpu_ids}


def one_thread_per_core(cpu_ids: Iterable[int]) -> List[int]:
    """
    Reduce a set of ids to one per physical core, the lowest of each.

    Parameters
    ----------
    cpu_ids : iterable of int
        The ids a job may use

    Returns
    -------
    cores : list of int
        One id per physical core among them, in ascending order
    """
    ids = sorted(set(cpu_ids))
    siblings = thread_siblings(ids)
    cores: List[int] = []
    taken: Set[int] = set()
    for cpu in ids:
        if cpu in taken:
            continue
        cores.append(cpu)
        taken.update(siblings[cpu])
    return cores


def physical_cores(cpu_ids: Iterable[int]) -> int:
    """
    How many physical cores a set of ids spans.

    Two sibling threads are one core; a task allowed both has one core's
    worth of the machine, not two.

    Parameters
    ----------
    cpu_ids : iterable of int
        The ids a job may use

    Returns
    -------
    count : int
        The number of physical cores among them
    """
    return len(one_thread_per_core(cpu_ids))


def with_siblings(cpu_ids: Iterable[int]) -> List[int]:
    """
    Every id on the same core as any of these, these included.

    Parameters
    ----------
    cpu_ids : iterable of int
        The ids to complete

    Returns
    -------
    ids : list of int
        The ids and every sibling of each, in ascending order
    """
    ids = set(cpu_ids)
    for siblings in thread_siblings(list(ids)).values():
        ids.update(siblings)
    return sorted(ids)


def _read_siblings(cpu: int) -> Tuple[int, ...]:
    """Ask the kernel which ids share this one's core."""
    path = os.path.join(
        SYSFS_CPU, f'cpu{cpu}', 'topology', 'thread_siblings_list'
    )
    try:
        with open(path) as handle:
            return _parse_list(handle.read())
    except (OSError, ValueError):
        return (cpu,)


def _parse_list(text: str) -> Tuple[int, ...]:
    """Read the kernel's ``0,64`` or ``0-1`` or ``0-1,64-65`` into ids."""
    ids: List[int] = []
    for part in text.strip().split(','):
        if not part:
            continue
        if '-' in part:
            first, last = part.split('-', 1)
            ids.extend(range(int(first), int(last) + 1))
        else:
            ids.append(int(part))
    return tuple(sorted(ids))
