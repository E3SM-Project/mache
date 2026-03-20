import os
import sys
from pathlib import Path

import pytest

from workflow_tests.helpers import (
    clone_jigsaw_python,
    configure_generated_deploy_files,
    copy_fixture_repo,
    init_and_update_repo,
    make_workflow_env,
    run,
)


def _setup_meshflow_repo(
    *,
    tmp_path: Path,
    overrides_name: str,
) -> tuple[Path, dict[str, str]]:
    downstream = tmp_path / 'meshflow-downstream'
    copy_fixture_repo('meshflow_repo', downstream)
    try:
        clone_jigsaw_python(dest=downstream / 'jigsaw-python')
    except RuntimeError as exc:
        if os.environ.get('CI'):
            raise
        pytest.skip(str(exc))

    env = make_workflow_env()

    init_and_update_repo(
        downstream=downstream,
        software='meshflow',
        env=env,
    )
    configure_generated_deploy_files(downstream, overrides_name)
    return downstream, env


def test_meshflow_deploy_workflow_installs_jigsaw_into_deployed_manifest(
    tmp_path: Path,
):
    import shutil

    pixi = shutil.which('pixi')
    if pixi is None:
        pytest.skip('pixi is required for workflow tests')
    assert pixi is not None

    downstream, env = _setup_meshflow_repo(
        tmp_path=tmp_path,
        overrides_name='meshflow_deploy_overrides',
    )
    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'

    run(
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

    manifest_text = (downstream / 'pixi-env' / 'pixi.toml').read_text(
        encoding='utf-8'
    )
    assert 'jigsawpy' in manifest_text

    smoke = run(
        [
            'bash',
            '-lc',
            'set -euo pipefail && '
            'source load_meshflow.sh && '
            'test "${MESHFLOW_DEPLOY_SENTINEL}" = "workflow-ok" && '
            'python -c "import jigsawpy; print(jigsawpy.__version__)"',
        ],
        cwd=downstream,
        env=env,
    )
    assert smoke.stdout.strip()


def test_meshflow_cli_jigsaw_install_uses_local_pixi_manifest(
    tmp_path: Path,
):
    import shutil

    pixi = shutil.which('pixi')
    if pixi is None:
        pytest.skip('pixi is required for workflow tests')
    assert pixi is not None

    downstream, env = _setup_meshflow_repo(
        tmp_path=tmp_path,
        overrides_name='meshflow_cli_overrides',
    )
    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'

    run(
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

    run(
        [
            'bash',
            '-lc',
            'set -euo pipefail && '
            'source load_meshflow.sh && '
            'test "${MESHFLOW_DEPLOY_SENTINEL}" = "workflow-ok" && '
            'meshflow --version && '
            'meshflow jigsaw install',
        ],
        cwd=downstream,
        env=env,
    )

    local_manifest = (
        downstream / '.mache_cache' / 'jigsaw' / 'pixi-local' / 'pixi.toml'
    )
    assert local_manifest.is_file()
    local_text = local_manifest.read_text(encoding='utf-8')
    assert '[feature.jigsaw.dependencies]' in local_text
    assert 'jigsaw = ["jigsaw"]' in local_text
    assert 'jigsawpy' not in (downstream / 'pixi-env' / 'pixi.toml').read_text(
        encoding='utf-8'
    )

    smoke = run(
        [
            'bash',
            '-lc',
            'set -euo pipefail && '
            f'pixi run -m {local_manifest} -e jigsaw '
            'python -c "import jigsawpy; print(jigsawpy.__version__)"',
        ],
        cwd=downstream,
        env=env,
    )
    assert smoke.stdout.strip()
