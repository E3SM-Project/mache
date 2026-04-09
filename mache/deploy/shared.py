from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SharedDeployArtifacts:
    managed_dirs: list[str]
    managed_files: list[str]


def create_shared_deploy_artifacts(
    *,
    config: dict[str, Any],
    runtime: dict[str, Any],
    repo_root: str,
    load_script_paths: list[str],
    logger: logging.Logger,
) -> SharedDeployArtifacts:
    shared_cfg = _merge_shared_config(config=config, runtime=runtime)

    managed_dirs = _normalize_path_entries(
        shared_cfg.get('managed_directories'),
        repo_root=repo_root,
        field_name='shared.managed_directories',
    )
    managed_files = _normalize_path_entries(
        shared_cfg.get('managed_files'),
        repo_root=repo_root,
        field_name='shared.managed_files',
    )

    load_script_copies = _normalize_load_script_copy_entries(
        shared_cfg.get('load_script_copies'),
        repo_root=repo_root,
    )
    load_script_symlinks = _normalize_load_script_symlink_entries(
        shared_cfg.get('load_script_symlinks'),
        repo_root=repo_root,
    )

    if load_script_copies or load_script_symlinks:
        source_script = _require_single_load_script(
            load_script_paths=load_script_paths,
            reason='shared load-script copies/symlinks',
        )

        for dest_script in load_script_copies:
            logger.info('Writing shared load-script copy: %s', dest_script)
            _copy_load_script(
                source_script=source_script,
                dest_script=dest_script,
            )
            managed_dirs.append(str(dest_script.parent))
            managed_files.append(str(dest_script))

    for dest_link, target_path in load_script_symlinks:
        if not (os.path.exists(target_path) or os.path.islink(target_path)):
            raise FileNotFoundError(
                'Shared load-script symlink target does not exist: '
                f'{target_path}'
            )
        logger.info(
            'Writing shared load-script symlink: %s -> %s',
            dest_link,
            target_path,
        )
        dest_link.parent.mkdir(parents=True, exist_ok=True)
        if dest_link.exists() or dest_link.is_symlink():
            dest_link.unlink()
        dest_link.symlink_to(target_path)
        managed_dirs.append(str(dest_link.parent))

    return SharedDeployArtifacts(
        managed_dirs=_dedupe_existing_paths(managed_dirs),
        managed_files=_dedupe_existing_paths(managed_files),
    )


def _merge_shared_config(
    *,
    config: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    config_shared = config.get('shared')
    if config_shared is not None:
        if not isinstance(config_shared, dict):
            raise ValueError('shared section must be a mapping if provided')
        merged.update(config_shared)

    runtime_shared = runtime.get('shared')
    if runtime_shared is not None:
        if not isinstance(runtime_shared, dict):
            raise ValueError('runtime.shared must be a mapping if provided')
        merged.update(runtime_shared)

    return merged


def _normalize_path_entries(
    value: Any,
    *,
    repo_root: str,
    field_name: str,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f'{field_name} must be a list if provided')

    entries: list[str] = []
    for index, item in enumerate(value):
        entries.append(
            _resolve_path(
                value=item,
                repo_root=repo_root,
                field_name=f'{field_name}[{index}]',
            )
        )
    return entries


def _normalize_load_script_copy_entries(
    value: Any,
    *,
    repo_root: str,
) -> list[Path]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            'shared.load_script_copies must be a list if provided'
        )

    copies: list[Path] = []
    for index, item in enumerate(value):
        field_name = f'shared.load_script_copies[{index}]'
        path_value: Any
        if isinstance(item, str):
            path_value = item
        elif isinstance(item, dict):
            path_value = item.get('path')
        else:
            raise ValueError(
                f'{field_name} must be a string or mapping with a path'
            )

        copies.append(
            Path(
                _resolve_path(
                    value=path_value,
                    repo_root=repo_root,
                    field_name=f'{field_name}.path',
                )
            )
        )

    return _dedupe_paths(copies)


def _normalize_load_script_symlink_entries(
    value: Any,
    *,
    repo_root: str,
) -> list[tuple[Path, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            'shared.load_script_symlinks must be a list if provided'
        )

    symlinks: list[tuple[Path, str]] = []
    for index, item in enumerate(value):
        field_name = f'shared.load_script_symlinks[{index}]'
        if not isinstance(item, dict):
            raise ValueError(
                f'{field_name} must be a mapping with path and target'
            )
        path_value = item.get('path')
        target_value = item.get('target')
        symlinks.append(
            (
                Path(
                    _resolve_path(
                        value=path_value,
                        repo_root=repo_root,
                        field_name=f'{field_name}.path',
                    )
                ),
                _resolve_path(
                    value=target_value,
                    repo_root=repo_root,
                    field_name=f'{field_name}.target',
                ),
            )
        )

    deduped: dict[str, tuple[Path, str]] = {}
    for path, target in symlinks:
        deduped[str(path)] = (path, target)
    return list(deduped.values())


def _resolve_path(
    *,
    value: Any,
    repo_root: str,
    field_name: str,
) -> str:
    if value is None:
        raise ValueError(f'{field_name} must not be null')

    candidate = str(value).strip()
    if candidate.lower() in ('', 'none', 'null'):
        raise ValueError(f'{field_name} must be a non-empty path')

    expanded = os.path.expanduser(os.path.expandvars(candidate))
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(repo_root, expanded))


def _require_single_load_script(
    *,
    load_script_paths: list[str],
    reason: str,
) -> Path:
    if not load_script_paths:
        raise ValueError(f'Expected one generated load script for {reason}.')
    if len(load_script_paths) != 1:
        raise ValueError(
            f'{reason} currently require exactly one generated load script.'
        )
    return Path(str(load_script_paths[0])).resolve()


def _copy_load_script(*, source_script: Path, dest_script: Path) -> None:
    dest_script.parent.mkdir(parents=True, exist_ok=True)
    source_text = source_script.read_text(encoding='utf-8')
    updated = source_text.replace(
        str(source_script),
        str(dest_script.resolve()),
    )
    dest_script.write_text(updated, encoding='utf-8')
    dest_script.chmod(0o644)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    deduped: dict[str, Path] = {}
    for path in paths:
        deduped[str(path)] = path
    return list(deduped.values())


def _dedupe_existing_paths(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        if not (os.path.exists(path) or os.path.islink(path)):
            continue
        seen.add(path)
        deduped.append(path)
    return deduped
