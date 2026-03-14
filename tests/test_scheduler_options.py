import pytest

from mache import MachineInfo
from mache.parallel.pbs import PbsSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem


def test_get_scheduler_target_aurora_gap_errors():
    config = MachineInfo(machine='aurora').config
    with pytest.raises(ValueError, match='No queue matches nodes=200'):
        ParallelSystem.get_scheduler_target(
            config=config, target_type='queue', nodes=200
        )


def test_get_pbs_options_aurora_capacity():
    config = MachineInfo(machine='aurora').config
    queue, constraint, gpus_per_node, wall_time, filesystems = (
        PbsSystem.get_pbs_options(config=config, nodes=8)
    )

    assert queue == 'capacity'
    assert constraint == ''
    assert gpus_per_node == ''
    assert wall_time == '168:00:00'
    assert filesystems == ''


def test_get_pbs_options_aurora_prod():
    config = MachineInfo(machine='aurora').config
    queue, constraint, gpus_per_node, wall_time, filesystems = (
        PbsSystem.get_pbs_options(config=config, nodes=256)
    )

    assert queue == 'prod'
    assert constraint == ''
    assert gpus_per_node == ''
    assert wall_time == '12:00:00'
    assert filesystems == ''


def test_get_slurm_options_compy():
    config = MachineInfo(machine='compy').config
    partition, qos, constraint, gpus_per_node, wall_time = (
        SlurmSystem.get_slurm_options(config=config, nodes=20)
    )

    assert partition == 'slurm'
    assert qos == 'regular'
    assert constraint == ''
    assert gpus_per_node == ''
    assert wall_time == '36:00:00'


def test_get_slurm_options_pm_gpu_uses_more_restrictive_qos_walltime():
    config = MachineInfo(machine='pm-gpu').config
    partition, qos, constraint, gpus_per_node, wall_time = (
        SlurmSystem.get_slurm_options(config=config, nodes=8)
    )

    assert partition == ''
    assert qos == 'regular'
    assert constraint == 'gpu'
    assert gpus_per_node == '4'
    assert wall_time == '48:00:00'
