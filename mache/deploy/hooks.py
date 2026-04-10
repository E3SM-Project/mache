"""Deployment hooks for ``mache deploy run``.

Security note
-------------
Hooks execute arbitrary Python code from the target-software repository.
In this workflow, the target repository is assumed to be trusted.

Design goals
------------
- Hooks are optional and only run during ``mache deploy run``.
- Hooks are loaded from a single Python module file (typically
  ``deploy/hooks.py`` in the target repository) and invoked via named
  entrypoint functions.
- Hook loading does not permanently modify ``sys.path``.

"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import uuid
from configparser import ConfigParser
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable

HookCallable = Callable[['DeployContext'], Any]


HOOK_STAGE_ORDER: tuple[str, ...] = (
    # pixi lifecycle (preferred names)
    'pre_pixi',
    'post_pixi',
    # future spack lifecycle
    'pre_spack',
    'post_spack',
    # publication lifecycle
    'pre_publish',
    'post_publish',
)

DEPRECATED_HOOK_STAGE_ALIASES: dict[str, str] = {
    'post_deploy': 'pre_publish',
}

KNOWN_HOOK_STAGES: tuple[str, ...] = HOOK_STAGE_ORDER + tuple(
    DEPRECATED_HOOK_STAGE_ALIASES
)


@dataclass
class DeployContext:
    """A small bundle of state passed to hook functions.

    Notes
    -----
    - Hooks may create/update files under ``work_dir``.
    - Hooks should prefer writing derived values into ``runtime`` rather than
      mutating ``config`` in-place.
    - Hooks may raise exceptions to abort deployment.

    """

    software: str
    machine: str | None
    repo_root: str
    deploy_dir: str
    work_dir: str

    config: dict[str, Any]
    pins: dict[str, dict[str, str]]
    machine_config: ConfigParser

    args: argparse.Namespace
    logger: logging.Logger

    # A place for hook-produced derived values (preferred over mutating config)
    runtime: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HookRegistry:
    """Resolved hooks for a single deploy run."""

    file_path: str | None
    entrypoints: dict[str, HookCallable]
    log_context: bool = False

    def run_hook(self, stage: str, context: DeployContext) -> None:
        """Run a hook stage if it is defined.

        If a hook returns a mapping, it is merged into ``context.runtime``.
        After the hook finishes, a JSON snapshot of the context is written
        under ``deploy_tmp/hooks`` to aid debugging.
        """

        func = self.entrypoints.get(stage)
        if func is None:
            return

        file_display = self.file_path or '<unknown>'
        func_name = getattr(func, '__name__', '<callable>')

        context.logger.info(
            'Running hook stage=%s file=%s func=%s',
            stage,
            file_display,
            func_name,
        )

        runtime_before = _json_ready(context.runtime)
        result: Any = None
        error: Exception | None = None

        try:
            result = func(context)
        except Exception as exc:  # pragma: no cover (covered indirectly)
            error = exc

        if isinstance(result, dict) and result:
            _deep_update(context.runtime, result)

        snapshot = _build_context_snapshot(
            stage=stage,
            context=context,
            file_path=file_display,
            func_name=func_name,
            runtime_before=runtime_before,
            hook_result=result,
            error=error,
        )
        _persist_context_snapshot(
            stage=stage,
            context=context,
            snapshot=snapshot,
            log_context=self.log_context,
        )

        if error is not None:
            raise RuntimeError(
                (
                    f'Hook failed: stage={stage} func={func_name} '
                    f'file={file_display}'
                )
            ) from error


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Recursively merge ``src`` into ``dst``.

    If both ``dst[key]`` and ``src[key]`` are dicts, merge recursively.
    Otherwise, ``src[key]`` overwrites ``dst[key]``.
    """

    for key, src_val in src.items():
        dst_val = dst.get(key)
        if isinstance(dst_val, dict) and isinstance(src_val, dict):
            _deep_update(dst_val, src_val)
        else:
            dst[key] = src_val


