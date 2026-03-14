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

    @classmethod
    def get_scheduler_target(
        cls, config: ConfigParser, target_type: str, nodes: int
    ) -> str:
        """
        Choose queue/partition/qos metadata target for a node count.

        If multiple targets match, the first configured target is selected.
        If no target matches and at least one target has explicit limits,
        a ValueError is raised.
        """
        if nodes <= 0:
            raise ValueError(f'nodes must be positive, got {nodes}.')

        target_map = {
            'queue': 'queues',
            'partition': 'partitions',
            'qos': 'qos',
        }
        if target_type not in target_map:
            expected = ', '.join(target_map.keys())
            raise ValueError(
                f'Unexpected target_type: {target_type}. Expected one of: '
                f'{expected}.'
            )

        parallel_configs = _get_parallel_configs(config)
        targets_value = parallel_configs.get(target_map[target_type])
        targets = _parse_list(targets_value)
        if len(targets) == 0:
            return ''

        any_limits = False
        for target in targets:
            section = f'{target_type}.{target}'
            min_nodes = _get_int_option(config, section, 'min_nodes')
            max_nodes = _get_int_option(config, section, 'max_nodes')

            if min_nodes is not None or max_nodes is not None:
                any_limits = True

            if _nodes_match(nodes, min_nodes, max_nodes):
                return target

        if any_limits:
            raise ValueError(
                f'No {target_type} matches nodes={nodes}. Checked '
                f'{target_type}s: {", ".join(targets)}.'
            )

        return targets[0]

    @classmethod
    def _get_common_submission_options(
        cls, config: ConfigParser
    ) -> tuple[str, str, str]:
        """Get first constraint, gpus_per_node and filesystems settings."""
        parallel_configs = _get_parallel_configs(config)
        constraint = _first_from_list(parallel_configs.get('constraints'))

        gpus_per_node = parallel_configs.get('gpus_per_node')
        if gpus_per_node is None:
            gpus_per_node_str = ''
        else:
            gpus_per_node_str = str(gpus_per_node)

        filesystems = parallel_configs.get('filesystems', '')
        return constraint, gpus_per_node_str, filesystems

    @classmethod
    def _get_wall_time(
        cls, config: ConfigParser, target_type: str, target: str
    ) -> str:
        """Get max wall-clock metadata for a selected scheduler target."""
        if target == '':
            return ''

        section = f'{target_type}.{target}'
        wall_time = _get_string_option(config, section, 'max_wallclock')
        if wall_time is None:
            return ''
        return wall_time

    @classmethod
    def _select_wall_time(cls, wall_time_a: str, wall_time_b: str) -> str:
        """Choose the more restrictive wall-clock string when possible."""
        if wall_time_a == '':
            return wall_time_b
        if wall_time_b == '':
            return wall_time_a

        seconds_a = _wall_time_to_seconds(wall_time_a)
        seconds_b = _wall_time_to_seconds(wall_time_b)
        if seconds_a is None or seconds_b is None:
            return wall_time_a

        if seconds_a <= seconds_b:
            return wall_time_a
        return wall_time_b


def _get_parallel_configs(config: ConfigParser) -> Dict[str, str]:
    """
    Get combined config options for the parallel section and the
    parallel.{compiler} section, if any.
    """
    section = dict(config['parallel'])
    compiler = config.get('build', 'compiler', fallback=None)
    if compiler is not None:
        compiler_underscore = compiler.replace('-', '_')
        compiler_section = f'parallel.{compiler_underscore}'
        if config.has_section(compiler_section):
            for key, value in config.items(compiler_section):
                section[key] = value
    return section


def _parse_list(value: str | None) -> list[str]:
    """Parse a comma-separated list into stripped items."""
    if value is None:
        return []

    items = [item.strip() for item in value.split(',') if item.strip() != '']
    return items


def _first_from_list(value: str | None) -> str:
    """Get the first item from a comma-separated list."""
    items = _parse_list(value)
    if len(items) == 0:
        return ''
    return items[0]


def _get_string_option(
    config: ConfigParser, section: str, option: str
) -> str | None:
    """Get a config value, treating missing/empty values as unset."""
    if not config.has_option(section, option):
        return None

    value = config.get(section, option).strip()
    if value == '':
        return None
    return value


def _get_int_option(
    config: ConfigParser, section: str, option: str
) -> int | None:
    """Get an integer config value if set."""
    value = _get_string_option(config, section, option)
    if value is None:
        return None
    return int(value)


def _nodes_match(
    nodes: int, min_nodes: int | None, max_nodes: int | None
) -> bool:
    """Check whether a node count satisfies optional min/max bounds."""
    if min_nodes is not None and nodes < min_nodes:
        return False
    if max_nodes is not None and nodes > max_nodes:
        return False
    return True


def _wall_time_to_seconds(wall_time: str) -> int | None:
    """Convert HH:MM:SS wall time to total seconds."""
    parts = wall_time.split(':')
    if len(parts) != 3:
        return None

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None

    return hours * 3600 + minutes * 60 + seconds


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
