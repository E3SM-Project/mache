import os
import warnings
from configparser import ConfigParser
from dataclasses import dataclass
from typing import List

from mache.parallel.system import (
    ParallelSystem,
    _ceil_division,
    _combine_reasons,
    _get_subprocess_int,
    cap_wall_time,
)


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
        Whether the requested partition and QOS were both used. ``True``
        when neither was requested.

    reason : str or None
        A human-readable explanation of why a requested partition or QOS
        could not be honored, suitable for printing verbatim. ``None`` when
        ``honored`` is ``True``.
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
        cores_per_node = self.get_config_int('cores_per_node')
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
        self.gpus_per_node = self.get_config_int('gpus_per_node')
        if self.gpus_per_node is not None:
            self.gpus = self.gpus_per_node * nodes

    @classmethod
    def resolve_slurm_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
        partition: str | None = None,
        qos: str | None = None,
        desired_wall_time: str | None = None,
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

        desired_wall_time : str, optional
            The wall time (``HH:MM:SS``) the caller intends to request. A
            requested target that does not allow it is not honored, and the
            returned ``wall_time`` is capped at ``max_wallclock``.

        Returns
        -------
        SlurmOptions
            The resolved Slurm submission options.
        """
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

        constraint, gpus_per_node, _ = cls._get_common_submission_options(
            config
        )

        max_wallclock = cls._select_max_wallclock(
            cls._get_max_wallclock(config, 'partition', partition_name),
            cls._get_max_wallclock(config, 'qos', qos_name),
        )

        wall_time = ''
        if desired_wall_time is not None:
            wall_time = cap_wall_time(desired_wall_time, max_wallclock)

        return SlurmOptions(
            partition=partition_name,
            qos=qos_name,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            max_wallclock=max_wallclock,
            effective_nodes=effective_nodes,
            wall_time=wall_time,
            honored=(partition_resolution.honored and qos_resolution.honored),
            reason=_combine_reasons(
                partition_resolution.reason, qos_resolution.reason
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

    def _get_parallel_args(
        self,
        cpus_per_task: int,
        gpus_per_task: int,
        ntasks: int,
    ) -> List[str]:
        """Get the parallel command-line arguments related to resources."""
        max_mpi_tasks_per_node = self.get_config_int('max_mpi_tasks_per_node')
        if max_mpi_tasks_per_node is None:
            raise ValueError(
                'max_mpi_tasks_per_node must be set in the config for the '
                'slurm system.'
            )

        nodes = self.nodes
        if nodes is None:
            raise ValueError('Node count is not set for the slurm system.')

        tasks_per_node = _ceil_division(ntasks, nodes)
        if tasks_per_node > max_mpi_tasks_per_node:
            raise ValueError(
                f'Calculated tasks_per_node ({tasks_per_node}) exceeds the '
                f'max_mpi_tasks_per_node ({max_mpi_tasks_per_node}).  You '
                f'likely need to allocate more nodes.'
            )
        launch_nodes = _ceil_division(ntasks, max_mpi_tasks_per_node)

        parallel_args = [
            '-c',
            f'{cpus_per_task}',
            '-N',
            f'{launch_nodes}',
            '-n',
            f'{ntasks}',
        ]
        if gpus_per_task > 0:
            gpus_per_task_flag = self.get_config('gpus_per_task_flag')
            if gpus_per_task_flag is None:
                gpus_per_task_flag = '--gpus-per-task'
            parallel_args.extend([gpus_per_task_flag, f'{gpus_per_task}'])

        flags = {
            'cpu_bind': '--cpu-bind',
            'gpu_bind': '--gpu-bind',
            'mem_bind': '--mem-bind',
        }
        for option, flag in flags.items():
            value = self.get_config(option)
            if value is not None and value != '':
                parallel_args.append(f'{flag}={value}')

        distribution = self.get_config('distribution')
        if distribution is not None and distribution != '':
            parallel_args.extend(['-m', distribution])
            return parallel_args

        placement = self.get_config('placement')
        if placement is not None and placement != '':
            parallel_args.extend(
                ['-m', f'{placement}={max_mpi_tasks_per_node}']
            )
        return parallel_args
