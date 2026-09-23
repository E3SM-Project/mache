import argparse
import configparser
import logging
from pathlib import Path

import pytest

from mache.deploy import spack as deploy_spack
from mache.deploy.hooks import DeployContext
from mache.spack.script import get_spack_script
from mache.spack.shared import (
    E3SM_HDF5_NETCDF_PACKAGES,
    _get_yaml_data,
)


def _logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return logger


def _ctx(
    tmp_path: Path,
    *,
    args: argparse.Namespace,
    runtime: dict | None = None,
    config: dict | None = None,
) -> DeployContext:
    return DeployContext(
        software='demo',
        machine='chrysalis',
        repo_root=str(tmp_path),
        deploy_dir=str(tmp_path / 'deploy'),
        work_dir=str(tmp_path / 'deploy_tmp'),
        config=config or {},
        pins={},
        machine_config=configparser.ConfigParser(),
        args=args,
        logger=_logger('deploy-spack-test'),
        runtime=runtime or {},
    )


def test_resolve_spack_path_prefers_cli(tmp_path: Path):
    args = argparse.Namespace(spack_path='~/cli-spack', no_spack=False)
    ctx = _ctx(
        tmp_path,
        args=args,
        runtime={'spack': {'spack_path': '/runtime-spack'}},
    )

    resolved = deploy_spack._resolve_spack_path(
        ctx=ctx,
        spack_cfg={'spack_path': '/config-spack'},
        reason='deployment is enabled',
    )

    # the path is expanded and made absolute, not resolved through
    # symlinks, so a symlinked home must not be followed here either
    assert resolved == str(Path.home() / 'cli-spack')


def test_resolve_spack_path_uses_runtime_then_config(tmp_path: Path):
    args = argparse.Namespace(spack_path=None, no_spack=False)
    ctx = _ctx(
        tmp_path,
        args=args,
        runtime={'spack': {'spack_path': '/runtime-spack'}},
    )

    resolved = deploy_spack._resolve_spack_path(
        ctx=ctx,
        spack_cfg={'spack_path': '/config-spack'},
        reason='support is enabled',
    )

    assert resolved == '/runtime-spack'


def test_resolve_spack_path_error_mentions_cli_override(tmp_path: Path):
    args = argparse.Namespace(spack_path=None, no_spack=False)
    ctx = _ctx(tmp_path, args=args, runtime={})

    with pytest.raises(ValueError, match='--no-spack'):
        deploy_spack._resolve_spack_path(
            ctx=ctx,
            spack_cfg={},
            reason='deployment is enabled',
        )


def test_effective_spack_config_applies_runtime_overrides(tmp_path: Path):
    args = argparse.Namespace(
        spack_path=None, deploy_spack=False, no_spack=False
    )
    ctx = _ctx(
        tmp_path,
        args=args,
        config={
            'spack': {
                'deploy': False,
                'supported': True,
                'software': {'supported': True, 'env_name': 'demo_software'},
            }
        },
        runtime={
            'spack': {'supported': False, 'software': {'supported': False}}
        },
    )

    spack_cfg = deploy_spack.get_effective_spack_config(ctx=ctx)

    assert spack_cfg['supported'] is False
    assert spack_cfg['software']['supported'] is False
    assert spack_cfg['software']['env_name'] == 'demo_software'


def test_no_spack_flag_disables_spack_deploy_even_if_requested(tmp_path: Path):
    args = argparse.Namespace(
        spack_path=None, deploy_spack=True, no_spack=True
    )
    ctx = _ctx(tmp_path, args=args)

    assert deploy_spack.spack_disabled_for_run(ctx=ctx) is True
    assert (
        deploy_spack.spack_should_deploy_for_run(
            ctx=ctx, spack_cfg={'deploy': True}
        )
        is False
    )


def test_load_existing_spack_envs_respects_runtime_disable(tmp_path: Path):
    args = argparse.Namespace(
        spack_path=None, deploy_spack=False, no_spack=False
    )
    ctx = _ctx(
        tmp_path,
        args=args,
        config={
            'spack': {
                'supported': True,
                'software': {'supported': True},
            }
        },
        runtime={
            'spack': {'supported': False, 'software': {'supported': False}}
        },
    )

    assert (
        deploy_spack.load_existing_spack_envs(
            ctx=ctx, toolchain_pairs=[('gnu', 'mpich')]
        )
        == []
    )
    assert deploy_spack.load_existing_spack_software_env(ctx=ctx) is None


def test_resolve_software_toolchain_error_mentions_machine_and_key():
    machine_config = configparser.ConfigParser()
    machine_config.add_section('deploy')

    with pytest.raises(ValueError) as excinfo:
        deploy_spack._resolve_software_toolchain(
            machine_config=machine_config, machine='chrysalis'
        )

    message = str(excinfo.value)
    assert "machine 'chrysalis'" in message
    assert '[deploy] software_compiler' in message
    assert '[deploy] mpi_<software_compiler>' in message


