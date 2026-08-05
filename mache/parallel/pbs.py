import os
import re
import subprocess
import warnings
from configparser import ConfigParser
from dataclasses import dataclass
from typing import List

from mache.parallel.system import (
    ParallelSystem,
    _ceil_division,
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
        Whether the requested queue was used. ``True`` when no queue was
        requested.

    reason : str or None
        A human-readable explanation of why a requested queue could not be
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
        if (
            gpus_per_node is not None
            and gpus_per_node != ''
            and gpus_per_node != '0'
        ):
            self.gpus_per_node = gpus_per_node
            self.gpus = gpus_per_node * nodes

    @classmethod
    def resolve_pbs_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
        queue: str | None = None,
        desired_wall_time: str | None = None,
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

        desired_wall_time : str, optional
            The wall time (``HH:MM:SS``) the caller intends to request. A
            requested queue that does not allow it is not honored, and the
            returned ``wall_time`` is capped at ``max_wallclock``.

        Returns
        -------
        PbsOptions
            The resolved PBS submission options.
        """
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

        constraint, gpus_per_node, filesystems = (
            cls._get_common_submission_options(config)
        )
        max_wallclock = cls._get_max_wallclock(
            config, 'queue', queue_name, effective_nodes
        )

        wall_time = ''
        if desired_wall_time is not None:
            wall_time = cap_wall_time(desired_wall_time, max_wallclock)

        return PbsOptions(
            queue=queue_name,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            max_wallclock=max_wallclock,
            filesystems=filesystems,
            effective_nodes=effective_nodes,
            wall_time=wall_time,
            honored=queue_resolution.honored,
            reason=queue_resolution.reason,
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

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
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
        tasks_per_node = _ceil_division(ntasks, nodes)
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
        if (
            gpus_per_task > 0
            and gpus_per_task_flag is not None
            and gpus_per_task_flag != ''
        ):
            parallel_args.extend([gpus_per_task_flag, f'{gpus_per_task}'])

        flags = {
            'cpu_bind': '--cpu-bind',
            'gpu_bind': '--gpu-bind',
            'mem_bind': '--mem-bind',
        }
        for option, flag in flags.items():
            value = self.get_config(option)
            if value is not None and value != '':
                parallel_args.extend([flag, value])
        return parallel_args

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
