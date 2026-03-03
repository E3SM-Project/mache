import multiprocessing
from configparser import ConfigParser
from typing import List

from mache.parallel.system import ParallelSystem


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

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        parallel_args = ['-n', f'{ntasks}', '-c', f'{cpus_per_task}']
        return parallel_args
