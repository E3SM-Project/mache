import os
from configparser import ConfigParser
from typing import List

from mache.parallel.system import (
    ParallelSystem,
    _ceil_division,
    _get_subprocess_int,
)


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
    def get_slurm_options(
        cls,
        config: ConfigParser,
        nodes: int,
        min_nodes_allowed: int | None = None,
    ) -> tuple[str, str, str, str, str, int]:
        """Get Slurm submission options for a requested node count."""
        partition_resolution = cls.resolve_submission(
            config=config,
            nodes=nodes,
            target_type='partition',
            min_nodes_allowed=min_nodes_allowed,
        )
        partition = partition_resolution.target
        effective_nodes = partition_resolution.effective_nodes

        qos_resolution = cls.resolve_submission(
            config=config,
            nodes=effective_nodes,
            target_type='qos',
            min_nodes_allowed=min_nodes_allowed,
        )
        qos = qos_resolution.target

        constraint, gpus_per_node, _ = cls._get_common_submission_options(
            config
        )

        max_wallclock = cls._select_max_wallclock(
            cls._get_max_wallclock(config, 'partition', partition),
            cls._get_max_wallclock(config, 'qos', qos),
        )

        return (
            partition,
            qos,
            constraint,
            gpus_per_node,
            max_wallclock,
            effective_nodes,
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

        parallel_args = [
            '-c',
            f'{cpus_per_task}',
            '-N',
            f'{nodes}',
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

        placement = self.get_config('placement')
        if placement is not None and placement != '':
            parallel_args.extend(
                ['-m', f'{placement}={max_mpi_tasks_per_node}']
            )
        return parallel_args
