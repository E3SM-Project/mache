import argparse
import configparser
import logging
from pathlib import Path

import pytest

from mache.deploy import spack as deploy_spack
from mache.deploy.hooks import DeployContext


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

    assert resolved == str((Path.home() / 'cli-spack').resolve())


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
