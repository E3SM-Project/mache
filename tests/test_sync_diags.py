import argparse
import configparser
import subprocess

import pytest

import mache.__main__
from mache.sync import cli as sync_cli
from mache.sync import diags


def test_sync_diags_to_remote_builds_expected_rsync_commands(monkeypatch):
    machine_configs = {
        'chrysalis': _machine_config(
            hostname='chrysalis.example.com',
            public_diags='/public/diags',
            private_diags='/private/diags',
            base_path='/local/diags',
            group='e3sm',
        ),
        'pm-cpu': _machine_config(
            hostname='pm.example.com',
            public_diags='/unused/public',
            private_diags='/unused/private',
            base_path='/remote/diags',
            group='nersc',
        ),
    }
    _patch_machine_info(monkeypatch, machine_configs)

    calls = []
    monkeypatch.setattr(
        diags.subprocess,
        'check_call',
        lambda args: calls.append(args),
    )

    update_calls = []
    monkeypatch.setattr(
        diags,
        'update_permissions',
        lambda **kwargs: update_calls.append(kwargs),
    )

    diags.sync_diags(
        other='pm-cpu',
        direction='to',
        machine='chrysalis',
        username='nersc_user',
    )

    expected_prefix = [
        'rsync',
        '--verbose',
        '--recursive',
        '--times',
        '--links',
        '--compress',
        '--progress',
        '--update',
        '--no-perms',
        '--omit-dir-times',
    ]
    assert calls == [
        expected_prefix
        + ['/public/diags/', 'nersc_user@pm.example.com:/remote/diags'],
        expected_prefix
        + ['/private/diags/', 'nersc_user@pm.example.com:/remote/diags'],
    ]
    assert update_calls == []


def test_sync_diags_from_remote_updates_permissions_after_failures(
    monkeypatch, capsys
):
    machine_configs = {
        'pm-cpu': _machine_config(
            hostname='pm.example.com',
            public_diags='/unused/public',
            private_diags='/unused/private',
            base_path='/local/diags',
            group='e3sm',
        ),
        'chrysalis': _machine_config(
            hostname='chrysalis.example.com',
            public_diags='/public/diags',
            private_diags='/private/diags',
            base_path='/unused/remote',
            group='cels',
            tunnel_hostname='ch-fe',
        ),
    }
    _patch_machine_info(monkeypatch, machine_configs)

    calls = []

    def _fake_check_call(args):
        calls.append(args)
        if len(calls) == 2:
            raise subprocess.CalledProcessError(returncode=1, cmd=args)

    monkeypatch.setattr(diags.subprocess, 'check_call', _fake_check_call)

    update_calls = []
    monkeypatch.setattr(
        diags,
        'update_permissions',
        lambda **kwargs: update_calls.append(kwargs),
    )

    diags.sync_diags(
        other='chrysalis',
        direction='from',
        machine='pm-cpu',
        username='lcrc_user',
    )

    expected_prefix = [
        'rsync',
        '--verbose',
        '--recursive',
        '--times',
        '--links',
        '--compress',
        '--progress',
        '--update',
        '--no-perms',
        '--omit-dir-times',
        '--rsync-path=ssh ch-fe rsync',
    ]
    assert calls == [
        expected_prefix
        + ['lcrc_user@chrysalis.example.com:/public/diags/', '/local/diags'],
        expected_prefix
        + ['lcrc_user@chrysalis.example.com:/private/diags/', '/local/diags'],
    ]
    assert update_calls == [
        {
            'base_paths': '/local/diags',
            'group': 'e3sm',
            'show_progress': True,
            'group_writable': True,
            'other_readable': True,
        }
    ]

    captured = capsys.readouterr()
    assert 'Warning: Some transfer operations failed' in captured.out
    assert 'Updating permissions on /local/diags:' in captured.out


def test_dispatch_diags_calls_sync_diags(monkeypatch):
    called = {}

    def _fake_sync_diags(
        other,
        direction='to',
        machine=None,
        username=None,
        config_filename=None,
    ):
        called['other'] = other
        called['direction'] = direction
        called['machine'] = machine
        called['username'] = username
        called['config_filename'] = config_filename

    monkeypatch.setattr(diags, 'sync_diags', _fake_sync_diags)

    args = argparse.Namespace(
        other='pm-cpu',
        direction='to',
        machine='chrysalis',
        username='nersc_user',
        config_file='override.cfg',
    )

    diags._dispatch_diags(args)

    assert called == {
        'other': 'pm-cpu',
        'direction': 'to',
        'machine': 'chrysalis',
        'username': 'nersc_user',
        'config_filename': 'override.cfg',
    }


