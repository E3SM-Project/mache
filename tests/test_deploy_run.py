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
