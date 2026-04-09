import argparse
import configparser
from pathlib import Path

import pytest

from mache.deploy import bootstrap as deploy_bootstrap
from mache.deploy import run as deploy_run
from mache.deploy.shared import SharedDeployArtifacts


def _make_pixi_executable(tmp_path: Path) -> str:
    pixi = tmp_path / 'bin' / 'pixi'
    pixi.parent.mkdir(parents=True, exist_ok=True)
    pixi.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    pixi.chmod(0o755)
    return str(pixi)


def _shared_load_script_pixi() -> dict[str, str]:
    return {'mode': 'shared', 'path': ''}


def _explicit_load_script_pixi(path: str) -> dict[str, str]:
    return {'mode': 'explicit', 'path': path}


def _path_load_script_pixi() -> dict[str, str]:
    return {'mode': 'path', 'path': ''}


def test_write_load_script_includes_machine_for_toolchain(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'prefix'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path=str(tmp_path),
        load_script_pixi_exe=_explicit_load_script_pixi(pixi_exe),
        software='polaris',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='pm-gpu',
        compute_pixi_mpi='nompi',
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
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'prefix'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path=str(tmp_path),
        load_script_pixi_exe=_explicit_load_script_pixi(pixi_exe),
        software='polaris',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='chrysalis',
        compute_pixi_mpi='nompi',
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


def test_resolve_load_script_branch_path_defaults_to_repo_root():
    branch_path = deploy_run._resolve_load_script_branch_path(
        config={'project': {}},
        runtime={},
        repo_root='/tmp/downstream',
    )

    assert branch_path == '/tmp/downstream'


def test_resolve_load_script_branch_path_runtime_none_disables_export():
    branch_path = deploy_run._resolve_load_script_branch_path(
        config={'project': {'branch_path': '/tmp/downstream'}},
        runtime={'project': {'branch_path': None}},
        repo_root='/tmp/repo',
    )

    assert branch_path is None


def test_resolve_load_script_pixi_exe_defaults_to_run_argument():
    resolved = deploy_run._resolve_load_script_pixi_exe(
        config={'pixi': {}},
        runtime={},
        pixi_exe='/tmp/pixi-from-run',
    )

    assert resolved == {
        'mode': 'explicit',
        'path': '/tmp/pixi-from-run',
    }


def test_resolve_load_script_pixi_exe_null_uses_path_mode():
    resolved = deploy_run._resolve_load_script_pixi_exe(
        config={'pixi': {'load_script_exe': None}},
        runtime={},
        pixi_exe='/tmp/pixi-from-run',
    )

    assert resolved == {'mode': 'path', 'path': ''}


def test_resolve_load_script_pixi_exe_shared_mode():
    resolved = deploy_run._resolve_load_script_pixi_exe(
        config={'pixi': {'load_script_exe': 'shared'}},
        runtime={},
        pixi_exe='/tmp/pixi-from-run',
    )

    assert resolved == {'mode': 'shared', 'path': ''}


def test_resolve_pixi_prefix_prefers_new_cli_flag():
    prefix = deploy_run._resolve_pixi_prefix(
        args=argparse.Namespace(pixi_path='/cli/pixi-path'),
        config={'pixi': {'prefix': '/config/prefix'}},
        runtime={'pixi': {'prefix': '/runtime/prefix'}},
    )

    assert prefix == '/cli/pixi-path'


def test_resolve_pixi_prefix_prefers_runtime_when_cli_missing():
    prefix = deploy_run._resolve_pixi_prefix(
        args=argparse.Namespace(pixi_path=None),
        config={'pixi': {'prefix': '/config/prefix'}},
        runtime={'pixi': {'prefix': '/runtime/prefix'}},
    )

    assert prefix == '/runtime/prefix'


def test_resolve_pixi_prefix_accepts_legacy_prefix_attribute():
    prefix = deploy_run._resolve_pixi_prefix(
        args=argparse.Namespace(prefix='/legacy/prefix'),
        config={'pixi': {'prefix': '/config/prefix'}},
        runtime={},
    )

    assert prefix == '/legacy/prefix'


def test_resolve_pixi_channels_prefers_runtime_override():
    channels = deploy_run._resolve_pixi_channels(
        pixi_cfg={'channels': ['conda-forge']},
        runtime={'pixi': {'channels': ['file:///tmp/local-channel']}},
    )

    assert channels == ['file:///tmp/local-channel']


def test_resolve_pixi_extra_dependencies_defaults_empty():
    extra_dependencies = deploy_run._resolve_pixi_extra_dependencies(
        pixi_cfg={},
        runtime={},
    )

    assert extra_dependencies == []


def test_resolve_pixi_extra_dependencies_prefers_runtime_override():
    extra_dependencies = deploy_run._resolve_pixi_extra_dependencies(
        pixi_cfg={'extra_dependencies': ['foo = "*"']},
        runtime={'pixi': {'extra_dependencies': ['bar = "*"']}},
    )

    assert extra_dependencies == ['bar = "*"']


def test_resolve_pixi_omit_dependencies_defaults_empty():
    omit_dependencies = deploy_run._resolve_pixi_omit_dependencies(
        pixi_cfg={},
        runtime={},
    )

    assert omit_dependencies == []


def test_resolve_pixi_omit_dependencies_prefers_runtime_override():
    omit_dependencies = deploy_run._resolve_pixi_omit_dependencies(
        pixi_cfg={'omit_dependencies': ['git']},
        runtime={'pixi': {'omit_dependencies': ['git', 'ncview']}},
    )

    assert omit_dependencies == ['git', 'ncview']


def test_resolve_login_pixi_env_uses_distinct_login_prefix():
    login_env = deploy_run._resolve_login_pixi_env(
        prefix='/tmp/compute-env',
        pixi_cfg={'login_mpi': 'nompi'},
        runtime={},
        compute_mpi='hpc',
    )

    assert login_env == {
        'prefix': '/tmp/compute-env_login',
        'mpi': 'nompi',
        'mpi_prefix': 'nompi',
    }


def test_resolve_login_pixi_env_runtime_can_disable_login_env():
    login_env = deploy_run._resolve_login_pixi_env(
        prefix='/tmp/compute-env',
        pixi_cfg={'login_mpi': 'nompi'},
        runtime={'pixi': {'login_mpi': None}},
        compute_mpi='openmpi',
    )

    assert login_env is None


def test_write_load_script_includes_login_env_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'compute'),
        login_env={
            'prefix': str(tmp_path / 'login'),
            'mpi': 'nompi',
            'mpi_prefix': 'nompi',
        },
        pixi_exe=pixi_exe,
        branch_path=str(tmp_path),
        load_script_pixi_exe=_explicit_load_script_pixi(pixi_exe),
        software='e3sm-unified',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='pm-cpu',
        compute_pixi_mpi='hpc',
        toolchain_compiler='gnu',
        toolchain_mpi='mpich',
        spack_library_view=None,
        spack_activation='echo spack',
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert 'MACHE_DEPLOY_LOGIN_PIXI_TOML' in script_text
    assert '_mache_deploy_is_compute_node' in script_text
    assert 'MACHE_DEPLOY_ACTIVE_ENV_KIND' in script_text
    assert (
        'if [[ "${MACHE_DEPLOY_ACTIVE_ENV_KIND}" == "compute" ]]; then'
        in script_text
    )


