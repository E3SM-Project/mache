from enum import Enum


class MemoryCapSupport(Enum):
    """
    Whether a machine will hold a launch to a memory cap.

    Memory is deliberately not part of
    :py:class:`~mache.parallel.placement.ResourcePlacement`: a placement says
    where a launch runs, and a cap says how much memory it may use, which is
    a different statement. This reports what the second one is worth on the
    current machine.

    Attributes
    ----------
    ENFORCED : MemoryCapSupport
        The batch system holds a launch to its cap and kills it for
        exceeding it. A caller can rely on the cap as a limit, though not as
        a reservation -- see
        :py:meth:`~mache.parallel.system.ParallelSystem.get_parallel_command`.

    NONE : MemoryCapSupport
        Nothing here will hold a launch to a cap, so ``mache`` renders none
        and a caller that exceeds what it meant to use will not be stopped.
        Either the launcher has no memory option at all, as PALS does not,
        or it accepts one and does not act on it, as Slurm before 20.11
        does.
    """

    ENFORCED = 'enforced'
    NONE = 'none'
