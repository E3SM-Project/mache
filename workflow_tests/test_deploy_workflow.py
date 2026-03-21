import json
import shutil
import sys
from pathlib import Path

import pytest

from workflow_tests.helpers import (
    configure_deploy_files,
    configure_generated_deploy_files,
    copy_fixture_repo,
    init_and_update_repo,
    mache_version,
    make_workflow_env,
    run,
)


def test_downstream_deploy_workflow(tmp_path: Path):
    pixi = shutil.which('pixi')
    if pixi is None:
        pytest.skip('pixi is required for workflow tests')
    assert pixi is not None

    downstream = tmp_path / 'toyflow-downstream'
    copy_fixture_repo('toyflow_repo', downstream)

    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
    expected_mache_version = mache_version()
    env = make_workflow_env()

    init_and_update_repo(
        downstream=downstream,
        software='toyflow',
        env=env,
    )

    preserved_files = configure_generated_deploy_files(
        downstream, 'deploy_overrides'
    )

    cli_spec = json.loads(
        (downstream / 'deploy' / 'cli_spec.json').read_text(encoding='utf-8')
    )
    assert cli_spec['meta']['software'] == 'toyflow'
    assert cli_spec['meta']['mache_version'] == expected_mache_version
    assert (downstream / 'deploy.py').read_text(encoding='utf-8') != (
        '# stale deploy.py\n'
    )

    for relpath, expected in preserved_files.items():
        assert (downstream / 'deploy' / relpath).read_text(
            encoding='utf-8'
        ) == expected

    configure_deploy_files(
        downstream,
        'deploy_hook_overrides',
        relpaths=('config.yaml.j2', 'custom_cli_spec.json', 'hooks.py'),
    )

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
            '--with-albany',
            '--recreate',
        ],
        cwd=downstream,
        env=env,
    )

    load_script = downstream / 'load_toyflow.sh'
    assert load_script.is_file()
    assert (downstream / 'deploy_tmp' / 'with_albany.txt').read_text(
        encoding='utf-8'
    ) == 'enabled\n'

    smoke = run(
        [
            'bash',
            '-lc',
            'set -euo pipefail && '
            'source load_toyflow.sh && '
            'test "${TOYFLOW_DEPLOY_SENTINEL}" = "workflow-ok" && '
            'python -c "from toyflow.version import __version__; '
            'print(__version__)" && '
            'toyflow --version && '
            'pytest tests/smoke_check.py -q',
        ],
        cwd=downstream,
        env=env,
    )

    assert '0.1.0' in smoke.stdout