def test_write_load_script_stages_shared_assets_and_omits_branch_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_root = tmp_path / 'repo'
    deploy_dir = repo_root / 'deploy'
    deploy_dir.mkdir(parents=True)
    (deploy_dir / 'load.sh').write_text(
        'export FROM_STAGED_SNIPPET=1\n',
        encoding='utf-8',
    )

    source_pixi = repo_root / 'pixi-source'
    source_pixi.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    source_pixi.chmod(0o755)

    monkeypatch.chdir(repo_root)

    compute_prefix = tmp_path / 'compute'
    login_prefix = tmp_path / 'login'
    script_path = deploy_run._write_load_script(
        prefix=str(compute_prefix),
        login_env={
            'prefix': str(login_prefix),
            'mpi': 'nompi',
            'mpi_prefix': 'nompi',
        },
        pixi_exe=str(source_pixi),
        branch_path=None,
        load_script_pixi_exe=_shared_load_script_pixi(),
        software='e3sm-unified',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine='pm-cpu',
        compute_pixi_mpi='hpc',
        toolchain_compiler='gnu',
        toolchain_mpi='mpich',
        spack_library_view=None,
        spack_activation='',
    )

    compute_staged_pixi = compute_prefix / 'bin' / 'pixi'
    login_staged_pixi = login_prefix / 'bin' / 'pixi'
    compute_staged_load = (
        compute_prefix / 'share' / 'mache' / 'deploy' / 'load.sh'
    )
    login_staged_load = login_prefix / 'share' / 'mache' / 'deploy' / 'load.sh'

    assert (
        compute_staged_pixi.read_text(encoding='utf-8')
        == '#!/bin/sh\nexit 0\n'
    )
    assert (
        login_staged_pixi.read_text(encoding='utf-8') == '#!/bin/sh\nexit 0\n'
    )
    assert (
        compute_staged_load.read_text(encoding='utf-8')
        == 'export FROM_STAGED_SNIPPET=1\n'
    )
    assert (
        login_staged_load.read_text(encoding='utf-8')
        == 'export FROM_STAGED_SNIPPET=1\n'
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert str(source_pixi) not in script_text
    assert str(deploy_dir / 'load.sh') not in script_text
    assert str(compute_staged_pixi) in script_text
    assert str(login_staged_pixi) in script_text
    assert str(compute_staged_load) in script_text
    assert str(login_staged_load) in script_text
    assert 'export PIXI="${MACHE_DEPLOY_ACTIVE_PIXI_EXE}"' in script_text
    assert (
        'export MACHE_DEPLOY_TARGET_LOAD_SNIPPET='
        '"${MACHE_DEPLOY_ACTIVE_TARGET_LOAD_SNIPPET}"' in script_text
    )
    assert 'E3SM_UNIFIED_BRANCH' not in script_text


def test_write_load_script_exports_branch_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'compute'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path='/shared/downstream/source',
        load_script_pixi_exe=_explicit_load_script_pixi('/shared/tools/pixi'),
        software='polaris',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine=None,
        compute_pixi_mpi='nompi',
        toolchain_compiler=None,
        toolchain_mpi=None,
        spack_library_view=None,
        spack_activation='',
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert 'export POLARIS_BRANCH="/shared/downstream/source"' in script_text
    assert (
        'export MACHE_DEPLOY_COMPUTE_PIXI_EXE="/shared/tools/pixi"'
        in script_text
    )


def test_write_load_script_uses_user_pixi_when_configured_for_path_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'compute'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path=str(tmp_path),
        load_script_pixi_exe=_path_load_script_pixi(),
        software='compass',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine=None,
        compute_pixi_mpi='nompi',
        toolchain_compiler=None,
        toolchain_mpi=None,
        spack_library_view=None,
        spack_activation='',
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert 'export MACHE_DEPLOY_COMPUTE_PIXI_EXE=""' in script_text
    assert (
        'if [[ -z "${MACHE_DEPLOY_ACTIVE_PIXI_EXE:-}" ]]; then' in script_text
    )
    assert 'command -v pixi' in script_text
    assert 'Set PIXI to a pixi executable path' in script_text


def test_write_load_script_without_login_env_skips_compute_detection(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'compute'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path=str(tmp_path),
        load_script_pixi_exe=_explicit_load_script_pixi(pixi_exe),
        software='e3sm-unified',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine=None,
        compute_pixi_mpi='mpich',
        toolchain_compiler=None,
        toolchain_mpi=None,
        spack_library_view=None,
        spack_activation='',
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert '_mache_deploy_is_compute_node' not in script_text
    assert 'MACHE_DEPLOY_ACTIVE_ENV_KIND="compute"' in script_text


def test_write_load_script_omits_optional_exports_when_values_are_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    pixi_exe = _make_pixi_executable(tmp_path)

    script_path = deploy_run._write_load_script(
        prefix=str(tmp_path / 'compute'),
        login_env=None,
        pixi_exe=pixi_exe,
        branch_path=None,
        load_script_pixi_exe=_path_load_script_pixi(),
        software='e3sm-unified',
        software_version='1.0.0',
        runtime_version_cmd=None,
        machine=None,
        compute_pixi_mpi='nompi',
        toolchain_compiler=None,
        toolchain_mpi=None,
        spack_library_view=None,
        spack_activation='',
    )

    script_text = Path(script_path).read_text(encoding='utf-8')
    assert 'export MACHE_DEPLOY_RUNTIME_VERSION_CMD=' not in script_text
    assert 'export MACHE_DEPLOY_LOGIN_PIXI_TOML=' not in script_text
    assert 'export MACHE_DEPLOY_TOOLCHAIN_COMPILER=' not in script_text
    assert 'export MACHE_DEPLOY_SPACK_LIBRARY_VIEW=' not in script_text
    assert 'export E3SM_UNIFIED_MACHINE=' not in script_text
    assert 'export E3SM_UNIFIED_COMPILER=' not in script_text
    assert 'export E3SM_UNIFIED_MPI=' not in script_text
    assert 'E3SM_UNIFIED_LOAD_SCRIPT' in script_text


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


def test_resolve_deploy_permissions_does_not_use_e3sm_unified_group():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('e3sm_unified')
    machine_config.set('e3sm_unified', 'group', 'legacy-group')

    group, world_readable = deploy_run._resolve_deploy_permissions(
        config={},
        runtime={},
        machine_config=machine_config,
    )

    assert group is None
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
        extra_prefixes=None,
        load_script_paths=[str(load_script)],
        spack_paths=[],
        shared_artifacts=SharedDeployArtifacts(
            managed_dirs=[],
            managed_files=[],
        ),
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
        extra_prefixes=None,
        load_script_paths=[],
        spack_paths=[],
        shared_artifacts=SharedDeployArtifacts(
            managed_dirs=[],
            managed_files=[],
        ),
        group=None,
        world_readable=True,
        logger=logger,
    )

    assert calls == []


def test_apply_deploy_permissions_includes_deployed_spack_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prefix = tmp_path / 'prefix'
    prefix.mkdir()

    spack_lib = tmp_path / 'spack-lib'
    spack_lib.mkdir()
    spack_soft = tmp_path / 'spack-soft'
    spack_soft.mkdir()

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
        extra_prefixes=None,
        load_script_paths=[],
        spack_paths=[str(spack_lib), str(spack_soft)],
        shared_artifacts=SharedDeployArtifacts(
            managed_dirs=[],
            managed_files=[],
        ),
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


def test_apply_deploy_permissions_includes_shared_managed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prefix = tmp_path / 'prefix'
    prefix.mkdir()

    shared_dir = tmp_path / 'shared'
    shared_dir.mkdir()
    shared_file = shared_dir / 'load_demo.sh'
    shared_file.write_text('#!/bin/sh\n', encoding='utf-8')

    calls = []

    def _fake_update_permissions(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        deploy_run, 'update_permissions', _fake_update_permissions
    )

    logger = deploy_run.logging.getLogger(
        'test-apply-deploy-permissions-shared'
    )
    logger.handlers = [deploy_run.logging.NullHandler()]
    logger.propagate = False

    deploy_run._apply_deploy_permissions(
        prefix=str(prefix),
        extra_prefixes=None,
        load_script_paths=[],
        spack_paths=[],
        shared_artifacts=SharedDeployArtifacts(
            managed_dirs=[str(shared_dir)],
            managed_files=[str(shared_file)],
        ),
        group='e3sm',
        world_readable=True,
        logger=logger,
    )

    assert len(calls) == 3

    first_args, first_kwargs = calls[0]
    assert first_args == (str(prefix), 'e3sm')
    assert first_kwargs['group_writable'] is True
    assert first_kwargs['recursive'] is False

    second_args, second_kwargs = calls[1]
    assert second_args == (str(shared_dir), 'e3sm')
    assert second_kwargs['group_writable'] is True
    assert second_kwargs['recursive'] is False

    third_args, third_kwargs = calls[2]
    assert third_args[1] == 'e3sm'
    assert third_args[0] == [str(shared_file)]
    assert third_kwargs['group_writable'] is False
    assert third_kwargs['recursive'] is True


def test_apply_deploy_permissions_updates_shared_base_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    shared_base = tmp_path / 'shared'
    shared_base.mkdir()

    prefix = shared_base / 'prefix'
    prefix.mkdir()
    (prefix / 'pixi.toml').write_text('[workspace]\n', encoding='utf-8')
    (prefix / 'bin').mkdir()

    load_script_in_base = shared_base / 'load_demo.sh'
    load_script_in_base.write_text('#!/bin/sh\n', encoding='utf-8')
    load_script_outside = tmp_path / 'load_external.sh'
    load_script_outside.write_text('#!/bin/sh\n', encoding='utf-8')

    spack_in_base = shared_base / 'spack'
    spack_in_base.mkdir()
    spack_outside = tmp_path / 'spack-outside'
    spack_outside.mkdir()

    managed_dir_in_base = shared_base / 'managed-dir'
    managed_dir_in_base.mkdir()
    managed_dir_outside = tmp_path / 'managed-dir-outside'
    managed_dir_outside.mkdir()

    managed_file_in_base = shared_base / 'managed.txt'
    managed_file_in_base.write_text('shared\n', encoding='utf-8')
    managed_file_outside = tmp_path / 'managed-outside.txt'
    managed_file_outside.write_text('outside\n', encoding='utf-8')

    calls = []

    def _fake_update_permissions(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        deploy_run, 'update_permissions', _fake_update_permissions
    )

    logger = deploy_run.logging.getLogger(
        'test-apply-deploy-permissions-shared-base'
    )
    logger.handlers = [deploy_run.logging.NullHandler()]
    logger.propagate = False

    deploy_run._apply_deploy_permissions(
        prefix=str(prefix),
        extra_prefixes=None,
        load_script_paths=[
            str(load_script_in_base),
            str(load_script_outside),
        ],
        spack_paths=[str(spack_in_base), str(spack_outside)],
        shared_artifacts=SharedDeployArtifacts(
            base_path=str(shared_base),
            managed_dirs=[
                str(managed_dir_in_base),
                str(managed_dir_outside),
            ],
            managed_files=[
                str(managed_file_in_base),
                str(managed_file_outside),
            ],
        ),
        group='e3sm',
        world_readable=True,
        logger=logger,
    )

    assert len(calls) == 3

    first_args, first_kwargs = calls[0]
    assert first_args == (str(shared_base), 'e3sm')
    assert first_kwargs['group_writable'] is True
    assert first_kwargs['other_readable'] is True
    assert first_kwargs['recursive'] is True

    second_args, second_kwargs = calls[1]
    assert second_args == (str(managed_dir_outside), 'e3sm')
    assert second_kwargs['group_writable'] is True
    assert second_kwargs['recursive'] is False

    third_args, third_kwargs = calls[2]
    assert third_args[1] == 'e3sm'
    assert sorted(third_args[0]) == sorted(
        [
            str(load_script_outside),
            str(spack_outside),
            str(managed_file_outside),
        ]
    )
    assert third_kwargs['group_writable'] is False
    assert third_kwargs['recursive'] is True


def test_pixi_install_writes_project_local_pixi_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = []

    def _fake_check_call(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(deploy_run, 'check_call', _fake_check_call)

    project_dir = tmp_path / 'prefix'
    project_dir.mkdir()

    deploy_run._pixi_install(
        pixi_exe='/usr/bin/pixi',
        project_dir=str(project_dir),
        recreate=False,
        log_filename=str(tmp_path / 'deploy.log'),
        quiet=True,
    )

    config_toml = project_dir / '.pixi' / 'config.toml'
    assert config_toml.is_file()
    assert '"https://conda.anaconda.org/conda-forge/label" = [' in (
        config_toml.read_text(encoding='utf-8')
    )
    assert len(calls) == 1


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

    assert deploy_run._get_deployed_spack_paths(
        spack_results=spack_results,
        spack_software_env=spack_software_env,
    ) == [
        '/opt/spack',
    ]
