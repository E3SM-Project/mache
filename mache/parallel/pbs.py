import functools
import os
import re
import subprocess
import warnings
from configparser import ConfigParser
from dataclasses import dataclass
from typing import List

from mache.parallel.placement import (
    BINDING_OPTIONS,
    PlacementSupport,
    ResourcePlacement,
    names_resources,
    split_cores,
)
from mache.parallel.system import (
    ParallelSystem,
    _ceil_division,
    _combine_reasons,
    _get_subprocess_str,
    _normalize_requested,
    cap_wall_time,
)


@dataclass(frozen=True)
class PbsOptions:
    """
    PBS submission options resolved from a machine's config.

    Attributes
    ----------
    queue : str
        The PBS queue, or an empty string if the machine defines none.

    constraint : str
        The constraint, or an empty string if the machine defines none.

    gpus_per_node : str
        The number of GPUs per node, or an empty string if not configured.

    max_wallclock : str
        The maximum wall clock (``HH:MM:SS``) of the selected queue, or an
        empty string if the queue does not set one.

    filesystems : str
        The filesystems used for batch jobs, or an empty string if not
        configured.

    effective_nodes : int
        The node count after clamping to the selected queue's limits.

    wall_time : str
        The requested wall time capped at ``max_wallclock``, or an empty
        string if no wall time was requested.

    honored : bool
        Whether every requested target -- queue, constraint and
        ``scheduler_target`` -- was used. ``True`` when none was requested.

    reason : str or None
        A human-readable explanation of why a requested target could not be
        honored, suitable for printing verbatim. ``None`` when ``honored``
        is ``True``.
    """

    queue: str
    constraint: str
    gpus_per_node: str
    max_wallclock: str
    filesystems: str
    effective_nodes: int
    wall_time: str = ''
    honored: bool = True
    reason: str | None = None


@functools.cache
def is_pals_launcher(executable: str) -> bool:
    """
    Check whether a launcher is PALS, which can place concurrent launches.

    PALS is the only PBS launcher mache has a placement mechanism for, and
    the other launchers on PBS machines -- Open MPI's ``mpirun`` on Improv,
    for example -- take none of its options. The launcher is asked directly
    rather than trusting the machine's config, since a site can change it
    without its mache config changing.

    Parameters
    ----------
    executable : str
        The launcher to ask, which is the first word of the machine's
        ``parallel_executable``.

    Returns
    -------
    is_pals : bool
        Whether the launcher identified itself as PALS.
    """
    try:
        output = _get_subprocess_str([executable, '--version'])
    except (OSError, subprocess.SubprocessError):
        return False

    # PALS reports e.g. "mpiexec version 1.8.0 revision ...", where Hydra
    # reports "HYDRA build details:" and Open MPI reports "mpiexec (OpenRTE)"
    return re.match(r'mpiexec version \d', output.strip()) is not None


