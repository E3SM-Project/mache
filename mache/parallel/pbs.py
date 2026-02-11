import os
import re
import subprocess
from configparser import ConfigParser
from typing import List

from mache.parallel.system import ParallelSystem, _ceil_division


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

        nodes = self.nodes
        if nodes is None:
            raise ValueError('Node count is not set for the pbs system.')

        tasks_per_node = _ceil_division(ntasks, nodes)
        max_mpi_tasks_per_node = self.get_config_int('max_mpi_tasks_per_node')
        if max_mpi_tasks_per_node is None:
            raise ValueError(
                'max_mpi_tasks_per_node must be set in the config for the pbs '
                'system.'
            )
        if tasks_per_node > max_mpi_tasks_per_node:
            raise ValueError(
                f'Calculated tasks_per_node ({tasks_per_node}) exceeds the '
                f'max_mpi_tasks_per_node ({max_mpi_tasks_per_node}).  You '
                f'likely need to allocate more nodes.'
            )

        parallel_args = [
            '-n',
            f'{ntasks}',
            '--ppn',
            f'{tasks_per_node}',
            cpus_per_task_flag,
            f'{cpus_per_task}',
        ]
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
