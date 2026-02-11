import multiprocessing
from configparser import ConfigParser
from typing import List

from mache.parallel.system import ParallelSystem


class LoginSystem(ParallelSystem):
    """Resource manager for login nodes (no parallel execution)."""

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        login_cores = self.get_config_int('login_cores')
        if login_cores is None:
            raise ValueError(
                'login_cores must be set in the config for the login system.'
            )
        self.cores = min(multiprocessing.cpu_count(), login_cores)
        self.cores_per_node = self.cores

        self.gpus = self.get_config_int('login_gpus')
        self.gpus_per_node = self.gpus

        self.nodes = 1
        self.mpi_allowed = False

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        # Not supported for login system
        raise ValueError('Parallel execution is not allowed on login nodes.')