class PbsSystem(ParallelSystem):
    """PBS resource manager for parallel jobs."""

    def __init__(self, config: ConfigParser):
        super().__init__(config)
        if 'PBS_JOBID' not in os.environ:
            raise RuntimeError(
                'PBS_JOBID environment variable not found but system is set '
                'to "pbs".'
            )

        cores_per_node = self.get_config_int('cores_per_node')
        if cores_per_node is None:
            raise ValueError(
                'cores_per_node must be set in the config for the pbs system.'
            )

        # First, try to get nodes and cores_per_node from qstat
        nodes = self._get_node_count_from_qstat()

        self.cores = nodes * cores_per_node
        self.cores_per_node = cores_per_node
        self.nodes = nodes
        self.mpi_allowed = True

        gpus_per_node = self.get_config_int('gpus_per_node')
        if gpus_per_node is not None:
            self.gpus_per_node = gpus_per_node
            self.gpus = gpus_per_node * nodes

    @classmethod
    def resolve_pbs_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
        queue: str | None = None,
        constraint: str | None = None,
        desired_wall_time: str | None = None,
        scheduler_target: str | None = None,
    ) -> PbsOptions:
        """
        Get PBS submission options for a requested node count.

        A requested queue is honored when the machine's metadata allows it;
        otherwise the default queue is used and the returned options explain
        why.

        Parameters
        ----------
        config : ConfigParser
            Machine configuration parser.

        nodes : int
            Requested node count.

        min_nodes_allowed : int, optional
            Optional lower bound for adjusted node counts.

        queue : str, optional
            A specific queue the caller would like to use.

        constraint : str, optional
            A specific constraint the caller would like to use.

        desired_wall_time : str, optional
            The wall time (``HH:MM:SS``) the caller intends to request. A
            requested queue that does not allow it is not honored, and the
            returned ``wall_time`` is capped at ``max_wallclock``.

        scheduler_target : str, optional
            A target named without saying which axis it is on, for callers
            with one machine-independent intent such as "use the debug
            target". PBS machines schedule by queue, so it is used as the
            queue when this machine lists it as one. ``queue`` takes
            precedence.

        Returns
        -------
        PbsOptions
            The resolved PBS submission options.
        """
        target_type, target_reason = cls._find_scheduler_target(
            config, scheduler_target, ('queue',)
        )
        if target_type == 'queue' and _normalize_requested(queue) is None:
            queue = scheduler_target

        queue_resolution = cls.resolve_submission(
            config=config,
            nodes=nodes,
            target_type='queue',
            min_nodes_allowed=min_nodes_allowed,
            requested=queue,
            desired_wall_time=desired_wall_time,
        )
        queue_name = queue_resolution.target
        effective_nodes = queue_resolution.effective_nodes

        _, gpus_per_node, filesystems = cls._get_common_submission_options(
            config
        )
        constraint_name, constraint_reason = cls._resolve_constraint(
            config, constraint
        )
        max_wallclock = cls._get_max_wallclock(
            config, 'queue', queue_name, effective_nodes
        )

        wall_time = ''
        if desired_wall_time is not None:
            wall_time = cap_wall_time(desired_wall_time, max_wallclock)

        return PbsOptions(
            queue=queue_name,
            constraint=constraint_name,
            gpus_per_node=gpus_per_node,
            max_wallclock=max_wallclock,
            filesystems=filesystems,
            effective_nodes=effective_nodes,
            wall_time=wall_time,
            honored=(
                queue_resolution.honored
                and constraint_reason is None
                and target_reason is None
            ),
            reason=_combine_reasons(
                target_reason, queue_resolution.reason, constraint_reason
            ),
        )

    @classmethod
    def get_pbs_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
    ) -> tuple[str, str, str, str, str, int]:
        """
        Get PBS submission options for a requested node count.

        .. deprecated:: 3.11.0
            Use :py:meth:`resolve_pbs_options` instead, which returns a
            :py:class:`PbsOptions` object and supports requesting a specific
            queue.
        """
        warnings.warn(
            'PbsSystem.get_pbs_options() is deprecated and will be removed '
            'in a future release. Use PbsSystem.resolve_pbs_options(), '
            'which returns a PbsOptions object.',
            DeprecationWarning,
            stacklevel=2,
        )
        options = cls.resolve_pbs_options(
            config=config,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
        )
        return (
            options.queue,
            options.constraint,
            options.gpus_per_node,
            options.max_wallclock,
            options.filesystems,
            options.effective_nodes,
        )

    @property
    def placement_support(self) -> PlacementSupport:
        """
        The placement mechanism available on this machine.

        PALS supports concurrent launches within one PBS job and places them
        by naming hosts and CPU lists explicitly. That binds each task to
        given cores but does not reserve them from the batch system, so it is
        the weaker of the two mechanisms. Other PBS launchers have no
        placement mechanism at all.
        """
        parallel_executable = self.get_config('parallel_executable')
        if parallel_executable is None or parallel_executable.strip() == '':
            return PlacementSupport.NONE
        executable = parallel_executable.split(' ')[0]
        if is_pals_launcher(executable):
            return PlacementSupport.CPU_BINDING
        return PlacementSupport.NONE

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement | None = None,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        self._check_placement_supported(placement)

        # PBS mpiexec/mpirun options are launcher's responsibility, so the
        # flag used for CPUs per task is configurable per machine
        cpus_per_task_flag = self.get_config('cpus_per_task_flag')
        if cpus_per_task_flag is None:
            cpus_per_task_flag = '-c'

        gpus_per_task_flag = self.get_config('gpus_per_task_flag')

        nodes = self.nodes
        if nodes is None:
            raise ValueError('Node count is not set for the pbs system.')

        max_mpi_tasks_per_node = self.get_config_int('max_mpi_tasks_per_node')
        if max_mpi_tasks_per_node is None:
            raise ValueError(
                'max_mpi_tasks_per_node must be set in the config for the pbs '
                'system.'
            )

        if placement is not None and len(placement.nodes) > 0:
            available_nodes = len(placement.nodes)
        else:
            available_nodes = nodes

        tasks_per_node = _ceil_division(ntasks, available_nodes)
        if tasks_per_node > max_mpi_tasks_per_node:
            raise ValueError(
                f'Calculated tasks_per_node ({tasks_per_node}) exceeds the '
                f'max_mpi_tasks_per_node ({max_mpi_tasks_per_node}).  You '
                f'likely need to allocate more nodes.'
            )
        tasks_per_node = min(ntasks, max_mpi_tasks_per_node)

        parallel_args = [
            '-n',
            f'{ntasks}',
            '--ppn',
            f'{tasks_per_node}',
            cpus_per_task_flag,
            f'{cpus_per_task}',
        ]

        if placement is not None:
            parallel_args.extend(
                self._get_placement_args(cpus_per_task, ntasks, placement)
            )
        elif (
            gpus_per_task > 0
            and gpus_per_task_flag is not None
            and gpus_per_task_flag != ''
        ):
            parallel_args.extend([gpus_per_task_flag, f'{gpus_per_task}'])

        for option in BINDING_OPTIONS:
            value = self.get_config(option)
            if value is None or value == '':
                continue
            if placement is not None and (
                names_resources(value) or option in ('cpu_bind', 'gpu_bind')
            ):
                # the placement is the authority on which cores and devices
                # this launch gets: it renders its own --cpu-bind, sets GPU
                # visibility instead of binding it, and a whole-node binding
                # list would contradict it
                continue
            parallel_args.extend([f'--{option.replace("_", "-")}', value])
        return parallel_args

    def _get_placement_args(
        self,
        cpus_per_task: int,
        ntasks: int,
        placement: ResourcePlacement,
    ) -> List[str]:
        """Get the arguments that confine a launch to a placement."""
        placement_args = []
        if len(placement.nodes) > 0:
            placement_args.extend(['--hosts', ','.join(placement.nodes)])

        chunks = split_cores(placement, ntasks, cpus_per_task)
        core_list = ':'.join(
            ','.join(f'{core}' for core in chunk) for chunk in chunks
        )
        placement_args.extend(['--cpu-bind', f'list:{core_list}'])

        placement_args.extend(self._get_visible_devices_args(placement))
        return placement_args

    def _get_visible_devices_args(
        self, placement: ResourcePlacement
    ) -> List[str]:
        """
        Get the arguments that confine a launch to given GPUs.

        PALS does not reserve GPUs, so isolation is by the vendor's
        visible-device variable, which is the documented approach on these
        machines. It is set on the command line rather than exported, so that
        a value cannot leak from the parent into a later launch that meant to
        set its own, and removed first for the same reason.
        """
        variable = self.get_config('gpu_visible_devices_var')
        if variable is None or variable == '':
            if placement.gpus > 0:
                raise ValueError(
                    f'The placement asks for {placement.gpus} gpus but this '
                    f'machine does not set gpu_visible_devices_var, so mache '
                    f'has no way to confine a launch to some of its GPUs.'
                )
            return []

        if placement.gpus == 0:
            # An explicit "no GPUs".  Unlike --gres=none on Slurm, this is
            # not the thing that makes concurrency work here: PALS reserves
            # nothing, so a launch that says nothing about GPUs does not
            # block the next one.  It is belt and braces, and how much it
            # actually hides has not been measured.  An empty
            # CUDA_VISIBLE_DEVICES means "no devices", but an empty
            # ZE_AFFINITY_MASK may instead mean "no mask", which is every
            # tile.  Settling that takes two placed CPU-only launches on
            # Aurora reporting what Level Zero sees.
            value = ''
        else:
            if placement.gpu_ids is None:
                raise ValueError(
                    f'The placement asks for {placement.gpus} gpus but does '
                    f'not say which. This machine has no scheduler to assign '
                    f'them, so the caller -- which is the only thing that '
                    f'knows about every concurrent launch -- must set '
                    f'gpu_ids.'
                )
            devices = self._get_devices()
            for gpu_id in placement.gpu_ids:
                if gpu_id >= len(devices):
                    raise ValueError(
                        f'The placement asks for GPU {gpu_id} but this '
                        f'machine has {len(devices)} per node.'
                    )
            value = ','.join(devices[gpu_id] for gpu_id in placement.gpu_ids)

        return [f'--env-remove={variable}', f'--env={variable}={value}']

    def _get_devices(self) -> List[str]:
        """
        Get the node's GPUs, in order, as the vendor's variable names them.

        A machine whose devices are not simply numbered from zero -- Aurora
        addresses a tile as ``0.1`` -- already lists them in order in its
        ``gpu_bind`` binding list, so that is used when it is present.
        """
        gpu_bind = self.get_config('gpu_bind')
        if gpu_bind is not None and gpu_bind.startswith('list:'):
            return gpu_bind[len('list:') :].split(':')

        gpus_per_node = self.gpus_per_node
        if gpus_per_node is None:
            raise ValueError(
                'gpus_per_node must be set in the config to place GPUs on '
                'the pbs system.'
            )
        return [f'{index}' for index in range(gpus_per_node)]

    def _get_node_count_from_qstat(self):
        """Try to determine node count from qstat output."""

        jobid = os.environ.get('PBS_JOBID')
        if not jobid:
            raise RuntimeError(
                'PBS_JOBID environment variable not found but system is set '
                'to "pbs".'
            )

        output = subprocess.check_output(['qstat', '-f', jobid], text=True)

        # Try to infer nodes and cores_per_node from various Resource_List
        # fields. Different PBS installations format these differently.

        # Case 1: Aurora style (current ALCF Aurora machine): separate
        # ncpus and nodect, and select
        #   Resource_List.ncpus = total_cores_for_job
        #   Resource_List.nodect = number_of_nodes
        #   Resource_List.select = number_of_nodes (or chunks)
        nodect_match = re.search(r'Resource_List\.nodect\s*=\s*(\d+)', output)
        simple_select_match = re.search(
            r'Resource_List\.select\s*=\s*(\d+)', output
        )

        nodect = int(nodect_match.group(1)) if nodect_match else None
        simple_select = (
            int(simple_select_match.group(1)) if simple_select_match else None
        )

        if nodect is not None and nodect != 0:
            return nodect

        if simple_select is not None and simple_select != 0:
            return simple_select

        # Case 2: PBS Pro style "select=N:ncpus=M" on a single line
        select_match = re.search(
            r'Resource_List\.select\s*=\s*(\d+)[^\n]*?:ncpus=(\d+)',
            output,
        )
        if select_match:
            return int(select_match.group(1))

        # Case 3: older PBS/Torque style: "nodes=N:ppn=M"
        nodes_match = re.search(
            r'Resource_List\.nodes\s*=\s*(\d+)[^\n]*?:ppn=(\d+)',
            output,
        )
        if nodes_match:
            return int(nodes_match.group(1))

        raise RuntimeError(
            f'Unable to determine node count from qstat output: {output}'
        )
