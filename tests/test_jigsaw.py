from functools import partial
from pathlib import Path

import mache.jigsaw as jigsaw


def test_deploy_jigsawpy_in_pixi_environment(monkeypatch, tmp_path: Path):
    """
    Test pixi command wiring without performing a real installation.

    This unit test mocks both the package build and shell execution. It
    verifies that ``deploy_jigsawpy()`` first adds the local channel to the
    target manifest and then adds ``jigsawpy``.
    """
    manifest = tmp_path / 'pixi.toml'
    manifest.write_text('[workspace]\nname = "demo"\n', encoding='utf-8')

    channel_uri = 'file:///tmp/jigsaw-channel'
    monkeypatch.setattr(
        jigsaw,
        'build_jigsawpy_package',
        lambda **kwargs: _fake_build_result(channel_uri, tmp_path),
    )

    commands: list[str] = []
    monkeypatch.setattr(
        jigsaw,
        'check_call',
        partial(_record_check_call, commands),
    )

    result = jigsaw.deploy_jigsawpy(
        pixi_exe='pixi',
        python_version='3.14',
        jigsaw_python_path='jigsaw-python',
        repo_root='.',
        log_filename=str(tmp_path / 'pixi.log'),
        quiet=True,
        backend='pixi',
        pixi_manifest=str(manifest),
    )

    assert result.channel_uri == channel_uri
    assert len(commands) == 2

    add_channel_command = commands[0]
    assert 'pixi workspace channel add' in add_channel_command
    assert '--manifest-path' in add_channel_command
    assert str(manifest) in add_channel_command
    assert '--prepend' in add_channel_command
    assert '--feature' not in add_channel_command
    assert 'file:///tmp/jigsaw-channel' in add_channel_command

    add_package_command = commands[1]
    assert 'pixi add' in add_package_command
    assert '--manifest-path' in add_package_command
    assert str(manifest) in add_package_command
    assert '--feature' not in add_package_command
    assert add_package_command.endswith('jigsawpy')


def test_deploy_jigsawpy_in_conda_environment(monkeypatch, tmp_path: Path):
    """
    Test conda command wiring without performing a real installation.

    This unit test mocks both the package build and shell execution. It
    verifies that ``deploy_jigsawpy()`` emits the expected ``conda install``
    command, including target prefix and channel ordering.
    """
    channel_uri = 'file:///tmp/jigsaw-channel'
    monkeypatch.setattr(
        jigsaw,
        'build_jigsawpy_package',
        lambda **kwargs: _fake_build_result(channel_uri, tmp_path),
    )

    commands: list[str] = []
    monkeypatch.setattr(
        jigsaw,
        'check_call',
        partial(_record_check_call, commands),
    )

    conda_prefix = tmp_path / 'conda-prefix'

    result = jigsaw.deploy_jigsawpy(
        python_version='3.14',
        jigsaw_python_path='jigsaw-python',
        repo_root='.',
        log_filename=str(tmp_path / 'conda.log'),
        quiet=True,
        backend='conda',
        conda_exe='conda',
        conda_prefix=str(conda_prefix),
    )

    assert result.channel_uri == channel_uri
    assert len(commands) == 1
    command = commands[0]
    assert 'conda install --yes' in command
    assert f'--prefix {conda_prefix}' in command
    assert '--channel file:///tmp/jigsaw-channel' in command
    assert '--channel conda-forge' in command
    assert command.endswith('jigsawpy')


def test_build_jigsawpy_package_conda_backend_without_pixi(monkeypatch):
    """Verify conda build backend works without a pixi executable."""

    recorded = {}

    monkeypatch.setattr(
        jigsaw,
        '_ensure_jigsaw_python_source',
        lambda **_: None,
    )
    monkeypatch.setattr(jigsaw, '_compute_jigsaw_cache_key', lambda **_: 'key')
    monkeypatch.setattr(
        jigsaw,
        '_is_cached_jigsaw_build_valid',
        lambda **_: False,
    )
    monkeypatch.setattr(jigsaw, '_get_jigsaw_version', lambda *_: '0.0.1')
    monkeypatch.setattr(jigsaw, '_write_jigsaw_cache_key', lambda **_: None)
    monkeypatch.setattr(
        jigsaw, '_get_local_channel_uri', lambda **_: 'file:///tmp'
    )

    def _fake_build_external_jigsaw(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(
        jigsaw,
        '_build_external_jigsaw',
        _fake_build_external_jigsaw,
    )

    result = jigsaw.build_jigsawpy_package(
        python_version='3.14',
        jigsaw_python_path='jigsaw-python',
        repo_root='.',
        log_filename='test.log',
        quiet=True,
        backend='conda',
        pixi_exe=None,
        conda_exe='conda',
    )

    assert result.channel_uri == 'file:///tmp'
    assert recorded['backend'] == 'conda'
    assert recorded['pixi_exe'] is None
    assert recorded['conda_exe'] == 'conda'


def test_deploy_jigsawpy_pixi_uses_isolated_manifest_when_implicit(
    monkeypatch, tmp_path: Path
):
    manifest = tmp_path / 'pixi.toml'
    manifest.write_text(
        '[workspace]\n'
        'name = "demo"\n'
        '\n'
        '[feature.py314.dependencies]\n'
        'python = "3.14.*"\n',
        encoding='utf-8',
    )

    channel_uri = 'file:///tmp/jigsaw-channel'
    monkeypatch.setattr(
        jigsaw,
        'build_jigsawpy_package',
        lambda **kwargs: _fake_build_result(channel_uri, tmp_path),
    )

    monkeypatch.setenv('PIXI_PROJECT_MANIFEST', str(manifest))

    commands: list[str] = []
    monkeypatch.setattr(
        jigsaw,
        'check_call',
        partial(_record_check_call, commands),
    )

    result = jigsaw.deploy_jigsawpy(
        pixi_exe='pixi',
        python_version='3.14',
        quiet=True,
        backend='pixi',
    )

    assert result.channel_uri == channel_uri
    assert len(commands) == 2
    assert str(manifest) not in commands[0]
    assert str(manifest) not in commands[1]
    assert '.mache_cache/jigsaw/pixi_install' in commands[0]
    assert '.mache_cache/jigsaw/pixi_install' in commands[1]
    assert '--feature py314' in commands[0]
    assert '--feature py314' in commands[1]


def _fake_build_result(channel_uri: str, tmp_path: Path):
    return jigsaw.JigsawBuildResult(
        channel_uri=channel_uri,
        channel_dir=tmp_path,
        cache_key='abc123',
        cache_hit=True,
        jigsaw_version='0.0.1',
    )


def _record_check_call(
    commands: list[str], command: str, log_filename: str, quiet: bool
) -> None:
    commands.append(command)
