import argparse
import configparser
import io
import json
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
    pre_pixi_context_path = (
        tmp_path / 'deploy_tmp' / 'hooks' / 'pre_pixi_context.json'
    )
    pre_pixi_snapshot = json.loads(
        pre_pixi_context_path.read_text(encoding='utf-8')
    )
    assert pre_pixi_snapshot['status'] == 'ok'
    assert pre_pixi_snapshot['context']['runtime_before'] == {}
    assert pre_pixi_snapshot['context']['runtime_after'] == {
        'pixi': {'mpi': 'openmpi'},
        'project': {'version': 'v1.2.3'},
    }
    assert pre_pixi_snapshot['hook_result'] == {
        'pixi': {'mpi': 'openmpi'},
        'project': {'version': 'v1.2.3'},
    }

    reg.run_hook('post_pixi', ctx)
    assert (tmp_path / 'deploy_tmp' / 'ran.txt').read_text(
        encoding='utf-8'
    ) == 'ok'
    post_pixi_snapshot = json.loads(
        (
            tmp_path / 'deploy_tmp' / 'hooks' / 'post_pixi_context.json'
        ).read_text(encoding='utf-8')
    )
    assert post_pixi_snapshot['status'] == 'ok'
    assert post_pixi_snapshot['context']['runtime_after'] == {
        'pixi': {'mpi': 'openmpi'},
        'project': {'version': 'v1.2.3'},
    }


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


def test_load_hooks_logs_context_when_enabled(tmp_path: Path):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        'def pre_pixi(ctx):\n    return {"project": {"version": "v9.9.9"}}\n',
        encoding='utf-8',
    )

    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'log_context': True,
            'entrypoints': {'pre_pixi': 'pre_pixi'},
        }
    }

    log_stream = io.StringIO()
    logger = logging.getLogger('t5')
    logger.setLevel(logging.INFO)
    logger.handlers = [logging.StreamHandler(log_stream)]
    logger.propagate = False

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

    log_text = log_stream.getvalue()
    assert 'Hook context snapshot stage=pre_pixi' in log_text
    assert '"runtime_after": {' in log_text
    assert '"version": "v9.9.9"' in log_text


def test_load_hooks_writes_failure_snapshot(tmp_path: Path):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        'def pre_pixi(ctx):\n    raise ValueError("boom")\n',
        encoding='utf-8',
    )

    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'entrypoints': {'pre_pixi': 'pre_pixi'},
        }
    }

    logger = _logger('t6')
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

    with pytest.raises(RuntimeError, match='Hook failed: stage=pre_pixi'):
        reg.run_hook('pre_pixi', ctx)

    snapshot_path = tmp_path / 'deploy_tmp' / 'hooks' / 'pre_pixi_context.json'
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    assert snapshot['status'] == 'failed'
    assert snapshot['context']['runtime_before'] == {}
    assert snapshot['context']['runtime_after'] == {}
    assert snapshot['error'] == {
        'type': 'ValueError',
        'message': 'boom',
    }


def test_load_hooks_maps_post_deploy_alias_to_pre_publish(tmp_path: Path):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        "def post_deploy(ctx):\n    ctx.runtime['alias_ran'] = True\n",
        encoding='utf-8',
    )

    logger = logging.getLogger('t7')
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.handlers = [handler]
    logger.propagate = False

    reg = load_hooks(
        config={
            'hooks': {
                'file': 'deploy/hooks.py',
                'entrypoints': {'post_deploy': 'post_deploy'},
            }
        },
        repo_root=str(tmp_path),
        logger=logger,
    )

    assert 'pre_publish' in reg.entrypoints
    assert 'post_deploy' not in reg.entrypoints
    assert 'deprecated' in stream.getvalue()

    ctx = DeployContext(
        software='demo',
        machine=None,
        repo_root=str(tmp_path),
        deploy_dir=str(tmp_path / 'deploy'),
        work_dir=str(tmp_path / 'deploy_tmp'),
        config={},
        pins={},
        machine_config=configparser.ConfigParser(),
        args=argparse.Namespace(),
        logger=logger,
    )

    reg.run_hook('pre_publish', ctx)
    assert ctx.runtime['alias_ran'] is True


def test_load_hooks_rejects_post_deploy_and_pre_publish_together(
    tmp_path: Path,
):
    (tmp_path / 'deploy').mkdir(parents=True)
    (tmp_path / 'deploy' / 'hooks.py').write_text(
        'def old_name(ctx):\n'
        '    return None\n'
        '\n'
        'def new_name(ctx):\n'
        '    return None\n',
        encoding='utf-8',
    )

    cfg = {
        'hooks': {
            'file': 'deploy/hooks.py',
            'entrypoints': {
                'post_deploy': 'old_name',
                'pre_publish': 'new_name',
            },
        }
    }

    with pytest.raises(
        ValueError,
        match='deprecated alias for hooks.entrypoints.pre_publish',
    ):
        load_hooks(config=cfg, repo_root=str(tmp_path), logger=_logger('t8'))
