import os
import warnings
from configparser import ConfigParser

from mache.parallel.login import LoginSystem
from mache.parallel.memory import (
    MemoryCapSupport as MemoryCapSupport,
)
from mache.parallel.pbs import PbsSystem
from mache.parallel.placement import (
    PlacementSupport as PlacementSupport,
)
from mache.parallel.placement import (
    ResourcePlacement as ResourcePlacement,
)
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import (
    LIVE_JOB_STATES,
    SlurmSystem,
    get_slurm_job_state,
    running_on_allocated_node,
)
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

    # SLURM_JOB_ID only says a job id was handed out at some point. salloc
    # does not kill its shell when the allocation ends, so that shell keeps
    # the variable and goes on claiming an allocation it no longer has.
    #
    # Running on one of the allocation's own nodes settles that locally and
    # for free, since Slurm kills a job's processes before it releases its
    # nodes. That covers a batch job, which is what a caller running a
    # process per unit of work is. Anything else -- a login shell that
    # still carries the variable, which is the case this check was added
    # for -- only the scheduler can settle, so it is asked.
    if (
        system == 'slurm'
        and not running_on_allocated_node()
        and not _slurm_job_is_active(os.environ['SLURM_JOB_ID'])
    ):
        system = 'login'

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


def _slurm_job_is_active(job_id: str) -> bool:
    """Whether the job still holds an allocation, warning if it does not."""
    state = get_slurm_job_state(job_id)
    if state in LIVE_JOB_STATES:
        return True

    if state is None:
        detail = 'the scheduler has no record of that job'
    else:
        detail = f'that job is {state}'
    warnings.warn(
        f'SLURM_JOB_ID={job_id} is set but {detail}. This shell has '
        f'outlived its allocation, so mache is falling back to the login '
        f'system. Start a new allocation, or unset SLURM_JOB_ID to '
        f'silence this warning.',
        stacklevel=3,
    )
    return False
