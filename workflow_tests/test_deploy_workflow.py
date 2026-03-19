import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixtures_dir() -> Path:
    return _repo_root() / 'workflow_tests' / 'fixtures'


def _mache_version() -> str:
    namespace: dict[str, str] = {}
    exec(
        (_repo_root() / 'mache' / 'version.py').read_text(encoding='utf-8'),
        namespace,
    )
    return namespace['__version__']


def _copy_downstream_repo(dest: Path) -> None:
    shutil.copytree(_fixtures_dir() / 'toyflow_repo', dest)


def _configure_generated_deploy_files(repo_root: Path) -> dict[str, str]:
    deploy_dir = repo_root / 'deploy'
    overrides_dir = _fixtures_dir() / 'deploy_overrides'
    relpaths = ('config.yaml.j2', 'pixi.toml.j2', 'load.sh')
    expected: dict[str, str] = {}

    for relpath in relpaths:
        source = overrides_dir / relpath
        text = source.read_text(encoding='utf-8')
        (deploy_dir / relpath).write_text(text, encoding='utf-8')
        expected[relpath] = text

    return expected


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def test_downstream_deploy_workflow(tmp_path: Path):
    pixi = shutil.which('pixi')
    if pixi is None:
        pytest.skip('pixi is required for workflow tests')
    assert pixi is not None

    source_repo = _repo_root()
    downstream = tmp_path / 'toyflow-downstream'
    _copy_downstream_repo(downstream)

    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
    mache_version = _mache_version()
    env = os.environ.copy()
    pythonpath = env.get('PYTHONPATH')
    env['PYTHONPATH'] = (
        f'{source_repo}:{pythonpath}' if pythonpath else str(source_repo)
    )

    _run(
        [
            sys.executable,
            '-m',
            'mache',
            'deploy',
            'init',
            '--repo-root',
            str(downstream),
            '--software',
            'toyflow',
            '--mache-version',
            mache_version,
        ],
        cwd=source_repo,
        env=env,
    )

    preserved_files = _configure_generated_deploy_files(downstream)

    (downstream / 'deploy.py').write_text(
        '# stale deploy.py\n',
        encoding='utf-8',
    )
    (downstream / 'deploy' / 'cli_spec.json').write_text(
        '{"stale": true}\n',
        encoding='utf-8',
    )

    _run(
        [
            sys.executable,
            '-m',
            'mache',
            'deploy',
            'update',
            '--repo-root',
            str(downstream),
            '--software',
            'toyflow',
            '--mache-version',
            mache_version,
        ],
        cwd=source_repo,
        env=env,
    )

    cli_spec = json.loads(
        (downstream / 'deploy' / 'cli_spec.json').read_text(encoding='utf-8')
    )
    assert cli_spec['meta']['software'] == 'toyflow'
    assert cli_spec['meta']['mache_version'] == mache_version
    assert (downstream / 'deploy.py').read_text(encoding='utf-8') != (
        '# stale deploy.py\n'
    )

    for relpath, expected in preserved_files.items():
        assert (downstream / 'deploy' / relpath).read_text(
            encoding='utf-8'
        ) == expected

    env['MACHE_BOOTSTRAP_URL'] = (
        (source_repo / 'mache' / 'deploy' / 'bootstrap.py').resolve().as_uri()
    )
    env['MACHE_LOCAL_SOURCE_PATH'] = str(source_repo)

    _run(
        [
            str(downstream / 'deploy.py'),
            '--pixi',
            pixi,
            '--python',
            python_version,
            '--mache-fork',
            'local/mache',
            '--mache-branch',
            'current',
            '--recreate',
        ],
        cwd=downstream,
        env=env,
    )

    load_script = downstream / 'load_toyflow.sh'
    assert load_script.is_file()

    smoke = _run(
        [
            'bash',
            '-lc',
            'set -euo pipefail && '
            'source load_toyflow.sh && '
            'test "${TOYFLOW_DEPLOY_SENTINEL}" = "workflow-ok" && '
            'python -c "from toyflow.version import __version__; '
            'print(__version__)" && '
            'toyflow --version && '
            'pytest tests/test_smoke.py -q',
        ],
        cwd=downstream,
        env=env,
    )

    assert '0.1.0' in smoke.stdout
