import pytest

from mache import MachineInfo
from mache.parallel.pbs import PbsSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem, cap_wall_time


def test_get_scheduler_target_aurora_gap_errors():
    config = MachineInfo(machine='aurora').config
    resolution = ParallelSystem.resolve_submission(
        config=config, target_type='queue', nodes=200
    )

    assert resolution.target == 'capacity'
    assert resolution.effective_nodes == 16
    assert resolution.adjustment == 'decrease'
    assert resolution.honored
    assert resolution.reason is None


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
    options = PbsSystem.resolve_pbs_options(config=config, nodes=8)

    assert options.queue == 'capacity'
    assert options.constraint == ''
    assert options.gpus_per_node == ''
    assert options.max_wallclock == '168:00:00'
    assert options.filesystems == 'home:flare'
    assert options.effective_nodes == 8
    assert options.wall_time == ''
    assert options.honored
    assert options.reason is None


def test_get_pbs_options_aurora_prod():
    config = MachineInfo(machine='aurora').config
    options = PbsSystem.resolve_pbs_options(config=config, nodes=256)

    assert options.queue == 'prod'
    assert options.constraint == ''
    assert options.gpus_per_node == ''
    assert options.max_wallclock == '12:00:00'
    assert options.filesystems == 'home:flare'
    assert options.effective_nodes == 256


def test_get_pbs_options_aurora_adjusted_nodes():
    config = MachineInfo(machine='aurora').config
    options = PbsSystem.resolve_pbs_options(config=config, nodes=200)

    assert options.queue == 'capacity'
    assert options.effective_nodes == 16
    assert options.max_wallclock == '168:00:00'


def test_get_slurm_options_compy():
    config = MachineInfo(machine='compy').config
    options = SlurmSystem.resolve_slurm_options(config=config, nodes=20)

    assert options.partition == 'slurm'
    assert options.qos == 'regular'
    assert options.constraint == ''
    assert options.gpus_per_node == ''
    assert options.max_wallclock == '36:00:00'
    assert options.effective_nodes == 20
    assert options.wall_time == ''
    assert options.honored
    assert options.reason is None


def test_get_slurm_options_pm_gpu_uses_more_restrictive_qos_walltime():
    config = MachineInfo(machine='pm-gpu').config
    options = SlurmSystem.resolve_slurm_options(config=config, nodes=8)

    assert options.partition == ''
    assert options.qos == 'regular'
    assert options.constraint == 'gpu'
    assert options.gpus_per_node == '4'
    assert options.max_wallclock == '48:00:00'
    assert options.effective_nodes == 8


def test_deprecated_get_slurm_options_matches_resolve():
    config = MachineInfo(machine='compy').config
    with pytest.warns(DeprecationWarning):
        options_tuple = SlurmSystem.get_slurm_options(config=config, nodes=20)

    options = SlurmSystem.resolve_slurm_options(config=config, nodes=20)

    assert options_tuple == (
        options.partition,
        options.qos,
        options.constraint,
        options.gpus_per_node,
        options.max_wallclock,
        options.effective_nodes,
    )
    assert options_tuple == ('slurm', 'regular', '', '', '36:00:00', 20)


def test_deprecated_get_pbs_options_matches_resolve():
    config = MachineInfo(machine='aurora').config
    with pytest.warns(DeprecationWarning):
        options_tuple = PbsSystem.get_pbs_options(config=config, nodes=8)

    options = PbsSystem.resolve_pbs_options(config=config, nodes=8)

    assert options_tuple == (
        options.queue,
        options.constraint,
        options.gpus_per_node,
        options.max_wallclock,
        options.filesystems,
        options.effective_nodes,
    )
    assert options_tuple == (
        'capacity',
        '',
        '',
        '168:00:00',
        'home:flare',
        8,
    )


def test_requested_qos_honored_pm_cpu():
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=4,
        qos='debug',
        desired_wall_time='00:20:00',
    )

    assert options.qos == 'debug'
    assert options.max_wallclock == '00:30:00'
    assert options.wall_time == '00:20:00'
    assert options.effective_nodes == 4
    assert options.honored
    assert options.reason is None


