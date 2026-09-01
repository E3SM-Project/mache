import functools
import getpass
import os
import re
import subprocess
import warnings
from configparser import ConfigParser
from dataclasses import dataclass
from typing import List

from mache.parallel.memory import MemoryCapSupport
from mache.parallel.placement import (
    BINDING_OPTIONS,
    PlacementSupport,
    ResourcePlacement,
    cpu_mask,
    names_resources,
    split_cores,
)
from mache.parallel.system import (
    ParallelSystem,
    _ceil_division,
    _combine_reasons,
    _get_subprocess_int,
    _get_subprocess_str,
    _normalize_requested,
    cap_wall_time,
)

# Slurm 20.11 made job steps reserve what they ask for instead of sharing a
# node, and added the options that control it. Before that release those
# options do not exist and passing them is an error, not a no-op, so the two
# eras need different commands. Both are in production on machines mache
# supports.
STEP_ISOLATION_VERSION = (20, 11)

# Where a memory cap on a job step is enforced. This is the same boundary as
# step isolation, but it is a separate fact and a separate constant: memory
# enforcement comes from the cgroup constraints a site configures, not from
# the step options 20.11 added, and evidence that moves one should not move
# the other. What was measured is that a step allowed 1024 MB and told to
# take 4 GB is killed at 960 MB on Perlmutter and Frontier, and runs to
# completion on Chrysalis.
MEMORY_ENFORCEMENT_VERSION = (20, 11)


@dataclass(frozen=True)
class SlurmOptions:
    """
    Slurm submission options resolved from a machine's config.

    Attributes
    ----------
    partition : str
        The Slurm partition, or an empty string if the machine defines none.

    qos : str
        The Slurm quality of service, or an empty string if the machine
        defines none.

    constraint : str
        The Slurm constraint, or an empty string if the machine defines none.

    gpus_per_node : str
        The number of GPUs per node, or an empty string if not configured.

    max_wallclock : str
        The most restrictive maximum wall clock (``HH:MM:SS``) of the
        selected partition and QOS, or an empty string if neither sets one.

    effective_nodes : int
        The node count after clamping to the selected targets' limits.

    wall_time : str
        The requested wall time capped at ``max_wallclock``, or an empty
        string if no wall time was requested.

    honored : bool
        Whether every requested target -- partition, QOS, constraint and
        ``scheduler_target`` -- was used. ``True`` when none was requested.

    reason : str or None
        A human-readable explanation of why a requested target could not be
        honored, suitable for printing verbatim. ``None`` when ``honored``
        is ``True``.
    """

    partition: str
    qos: str
    constraint: str
    gpus_per_node: str
    max_wallclock: str
    effective_nodes: int
    wall_time: str = ''
    honored: bool = True
    reason: str | None = None


@functools.cache
def get_slurm_version() -> tuple[int, int] | None:
    """
    Get the major and minor version of the Slurm installed on this machine.

    The version is read from ``srun`` itself rather than from a machine's
    config, because a site can be upgraded across the 20.11 change in job
    step behavior without its mache config changing. It is looked up at most
    once per process.

    Returns
    -------
    version : tuple of int or None
        The major and minor version, or ``None`` if ``srun`` is missing or
        reports a version that cannot be parsed.
    """
    try:
        output = _get_subprocess_str(['srun', '--version'])
    except (OSError, subprocess.SubprocessError):
        return None

    # e.g. "slurm 25.11.5"
    match = re.search(r'(\d+)\.(\d+)', output)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


# Job states in which the allocation still exists and can run job steps.
# Anything else, COMPLETING included, means the nodes are already on their
# way back to the scheduler, whatever the environment still says.
LIVE_JOB_STATES = frozenset({'CONFIGURING', 'RESIZING', 'RUNNING'})


