import configparser
import os

import pytest

from mache.deploy.conda import get_conda_platform_and_system
from mache.deploy.machine import get_machine, get_machine_config


def _target_machines_path() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, 'tests', 'target_machines_dir')


def test_get_machine_known():
    assert (
        get_machine(
            requested_machine='chrysalis',
            machines_path=_target_machines_path(),
            quiet=True,
        )
        == 'chrysalis'
    )


def test_get_machine_unknown_raises():
    with pytest.raises(ValueError):
        get_machine(
            requested_machine='not-a-real-machine',
            machines_path=_target_machines_path(),
            quiet=True,
        )


def test_get_machine_target_only():
    assert (
        get_machine(
            requested_machine='target-only',
            machines_path=_target_machines_path(),
            quiet=True,
        )
        == 'target-only'
    )


def test_machine_config_merge_precedence():
    platform, _ = get_conda_platform_and_system()
    cfg = get_machine_config(
        machine='chrysalis',
        machines_path=_target_machines_path(),
        platform=platform,
        quiet=True,
    )
    assert isinstance(cfg, configparser.ConfigParser)

    # From mache.machines/chrysalis.cfg but overridden by our target package
    assert cfg.get('parallel', 'account') == 'TEST_ACCOUNT'

    # A section only present in the target machines package
    assert cfg.get('extra', 'foo') == 'bar'


def test_machine_config_target_only_machine():
    platform, _ = get_conda_platform_and_system()
    cfg = get_machine_config(
        machine='target-only',
        machines_path=_target_machines_path(),
        platform=platform,
        quiet=True,
    )
    assert cfg.get('target', 'x') == '1'


def test_machine_config_keeps_e3sm_unified_metadata_out_of_deploy():
    platform, _ = get_conda_platform_and_system()
    cfg = get_machine_config(
        machine='aurora',
        machines_path=None,
        platform=platform,
        quiet=True,
    )

    assert cfg.get('e3sm_unified', 'group') == 'E3SMinput'
    assert cfg.get('e3sm_unified', 'base_path') == (
        '/lus/flare/projects/E3SMinput/soft/e3sm-unified'
    )
    assert cfg.get('e3sm_unified', 'compiler') == 'oneapi-ifx'
    assert cfg.get('e3sm_unified', 'mpi') == 'mpich'
    assert cfg.getboolean('e3sm_unified', 'use_e3sm_hdf5_netcdf') is True
    assert not cfg.has_section('deploy')


def test_machine_config_without_machine_has_no_deploy_defaults():
    platform, _ = get_conda_platform_and_system()
    cfg = get_machine_config(
        machine=None,
        machines_path=None,
        platform=platform,
        quiet=True,
    )

    assert not cfg.has_section('deploy')


def test_machine_config_has_toolchain_defaults_for_newly_completed_machines():
    platform, _ = get_conda_platform_and_system()
    expected = {
        'andes': ('gnu', 'mpich'),
        'chicoma-cpu': ('gnu', 'mpich'),
        'polaris': ('gnu', 'mpich'),
    }

    for machine, (compiler, mpi) in expected.items():
        cfg = get_machine_config(
            machine=machine,
            machines_path=None,
            platform=platform,
            quiet=True,
        )
        assert cfg.get('e3sm_unified', 'compiler') == compiler
        assert cfg.get('e3sm_unified', 'mpi') == mpi
