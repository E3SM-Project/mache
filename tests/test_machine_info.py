from pathlib import Path

import pytest
from lxml import etree

from mache import MachineInfo, discover_machine

REPO_ROOT = Path(__file__).resolve().parents[1]
MACHINES_DIR = REPO_ROOT / 'mache' / 'machines'
CONFIG_MACHINES_XML = (
    REPO_ROOT / 'mache' / 'cime_machine_config' / 'config_machines.xml'
)


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


@pytest.mark.parametrize(
    'machine, expected_inputdata_base',
    [
        ('chrysalis', '/lcrc/group/e3sm/data/inputdata'),
        ('pm-cpu', '/global/cfs/cdirs/e3sm/inputdata'),
        ('aurora', '/lus/flare/projects/E3SMinput/data'),
        ('andes', '/lustre/orion/cli115/world-shared/e3sm/inputdata'),
    ],
)
def test_inputdata_base(machine, expected_inputdata_base):
    machinfo = MachineInfo(machine=machine)
    assert machinfo.inputdata_base == expected_inputdata_base


def test_inputdata_base_missing_for_chicoma_cpu():
    machinfo = MachineInfo(machine='chicoma-cpu')
    assert machinfo.inputdata_base is None


def test_inputdata_base_matches_config_machines_xml():
    din_loc_root_by_machine = _get_xml_din_loc_root_by_machine()

    machine_names = _get_machine_config_names()
    for machine in machine_names:
        machinfo = MachineInfo(machine=machine)
        if machinfo.inputdata_base is None:
            continue
        if machine not in din_loc_root_by_machine:
            continue

        assert machinfo.inputdata_base == din_loc_root_by_machine[machine]


def _get_xml_din_loc_root_by_machine():
    root = etree.parse(str(CONFIG_MACHINES_XML))
    machines = next(root.iter('config_machines'))
    din_loc_root_by_machine = {}
    for machine in machines:
        if machine.tag != 'machine':
            continue

        for child in machine:
            if child.tag == 'DIN_LOC_ROOT':
                din_loc_root_by_machine[machine.attrib['MACH']] = child.text
                break

    return din_loc_root_by_machine


def _get_machine_config_names():
    return sorted(
        path.stem
        for path in MACHINES_DIR.glob('*.cfg')
        if path.stem != 'default'
    )
