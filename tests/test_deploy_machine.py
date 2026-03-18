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
