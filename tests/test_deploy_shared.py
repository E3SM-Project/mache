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
        base_path=None,
        managed_dirs=[
            str(copied_script.parent),
        ],
        managed_files=[
            str(extra_file),
            str(copied_script),
        ],
        managed_recursive_dirs=[
            str(extra_dir),
        ],
    )


def test_create_shared_deploy_artifacts_resolves_runtime_base_path(
    tmp_path: Path,
):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    artifacts = create_shared_deploy_artifacts(
        config={'shared': {'base_path': 'shared/from-config'}},
        runtime={'shared': {'base_path': 'shared/from-runtime'}},
        repo_root=str(repo_root),
        load_script_paths=[],
        logger=_logger(),
    )

    assert artifacts == SharedDeployArtifacts(
        base_path=str(repo_root / 'shared' / 'from-runtime'),
        managed_dirs=[],
        managed_files=[],
    )


def test_create_shared_deploy_artifacts_marks_writable_roots(
    tmp_path: Path,
):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    readonly_dir = repo_root / 'shared' / 'readonly'
    writable_dir = repo_root / 'shared' / 'writable'
    duplicate_dir = repo_root / 'shared' / 'duplicate'
    runtime_dir = repo_root / 'shared' / 'runtime'
    for path in [
        readonly_dir,
        writable_dir,
        duplicate_dir,
        runtime_dir,
    ]:
        path.mkdir(parents=True)

    artifacts = create_shared_deploy_artifacts(
        config={
            'shared': {
                'managed_directories': [
                    'shared/readonly',
                    'shared/duplicate',
                    {
                        'path': 'shared/duplicate',
                        'root_group_writable': True,
                    },
                    {
                        'path': 'shared/writable',
                        'root_group_writable': 'true',
                    },
                ],
            }
        },
        runtime={},
        repo_root=str(repo_root),
        load_script_paths=[],
        logger=_logger(),
    )

    assert artifacts == SharedDeployArtifacts(
        managed_recursive_dirs=[
            str(readonly_dir),
            str(duplicate_dir),
            str(writable_dir),
        ],
        root_group_writable_dirs=[
            str(duplicate_dir),
            str(writable_dir),
        ],
    )

    runtime_artifacts = create_shared_deploy_artifacts(
        config={
            'shared': {
                'managed_directories': ['shared/readonly'],
            }
        },
        runtime={
            'shared': {
                'managed_directories': [
                    {
                        'path': 'shared/runtime',
                        'root_group_writable': True,
                    }
                ],
            }
        },
        repo_root=str(repo_root),
        load_script_paths=[],
        logger=_logger(),
    )

    assert runtime_artifacts == SharedDeployArtifacts(
        managed_recursive_dirs=[str(runtime_dir)],
        root_group_writable_dirs=[str(runtime_dir)],
    )


def test_create_shared_deploy_artifacts_validates_managed_directory_entries(
    tmp_path: Path,
):
    with pytest.raises(
        ValueError,
        match='shared.managed_directories\\[0\\] must be a string',
    ):
        create_shared_deploy_artifacts(
            config={'shared': {'managed_directories': [42]}},
            runtime={},
            repo_root=str(tmp_path),
            load_script_paths=[],
            logger=_logger(),
        )

    with pytest.raises(
        ValueError,
        match='shared.managed_directories\\[0\\].path must not be null',
    ):
        create_shared_deploy_artifacts(
            config={'shared': {'managed_directories': [{}]}},
            runtime={},
            repo_root=str(tmp_path),
            load_script_paths=[],
            logger=_logger(),
        )

    with pytest.raises(
        ValueError,
        match='shared.managed_directories\\[0\\].root_group_writable',
    ):
        create_shared_deploy_artifacts(
            config={
                'shared': {
                    'managed_directories': [
                        {
                            'path': 'shared/writable',
                            'root_group_writable': 'maybe',
                        }
                    ]
                }
            },
            runtime={},
            repo_root=str(tmp_path),
            load_script_paths=[],
            logger=_logger(),
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
