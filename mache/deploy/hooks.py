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
import logging
import os
import uuid
from configparser import ConfigParser
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable

HookCallable = Callable[['DeployContext'], Any]


KNOWN_HOOK_STAGES: tuple[str, ...] = (
    # pixi lifecycle (preferred names)
    'pre_pixi',
    'post_pixi',
    # future spack lifecycle
    'pre_spack',
    'post_spack',
    # always last (on success by default)
    'post_deploy',
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

    def run_hook(self, stage: str, context: DeployContext) -> None:
        """Run a hook stage if it is defined.

        If a hook returns a mapping, it is merged into ``context.runtime``.
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

        try:
            result = func(context)
        except Exception as exc:  # pragma: no cover (covered indirectly)
            raise RuntimeError(
                (
                    f'Hook failed: stage={stage} func={func_name} '
                    f'file={file_display}'
                )
            ) from exc

        if isinstance(result, dict) and result:
            _deep_update(context.runtime, result)


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
             entrypoints:
               pre_pixi: "pre_pixi"        # optional
               post_pixi: "post_pixi"      # optional
               pre_spack: "pre_spack"      # optional
               post_spack: "post_spack"    # optional
               post_deploy: "post_deploy"  # optional

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

    repo_root_abs = os.path.abspath(os.path.expanduser(str(repo_root)))
    hooks_path = os.path.abspath(os.path.join(repo_root_abs, file_rel))

    if not os.path.exists(hooks_path):
        raise FileNotFoundError(
            f'Hooks configured but file not found: {hooks_path}'
        )

    module = _load_module_from_path(hooks_path=hooks_path)

    resolved: dict[str, HookCallable] = {}
    for stage in KNOWN_HOOK_STAGES:
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

    return HookRegistry(file_path=hooks_path, entrypoints=resolved)


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