def load_hooks(
    config: dict[str, Any],
    repo_root: str,
    logger: logging.Logger,
) -> HookRegistry:
    """Load deployment hooks from a target-software repository.

    Parameters
    ----------
    config
        Parsed config from rendered ``deploy/config.yaml.j2``.

        Hooks are configured under the optional top-level ``hooks`` section:

        .. code-block:: yaml

           hooks:
             file: "deploy/hooks.py"  # default
             log_context: false        # optional
             entrypoints:
               pre_pixi: "pre_pixi"        # optional
               post_pixi: "post_pixi"      # optional
               pre_spack: "pre_spack"      # optional
               post_spack: "post_spack"    # optional
               pre_publish: "pre_publish"  # optional
               post_publish: "post_publish"  # optional

        If the ``hooks`` section is missing, hooks are considered disabled.

    repo_root
        Target-software repository root (the working directory where
        ``deploy/`` lives).

    logger
        Logger used for hook loading and execution messages.

    Returns
    -------
    HookRegistry
        A registry containing a resolved hook module path and stage->callable
        mapping. Stages not present are simply no-ops.

    Missing file semantics
    ----------------------
    - If the ``hooks`` section is not present, a missing hooks file is treated
      as "no hooks".
    - If the ``hooks`` section is present (explicitly configured) and the
      hooks file is missing, a ``FileNotFoundError`` is raised.

    """

    hooks_cfg_raw = config.get('hooks', None)
    if hooks_cfg_raw is None:
        return HookRegistry(file_path=None, entrypoints={})

    if not isinstance(hooks_cfg_raw, dict):
        raise ValueError("'hooks' section must be a mapping")

    hooks_cfg: dict[str, Any] = hooks_cfg_raw

    file_rel = hooks_cfg.get('file', 'deploy/hooks.py')
    if file_rel is None or str(file_rel).strip() == '':
        file_rel = 'deploy/hooks.py'
    if not isinstance(file_rel, str):
        raise ValueError('hooks.file must be a string')

    log_context = hooks_cfg.get('log_context', False)
    if not isinstance(log_context, bool):
        raise ValueError('hooks.log_context must be a boolean')

    entrypoints_cfg = hooks_cfg.get('entrypoints', {})
    if entrypoints_cfg is None:
        entrypoints_cfg = {}
    if not isinstance(entrypoints_cfg, dict):
        raise ValueError('hooks.entrypoints must be a mapping')

    unknown = set(entrypoints_cfg.keys()) - set(KNOWN_HOOK_STAGES)
    if unknown:
        unknown_list = ', '.join(sorted(unknown))
        known_list = ', '.join(KNOWN_HOOK_STAGES)
        raise ValueError(
            (
                f'Unknown hook stage(s): {unknown_list}. '
                f'Known stages: {known_list}'
            )
        )

    entrypoints_cfg = _normalize_entrypoints_config(
        entrypoints_cfg=entrypoints_cfg,
        logger=logger,
    )

    repo_root_abs = os.path.abspath(os.path.expanduser(str(repo_root)))
    hooks_path = os.path.abspath(os.path.join(repo_root_abs, file_rel))

    if not os.path.exists(hooks_path):
        raise FileNotFoundError(
            f'Hooks configured but file not found: {hooks_path}'
        )

    module = _load_module_from_path(hooks_path=hooks_path)

    resolved: dict[str, HookCallable] = {}
    for stage in HOOK_STAGE_ORDER:
        func_name = entrypoints_cfg.get(stage)
        if func_name is None:
            continue
        func_name = str(func_name).strip()
        if not func_name:
            continue

        func = getattr(module, func_name, None)
        if func is None:
            raise AttributeError(
                f'Hook entrypoint not found: stage={stage} '
                f'func={func_name} file={hooks_path}'
            )
        if not callable(func):
            raise TypeError(
                f'Hook entrypoint is not callable: stage={stage} '
                f'func={func_name} file={hooks_path}'
            )

        resolved[stage] = func

    if resolved:
        logger.info(
            'Loaded hooks from %s: %s',
            hooks_path,
            ', '.join(sorted(resolved.keys())),
        )
    else:
        logger.info(
            'Hooks file loaded but no entrypoints configured: %s',
            hooks_path,
        )

    return HookRegistry(
        file_path=hooks_path,
        entrypoints=resolved,
        log_context=log_context,
    )


