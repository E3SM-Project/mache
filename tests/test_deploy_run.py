import argparse
import configparser
from pathlib import Path

import pytest

from mache.deploy import bootstrap as deploy_bootstrap
from mache.deploy import run as deploy_run


def test_write_load_script_includes_machine_for_toolchain(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'prefix'),
        pixi_exe='/usr/bin/pixi',
        software='polaris',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='pm-gpu',
        toolchain_compiler='oneapi/2024.2',
        toolchain_mpi='mpich@4.2',
        spack_library_view=None,
        spack_activation='',
    )

    assert script_path == 'load_polaris_pm-gpu_oneapi_2024.2_mpich_4.2.sh'
    assert Path(script_path).is_file()


def test_write_load_script_without_toolchain_keeps_default_name(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'prefix'),
        pixi_exe='/usr/bin/pixi',
        software='polaris',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='chrysalis',
        toolchain_compiler=None,
        toolchain_mpi=None,
        spack_library_view=None,
        spack_activation='',
    )

    assert script_path == 'load_polaris.sh'
    assert Path(script_path).is_file()


def test_get_pixi_executable_requires_explicit_argument():
    with pytest.raises(ValueError, match='must be passed explicitly'):
        deploy_run._get_pixi_executable(None)


def test_get_pixi_executable_expands_and_validates_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    home = tmp_path / 'home'
    pixi = home / 'bin' / 'pixi'
    pixi.parent.mkdir(parents=True)
    pixi.write_text('#!/bin/sh\n', encoding='utf-8')
    pixi.chmod(0o755)

    monkeypatch.setenv('HOME', str(home))

    assert deploy_run._get_pixi_executable('~/bin/pixi') == str(pixi)


def test_run_uses_valid_pixi_version_specifier_for_wildcard_mache_pin():
    assert deploy_run._format_pixi_version_specifier('3.0.2.*') == '3.0.2.*'


def test_run_uses_exact_pixi_version_specifier_for_exact_mache_pin():
    assert deploy_run._format_pixi_version_specifier('3.0.2') == '==3.0.2'


def test_copy_mache_pixi_toml_writes_slim_bootstrap_manifest(tmp_path: Path):
    source_repo = tmp_path / 'source'
    source_repo.mkdir()
    (source_repo / 'pixi.toml').write_text(
        '[workspace]\n'
        'name = "mache-dev"\n'
        'channels = ["conda-forge", "custom"]\n'
        'platforms = ["linux-64", "osx-64"]\n'
        '\n'
        '[dependencies]\n'
        'python = ">=3.10,<3.15"\n'
        'jinja2 = ">=2.9"\n'
        'pyyaml = "*"\n'
        'rsync = "*"\n'
        'setuptools = ">=60"\n'
        'wheel = "*"\n'
        'rattler-build = "*"\n'
        'pytest = "*"\n',
        encoding='utf-8',
    )

    dest = tmp_path / 'bootstrap.toml'
    deploy_bootstrap._copy_mache_pixi_toml(
        dest_pixi_toml=dest,
        source_repo_dir=source_repo,
        python_version='3.14',
    )

    copied = dest.read_text(encoding='utf-8')
    assert 'name = "mache-bootstrap-local"' in copied
    assert 'channels = ["conda-forge", "custom"]' in copied
    assert f'platforms = ["{deploy_bootstrap._get_pixi_platform()}"]' in copied
    assert 'python = "3.14.*"' in copied
    assert 'jinja2 = ">=2.9"' in copied
    assert 'pyyaml = "*"' in copied
    assert 'pip = "*"' in copied
    assert 'setuptools = ">=60"' in copied
    assert 'wheel = "*"' in copied
    assert 'pytest = "*"' in copied
    assert '[environments]' not in copied


