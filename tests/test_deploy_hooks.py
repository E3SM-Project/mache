import argparse
import configparser
import logging
from pathlib import Path

import pytest

from mache.deploy.hooks import DeployContext, load_hooks


def _logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return logger


def test_load_hooks_no_section_is_noop(tmp_path: Path):
    # Even if a file exists, hooks are disabled unless the config opts in.
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        "def post_pixi(ctx):\n    raise RuntimeError('should not load')\n",
        encoding='utf-8',
    )

    reg = load_hooks(config={}, repo_root=str(tmp_path), logger=_logger('t1'))
    assert reg.file_path is None
    assert reg.entrypoints == {}


def test_load_hooks_missing_file_raises_when_configured(tmp_path: Path):
    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'entrypoints': {'post_pixi': 'post_pixi'},
        }
    }
    with pytest.raises(FileNotFoundError):
        load_hooks(config=cfg, repo_root=str(tmp_path), logger=_logger('t2'))


def test_load_hooks_loads_and_runs(tmp_path: Path):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        'from pathlib import Path\n'
        '\n'
        'def pre_pixi(ctx):\n'
        '    return {\n'
        "        'project': {'version': 'v1.2.3'},\n"
        "        'pixi': {'mpi': 'openmpi'},\n"
        '    }\n'
        '\n'
        'def post_pixi(ctx):\n'
        "    p = Path(ctx.work_dir) / 'ran.txt'\n"
        '    p.parent.mkdir(parents=True, exist_ok=True)\n'
        "    p.write_text('ok', encoding='utf-8')\n",
        encoding='utf-8',
    )

    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'entrypoints': {
                'pre_pixi': 'pre_pixi',
                'post_pixi': 'post_pixi',
            },
        }
    }

    logger = _logger('t3')
    reg = load_hooks(config=cfg, repo_root=str(tmp_path), logger=logger)

    ctx = DeployContext(
        software='demo',
        machine=None,
        repo_root=str(tmp_path),
        deploy_dir=str(tmp_path / 'deploy'),
        work_dir=str(tmp_path / 'deploy_tmp'),
        config=cfg,
        pins={},
        machine_config=configparser.ConfigParser(),
        args=argparse.Namespace(),
        logger=logger,
    )

    reg.run_hook('pre_pixi', ctx)
    assert ctx.runtime['project']['version'] == 'v1.2.3'
    assert ctx.runtime['pixi']['mpi'] == 'openmpi'

    reg.run_hook('post_pixi', ctx)
    assert (tmp_path / 'deploy_tmp' / 'ran.txt').read_text(
        encoding='utf-8'
    ) == 'ok'


def test_load_hooks_missing_entrypoint_function_raises(tmp_path: Path):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text('x = 1\n', encoding='utf-8')

    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'entrypoints': {'post_pixi': 'does_not_exist'},
        }
    }

    with pytest.raises(AttributeError):
        load_hooks(config=cfg, repo_root=str(tmp_path), logger=_logger('t4'))
