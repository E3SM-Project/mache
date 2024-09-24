from mache import MachineInfo, discover_machine


def test_discover_machine():
    discover_machine()


def test_machine_info():
    machine = 'anvil'
    machinfo = MachineInfo(machine=machine)
    assert machinfo.machine == machine
    assert machinfo.e3sm_supported
    config = machinfo.config
    assert config.get('sync', 'hostname') == 'blues.lcrc.anl.gov'
    print(machinfo)

    machine = 'unknown'
    machinfo = MachineInfo(machine=machine)
    assert machinfo.machine == machine
    assert not machinfo.e3sm_supported
    print(machinfo)