def test_copy_mache_pixi_toml_ignores_feature_only_dependencies(
    tmp_path: Path,
):
    source_repo = tmp_path / 'source'
    source_repo.mkdir()
    (source_repo / 'pixi.toml').write_text(
        '[workspace]\n'
        'name = "mache-dev"\n'
        'channels = ["conda-forge"]\n'
        '\n'
        '[dependencies]\n'
        'requests = "*"\n'
        '\n'
        '[feature.py314.dependencies]\n'
        'python = "3.14.*"\n'
        'special-ci-only = "*"\n',
        encoding='utf-8',
    )

    dest = tmp_path / 'bootstrap.toml'
    deploy_bootstrap._copy_mache_pixi_toml(
        dest_pixi_toml=dest,
        source_repo_dir=source_repo,
        python_version='3.14',
    )

    copied = dest.read_text(encoding='utf-8')
    assert 'requests = "*"' in copied
    assert 'special-ci-only = "*"' not in copied
    assert copied.count('setuptools = ">=60"') == 1
    assert copied.count('wheel = "*"') == 1


def test_copy_local_mache_source_snapshot_ignores_untracked_files(
    tmp_path: Path,
):
    source_repo = tmp_path / 'source'
    source_repo.mkdir()
    (source_repo / 'tracked.txt').write_text('tracked\n', encoding='utf-8')
    (source_repo / 'ignored.txt').write_text('ignored\n', encoding='utf-8')

    deploy_bootstrap.subprocess.run(
        ['git', 'init'],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    deploy_bootstrap.subprocess.run(
        ['git', 'config', 'user.email', 'test@example.com'],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    deploy_bootstrap.subprocess.run(
        ['git', 'config', 'user.name', 'Test User'],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    deploy_bootstrap.subprocess.run(
        ['git', 'add', 'tracked.txt'],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    deploy_bootstrap.subprocess.run(
        ['git', 'commit', '-m', 'init'],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )

    dest_repo = tmp_path / 'dest'
    deploy_bootstrap._copy_local_mache_source_snapshot(
        source_repo=source_repo,
        repo_dir=dest_repo,
    )

    assert (dest_repo / 'tracked.txt').read_text(
        encoding='utf-8'
    ) == 'tracked\n'
    assert not (dest_repo / 'ignored.txt').exists()


def test_resolve_toolchain_pairs_ignores_machine_config_without_machine():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('deploy')
    machine_config.set('deploy', 'compiler', 'gnu')
    machine_config.set('deploy', 'mpi_gnu', 'mpich')

    pairs = deploy_run._resolve_toolchain_pairs(
        config={},
        runtime={},
        machine=None,
        machine_config=machine_config,
        args=argparse.Namespace(compiler=None, mpi=None),
        quiet=True,
    )

    assert pairs == []


def test_resolve_toolchain_pairs_uses_machine_config_with_machine():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('deploy')
    machine_config.set('deploy', 'compiler', 'gnu')
    machine_config.set('deploy', 'mpi_gnu', 'mpich')

    pairs = deploy_run._resolve_toolchain_pairs(
        config={},
        runtime={},
        machine='anvil',
        machine_config=machine_config,
        args=argparse.Namespace(compiler=None, mpi=None),
        quiet=True,
    )

    assert pairs == [('gnu', 'mpich')]


def test_resolve_deploy_permissions_prefers_runtime_then_config_then_machine():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('deploy')
    machine_config.set('deploy', 'group', 'deployers')
    machine_config.set('deploy', 'world_readable', 'false')
    machine_config.add_section('e3sm_unified')
    machine_config.set('e3sm_unified', 'group', 'legacy')

    group, world_readable = deploy_run._resolve_deploy_permissions(
        config={
            'permissions': {
                'group': 'from-config',
                'world_readable': True,
            }
        },
        runtime={
            'permissions': {
                'group': 'from-hook',
                'world_readable': False,
            }
        },
        machine_config=machine_config,
    )

    assert group == 'from-hook'
    assert world_readable is False


def test_resolve_deploy_permissions_uses_legacy_group_fallback():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('e3sm_unified')
    machine_config.set('e3sm_unified', 'group', 'legacy-group')

    group, world_readable = deploy_run._resolve_deploy_permissions(
        config={},
        runtime={},
        machine_config=machine_config,
    )

    assert group == 'legacy-group'
    assert world_readable is True


def test_apply_deploy_permissions_updates_prefix_and_managed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prefix = tmp_path / 'prefix'
    prefix.mkdir()
    (prefix / 'pixi.toml').write_text('[workspace]\n', encoding='utf-8')
    (prefix / 'bin').mkdir()

    load_script = tmp_path / 'load_demo.sh'
    load_script.write_text('#!/bin/sh\n', encoding='utf-8')

    calls = []

    def _fake_update_permissions(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        deploy_run, 'update_permissions', _fake_update_permissions
    )

    logger = deploy_run.logging.getLogger('test-apply-deploy-permissions')
    logger.handlers = [deploy_run.logging.NullHandler()]
    logger.propagate = False

    deploy_run._apply_deploy_permissions(
        prefix=str(prefix),
        load_script_paths=[str(load_script)],
        spack_env_paths=[],
        group='e3sm',
        world_readable=False,
        logger=logger,
    )

    assert len(calls) == 2

    first_args, first_kwargs = calls[0]
    assert first_args == (str(prefix), 'e3sm')
    assert first_kwargs['group_writable'] is True
    assert first_kwargs['other_readable'] is False
    assert first_kwargs['recursive'] is False

    second_args, second_kwargs = calls[1]
    assert second_args[1] == 'e3sm'
    assert sorted(second_args[0]) == sorted(
        [
            str(load_script),
            str(prefix / 'pixi.toml'),
            str(prefix / 'bin'),
        ]
    )
    assert second_kwargs['group_writable'] is False
    assert second_kwargs['other_readable'] is False
    assert second_kwargs['recursive'] is True


def test_apply_deploy_permissions_is_noop_without_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = []

    def _fake_update_permissions(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        deploy_run, 'update_permissions', _fake_update_permissions
    )

    logger = deploy_run.logging.getLogger('test-apply-deploy-permissions-noop')
    logger.handlers = [deploy_run.logging.NullHandler()]
    logger.propagate = False

    deploy_run._apply_deploy_permissions(
        prefix=str(tmp_path / 'prefix'),
        load_script_paths=[],
        spack_env_paths=[],
        group=None,
        world_readable=True,
        logger=logger,
    )

    assert calls == []


def test_apply_deploy_permissions_includes_deployed_spack_envs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prefix = tmp_path / 'prefix'
    prefix.mkdir()

    spack_lib = tmp_path / 'spack' / 'var' / 'spack' / 'environments' / 'lib'
    spack_lib.mkdir(parents=True)
    spack_soft = (
        tmp_path / 'spack' / 'var' / 'spack' / 'environments' / 'software'
    )
    spack_soft.mkdir(parents=True)

    calls = []

    def _fake_update_permissions(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        deploy_run, 'update_permissions', _fake_update_permissions
    )

    logger = deploy_run.logging.getLogger(
        'test-apply-deploy-permissions-spack'
    )
    logger.handlers = [deploy_run.logging.NullHandler()]
    logger.propagate = False

    deploy_run._apply_deploy_permissions(
        prefix=str(prefix),
        load_script_paths=[],
        spack_env_paths=[str(spack_lib), str(spack_soft)],
        group='e3sm',
        world_readable=True,
        logger=logger,
    )

    assert len(calls) == 2

    second_args, second_kwargs = calls[1]
    assert second_args[1] == 'e3sm'
    assert sorted(second_args[0]) == sorted(
        [
            str(spack_lib),
            str(spack_soft),
        ]
    )
    assert second_kwargs['show_progress'] is True
    assert second_kwargs['recursive'] is True


def test_get_deployed_spack_env_paths_includes_library_and_software_envs():
    spack_results = [
        deploy_run.SpackDeployResult(
            compiler='gnu',
            mpi='mpich',
            env_name='spack_env_gnu_mpich',
            spack_path='/opt/spack',
            view_path=(
                '/opt/spack/var/spack/environments/spack_env_gnu_mpich/'
                '.spack-env/view'
            ),
            activation='',
        )
    ]
    spack_software_env = deploy_run.SpackSoftwareEnvResult(
        compiler='gnu',
        mpi='mpich',
        env_name='myproj_software',
        spack_path='/opt/spack',
        view_path=(
            '/opt/spack/var/spack/environments/myproj_software/.spack-env/view'
        ),
        path_setup='',
    )

    assert deploy_run._get_deployed_spack_env_paths(
        spack_results=spack_results,
        spack_software_env=spack_software_env,
    ) == [
        '/opt/spack/var/spack/environments/spack_env_gnu_mpich',
        '/opt/spack/var/spack/environments/myproj_software',
    ]
