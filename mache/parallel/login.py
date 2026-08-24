import multiprocessing
from configparser import ConfigParser
from typing import List

from mache.parallel.placement import ResourcePlacement
from mache.parallel.system import ParallelSystem


class LoginSystem(ParallelSystem):
    """Resource manager for login nodes (no parallel execution)."""

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        # default=None so an absent option reaches the check below:
        # get_config_int defaults to 0, which would leave the login node
        # reporting no cores instead of raising
        login_cores = self.get_config_int('login_cores', default=None)
        if login_cores is None:
            raise ValueError(
                'login_cores must be set in the config for the login system.'
            )
        self.cores = min(multiprocessing.cpu_count(), login_cores)
        self.cores_per_node = self.cores

        # 0 rather than None here: a machine that says nothing about GPUs
        # has none, which is an answer and not a gap
        self.gpus = self.get_config_int('login_gpus', default=0)
        self.gpus_per_node = self.gpus

        # memory stays None: memory_per_node describes a compute node, and a
        # login node neither has that much nor hands out what it does have
        self.nodes = 1
        self.mpi_allowed = False

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement | None = None,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        # Not supported for login system
        raise ValueError('Parallel execution is not allowed on login nodes.')