def test_get_excluded_spack_packages_supports_bundle_aliases():
    excluded = deploy_spack._get_excluded_spack_packages(
        {'exclude_packages': 'cmake, e3sm_hdf5_netcdf'}
    )

    assert 'cmake' in excluded
    assert E3SM_HDF5_NETCDF_PACKAGES.issubset(excluded)


def test_get_yaml_data_can_exclude_cmake_external():
    yaml_text = _get_yaml_data(
        machine='chicoma-cpu',
        compiler='gnu',
        mpi='mpich',
        include_e3sm_lapack=False,
        e3sm_hdf5_netcdf=False,
        specs=['trilinos'],
        yaml_template=None,
        exclude_packages=['cmake'],
    )

    assert 'cmake:' not in yaml_text
    assert 'curl:' in yaml_text
    assert '- trilinos' in yaml_text


def test_get_yaml_data_can_exclude_e3sm_hdf5_netcdf_bundle():
    yaml_text = _get_yaml_data(
        machine='chicoma-cpu',
        compiler='gnu',
        mpi='mpich',
        include_e3sm_lapack=False,
        e3sm_hdf5_netcdf=True,
        specs=['trilinos'],
        yaml_template=None,
        exclude_packages=['hdf5_netcdf'],
    )

    assert 'hdf5:' not in yaml_text
    assert 'netcdf-c:' not in yaml_text
    assert 'netcdf-fortran:' not in yaml_text
    assert 'parallel-netcdf:' not in yaml_text
    assert '- hdf5' not in yaml_text
    assert '- netcdf-c' not in yaml_text


def test_get_spack_script_filters_compy_template_modules():
    script = get_spack_script(
        spack_path='/unused',
        env_name='unused',
        compiler='gnu',
        mpi='openmpi',
        shell='sh',
        machine='compy',
        load_spack_env=False,
        e3sm_hdf5_netcdf=True,
        exclude_packages=['hdf5_netcdf'],
    )

    assert 'gcc/10.2.0' in script
    assert 'openmpi/4.0.1' in script
    assert 'hdf5/1.10.5' not in script
    assert 'netcdf/4.6.3' not in script
    assert 'pnetcdf/1.9.0' not in script


def test_get_spack_script_filters_config_machine_cmake_module():
    script = get_spack_script(
        spack_path='/unused',
        env_name='unused',
        compiler='gnu',
        mpi='mpich',
        shell='sh',
        machine='chicoma-cpu',
        load_spack_env=False,
        e3sm_hdf5_netcdf=True,
        exclude_packages=['cmake'],
    )

    assert 'PrgEnv-gnu/8.5.0' in script
    assert 'cray-mpich/8.1.28' in script
    assert 'cmake/3.29.6' not in script


def test_load_spack_pins_precedence(tmp_path: Path):
    pins_file = tmp_path / 'pins.yaml'
    pins_file.write_text('repos:\n  e3sm:\n    commit: fromcli\n')
    args = argparse.Namespace(spack_pins=str(pins_file), no_spack=False)
    ctx = _ctx(
        tmp_path,
        args=args,
        config={
            'spack': {
                'pins': {
                    'spack': {'branch': 'fromconfig'},
                    'repos': {'builtin': {'branch': 'fromconfig'}},
                }
            }
        },
        runtime={
            'spack': {'pins': {'repos': {'builtin': {'tag': 'fromruntime'}}}}
        },
    )

    pins = deploy_spack._load_spack_pins(ctx=ctx)

    assert pins['spack']['branch'] == 'fromconfig'
    assert pins['repos']['builtin'] == {
        'git': 'https://github.com/spack/spack-packages.git',
        'tag': 'fromruntime',
    }
    assert pins['repos']['e3sm']['commit'] == 'fromcli'
    assert 'tag' not in pins['repos']['e3sm']


def test_load_spack_pins_defaults_to_packaged(tmp_path: Path):
    args = argparse.Namespace(no_spack=False)
    ctx = _ctx(tmp_path, args=args, config={'spack': {'pins': {}}})

    pins = deploy_spack._load_spack_pins(ctx=ctx)

    assert pins['spack']['tag'] == 'v1.2.2'
    assert list(pins['repos']) == ['e3sm', 'builtin']


