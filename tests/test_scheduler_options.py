from configparser import ConfigParser

import pytest

from mache import MachineInfo
from mache.parallel.pbs import PbsSystem
from mache.parallel.slurm import SlurmSystem
from mache.parallel.system import ParallelSystem, cap_wall_time

BINNED_CONFIG = """
[parallel]
system = slurm
partitions = batch
qos = normal, debug

[partition.batch]
min_nodes = 1
max_nodes = 1000
max_wallclock_bins = 91: 02:00:00,
                     183: 06:00:00,
                     1000: 12:00:00

[qos.normal]
min_nodes = 1

[qos.debug]
min_nodes = 1
max_wallclock = 01:00:00
"""


def _config_from_string(text):
    config = ConfigParser()
    config.read_string(text)
    return config


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


def test_requested_constraint_honored_pm_gpu():
    config = MachineInfo(machine='pm-gpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, constraint='gpu'
    )

    assert options.constraint == 'gpu'
    assert options.honored
    assert options.reason is None


def test_requested_constraint_not_available_pm_gpu():
    config = MachineInfo(machine='pm-gpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, constraint='cpu'
    )

    assert options.constraint == 'gpu'
    assert not options.honored
    assert options.reason is not None
    assert 'not an available constraint' in options.reason
    assert 'available: gpu' in options.reason


@pytest.mark.parametrize('requested', [None, '', '   ', '<<<default>>>'])
def test_requested_constraint_placeholders_mean_no_request(requested):
    config = MachineInfo(machine='pm-cpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, constraint=requested
    )

    assert options.constraint == 'cpu'
    assert options.honored
    assert options.reason is None


def test_requested_constraint_on_machine_without_constraints():
    config = MachineInfo(machine='chrysalis').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=4, constraint='anything'
    )

    assert options.constraint == ''
    assert not options.honored
    assert options.reason is not None
    assert 'no constraints' in options.reason


def test_requested_constraint_pbs():
    config = MachineInfo(machine='aurora').config
    options = PbsSystem.resolve_pbs_options(
        config=config, nodes=8, constraint='anything'
    )

    assert options.queue == 'capacity'
    assert options.constraint == ''
    assert not options.honored
    assert options.reason is not None
    assert 'no constraints' in options.reason


def test_honored_constraint_with_unhonored_qos():
    config = MachineInfo(machine='pm-gpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, constraint='gpu', qos='nonexistent'
    )

    assert options.constraint == 'gpu'
    assert options.qos == 'regular'
    assert not options.honored
    assert options.reason is not None
    assert 'nonexistent' in options.reason


def test_unhonored_constraint_and_qos_report_both_reasons():
    config = MachineInfo(machine='pm-gpu').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, constraint='cpu', qos='nonexistent'
    )

    assert options.constraint == 'gpu'
    assert options.qos == 'regular'
    assert not options.honored
    assert options.reason is not None
    assert 'nonexistent' in options.reason
    assert 'not an available constraint' in options.reason


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


@pytest.mark.parametrize(
    'nodes, expected_wallclock',
    [
        (8, '02:00:00'),
        (100, '06:00:00'),
        (200, '12:00:00'),
        (1000, '12:00:00'),
    ],
)
def test_frontier_defaults(nodes, expected_wallclock):
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(config=config, nodes=nodes)

    assert options.partition == 'batch'
    assert options.qos == 'normal'
    assert options.max_wallclock == expected_wallclock
    assert options.effective_nodes == nodes
    assert options.honored
    assert options.reason is None


def test_frontier_debug_qos_honored():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=8,
        qos='debug',
        desired_wall_time='01:00:00',
    )

    assert options.partition == 'batch'
    assert options.qos == 'debug'
    assert options.max_wallclock == '02:00:00'
    assert options.wall_time == '01:00:00'
    assert options.honored


def test_frontier_debug_qos_wall_time_too_long():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=8,
        qos='debug',
        desired_wall_time='03:00:00',
    )

    assert options.qos == 'normal'
    assert not options.honored
    assert options.reason is not None
    assert '02:00:00' in options.reason


def test_frontier_debug_qos_binds_before_the_partition_bin():
    config = MachineInfo(machine='frontier').config
    # the batch bin allows 12 hours at 200 nodes, but debug allows only two
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=200,
        qos='debug',
        desired_wall_time='03:00:00',
    )

    assert options.qos == 'normal'
    assert options.max_wallclock == '12:00:00'
    assert not options.honored
    assert options.reason is not None
    assert '02:00:00' in options.reason


def test_frontier_extended_partition_honored():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=8,
        partition='extended',
        desired_wall_time='20:00:00',
    )

    assert options.partition == 'extended'
    assert options.max_wallclock == '24:00:00'
    assert options.wall_time == '20:00:00'
    assert options.honored