def _normalize_entrypoints_config(
    *,
    entrypoints_cfg: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, str]:
    normalized: dict[str, str] = {}

    for stage in HOOK_STAGE_ORDER:
        func_name = _normalize_entrypoint_name(entrypoints_cfg.get(stage))
        if func_name is not None:
            normalized[stage] = func_name

    for alias, canonical_stage in DEPRECATED_HOOK_STAGE_ALIASES.items():
        alias_func_name = _normalize_entrypoint_name(
            entrypoints_cfg.get(alias)
        )
        if alias_func_name is None:
            continue

        if canonical_stage in normalized:
            raise ValueError(
                'hooks.entrypoints.'
                f'{alias} is a deprecated alias for '
                f'hooks.entrypoints.{canonical_stage}; '
                'do not configure both.'
            )

        logger.warning(
            'hooks.entrypoints.%s is deprecated; use '
            'hooks.entrypoints.%s instead.',
            alias,
            canonical_stage,
        )
        normalized[canonical_stage] = alias_func_name

    return normalized


def _normalize_entrypoint_name(value: Any) -> str | None:
    if value is None:
        return None

    func_name = str(value).strip()
    if not func_name:
        return None

    return func_name


def _load_module_from_path(*, hooks_path: str) -> ModuleType:
    """Dynamically import a module without modifying sys.path."""

    module_name = f'mache_deploy_hooks_{uuid.uuid4().hex}'

    spec = importlib.util.spec_from_file_location(module_name, hooks_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Unable to load hooks module from: {hooks_path}')

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configparser_to_nested_dict(
    cfg: ConfigParser,
) -> dict[str, dict[str, str]]:
    """Convert a ``ConfigParser`` to a JSON/YAML-friendly nested mapping."""

    out: dict[str, dict[str, str]] = {}
    for section in cfg.sections():
        out[section] = {k: cfg.get(section, k) for k in cfg[section]}
    return out


def _build_context_snapshot(
    *,
    stage: str,
    context: DeployContext,
    file_path: str,
    func_name: str,
    runtime_before: Any,
    hook_result: Any,
    error: Exception | None,
) -> dict[str, Any]:
    """Build a JSON-friendly context snapshot for hook debugging."""

    snapshot: dict[str, Any] = {
        'stage': stage,
        'status': 'failed' if error is not None else 'ok',
        'file': file_path,
        'function': func_name,
        'context': {
            'software': context.software,
            'machine': context.machine,
            'repo_root': context.repo_root,
            'deploy_dir': context.deploy_dir,
            'work_dir': context.work_dir,
            'config': _json_ready(context.config),
            'pins': _json_ready(context.pins),
            'machine_config': configparser_to_nested_dict(
                context.machine_config
            ),
            'args': _json_ready(vars(context.args)),
            'runtime_before': runtime_before,
            'runtime_after': _json_ready(context.runtime),
        },
    }

    if hook_result is not None:
        snapshot['hook_result'] = _json_ready(hook_result)

    if error is not None:
        snapshot['error'] = {
            'type': type(error).__name__,
            'message': str(error),
        }

    return snapshot


def _persist_context_snapshot(
    *,
    stage: str,
    context: DeployContext,
    snapshot: dict[str, Any],
    log_context: bool,
) -> None:
    """Write and optionally log a hook context snapshot."""

    snapshot_dir = os.path.join(context.work_dir, 'hooks')
    snapshot_path = os.path.join(snapshot_dir, f'{stage}_context.json')

    try:
        os.makedirs(snapshot_dir, exist_ok=True)
        with open(snapshot_path, 'w', encoding='utf-8') as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
            handle.write('\n')
    except OSError as exc:  # pragma: no cover - unlikely filesystem error
        context.logger.warning(
            'Failed to write hook context snapshot stage=%s path=%s: %s',
            stage,
            snapshot_path,
            exc,
        )
        return

    context.logger.info(
        'Wrote hook context snapshot stage=%s path=%s',
        stage,
        snapshot_path,
    )
    if log_context:
        context.logger.info(
            'Hook context snapshot stage=%s\n%s',
            stage,
            json.dumps(snapshot, indent=2, sort_keys=True),
        )


def _json_ready(value: Any) -> Any:
    """Convert a value into a JSON-friendly structure."""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    return repr(value)