def get_slurm_job_state(job_id: str) -> str | None:
    """
    Get the state of a Slurm job.

    ``-t all`` is not optional here. Squeue's default state filter hides
    jobs that have finished, so without it a job that ended within
    ``MinJobAge`` comes back as an empty listing that reports success, and
    that cannot be told apart from a healthy query with nothing to say.

    Parameters
    ----------
    job_id : str
        The job id to look up, normally the value of ``SLURM_JOB_ID``.

    Returns
    -------
    state : str or None
        The job's state, such as ``'RUNNING'`` or ``'TIMEOUT'``, or
        ``None`` if the scheduler has no record of the job id.

    Raises
    ------
    RuntimeError
        If squeue could not be run or could not reach the controller, so
        that a live job cannot be ruled out.
    """
    args = ['squeue', '--noheader', '-t', 'all', '-j', job_id, '-o', '%T']
    try:
        process = subprocess.run(
            args, capture_output=True, text=True, check=False
        )
    except OSError as exception:
        raise RuntimeError(
            f'Could not run squeue to check whether SLURM job {job_id} is '
            f'still running: {exception}'
        ) from exception

    if process.returncode == 0:
        # a heterogeneous job reports one row per component, and the
        # components share a fate, so the first row answers the question
        return process.stdout.strip().split('\n')[0].strip() or None

    # A nonzero exit is either a job id the scheduler has purged or squeue
    # itself failing, and the exit status alone does not tell those apart.
    # Asking squeue something that does not mention the job id does: if
    # that succeeds, squeue is healthy and the job id really is gone.
    if _squeue_is_responsive():
        return None

    raise RuntimeError(
        f'Could not determine whether SLURM job {job_id} is still '
        f'running. squeue said: {process.stderr.strip()}'
    )


