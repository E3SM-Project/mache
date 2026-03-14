from mache import MachineInfo, discover_machine


def test_discover_machine():
    discover_machine()


def test_machine_info():
    machine = 'chrysalis'
    machinfo = MachineInfo(machine=machine)
    assert machinfo.machine == machine
    assert machinfo.e3sm_supported
    config = machinfo.config
    assert config.get('sync', 'hostname') == 'chrysalis.lcrc.anl.gov'
    print(machinfo)

    machine = 'unknown'
    machinfo = MachineInfo(machine=machine)
    assert machinfo.machine == machine
    assert not machinfo.e3sm_supported
    print(machinfo)


def test_get_queue_specs_aurora():
    machinfo = MachineInfo(machine='aurora')
    queue_specs = machinfo.get_queue_specs()

    assert list(queue_specs.keys()) == ['capacity', 'prod', 'debug']
    assert queue_specs['capacity'] == {
        'min_nodes': 1,
        'max_nodes': 16,
        'max_wallclock': '168:00:00',
    }
    assert queue_specs['prod'] == {
        'min_nodes': 256,
        'max_nodes': None,
        'max_wallclock': '12:00:00',
    }
    assert queue_specs['debug'] == {
        'min_nodes': 1,
        'max_nodes': 2,
        'max_wallclock': '01:00:00',
    }


def test_get_queue_specs_missing():
    machinfo = MachineInfo(machine='chrysalis')
    assert machinfo.get_queue_specs() == {}


def test_get_partition_specs_chrysalis():
    machinfo = MachineInfo(machine='chrysalis')
    partition_specs = machinfo.get_partition_specs()

    assert list(partition_specs.keys()) == ['compute', 'debug']
    assert partition_specs['compute'] == {
        'min_nodes': 1,
        'max_nodes': None,
        'max_wallclock': '168:00:00',
    }
    assert partition_specs['debug'] == {
        'min_nodes': 1,
        'max_nodes': 10,
        'max_wallclock': '168:00:00',
    }


def test_get_partition_specs_compy():
    machinfo = MachineInfo(machine='compy')
    partition_specs = machinfo.get_partition_specs()

    assert list(partition_specs.keys()) == ['slurm', 'short']
    assert partition_specs['slurm'] == {
        'min_nodes': 1,
        'max_nodes': 440,
        'max_wallclock': '36:00:00',
    }
    assert partition_specs['short'] == {
        'min_nodes': 1,
        'max_nodes': 50,
        'max_wallclock': '02:00:00',
    }


def test_get_qos_specs_pm_cpu():
    machinfo = MachineInfo(machine='pm-cpu')
    qos_specs = machinfo.get_qos_specs()

    assert list(qos_specs.keys()) == ['regular', 'debug', 'premium']
    assert qos_specs['debug'] == {
        'min_nodes': 1,
        'max_nodes': 8,
        'max_wallclock': '00:30:00',
    }
    assert qos_specs['regular'] == {
        'min_nodes': 1,
        'max_nodes': None,
        'max_wallclock': '48:00:00',
    }
    assert qos_specs['premium'] == {
        'min_nodes': 1,
        'max_nodes': None,
        'max_wallclock': '48:00:00',
    }


def test_get_qos_specs_pm_gpu():
    machinfo = MachineInfo(machine='pm-gpu')
    qos_specs = machinfo.get_qos_specs()

    assert list(qos_specs.keys()) == ['regular', 'debug', 'premium']
    assert qos_specs['debug'] == {
        'min_nodes': 1,
        'max_nodes': 8,
        'max_wallclock': '00:30:00',
    }
    assert qos_specs['regular'] == {
        'min_nodes': 1,
        'max_nodes': 3072,
        'max_wallclock': '48:00:00',
    }
    assert qos_specs['premium'] == {
        'min_nodes': 1,
        'max_nodes': 3072,
        'max_wallclock': '48:00:00',
    }


def test_get_queue_specs_polaris():
    machinfo = MachineInfo(machine='polaris')
    queue_specs = machinfo.get_queue_specs()

    assert list(queue_specs.keys()) == ['prod', 'debug']
    assert queue_specs['debug'] == {
        'min_nodes': 1,
        'max_nodes': 2,
        'max_wallclock': '01:00:00',
    }
    assert queue_specs['prod'] == {
        'min_nodes': 1,
        'max_nodes': 512,
        'max_wallclock': '24:00:00',
    }


def test_get_scheduler_specs_invalid_target_type():
    machinfo = MachineInfo(machine='chrysalis')
    try:
        machinfo.get_scheduler_specs(target_type='constraint')
    except ValueError as exc:
        assert 'Unexpected target_type' in str(exc)
    else:
        raise AssertionError('Expected get_scheduler_specs() to fail.')
