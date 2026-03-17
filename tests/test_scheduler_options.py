from mache import MachineInfo
from mache.parallel.pbs import PbsSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem


def test_get_scheduler_target_aurora_gap_errors():
    config = MachineInfo(machine='aurora').config
    resolution = ParallelSystem.resolve_submission(
        config=config, target_type='queue', nodes=200
    )

    assert resolution.target == 'capacity'
    assert resolution.effective_nodes == 16
    assert resolution.adjustment == 'decrease'


def test_resolve_submission_aurora_gap_with_min_nodes_allowed():
    config = MachineInfo(machine='aurora').config
    resolution = ParallelSystem.resolve_submission(
        config=config,
        target_type='queue',
        nodes=200,
        min_nodes_allowed=32,
    )

    assert resolution.target == 'prod'
    assert resolution.effective_nodes == 256
    assert resolution.adjustment == 'increase'


def test_get_pbs_options_aurora_capacity():
    config = MachineInfo(machine='aurora').config
    (
        queue,
        constraint,
        gpus_per_node,
        max_wallclock,
        filesystems,
        effective_nodes,
    ) = PbsSystem.get_pbs_options(config=config, nodes=8)

    assert queue == 'capacity'
    assert constraint == ''
    assert gpus_per_node == ''
    assert max_wallclock == '168:00:00'
    assert filesystems == 'home:flare'
    assert effective_nodes == 8


def test_get_pbs_options_aurora_prod():
    config = MachineInfo(machine='aurora').config
    (
        queue,
        constraint,
        gpus_per_node,
        max_wallclock,
        filesystems,
        effective_nodes,
    ) = PbsSystem.get_pbs_options(config=config, nodes=256)

    assert queue == 'prod'
    assert constraint == ''
    assert gpus_per_node == ''
    assert max_wallclock == '12:00:00'
    assert filesystems == 'home:flare'
    assert effective_nodes == 256


def test_get_pbs_options_aurora_adjusted_nodes():
    config = MachineInfo(machine='aurora').config
    (
        queue,
        _,
        _,
        max_wallclock,
        _,
        effective_nodes,
    ) = PbsSystem.get_pbs_options(config=config, nodes=200)

    assert queue == 'capacity'
    assert effective_nodes == 16
    assert max_wallclock == '168:00:00'


def test_get_slurm_options_compy():
    config = MachineInfo(machine='compy').config
    (
        partition,
        qos,
        constraint,
        gpus_per_node,
        max_wallclock,
        effective_nodes,
    ) = SlurmSystem.get_slurm_options(config=config, nodes=20)

    assert partition == 'slurm'
    assert qos == 'regular'
    assert constraint == ''
    assert gpus_per_node == ''
    assert max_wallclock == '36:00:00'
    assert effective_nodes == 20


def test_get_slurm_options_pm_gpu_uses_more_restrictive_qos_walltime():
    config = MachineInfo(machine='pm-gpu').config
    (
        partition,
        qos,
        constraint,
        gpus_per_node,
        max_wallclock,
        effective_nodes,
    ) = SlurmSystem.get_slurm_options(config=config, nodes=8)

    assert partition == ''
    assert qos == 'regular'
    assert constraint == 'gpu'
    assert gpus_per_node == '4'
    assert max_wallclock == '48:00:00'
    assert effective_nodes == 8