def _squeue_is_responsive() -> bool:
    """Whether squeue can reach the Slurm controller at all."""
    args = ['squeue', '--noheader', '-u', getpass.getuser(), '-o', '%i']
    try:
        subprocess.run(args, capture_output=True, check=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


class SlurmSystem(ParallelSystem):
    """SLURM resource manager for parallel jobs."""

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        if 'SLURM_JOB_ID' not in os.environ:
            raise RuntimeError(
                'SLURM_JOB_ID environment variable not found but system is '
                'set to "slurm".'
            )
        job_id = os.environ['SLURM_JOB_ID']
        # default=None so an absent option reaches the check below:
        # get_config_int defaults to 0, which would leave the machine
        # reporting no cores instead of raising
        cores_per_node = self.get_config_int('cores_per_node', default=None)
        if cores_per_node is None:
            raise ValueError(
                'cores_per_node must be set in the config for the slurm '
                'system.'
            )
        args = ['squeue', '--noheader', '-j', job_id, '-o', '%D']
        nodes = _get_subprocess_int(args)
        cores = cores_per_node * nodes
        self.cores = cores
        self.cores_per_node = cores_per_node
        self.nodes = nodes
        self.mpi_allowed = True
        # 0 rather than None here: a machine that says nothing about GPUs
        # has none, which is an answer and not a gap
        gpus_per_node = self.get_config_int('gpus_per_node', default=0)
        self.gpus_per_node = gpus_per_node
        self.gpus = gpus_per_node * nodes
        self.memory_per_node = self.get_config_int(
            'memory_per_node', default=None
        )
        if self.memory_per_node is not None:
            self.memory = self.memory_per_node * nodes

    @classmethod
    def resolve_slurm_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
        partition: str | None = None,
        qos: str | None = None,
        constraint: str | None = None,
        desired_wall_time: str | None = None,
        scheduler_target: str | None = None,
    ) -> SlurmOptions:
        """
        Get Slurm submission options for a requested node count.

        The partition is resolved first and the QOS is then resolved against
        the resulting node count. A requested partition or QOS is honored
        when the machine's metadata allows it; otherwise the default is used
        and the returned options explain why.

        Parameters
        ----------
        config : ConfigParser
            Machine configuration parser.

        nodes : int
            Requested node count.

        min_nodes_allowed : int, optional
            Optional lower bound for adjusted node counts.

        partition : str, optional
            A specific partition the caller would like to use.

        qos : str, optional
            A specific quality of service the caller would like to use.

        constraint : str, optional
            A specific constraint the caller would like to use.

        desired_wall_time : str, optional
            The wall time (``HH:MM:SS``) the caller intends to request. A
            requested target that does not allow it is not honored, and the
            returned ``wall_time`` is capped at ``max_wallclock``.

        scheduler_target : str, optional
            A target named without saying which axis it is on, for callers
            with one machine-independent intent such as "use the debug
            target". It is used as the partition or the QOS, whichever this
            machine lists it under, checking partitions first. ``partition``
            and ``qos`` take precedence on the axis they name.

        Returns
        -------
        SlurmOptions
            The resolved Slurm submission options.
        """
        target_type, target_reason = cls._find_scheduler_target(
            config, scheduler_target, ('partition', 'qos')
        )
        if (
            target_type == 'partition'
            and _normalize_requested(partition) is None
        ):
            partition = scheduler_target
        elif target_type == 'qos' and _normalize_requested(qos) is None:
            qos = scheduler_target

        partition_resolution = cls.resolve_submission(
            config=config,
            nodes=nodes,
            target_type='partition',
            min_nodes_allowed=min_nodes_allowed,
            requested=partition,
            desired_wall_time=desired_wall_time,
        )
        partition_name = partition_resolution.target

        qos_resolution = cls.resolve_submission(
            config=config,
            nodes=partition_resolution.effective_nodes,
            target_type='qos',
            min_nodes_allowed=min_nodes_allowed,
            requested=qos,
            desired_wall_time=desired_wall_time,
        )
        qos_name = qos_resolution.target
        effective_nodes = qos_resolution.effective_nodes

        _, gpus_per_node, _ = cls._get_common_submission_options(config)
        constraint_name, constraint_reason = cls._resolve_constraint(
            config, constraint
        )

        max_wallclock = cls._select_max_wallclock(
            cls._get_max_wallclock(
                config, 'partition', partition_name, effective_nodes
            ),
            cls._get_max_wallclock(config, 'qos', qos_name, effective_nodes),
        )

        wall_time = ''
        if desired_wall_time is not None:
            wall_time = cap_wall_time(desired_wall_time, max_wallclock)

        return SlurmOptions(
            partition=partition_name,
            qos=qos_name,
            constraint=constraint_name,
            gpus_per_node=gpus_per_node,
            max_wallclock=max_wallclock,
            effective_nodes=effective_nodes,
            wall_time=wall_time,
            honored=(
                partition_resolution.honored
                and qos_resolution.honored
                and constraint_reason is None
                and target_reason is None
            ),
            reason=_combine_reasons(
                target_reason,
                partition_resolution.reason,
                qos_resolution.reason,
                constraint_reason,
            ),
        )

    @classmethod
    def get_slurm_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
    ) -> tuple[str, str, str, str, str, int]:
        """
        Get Slurm submission options for a requested node count.

        .. deprecated:: 3.11.0
            Use :py:meth:`resolve_slurm_options` instead, which returns a
            :py:class:`SlurmOptions` object and supports requesting a
            specific partition or QOS.
        """
        warnings.warn(
            'SlurmSystem.get_slurm_options() is deprecated and will be '
            'removed in a future release. Use '
            'SlurmSystem.resolve_slurm_options(), which returns a '
            'SlurmOptions object.',
            DeprecationWarning,
            stacklevel=2,
        )
        options = cls.resolve_slurm_options(
            config=config,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
        )
        return (
            options.partition,
            options.qos,
            options.constraint,
            options.gpus_per_node,
            options.max_wallclock,
            options.effective_nodes,
        )

    @property
    def placement_support(self) -> PlacementSupport:
        """
        The placement mechanism available on this machine.

        Slurm 20.11 and newer reserves what a job step asks for, so placement
        is scheduler enforced. Before that release, steps share a node and
        the only mechanism is an explicit CPU binding, which keeps concurrent
        launches on disjoint cores but does not reserve them.
        """
        version = get_slurm_version()
        if version is None:
            return PlacementSupport.NONE
        if version >= STEP_ISOLATION_VERSION:
            return PlacementSupport.SCHEDULER
        return PlacementSupport.CPU_BINDING

    @property
    def memory_cap_support(self) -> MemoryCapSupport:
        """
        Whether this machine will hold a launch to a memory cap.

        The Slurm version is what this is read from, since that is what was
        measured and it is what mache can ask the machine. It is a proxy:
        the enforcement itself comes from the site's cgroup configuration,
        so a site running a new Slurm with memory constraints turned off
        would be reported as enforcing when it does not.
        """
        version = get_slurm_version()
        if version is None or version < MEMORY_ENFORCEMENT_VERSION:
            return MemoryCapSupport.NONE
        return MemoryCapSupport.ENFORCED

    def _get_memory_args(self, memory_cap: int | None) -> List[str]:
        """Get the arguments that hold a launch to a memory cap."""
        if memory_cap is None:
            return []
        if self.memory_cap_support is not MemoryCapSupport.ENFORCED:
            # Chrysalis's Slurm accepts --mem on a step and does not act on
            # it. Rendering it there would put a figure on the command line
            # that nothing keeps, which reads to anyone who sees the command
            # as a safety net that is not there.
            return []
        # a per-node figure, which is what --mem means and what
        # memory_per_node is denominated in
        return [f'--mem={memory_cap}M']

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement | None = None,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        self._check_placement_supported(placement)

        # default=None so an absent option reaches the check below:
        # get_config_int defaults to 0, which would cap the launch at no
        # tasks at all instead of raising
        max_mpi_tasks_per_node = self.get_config_int(
            'max_mpi_tasks_per_node', default=None
        )
        if max_mpi_tasks_per_node is None:
            raise ValueError(
                'max_mpi_tasks_per_node must be set in the config for the '
                'slurm system.'
            )

        nodes = self.nodes
        if nodes is None:
            raise ValueError('Node count is not set for the slurm system.')

        if placement is not None and len(placement.nodes) > 0:
            available_nodes = len(placement.nodes)
            launch_nodes = available_nodes
        else:
            available_nodes = nodes
            launch_nodes = _ceil_division(ntasks, max_mpi_tasks_per_node)

        tasks_per_node = _ceil_division(ntasks, available_nodes)
        if tasks_per_node > max_mpi_tasks_per_node:
            raise ValueError(
                f'Calculated tasks_per_node ({tasks_per_node}) exceeds the '
                f'max_mpi_tasks_per_node ({max_mpi_tasks_per_node}).  You '
                f'likely need to allocate more nodes.'
            )

        parallel_args = [
            '-c',
            f'{cpus_per_task}',
            '-N',
            f'{launch_nodes}',
            '-n',
            f'{ntasks}',
        ]

        if placement is not None:
            parallel_args = self._add_placement_args(
                parallel_args, cpus_per_task, ntasks, placement
            )
        elif gpus_per_task > 0:
            gpus_per_task_flag = self.get_config('gpus_per_task_flag')
            if gpus_per_task_flag is None:
                gpus_per_task_flag = '--gpus-per-task'
            parallel_args.extend([gpus_per_task_flag, f'{gpus_per_task}'])

        parallel_args.extend(self._get_binding_args(placement))

        if placement is not None:
            # a placement already says which nodes and how many cores a
            # launch gets, so the machine's way of spreading a launch over a
            # whole node has nothing left to decide and could only contradict
            # it
            return parallel_args

        distribution = self.get_config('distribution')
        if distribution is not None and distribution != '':
            parallel_args.extend(['-m', distribution])
            return parallel_args

        # the legacy `placement` config option, which is the srun task
        # distribution and is unrelated to the `placement` argument above
        distribution_type = self.get_config('placement')
        if distribution_type is not None and distribution_type != '':
            parallel_args.extend(
                ['-m', f'{distribution_type}={max_mpi_tasks_per_node}']
            )
        return parallel_args

    def _add_placement_args(
        self,
        parallel_args: List[str],
        cpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement,
    ) -> List[str]:
        """Add the arguments that confine a launch to a placement."""
        if len(placement.nodes) > 0:
            parallel_args.extend(['-w', ','.join(placement.nodes)])

        chunks = split_cores(placement, ntasks, cpus_per_task)

        if self.placement_support is PlacementSupport.CPU_BINDING:
            if placement.gpus > 0:
                version = get_slurm_version()
                if version is None:
                    running = 'unknown'
                else:
                    running = f'{version[0]}.{version[1]}'
                raise ValueError(
                    f'This machine runs Slurm {running}, which has no way to '
                    f"give a job step a share of the node's GPUs. Placing "
                    f'GPUs needs Slurm {STEP_ISOLATION_VERSION[0]}.'
                    f'{STEP_ISOLATION_VERSION[1]} or newer.'
                )
            # Before 20.11 steps share a node's cores by default and --exact
            # does not exist, so the cores a launch may use have to be named
            # one mask per task.
            masks = ','.join(cpu_mask(chunk) for chunk in chunks)
            parallel_args.append(f'--cpu-bind=mask_cpu:{masks}')
            return parallel_args

        # 20.11 and newer: ask for exactly what this launch needs instead of
        # inheriting the job's resources, and let Slurm choose which cores
        # satisfy the count.
        parallel_args.append('--exact')
        if placement.gpus > 0:
            # a total for the launch, not a count per task: a per-task count
            # was measured not to confine a launch on either GPU machine
            parallel_args.append(f'--gpus={placement.gpus}')
        else:
            # saying nothing about GPUs is read as claiming every one on the
            # node, which is what serializes concurrent launches there
            parallel_args.append('--gres=none')
        return parallel_args

    def _get_binding_args(
        self, placement: ResourcePlacement | None
    ) -> List[str]:
        """Get the binding arguments the machine's config asks for."""
        binding_args = []
        for option in BINDING_OPTIONS:
            value = self.get_config(option)
            if value is None or value == '':
                continue
            if placement is not None and not self._keeps_binding(
                option, value, placement
            ):
                continue
            flag = f'--{option.replace("_", "-")}'
            binding_args.append(f'{flag}={value}')
        return binding_args

    def _keeps_binding(
        self, option: str, value: str, placement: ResourcePlacement
    ) -> bool:
        """
        Check whether a config binding survives alongside a placement.

        A binding policy such as ``cores`` or ``closest`` still applies
        within whatever the placement gave the launch. One that names
        specific cores or devices does not, because the placement is now the
        authority on which resources the launch has. Nor does a ``gpu_bind``
        of ``none``, which asks for no binding at all.
        """
        if names_resources(value):
            return False
        if option == 'cpu_bind':
            # on pre-20.11 Slurm the placement renders its own cpu binding
            return self.placement_support is not PlacementSupport.CPU_BINDING
        if option == 'gpu_bind':
            if placement.gpus == 0:
                # binding tasks to GPUs contradicts having asked for none
                return False
            # A `gpu_bind` of `none` asks Slurm not to bind tasks to GPUs,
            # which is what it does anyway without the option, so dropping
            # it takes nothing away.  Keeping it alongside an explicit
            # --gpus=N appears to cost something: of four concurrent placed
            # launches on Perlmutter GPU asking for one GPU each, one was
            # given a GPU and the other three got none, ran anyway and
            # exited 0.  Frontier, whose `gpu_bind` is `closest`, gave all
            # four disjoint GPUs from a nearly identical command.  That
            # `none` is what suppressed the assignment rather than merely
            # the binding is a hypothesis, still to be confirmed by a rerun
            # on Perlmutter GPU with the option gone.
            return value.strip() != 'none'
        return True
