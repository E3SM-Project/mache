from pathlib import Path

import pytest

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