def test_requested_qos_wall_time_too_long_pm_cpu():
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=4,
        qos='debug',
        desired_wall_time='02:00:00',
    )

    assert options.qos == 'regular'
    assert options.wall_time == '02:00:00'
    assert not options.honored
    assert options.reason is not None
    assert 'wall clock' in options.reason
    assert '00:30:00' in options.reason
    assert '02:00:00' in options.reason


def test_requested_qos_not_available_pm_cpu():
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, qos='nonexistent'
    )

    assert options.qos == 'regular'
    assert not options.honored
    assert options.reason is not None
    assert 'not an available qos' in options.reason


def test_requested_qos_honored_with_adjusted_nodes_pm_cpu():
    config = MachineInfo(machine='pm-cpu').config
    resolution = ParallelSystem.resolve_submission(
        config=config, nodes=16, target_type='qos', requested='debug'
    )

    assert resolution.target == 'debug'
    assert resolution.effective_nodes == 8
    assert resolution.adjustment == 'decrease'
    assert resolution.honored

    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=16, qos='debug'
    )

    assert options.qos == 'debug'
    assert options.effective_nodes == 8
    assert options.honored


def test_requested_qos_below_min_nodes_allowed_pm_cpu():
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=16, qos='debug', min_nodes_allowed=16
    )

    assert options.qos == 'regular'
    assert options.effective_nodes == 16
    assert not options.honored
    assert options.reason is not None
    assert '16' in options.reason
    assert 'at least' in options.reason


@pytest.mark.parametrize('requested', [None, '', '   ', '<<<default>>>'])
def test_requested_qos_placeholders_mean_no_request(requested):
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, qos=requested
    )

    assert options.qos == 'regular'
    assert options.honored
    assert options.reason is None


def test_requested_queue_honored_aurora():
    config = MachineInfo(machine='aurora').config
    options = PbsSystem.resolve_pbs_options(
        config=config,
        nodes=2,
        queue='debug',
        desired_wall_time='00:30:00',
    )

    assert options.queue == 'debug'
    assert options.max_wallclock == '01:00:00'
    assert options.wall_time == '00:30:00'
    assert options.honored


def test_requested_queue_wall_time_too_long_aurora():
    config = MachineInfo(machine='aurora').config
    options = PbsSystem.resolve_pbs_options(
        config=config,
        nodes=2,
        queue='debug',
        desired_wall_time='02:00:00',
    )

    assert options.queue == 'capacity'
    assert options.wall_time == '02:00:00'
    assert not options.honored
    assert options.reason is not None
    assert '01:00:00' in options.reason


def test_requested_partition_honored_chrysalis():
    config = MachineInfo(machine='chrysalis').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, partition='debug'
    )

    assert options.partition == 'debug'
    assert options.effective_nodes == 4
    assert options.honored


def test_requested_target_on_machine_without_targets():
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, partition='debug'
    )

    assert options.partition == ''
    assert not options.honored
    assert options.reason is not None
    assert 'no partitions' in options.reason


def test_resolve_submission_still_raises_when_infeasible():
    config = MachineInfo(machine='aurora').config
    with pytest.raises(ValueError, match='No queue matches'):
        ParallelSystem.resolve_submission(
            config=config,
            target_type='queue',
            nodes=8,
            min_nodes_allowed=1024,
        )


@pytest.mark.parametrize(
    'desired, max_wallclock, expected',
    [
        ('00:20:00', '00:30:00', '00:20:00'),
        ('02:00:00', '00:30:00', '00:30:00'),
        ('00:30:00', '00:30:00', '00:30:00'),
        ('02:00:00', '', '02:00:00'),
        ('', '00:30:00', ''),
        ('bogus', '00:30:00', 'bogus'),
        ('02:00:00', 'bogus', '02:00:00'),
        ('1-00:00:00', '12:00:00', '1-00:00:00'),
    ],
)
def test_cap_wall_time(desired, max_wallclock, expected):
    assert cap_wall_time(desired, max_wallclock) == expected
