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
) -> DeployContext:
    return DeployContext(
        software='demo',
        machine='chrysalis',
        repo_root=str(tmp_path),
        deploy_dir=str(tmp_path / 'deploy'),
        work_dir=str(tmp_path / 'deploy_tmp'),
        config={},
        pins={},
        machine_config=configparser.ConfigParser(),
        args=args,
        logger=_logger('deploy-spack-test'),
        runtime=runtime or {},
    )


def test_resolve_spack_path_prefers_cli(tmp_path: Path):
    args = argparse.Namespace(spack_path='~/cli-spack')
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
    args = argparse.Namespace(spack_path=None)
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
    args = argparse.Namespace(spack_path=None)
    ctx = _ctx(tmp_path, args=args, runtime={})

    with pytest.raises(ValueError, match='--spack-path'):
        deploy_spack._resolve_spack_path(
            ctx=ctx,
            spack_cfg={},
            reason='deployment is enabled',
        )