def test_spack_activation_mode_and_build_jobs():
    assert deploy_spack.get_spack_activation_mode({}) == 'captured'
    assert deploy_spack.get_spack_activation_mode({'activation': None}) == (
        'captured'
    )
    assert (
        deploy_spack.get_spack_activation_mode({'activation': 'Dynamic'})
        == 'dynamic'
    )
    with pytest.raises(ValueError, match='spack.activation'):
        deploy_spack.get_spack_activation_mode({'activation': 'lazy'})

    assert deploy_spack._get_build_jobs({}) is None
    assert deploy_spack._get_build_jobs({'build_jobs': None}) is None
    assert deploy_spack._get_build_jobs({'build_jobs': 8}) == 8
    assert deploy_spack._get_build_jobs({'build_jobs': '4'}) == 4
    with pytest.raises(ValueError, match='build_jobs'):
        deploy_spack._get_build_jobs({'build_jobs': 0})
    with pytest.raises(ValueError, match='build_jobs'):
        deploy_spack._get_build_jobs({'build_jobs': 'many'})


def _existing_env(tmp_path: Path, env_name: str, captured: bool) -> str:
    spack_path = tmp_path / 'spack'
    env_dir = spack_path / 'var' / 'spack' / 'environments' / env_name
    env_dir.mkdir(parents=True)
    if captured:
        (env_dir / 'activate.sh').write_text('export SPACK_ENV=x\n')
    return str(spack_path)


def test_load_existing_spack_envs_captured(tmp_path: Path):
    spack_path = _existing_env(tmp_path, 'spack_env_gnu_openmpi', True)
    args = argparse.Namespace(
        spack_path=spack_path, deploy_spack=False, no_spack=False
    )
    ctx = _ctx(tmp_path, args=args, config={'spack': {'supported': True}})

    results = deploy_spack.load_existing_spack_envs(
        ctx=ctx, toolchain_pairs=[('gnu', 'openmpi')]
    )

    assert len(results) == 1
    result = results[0]
    assert result.activation.startswith(
        f'source {spack_path}/share/spack/setup-env.sh\n'
        'spack env activate spack_env_gnu_openmpi\n'
    )
    assert result.load_activation.startswith(
        f'source {spack_path}/var/spack/environments/spack_env_gnu_openmpi/'
        'activate.sh\n'
    )
    assert result.load_activation != result.activation


def test_load_existing_spack_envs_requires_captured_activation(
    tmp_path: Path,
):
    spack_path = _existing_env(tmp_path, 'spack_env_gnu_openmpi', False)
    args = argparse.Namespace(
        spack_path=spack_path, deploy_spack=False, no_spack=False
    )
    ctx = _ctx(tmp_path, args=args, config={'spack': {'supported': True}})

    with pytest.raises(ValueError, match='redeploy'):
        deploy_spack.load_existing_spack_envs(
            ctx=ctx, toolchain_pairs=[('gnu', 'openmpi')]
        )

    # dynamic activation needs no captured file and uses the same form for
    # hooks and load scripts
    ctx = _ctx(
        tmp_path,
        args=args,
        config={'spack': {'supported': True, 'activation': 'dynamic'}},
    )
    results = deploy_spack.load_existing_spack_envs(
        ctx=ctx, toolchain_pairs=[('gnu', 'openmpi')]
    )
    assert results[0].load_activation == results[0].activation
    assert 'spack env activate' in results[0].load_activation


def test_capture_spack_activations_skipped_when_dynamic(tmp_path: Path):
    args = argparse.Namespace(no_spack=False)
    ctx = _ctx(
        tmp_path,
        args=args,
        config={'spack': {'activation': 'dynamic'}},
    )
    result = deploy_spack.SpackDeployResult(
        compiler='gnu',
        mpi='openmpi',
        env_name='spack_env_gnu_openmpi',
        spack_path='/nonexistent',
        view_path='/nonexistent/view',
        activation='',
    )
    # would fail if it tried to run anything against /nonexistent
    deploy_spack.capture_spack_activations(ctx=ctx, results=[result])


def test_install_spack_env_creates_tmpdir(tmp_path: Path, monkeypatch):
    commands = []
    monkeypatch.setattr(
        deploy_spack,
        'check_call',
        lambda cmd, *args, **kwargs: commands.append(cmd),
    )
    ctx = _ctx(tmp_path, args=argparse.Namespace())
    tmpdir = tmp_path / 'spack-tmp'

    deploy_spack._install_spack_env(
        ctx=ctx,
        spack_path=str(tmp_path / 'spack'),
        env_name='demo_gnu_openmpi',
        yaml_path=str(tmp_path / 'demo_gnu_openmpi.yaml'),
        compiler='gnu',
        mpi='openmpi',
        tmpdir=str(tmpdir),
        mirror=None,
        custom_spack='',
        e3sm_hdf5_netcdf=True,
        pins=deploy_spack.load_pins(),
        build_jobs=None,
        log_filename=str(tmp_path / 'deploy.log'),
        quiet=True,
    )

    assert tmpdir.is_dir()
    script = tmp_path / 'deploy_tmp/spack/build_demo_gnu_openmpi.bash'
    assert f'export TMPDIR={tmpdir}' in script.read_text()
    assert len(commands) == 1