def test_frontier_extended_partition_clamps_nodes():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=100, partition='extended'
    )

    assert options.partition == 'extended'
    assert options.effective_nodes == 64
    assert options.honored

    resolution = ParallelSystem.resolve_submission(
        config=config,
        nodes=100,
        target_type='partition',
        requested='extended',
    )
    assert resolution.adjustment == 'decrease'


def test_frontier_extended_partition_below_min_nodes_allowed():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=100,
        partition='extended',
        min_nodes_allowed=100,
    )

    assert options.partition == 'batch'
    assert options.effective_nodes == 100
    assert not options.honored
    assert options.reason is not None
    assert '64' in options.reason
    assert 'at least 100' in options.reason


def test_frontier_wall_time_capped_at_the_small_job_bin():
    config = MachineInfo(machine='frontier').config
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, desired_wall_time='04:00:00'
    )

    assert options.wall_time == '02:00:00'


def test_frontier_partition_specs():
    machinfo = MachineInfo(machine='frontier')
    partition_specs = machinfo.get_partition_specs()

    assert list(partition_specs.keys()) == ['batch', 'extended']
    assert partition_specs['batch']['max_wallclock'] is None
    assert partition_specs['batch']['max_wallclock_bins'] == [
        (91, '02:00:00'),
        (183, '06:00:00'),
        (9472, '12:00:00'),
    ]
    assert partition_specs['extended'] == {
        'min_nodes': 1,
        'max_nodes': 64,
        'max_wallclock': '24:00:00',
        'max_wallclock_bins': None,
    }


@pytest.mark.parametrize(
    'nodes, expected',
    [
        (1, '02:00:00'),
        (90, '02:00:00'),
        (91, '02:00:00'),
        (92, '06:00:00'),
        (183, '06:00:00'),
        (184, '12:00:00'),
        (1000, '12:00:00'),
        (2000, '12:00:00'),
    ],
)
def test_wallclock_bins_select_by_node_count(nodes, expected):
    config = _config_from_string(BINNED_CONFIG)
    options = SlurmSystem.resolve_slurm_options(config=config, nodes=nodes)

    assert options.partition == 'batch'
    assert options.qos == 'normal'
    assert options.max_wallclock == expected


def test_wallclock_bins_single_entry_acts_like_max_wallclock():
    config = _config_from_string(
        """
[parallel]
system = slurm
partitions = batch

[partition.batch]
min_nodes = 1
max_wallclock_bins = 1000: 04:00:00
"""
    )
    for nodes in [1, 500, 5000]:
        options = SlurmSystem.resolve_slurm_options(config=config, nodes=nodes)
        assert options.max_wallclock == '04:00:00'


def test_wallclock_bins_combine_with_qos_limit():
    config = _config_from_string(BINNED_CONFIG)

    # the debug qos is more restrictive than the small-job bin
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, qos='debug'
    )
    assert options.max_wallclock == '01:00:00'
    assert options.honored

    # the small-job bin is more restrictive than the debug qos
    config.set('qos.debug', 'max_wallclock', '04:00:00')
    options = SlurmSystem.resolve_slurm_options(
        config=config, nodes=8, qos='debug'
    )
    assert options.max_wallclock == '02:00:00'


def test_wallclock_bins_used_to_reject_a_request():
    config = _config_from_string(BINNED_CONFIG)
    options = SlurmSystem.resolve_slurm_options(
        config=config,
        nodes=8,
        partition='batch',
        desired_wall_time='04:00:00',
    )

    assert not options.honored
    assert options.reason is not None
    assert '02:00:00' in options.reason


def test_wallclock_bins_are_sorted():
    config = _config_from_string(
        """
[parallel]
system = slurm
partitions = batch

[partition.batch]
min_nodes = 1
max_wallclock_bins = 1000: 12:00:00, 91: 02:00:00, 183: 06:00:00
"""
    )
    options = SlurmSystem.resolve_slurm_options(config=config, nodes=8)

    assert options.max_wallclock == '02:00:00'


def test_wallclock_bins_conflict_with_max_wallclock():
    config = _config_from_string(
        """
[parallel]
system = slurm
partitions = batch

[partition.batch]
min_nodes = 1
max_wallclock = 12:00:00
max_wallclock_bins = 91: 02:00:00
"""
    )
    with pytest.raises(ValueError, match='cannot both be set'):
        SlurmSystem.resolve_slurm_options(config=config, nodes=8)


@pytest.mark.parametrize(
    'bins, message',
    [
        ('lots: 02:00:00', 'expected an integer node count'),
        ('91: two hours', 'expected a wall clock'),
        ('02:00:00', 'expected a wall clock'),
        ('91', 'expected a wall clock'),
        (',', 'no entries'),
    ],
)
def test_wallclock_bins_malformed(bins, message):
    config = _config_from_string(
        f"""
[parallel]
system = slurm
partitions = batch

[partition.batch]
min_nodes = 1
max_wallclock_bins = {bins}
"""
    )
    with pytest.raises(ValueError, match=message):
        SlurmSystem.resolve_slurm_options(config=config, nodes=8)