def test_add_sync_subparser_parses_diags_arguments():
    parser = argparse.ArgumentParser(prog='mache')
    subparsers = parser.add_subparsers(dest='command', required=True)
    sync_cli.add_sync_subparser(subparsers)

    args = parser.parse_args(
        [
            'sync',
            'diags',
            'from',
            'chrysalis',
            '-m',
            'pm-cpu',
            '-u',
            'lcrc_user',
            '-f',
            'override.cfg',
        ]
    )

    assert args.command == 'sync'
    assert args.sync_cmd == 'diags'
    assert args.direction == 'from'
    assert args.other == 'chrysalis'
    assert args.machine == 'pm-cpu'
    assert args.username == 'lcrc_user'
    assert args.config_file == 'override.cfg'
    assert args.func is diags._dispatch_diags


def test_sync_diags_main_dispatches_from_wrapper_argv(monkeypatch):
    called = {}

    def _fake_sync_diags(
        other,
        direction='to',
        machine=None,
        username=None,
        config_filename=None,
    ):
        called['other'] = other
        called['direction'] = direction
        called['machine'] = machine
        called['username'] = username
        called['config_filename'] = config_filename

    monkeypatch.setattr(diags, 'sync_diags', _fake_sync_diags)
    monkeypatch.setattr(
        diags.sys,
        'argv',
        [
            'mache',
            'sync',
            'diags',
            'to',
            'pm-cpu',
            '-m',
            'chrysalis',
            '-u',
            'nersc_user',
            '-f',
            'override.cfg',
        ],
    )

    diags.main()

    assert called == {
        'other': 'pm-cpu',
        'direction': 'to',
        'machine': 'chrysalis',
        'username': 'nersc_user',
        'config_filename': 'override.cfg',
    }


def test_main_dispatches_sync_diags_from_top_level_cli(monkeypatch):
    called = {}

    def _fake_sync_diags(
        other,
        direction='to',
        machine=None,
        username=None,
        config_filename=None,
    ):
        called['other'] = other
        called['direction'] = direction
        called['machine'] = machine
        called['username'] = username
        called['config_filename'] = config_filename

    monkeypatch.setattr(diags, 'sync_diags', _fake_sync_diags)
    monkeypatch.setattr(
        mache.__main__.sys,
        'argv',
        [
            'mache',
            'sync',
            'diags',
            'from',
            'chrysalis',
            '-m',
            'pm-cpu',
            '-u',
            'lcrc_user',
            '-f',
            'override.cfg',
        ],
    )

    mache.__main__.main()

    assert called == {
        'other': 'chrysalis',
        'direction': 'from',
        'machine': 'pm-cpu',
        'username': 'lcrc_user',
        'config_filename': 'override.cfg',
    }


def test_sync_diags_requires_username_for_from_direction(monkeypatch):
    machine_configs = {
        'pm-cpu': _machine_config(
            hostname='pm.example.com',
            public_diags='/unused/public',
            private_diags='/unused/private',
            base_path='/local/diags',
            group='e3sm',
        ),
        'chrysalis': _machine_config(
            hostname='chrysalis.example.com',
            public_diags='/public/diags',
            private_diags='/private/diags',
            base_path='/unused/remote',
            group='cels',
        ),
    }
    _patch_machine_info(monkeypatch, machine_configs)

    with pytest.raises(ValueError, match='LCRC username is required'):
        diags.sync_diags(
            other='chrysalis',
            direction='from',
            machine='pm-cpu',
            username=None,
        )


def _machine_config(
    hostname,
    public_diags,
    private_diags,
    base_path,
    group,
    tunnel_hostname=None,
):
    config = configparser.ConfigParser()
    config.add_section('sync')
    config.set('sync', 'hostname', hostname)
    config.set('sync', 'public_diags', public_diags)
    config.set('sync', 'private_diags', private_diags)
    if tunnel_hostname is not None:
        config.set('sync', 'tunnel_hostname', tunnel_hostname)
    config.add_section('diagnostics')
    config.set('diagnostics', 'base_path', base_path)
    config.set('diagnostics', 'group', group)
    return config


def _patch_machine_info(monkeypatch, machine_configs):
    class _FakeMachineInfo:
        def __init__(self, machine=None):
            self.machine = machine
            self.config = machine_configs[machine]

    monkeypatch.setattr(diags, 'MachineInfo', _FakeMachineInfo)
