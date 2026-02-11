import os
from configparser import ConfigParser

from mache.parallel.login import LoginSystem
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem

JOB_ENV_VARS = {
    'slurm': 'SLURM_JOB_ID',
    'pbs': 'PBS_JOBID',
}


def get_parallel_system(config: ConfigParser) -> ParallelSystem:
    system = config.get('parallel', 'system')
    for system_name, env_var in JOB_ENV_VARS.items():
        if system == system_name and env_var not in os.environ:
            system = 'login'
            break

    if system == 'slurm':
        return SlurmSystem(config)
    elif system == 'pbs':
        return PbsSystem(config)
    elif system == 'single_node':
        return SingleNodeSystem(config)
    elif system == 'login':
        return LoginSystem(config)
    else:
        raise ValueError(f'Unexpected parallel system: {system}')
