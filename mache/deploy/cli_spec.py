from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CliArgSpec:
    flags: list[str]
    dest: str
    route: list[str]  # one or more of ["deploy", "bootstrap", "run"]
    kwargs: dict[str, Any]  # safe subset to pass to argparse


@dataclass(frozen=True)
class CliSpec:
    meta: dict[str, Any]
    args: list[CliArgSpec]


def parse_cli_spec(
    rendered_json: str,
    *,
    source: str = 'cli_spec',
    require_meta: bool = True,
) -> CliSpec:
    try:
        spec = json.loads(rendered_json)
    except json.JSONDecodeError as e:
        raise ValueError(f'{source} rendered to invalid JSON: {e}') from e

    if not isinstance(spec, dict):
        raise ValueError(f'{source} must be a JSON object')

    args = spec.get('arguments')
    meta = spec.get('meta', {})

    if not isinstance(args, list):
        raise ValueError(f"{source} must contain list 'arguments'")
    if require_meta and not isinstance(meta, dict):
        raise ValueError(f"{source} must contain object 'meta'")
    if not require_meta and meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise ValueError(f'{source}.meta must be an object')

    if require_meta and (
        'mache_version' not in meta or not str(meta['mache_version']).strip()
    ):
        raise ValueError(
            f'{source}.meta.mache_version is required and must be non-empty'
        )

    parsed_args: list[CliArgSpec] = []
    for i, entry in enumerate(args):
        if not isinstance(entry, dict):
            raise ValueError(f'{source}.arguments[{i}] must be an object')

        flags = entry.get('flags')
        dest = entry.get('dest')
        route = entry.get('route')

        if (
            not isinstance(flags, list)
            or not all(isinstance(f, str) for f in flags)
            or not flags
        ):
            raise ValueError(
                f'{source}.arguments[{i}].flags must be a non-empty list[str]'
            )
        if not isinstance(dest, str) or not dest.strip():
            raise ValueError(
                f'{source}.arguments[{i}].dest must be a non-empty string'
            )

        if isinstance(route, list) and all(isinstance(r, str) for r in route):
            route_list = route
        else:
            raise ValueError(
                f'{source}.arguments[{i}].route must be a list[str]'
            )

        # Allow only a safe subset of argparse kwargs
        kwargs: dict[str, Any] = {}
        for k in (
            'help',
            'action',
            'default',
            'required',
            'choices',
            'nargs',
        ):
            if k in entry:
                kwargs[k] = entry[k]

        parsed_args.append(
            CliArgSpec(flags=flags, dest=dest, route=route_list, kwargs=kwargs)
        )

    return CliSpec(meta=meta, args=parsed_args)


def merge_cli_specs(base: CliSpec, extra: CliSpec | None) -> CliSpec:
    if extra is None:
        return base

    merged_args = list(base.args)
    seen_dests = {arg.dest for arg in base.args}
    seen_flags = {flag for arg in base.args for flag in arg.flags}

    for arg in extra.args:
        if arg.dest in seen_dests:
            raise ValueError(
                f'custom_cli_spec dest duplicates generated cli_spec: '
                f'{arg.dest}'
            )
        duplicate_flags = [flag for flag in arg.flags if flag in seen_flags]
        if duplicate_flags:
            dup_str = ', '.join(duplicate_flags)
            raise ValueError(
                f'custom_cli_spec flags duplicate generated cli_spec: '
                f'{dup_str}'
            )
        merged_args.append(arg)
        seen_dests.add(arg.dest)
        seen_flags.update(arg.flags)

    return CliSpec(meta=dict(base.meta), args=merged_args)


def routes_include(arg: CliArgSpec, route: str) -> bool:
    return route in arg.route


def filter_args_by_route(spec: CliSpec, route: str) -> list[CliArgSpec]:
    return [a for a in spec.args if routes_include(a, route)]


def load_cli_spec_file() -> CliSpec:
    with resources.open_text(
        'mache.deploy.templates', 'cli_spec.json.j2'
    ) as f:
        return parse_cli_spec(f.read(), source='cli_spec')


def load_repo_cli_spec_file(repo_root: str = '.') -> CliSpec:
    spec = load_cli_spec_file()
    custom_spec_path = Path(repo_root) / 'deploy' / 'custom_cli_spec.json'
    if not custom_spec_path.exists():
        return spec

    custom_text = custom_spec_path.read_text(encoding='utf-8')
    custom_spec = parse_cli_spec(
        custom_text,
        source=str(custom_spec_path),
        require_meta=False,
    )
    return merge_cli_specs(spec, custom_spec)


def add_args_to_parser(
    parser: argparse.ArgumentParser,
    args: list[CliArgSpec],
) -> None:
    for a in args:
        parser.add_argument(*a.flags, dest=a.dest, **a.kwargs)
