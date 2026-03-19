from pathlib import Path

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
