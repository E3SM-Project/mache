import subprocess
from configparser import ConfigParser
from typing import Any, Dict, List


class ParallelSystem:
    """
    Base class for parallel system resource management.

    Attributes
    ----------
    parallel_configs : Dict[str, str]
        A dictionary containing combined config options for the parallel
        section and the parallel.{compiler} section, if any.

    cores : int
        The total number of CPU cores available on the system.

    cores_per_node : int
        The number of CPU cores available per node.

    gpus : int
        The total number of GPUs available on the system.

    gpus_per_node : int
        The number of GPUs available per node.

    nodes : int
        The total number of nodes available on the system.

    mpi_allowed : bool
        Whether MPI execution is allowed on the system.
    """

    def __init__(self, config: ConfigParser):
        """
        Set available resources for the parallel system based on the config.

        Parameters
        ----------
        config : ConfigParser
            The configuration parser containing the parallel system options.
        """
        self.parallel_configs = _get_parallel_configs(config)
        self.cores: int | None = None
        self.cores_per_node: int | None = None
        self.gpus: int | None = None
        self.gpus_per_node: int | None = None
        self.nodes: int | None = None
        self.mpi_allowed: bool | None = None

    def get_parallel_command(
        self,
        args: List[str],
        ntasks: int,
        cpus_per_task: int = 0,
        gpus_per_task: int = 0,
    ) -> List[str]:
        """
        Get the parallel execution command for the current system.

        Parameters
        ----------
        args : list of str
            The command-line arguments for the parallel execution.

        ntasks : int
            The total number of tasks to run in parallel.

        cpus_per_task : int, optional
            The number of CPUs to allocate per task.

        gpus_per_task : int, optional
            The number of GPUs to allocate per task.

        Returns
        -------
        command : list of str
            The complete command to execute the parallel job.
        """
        parallel_executable = self.get_config('parallel_executable')
        command = parallel_executable.split(' ')
        parallel_args = self._get_parallel_args(
            cpus_per_task, gpus_per_task, ntasks
        )
        command.extend(parallel_args)
        command.extend(args)
        return command

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        raise NotImplementedError

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a config value from the parallel configs."""
        return self.parallel_configs.get(key, default)

    def get_config_int(self, key: str, default: int = 0) -> int | None:
        """Get an integer config value from the parallel configs."""
        value = self.get_config(key, default)
        return int(value) if value is not None else None


def _get_parallel_configs(config: ConfigParser) -> Dict[str, str]:
    """
    Get combined config options for the parallel section and the
    parallel.{compiler} section, if any.
    """
    section = dict(config['parallel'])
    compiler = config.get('build', 'compiler')
    if compiler is not None:
        compiler_section = f'parallel.{compiler}'
        if config.has_section(compiler_section):
            for key, value in config.items(compiler_section):
                section[key] = value
    return section


def _ceil_division(a: int, b: int) -> int:
    """Return the ceiling of a divided by b."""
    return (a + b - 1) // b


def _get_subprocess_str(args: List[str]) -> str:
    """Run a subprocess and return its output as a string."""
    value = subprocess.check_output(args)
    value_str = value.decode('utf-8').strip('\n')
    return value_str


def _get_subprocess_int(args: List[str]) -> int:
    """Run a subprocess and return its output as an integer."""
    value_int = int(_get_subprocess_str(args))
    return value_int
