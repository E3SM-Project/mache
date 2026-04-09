import os
from pathlib import Path

import pytest

from mache.deploy.shared import (
    SharedDeployArtifacts,
    create_shared_deploy_artifacts,
)


def test_create_shared_deploy_artifacts_copies_load_scripts_and_links(
    tmp_path: Path,
):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    source_script = repo_root / 'load_demo.sh'
    source_script.write_text(
        (f'#!/bin/bash\nexport DEMO_LOAD_SCRIPT="{source_script}"\n'),
        encoding='utf-8',
    )

    extra_dir = repo_root / 'shared' / 'extra-dir'
    extra_dir.mkdir(parents=True)
    extra_file = repo_root / 'shared' / 'extra.txt'
    extra_file.write_text('x\n', encoding='utf-8')

    artifacts = create_shared_deploy_artifacts(
        config={
            'shared': {
                'load_script_copies': [
                    'shared/load_demo_shared.sh',
                ],
                'load_script_symlinks': [
                    {
                        'path': 'shared/load_demo_latest.sh',
                        'target': 'shared/load_demo_shared.sh',
                    }
                ],
                'managed_directories': ['shared/extra-dir'],
                'managed_files': ['shared/extra.txt'],
            }
        },
        runtime={},
        repo_root=str(repo_root),
        load_script_paths=[str(source_script)],
        logger=_logger(),
    )

    copied_script = repo_root / 'shared' / 'load_demo_shared.sh'
    latest_link = repo_root / 'shared' / 'load_demo_latest.sh'

    assert copied_script.read_text(encoding='utf-8') == (
        f'#!/bin/bash\nexport DEMO_LOAD_SCRIPT="{copied_script.resolve()}"\n'
    )
    assert latest_link.is_symlink()
    assert os.readlink(latest_link) == str(copied_script)
    assert artifacts == SharedDeployArtifacts(
        managed_dirs=[
            str(extra_dir),
            str(copied_script.parent),
        ],
        managed_files=[
            str(extra_file),
            str(copied_script),
        ],
    )


def test_create_shared_deploy_artifacts_requires_single_load_script(
    tmp_path: Path,
):
    with pytest.raises(
        ValueError,
        match='require exactly one generated load script',
    ):
        create_shared_deploy_artifacts(
            config={'shared': {'load_script_copies': ['shared/load_demo.sh']}},
            runtime={},
            repo_root=str(tmp_path),
            load_script_paths=['load_a.sh', 'load_b.sh'],
            logger=_logger(),
        )


def test_create_shared_deploy_artifacts_requires_existing_symlink_target(
    tmp_path: Path,
):
    source_script = tmp_path / 'load_demo.sh'
    source_script.write_text('#!/bin/bash\n', encoding='utf-8')

    with pytest.raises(
        FileNotFoundError,
        match='Shared load-script symlink target does not exist',
    ):
        create_shared_deploy_artifacts(
            config={
                'shared': {
                    'load_script_symlinks': [
                        {
                            'path': 'shared/load_demo_latest.sh',
                            'target': 'shared/load_demo_shared.sh',
                        }
                    ]
                }
            },
            runtime={},
            repo_root=str(tmp_path),
            load_script_paths=[str(source_script)],
            logger=_logger(),
        )


def _logger():
    import logging

    logger = logging.getLogger('test-deploy-shared')
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return logger
