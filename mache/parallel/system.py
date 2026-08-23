import subprocess
from configparser import ConfigParser
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Literal

from mache.parallel.placement import PlacementSupport, ResourcePlacement

# the config option in [parallel] that lists each type of scheduler target
TARGET_TYPE_MAP = {
    'queue': 'queues',
    'partition': 'partitions',
    'qos': 'qos',
}


@dataclass(frozen=True)
class SubmissionResolution:
    """
    Resolved scheduler target and effective node count.

    Attributes
    ----------
    target : str
        The selected queue, partition or QOS, or an empty string if the
        machine does not define any for this target type.

    requested_nodes : int
        The node count the caller asked for.

    effective_nodes : int
        The node count after clamping to the selected target's limits.

    adjustment : {'exact', 'decrease', 'increase'}
        How ``effective_nodes`` compares with ``requested_nodes``.

    honored : bool
        Whether a requested target was used. ``True`` when no target was
        requested.

    reason : str or None
        A human-readable explanation of why a requested target could not be
        honored, suitable for printing verbatim. ``None`` when ``honored``
        is ``True``.
    """

    target: str
    requested_nodes: int
    effective_nodes: int
    adjustment: Literal['exact', 'decrease', 'increase']
    honored: bool = True
    reason: str | None = None


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

    memory : int
        The total memory available on the system in MB, or ``None`` if the
        machine's config does not describe it.

    memory_per_node : int
        The memory available per node in MB, or ``None`` if the machine's
        config does not describe it. This is the memory a job may actually
        use, which is smaller than the hardware capacity of a node.

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
        self.memory: int | None = None
        self.memory_per_node: int | None = None
        self.nodes: int | None = None
        self.mpi_allowed: bool | None = None

    @property
    def placement_support(self) -> PlacementSupport:
        """
        The placement mechanism available on this machine.

        A caller that wants to run several launches at once inside one
        allocation should check this first: on a machine that reports
        ``PlacementSupport.NONE``, concurrent launches will oversubscribe or
        serialize rather than run side by side.

        This is determined from the launcher actually present rather than
        from the machine's config, since a site can be upgraded across a
        launcher change without its mache config changing, and a stale
        assumption there fails in the worst way -- the command is accepted
        and the placement silently does nothing.
        """
        return PlacementSupport.NONE

    def get_parallel_command(
        self,
        args: List[str],
        ntasks: int,
        cpus_per_task: int = 0,
        gpus_per_task: int = 0,
        placement: ResourcePlacement | None = None,
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
            The number of GPUs to allocate per task. Ignored when
            ``placement`` is given, which expresses GPUs as a total for the
            launch instead.

        placement : mache.parallel.ResourcePlacement, optional
            Which nodes, cores and GPUs to confine this launch to, for
            callers running several launches at once inside one allocation.
            When it is not given, the command is exactly what it would have
            been without this argument.

            A placement supersedes the machine's ``distribution``,
            ``placement``, ``gpu_bind`` and ``mem_bind`` config options,
            which describe how to spread a launch over a whole node.

        Returns
        -------
        command : list of str
            The complete command to execute the parallel job.
        """
        parallel_executable = self.get_config('parallel_executable')
        command = self._get_command_prefix(placement)
        command.extend(parallel_executable.split(' '))
        parallel_args = self._get_parallel_args(
            cpus_per_task, gpus_per_task, ntasks, placement
        )
        command.extend(parallel_args)
        command.extend(args)
        return command

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement | None = None,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        raise NotImplementedError

    def _get_command_prefix(
        self, placement: ResourcePlacement | None
    ) -> List[str]:
        """Get anything that has to come before the parallel executable."""
        return []

    def _check_placement_supported(
        self, placement: ResourcePlacement | None
    ) -> None:
        """Raise if a placement was given but cannot be honored here."""
        if placement is None:
            return
        if self.placement_support is PlacementSupport.NONE:
            raise ValueError(
                f'This machine cannot place a launch: no placement mechanism '
                f'was found for the "{self.get_config("parallel_executable")}"'
                f' launcher. Check placement_support before passing a '
                f'placement.'
            )

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a config value from the parallel configs."""
        return self.parallel_configs.get(key, default)

    def get_config_int(self, key: str, default: int | None = 0) -> int | None:
        """Get an integer config value from the parallel configs."""
        value = self.get_config(key, default)
        return int(value) if value is not None else None

    @classmethod
    def get_scheduler_target(
        cls, config: ConfigParser, target_type: str, nodes: int
    ) -> str:
        """
        Choose queue/partition/qos metadata target for a node count.

        This is a convenience wrapper around ``resolve_submission()`` that
        returns only the selected target.
        """
        resolution = cls.resolve_submission(config, nodes, target_type)
        return resolution.target

    @classmethod
    def resolve_submission(
        cls,
        config: ConfigParser,
        nodes: int,
        target_type: str,
        min_nodes_allowed: int | None = None,
        requested: str | None = None,
        desired_wall_time: str | None = None,
    ) -> SubmissionResolution:
        """
        Resolve a scheduler target and effective node count.

        Policy:

        - If ``requested`` is given and can be honored, use it.
        - Otherwise, prefer exact match when available.
        - Otherwise choose the nearest valid node count.
        - Tie-break toward lower (decrease) adjustments.
        - If a lower adjustment violates ``min_nodes_allowed``, choose the
          nearest feasible higher adjustment.

        A requested target is a preference, not an assertion: if it cannot be
        honored, the default target is resolved instead and the returned
        resolution has ``honored=False`` along with a ``reason``.

        Parameters
        ----------
        config : ConfigParser
            Machine configuration parser.

        nodes : int
            Requested node count.

        target_type : {'queue', 'partition', 'qos'}
            Scheduler target type to resolve.

        min_nodes_allowed : int, optional
            Optional lower bound for adjusted node counts.

        requested : str, optional
            A specific target the caller would like to use. ``None``, an
            empty string and placeholders such as ``<<<default>>>`` all mean
            "no target was requested".  A request is also ignored when the
            machine defines no targets of this type at all, since there is
            then no choice for the request to have been denied.

        desired_wall_time : str, optional
            The wall time (``HH:MM:SS``) the caller intends to request. When
            given, a requested target whose ``max_wallclock`` is shorter is
            not honored.

        Returns
        -------
        SubmissionResolution
            The selected target and adjusted node count.
        """
        targets = cls._get_targets(
            config, nodes, target_type, min_nodes_allowed
        )

        requested_target = _normalize_requested(requested)
        if requested_target is None or len(targets) == 0:
            # A machine that defines no targets of this type has no notion
            # of one, so a request is a no-op rather than a denied request.
            return cls._resolve_default(
                config, nodes, target_type, min_nodes_allowed, targets
            )

        effective_nodes, reason = cls._check_requested(
            config=config,
            nodes=nodes,
            target_type=target_type,
            min_nodes_allowed=min_nodes_allowed,
            targets=targets,
            requested=requested_target,
            desired_wall_time=desired_wall_time,
        )
        if reason is None:
            return SubmissionResolution(
                target=requested_target,
                requested_nodes=nodes,
                effective_nodes=effective_nodes,
                adjustment=_get_adjustment(nodes, effective_nodes),
            )

        fallback = cls._resolve_default(
            config, nodes, target_type, min_nodes_allowed, targets
        )
        return replace(fallback, honored=False, reason=reason)

    @classmethod
    def _get_targets(
        cls,
        config: ConfigParser,
        nodes: int,
        target_type: str,
        min_nodes_allowed: int | None,
    ) -> list[str]:
        """Validate arguments and get the available targets."""
        if nodes <= 0:
            raise ValueError(f'nodes must be positive, got {nodes}.')
        if min_nodes_allowed is not None and min_nodes_allowed <= 0:
            raise ValueError(
                f'min_nodes_allowed must be positive, got {min_nodes_allowed}.'
            )

        if target_type not in TARGET_TYPE_MAP:
            expected = ', '.join(TARGET_TYPE_MAP.keys())
            raise ValueError(
                f'Unexpected target_type: {target_type}. Expected one of: '
                f'{expected}.'
            )

        parallel_configs = _get_parallel_configs(config)
        targets_value = parallel_configs.get(TARGET_TYPE_MAP[target_type])
        return _parse_list(targets_value)

    @classmethod
    def _check_requested(
        cls,
        config: ConfigParser,
        nodes: int,
        target_type: str,
        min_nodes_allowed: int | None,
        targets: list[str],
        requested: str,
        desired_wall_time: str | None,
    ) -> tuple[int, str | None]:
        """
        Check whether a requested target can be honored.

        Returns the effective node count and either ``None`` (the request can
        be honored) or a reason why it cannot.
        """
        if requested not in targets:
            return nodes, (
                f'"{requested}" is not an available {target_type} on this '
                f'machine (available: {", ".join(targets)})'
            )

        effective_nodes = cls._get_effective_nodes(
            config, target_type, requested, nodes
        )

        if (
            min_nodes_allowed is not None
            and effective_nodes < min_nodes_allowed
        ):
            return effective_nodes, (
                f'the "{requested}" {target_type} would run on '
                f'{effective_nodes} nodes but at least {min_nodes_allowed} '
                f'are required'
            )

        max_wallclock = cls._get_max_wallclock(
            config, target_type, requested, effective_nodes
        )
        if _wall_time_exceeds(desired_wall_time, max_wallclock):
            return effective_nodes, (
                f'the "{requested}" {target_type} allows a maximum wall '
                f'clock of {max_wallclock} but {desired_wall_time} was '
                f'requested'
            )

        return effective_nodes, None

    @classmethod
    def _get_effective_nodes(
        cls,
        config: ConfigParser,
        target_type: str,
        target: str,
        nodes: int,
    ) -> int:
        """Clamp a node count to a target's ``min_nodes``/``max_nodes``."""
        section = f'{target_type}.{target}'
        min_nodes = _get_int_option(config, section, 'min_nodes')
        max_nodes = _get_int_option(config, section, 'max_nodes')

        if (
            min_nodes is not None
            and max_nodes is not None
            and min_nodes > max_nodes
        ):
            raise ValueError(
                f'Invalid {target_type} config [{section}]: min_nodes '
                f'({min_nodes}) is greater than max_nodes ({max_nodes}).'
            )

        return _clamp_nodes(nodes, min_nodes, max_nodes)

    @classmethod
    def _resolve_default(
        cls,
        config: ConfigParser,
        nodes: int,
        target_type: str,
        min_nodes_allowed: int | None,
        targets: list[str],
    ) -> SubmissionResolution:
        """Resolve a target from the node count alone."""
        if len(targets) == 0:
            return SubmissionResolution(
                target='',
                requested_nodes=nodes,
                effective_nodes=nodes,
                adjustment='exact',
            )

        candidates: list[tuple[str, int, int]] = []
        # tuple: (target, effective_nodes, order)
        for index, target in enumerate(targets):
            effective_nodes = cls._get_effective_nodes(
                config, target_type, target, nodes
            )

            if (
                min_nodes_allowed is not None
                and effective_nodes < min_nodes_allowed
            ):
                continue

            candidates.append((target, effective_nodes, index))

        if len(candidates) == 0:
            min_nodes_suffix = ''
            if min_nodes_allowed is not None:
                min_nodes_suffix = (
                    f' and min_nodes_allowed={min_nodes_allowed}'
                )
            raise ValueError(
                f'No {target_type} matches nodes={nodes}{min_nodes_suffix}. '
                f'Checked {target_type}s: {", ".join(targets)}.'
            )

        exact_candidates = [item for item in candidates if item[1] == nodes]
        if len(exact_candidates) > 0:
            best_target, best_nodes, _ = min(
                exact_candidates,
                key=lambda item: item[2],
            )
        else:
            lower_candidates = [item for item in candidates if item[1] < nodes]
            if len(lower_candidates) > 0:
                # Prefer the closest feasible lower adjustment.
                best_target, best_nodes, _ = max(
                    lower_candidates,
                    key=lambda item: (item[1], -item[2]),
                )
            else:
                # No feasible lower adjustment; move to nearest higher.
                higher_candidates = [
                    item for item in candidates if item[1] > nodes
                ]
                best_target, best_nodes, _ = min(
                    higher_candidates,
                    key=lambda item: (item[1], item[2]),
                )

        return SubmissionResolution(
            target=best_target,
            requested_nodes=nodes,
            effective_nodes=best_nodes,
            adjustment=_get_adjustment(nodes, best_nodes),
        )

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
    def _find_scheduler_target(
        cls,
        config: ConfigParser,
        scheduler_target: str | None,
        target_types: tuple[str, ...],
    ) -> tuple[str | None, str | None]:
        """
        Find which scheduler axis a target name belongs to on this machine.

        Machines hang a concept such as "debug" off whichever axis they use,
        so a caller with one machine-independent intent can name it once and
        let mache decide whether it is a queue, a partition or a QOS here.

        ``target_types`` is searched in order, so the first axis that lists
        the name wins.

        Returns the target type that lists ``scheduler_target``, or ``None``
        along with a reason when no axis in ``target_types`` does.  Both are
        ``None`` when nothing was requested.
        """
        requested = _normalize_requested(scheduler_target)
        if requested is None:
            return None, None

        parallel_configs = _get_parallel_configs(config)

        described = []
        for target_type in target_types:
            plural = TARGET_TYPE_MAP[target_type]
            targets = _parse_list(parallel_configs.get(plural))
            if requested in targets:
                return target_type, None
            if len(targets) > 0:
                described.append(f'{plural}: {", ".join(targets)}')

        if len(described) == 0:
            available = 'this machine defines no scheduler targets'
        else:
            available = '; '.join(described)

        return None, (
            f'"{requested}" is not an available scheduler target on this '
            f'machine ({available})'
        )

    @classmethod
    def _resolve_constraint(
        cls, config: ConfigParser, requested: str | None
    ) -> tuple[str, str | None]:
        """
        Resolve a constraint, honoring a requested one when it is available.

        Unlike queues, partitions and QOS, a constraint has no node-count or
        wall-clock metadata, so it is only checked against the machine's
        ``[parallel] constraints`` list.

        Returns the constraint and either ``None`` (nothing was requested or
        the request was honored) or a reason why the request could not be.
        """
        parallel_configs = _get_parallel_configs(config)
        constraints = _parse_list(parallel_configs.get('constraints'))
        default = constraints[0] if len(constraints) > 0 else ''

        requested_constraint = _normalize_requested(requested)
        if requested_constraint is None or len(constraints) == 0:
            # A machine that defines no constraints has no notion of one, so
            # a request is a no-op rather than a denied request.
            return default, None

        if requested_constraint in constraints:
            return requested_constraint, None

        return default, (
            f'"{requested_constraint}" is not an available constraint on '
            f'this machine (available: {", ".join(constraints)})'
        )

    @classmethod
    def _get_max_wallclock(
        cls,
        config: ConfigParser,
        target_type: str,
        target: str,
        nodes: int,
    ) -> str:
        """
        Get max wall-clock metadata for a selected scheduler target.

        Targets whose limit depends on the job size supply
        ``max_wallclock_bins`` instead of ``max_wallclock``, in which case
        the bin containing ``nodes`` is used.
        """
        if target == '':
            return ''

        section = f'{target_type}.{target}'
        bins = _get_wallclock_bins(config, section)
        if bins is not None:
            return _select_wallclock_bin(bins, nodes)

        max_wallclock = _get_string_option(config, section, 'max_wallclock')
        if max_wallclock is None:
            return ''
        return max_wallclock

    @classmethod
    def _select_max_wallclock(
        cls, max_wallclock_a: str, max_wallclock_b: str
    ) -> str:
        """Choose the more restrictive wall-clock string when possible."""
        if max_wallclock_a == '':
            return max_wallclock_b
        if max_wallclock_b == '':
            return max_wallclock_a

        seconds_a = _max_wallclock_to_seconds(max_wallclock_a)
        seconds_b = _max_wallclock_to_seconds(max_wallclock_b)
        if seconds_a is None or seconds_b is None:
            return max_wallclock_a

        if seconds_a <= seconds_b:
            return max_wallclock_a
        return max_wallclock_b


def cap_wall_time(desired: str, max_wallclock: str) -> str:
    """
    Cap a desired wall time at a scheduler target's maximum.

    Parameters
    ----------
    desired : str
        The wall time (``HH:MM:SS``) the caller would like to request.

    max_wallclock : str
        The maximum wall time (``HH:MM:SS``) the target allows, typically
        from ``SlurmOptions.max_wallclock`` or ``PbsOptions.max_wallclock``.

    Returns
    -------
    wall_time : str
        ``max_wallclock`` if it is shorter than ``desired``, otherwise
        ``desired`` unchanged. ``desired`` is also returned unchanged if
        either value is empty or cannot be parsed.
    """
    if not _wall_time_exceeds(desired, max_wallclock):
        return desired
    return max_wallclock


def _get_wallclock_bins(
    config: ConfigParser, section: str
) -> list[tuple[int, str]] | None:
    """
    Get the parsed ``max_wallclock_bins`` for a scheduler target section.

    Returns ``None`` if the section does not define job-size-dependent wall
    clocks. Raises ``ValueError`` if the section also defines a plain
    ``max_wallclock``, since the two would be ambiguous.
    """
    value = _get_string_option(config, section, 'max_wallclock_bins')
    if value is None:
        return None

    if _get_string_option(config, section, 'max_wallclock') is not None:
        raise ValueError(
            f'Invalid config [{section}]: max_wallclock and '
            f'max_wallclock_bins cannot both be set.'
        )

    return _parse_wallclock_bins(value, section)


def _parse_wallclock_bins(value: str, section: str) -> list[tuple[int, str]]:
    """
    Parse ``<max nodes>: <max wallclock>`` entries into sorted bins.

    Entries are comma-separated and each is split on its first colon, since
    the wall clock itself contains colons.
    """
    bins: list[tuple[int, str]] = []
    for entry in value.split(','):
        entry = entry.strip()
        if entry == '':
            continue

        node_bound_str, _, max_wallclock = entry.partition(':')
        max_wallclock = max_wallclock.strip()
        try:
            node_bound = int(node_bound_str.strip())
        except ValueError:
            raise ValueError(
                f'Invalid max_wallclock_bins entry "{entry}" in [{section}]: '
                f'expected an integer node count before the colon.'
            ) from None

        if _max_wallclock_to_seconds(max_wallclock) is None:
            raise ValueError(
                f'Invalid max_wallclock_bins entry "{entry}" in [{section}]: '
                f'expected a wall clock of the form HH:MM:SS after the '
                f'colon.'
            )

        bins.append((node_bound, max_wallclock))

    if len(bins) == 0:
        raise ValueError(
            f'Invalid config [{section}]: max_wallclock_bins is set but has '
            f'no entries.'
        )

    return sorted(bins)


def _select_wallclock_bin(bins: list[tuple[int, str]], nodes: int) -> str:
    """Get the wall clock for the bin containing a node count."""
    for node_bound, max_wallclock in bins:
        if nodes <= node_bound:
            return max_wallclock

    # a node count above every bin gets the largest bin's wall clock
    return bins[-1][1]


def _normalize_requested(requested: str | None) -> str | None:
    """
    Normalize a requested target, treating placeholders as no request.

    ``None``, an empty string and placeholders such as ``<<<default>>>``
    (used by downstream config files to mean "let mache choose") all become
    ``None``.
    """
    if requested is None:
        return None

    requested = requested.strip()
    if requested == '':
        return None
    if requested.startswith('<<<') and requested.endswith('>>>'):
        return None
    return requested


def _get_adjustment(
    nodes: int, effective_nodes: int
) -> Literal['exact', 'decrease', 'increase']:
    """Describe how an effective node count differs from the request."""
    if effective_nodes == nodes:
        return 'exact'
    if effective_nodes < nodes:
        return 'decrease'
    return 'increase'


def _wall_time_exceeds(desired: str | None, max_wallclock: str) -> bool:
    """
    Check whether a desired wall time is longer than a maximum.

    Returns ``False`` if either value is missing or cannot be parsed, since
    an unknown limit is not a reason to reject anything.
    """
    if desired is None or desired == '' or max_wallclock == '':
        return False

    desired_seconds = _max_wallclock_to_seconds(desired)
    max_seconds = _max_wallclock_to_seconds(max_wallclock)
    if desired_seconds is None or max_seconds is None:
        return False

    return desired_seconds > max_seconds


def _combine_reasons(*reasons: str | None) -> str | None:
    """Join the reasons from several resolutions into one message."""
    present = [reason for reason in reasons if reason is not None]
    if len(present) == 0:
        return None
    return '; '.join(present)


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


def _clamp_nodes(
    nodes: int, min_nodes: int | None, max_nodes: int | None
) -> int:
    """Clamp a node count to optional min/max bounds."""
    effective_nodes = nodes
    if min_nodes is not None and effective_nodes < min_nodes:
        effective_nodes = min_nodes
    if max_nodes is not None and effective_nodes > max_nodes:
        effective_nodes = max_nodes
    return effective_nodes


def _max_wallclock_to_seconds(max_wallclock: str) -> int | None:
    """Convert HH:MM:SS wall time to total seconds."""
    parts = max_wallclock.split(':')
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
