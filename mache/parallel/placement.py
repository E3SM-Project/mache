from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence

# the machine's binding config options, in the order they are rendered
BINDING_OPTIONS = ('cpu_bind', 'gpu_bind', 'mem_bind')

# binding values that name specific cores or devices rather than stating a
# policy such as "cores" or "closest"
_RESOURCE_PREFIXES = (
    'list:',
    'map_cpu:',
    'mask_cpu:',
    'map_gpu:',
    'mask_gpu:',
    'map_mem:',
    'mask_mem:',
)


def names_resources(value: str) -> bool:
    """Check whether a binding config value names specific resources."""
    return value.startswith(_RESOURCE_PREFIXES)


class PlacementSupport(Enum):
    """
    The mechanism a machine has for confining a launch to given resources.

    Attributes
    ----------
    SCHEDULER : PlacementSupport
        The batch system reserves the resources a launch asks for, so two
        concurrent launches cannot exceed what each was given.

    CPU_BINDING : PlacementSupport
        The launcher binds each task to specific cores, which keeps
        concurrent launches apart but does not reserve anything. Work that
        rebinds itself is not prevented from doing so.

    NONE : PlacementSupport
        There is no way to confine a launch on this machine, so concurrent
        launches will oversubscribe or serialize.
    """

    SCHEDULER = 'scheduler'
    CPU_BINDING = 'cpu_binding'
    NONE = 'none'


@dataclass(frozen=True)
class ResourcePlacement:
    """
    Where a single parallel launch should run.

    A placement says which nodes a launch may use, which cores it may use on
    each of them, and how many GPUs it needs in total. It is machine
    independent: each :py:class:`~mache.parallel.system.ParallelSystem`
    renders it into whatever its launcher needs.

    Attributes
    ----------
    nodes : tuple of str
        The hostnames the launch may run on. An empty tuple leaves the choice
        of nodes to the scheduler, which is only useful when nothing else is
        running concurrently.

    cores : tuple of int
        The cores, on each of ``nodes``, that the launch may use, in the order
        they should be handed out to tasks. This is an explicit set rather
        than a count because the usable cores on a node may not be contiguous
        and may not start at zero.

        Whether the exact set is honored depends on the machine: launchers
        that bind explicitly use it as given, while a scheduler that reserves
        resources uses only how many cores there are and picks which ones
        itself.

    gpus : int
        The number of GPUs the launch needs *in total*, not per task. A
        per-task count does not confine a launch on the GPU machines mache
        supports, whereas a total does. The default of 0 is rendered as an
        explicit request for no GPUs, since a launch that says nothing about
        GPUs is read as claiming every one on the node.

    gpu_ids : tuple of int or None
        Which of the node's GPUs to use, as indices from 0 to
        ``gpus_per_node - 1``. This is needed only where the batch system
        does not assign GPUs itself and mache has to name them, which is the
        case on PBS with PALS. Only the caller knows about every concurrent
        launch, so only the caller can assign disjoint GPUs; mache renders
        what it is given and never guesses. ``None`` where the scheduler
        assigns GPUs from ``gpus``.
    """

    nodes: Sequence[str]
    cores: Sequence[int]
    gpus: int = 0
    gpu_ids: Sequence[int] | None = None

    def __post_init__(self) -> None:
        nodes = tuple(str(node).strip() for node in self.nodes)
        if any(node == '' for node in nodes):
            raise ValueError('Placement node names must not be empty.')
        if len(set(nodes)) != len(nodes):
            raise ValueError(f'Placement nodes must be unique, got {nodes}.')
        object.__setattr__(self, 'nodes', nodes)

        cores = tuple(int(core) for core in self.cores)
        if len(cores) == 0:
            raise ValueError('A placement must list at least one core.')
        if any(core < 0 for core in cores):
            raise ValueError(
                f'Placement cores must not be negative, got {cores}.'
            )
        if len(set(cores)) != len(cores):
            raise ValueError(f'Placement cores must be unique, got {cores}.')
        object.__setattr__(self, 'cores', cores)

        if self.gpus < 0:
            raise ValueError(
                f'Placement gpus must not be negative, got {self.gpus}.'
            )

        if self.gpu_ids is None:
            return

        gpu_ids = tuple(int(gpu_id) for gpu_id in self.gpu_ids)
        if any(gpu_id < 0 for gpu_id in gpu_ids):
            raise ValueError(
                f'Placement gpu_ids must not be negative, got {gpu_ids}.'
            )
        if len(set(gpu_ids)) != len(gpu_ids):
            raise ValueError(
                f'Placement gpu_ids must be unique, got {gpu_ids}.'
            )
        if len(gpu_ids) != self.gpus:
            # a mismatch here is a bug in whatever assigned the GPUs, and it
            # is much cheaper to catch at the boundary than as silent
            # oversubscription once the work is running
            raise ValueError(
                f'Placement lists {len(gpu_ids)} gpu_ids but asks for '
                f'{self.gpus} gpus. They must agree.'
            )
        object.__setattr__(self, 'gpu_ids', gpu_ids)


def split_cores(
    placement: ResourcePlacement, ntasks: int, cpus_per_task: int
) -> List[List[int]]:
    """
    Divide a placement's cores into a contiguous chunk per task.

    Parameters
    ----------
    placement : ResourcePlacement
        The placement whose cores should be divided.

    ntasks : int
        The number of tasks to divide the cores between.

    cpus_per_task : int
        The number of cores each task should get. A value of 0 means one core
        per task, matching what ``get_parallel_command()`` does with an
        unspecified ``cpus_per_task``.

    Returns
    -------
    chunks : list of list of int
        One list of cores per task, in task order.
    """
    cpus_per_task = max(cpus_per_task, 1)
    needed = ntasks * cpus_per_task
    if needed > len(placement.cores):
        raise ValueError(
            f'The placement has {len(placement.cores)} cores but '
            f'{ntasks} tasks x {cpus_per_task} cpus per task need {needed}.'
        )

    chunks = []
    for index in range(ntasks):
        start = index * cpus_per_task
        chunks.append(list(placement.cores[start : start + cpus_per_task]))
    return chunks


def format_core_ranges(cores: Sequence[int]) -> str:
    """Format cores as a compact ``0-3,8`` list, as ``taskset -c`` takes."""
    ranges: List[str] = []
    for core in sorted(cores):
        if len(ranges) > 0:
            first, _, last = ranges[-1].partition('-')
            end = int(last) if last != '' else int(first)
            if core == end + 1:
                ranges[-1] = f'{first}-{core}'
                continue
        ranges.append(f'{core}')
    return ','.join(ranges)


def cpu_mask(cores: Sequence[int]) -> str:
    """Format cores as the hexadecimal mask ``--cpu-bind=mask_cpu:`` takes."""
    mask = 0
    for core in cores:
        mask |= 1 << core
    return hex(mask)
