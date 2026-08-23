import multiprocessing
import shutil
from configparser import ConfigParser
from typing import List

from mache.parallel.placement import (
    PlacementSupport,
    ResourcePlacement,
    format_core_ranges,
)
from mache.parallel.system import ParallelSystem

# the command used to confine a launch to a set of cores
TASKSET = 'taskset'


class SingleNodeSystem(ParallelSystem):
    """Resource manager for single-node parallel execution."""

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        cores_detected = multiprocessing.cpu_count()
        cores_per_node = self.get_config_int('cores_per_node')
        if cores_per_node is None:
            cores_per_node = cores_detected
        else:
            cores_per_node = min(cores_detected, cores_per_node)
        self.cores_per_node = cores_per_node
        self.cores = cores_per_node
        self.nodes = 1
        self.mpi_allowed = True
        self.gpus_per_node = self.get_config_int('gpus_per_node')
        self.gpus = self.gpus_per_node

    @property
    def placement_support(self) -> PlacementSupport:
        """
        The placement mechanism available on this machine.

        There is no batch system to reserve anything, so a launch is confined
        to its cores with ``taskset``, which the whole process tree inherits.
        """
        if shutil.which(TASKSET) is None:
            return PlacementSupport.NONE
        return PlacementSupport.CPU_BINDING

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement | None = None,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        self._check_placement_supported(placement)
        self._check_placement(placement, cpus_per_task, ntasks)
        parallel_args = ['-n', f'{ntasks}', '-c', f'{cpus_per_task}']
        return parallel_args

    def _get_command_prefix(
        self, placement: ResourcePlacement | None
    ) -> List[str]:
        """Get anything that has to come before the parallel executable."""
        if placement is None:
            return []
        self._check_placement_supported(placement)
        return [TASKSET, '-c', format_core_ranges(placement.cores)]

    def _check_placement(
        self,
        placement: ResourcePlacement | None,
        cpus_per_task: int,
        ntasks: int,
    ) -> None:
        """Check that a placement is one this system can honor."""
        if placement is None:
            return

        if len(placement.nodes) > 1:
            raise ValueError(
                f'The placement names {len(placement.nodes)} nodes but the '
                f'single_node system has only one.'
            )

        if placement.gpus > 0:
            raise ValueError(
                f'The placement asks for {placement.gpus} gpus but the '
                f'single_node system has no mechanism for confining a launch '
                f"to some of a machine's GPUs."
            )

        needed = ntasks * max(cpus_per_task, 1)
        if needed > len(placement.cores):
            raise ValueError(
                f'The placement has {len(placement.cores)} cores but '
                f'{ntasks} tasks x {max(cpus_per_task, 1)} cpus per task '
                f'need {needed}.'
            )
