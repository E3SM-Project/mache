from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CliArgSpec:
    flags: list[str]
    dest: str
    route: list[str]  # e.g. ["deploy", "bootstrap", "mache"] etc.
    kwargs: dict[str, Any]  # safe subset to pass to argparse


@dataclass(frozen=True)
class CliSpec:
    meta: dict[str, Any]
    args: list[CliArgSpec]


def parse_cli_spec(rendered_json: str) -> CliSpec:
    try:
        spec = json.loads(rendered_json)
    except json.JSONDecodeError as e:
        raise ValueError(f'cli_spec rendered to invalid JSON: {e}') from e

    if not isinstance(spec, dict):
        raise ValueError('cli_spec must be a JSON object')

    meta = spec.get('meta')
    args = spec.get('arguments')

    if not isinstance(meta, dict) or not isinstance(args, list):
        raise ValueError(
            "cli_spec must contain object 'meta' and list 'arguments'"
        )

    if 'mache_version' not in meta or not str(meta['mache_version']).strip():
        raise ValueError(
            'cli_spec.meta.mache_version is required and must be non-empty'
        )

    parsed_args: list[CliArgSpec] = []
    for i, entry in enumerate(args):
        if not isinstance(entry, dict):
            raise ValueError(f'cli_spec.arguments[{i}] must be an object')

        flags = entry.get('flags')
        dest = entry.get('dest')
        route = entry.get('route')

        if (
            not isinstance(flags, list)
            or not all(isinstance(f, str) for f in flags)
            or not flags
        ):
            raise ValueError(
                f'cli_spec.arguments[{i}].flags must be a non-empty list[str]'
            )
        if not isinstance(dest, str) or not dest.strip():
            raise ValueError(
                f'cli_spec.arguments[{i}].dest must be a non-empty string'
            )

        if isinstance(route, list) and all(isinstance(r, str) for r in route):
            route_list = route
        else:
            raise ValueError(
                f'cli_spec.arguments[{i}].route must be a list[str]'
            )

        # Allow only a safe subset of argparse kwargs
        kwargs: dict[str, Any] = {}
        for k in ('help', 'action', 'default', 'required', 'choices'):
            if k in entry:
                kwargs[k] = entry[k]

        parsed_args.append(
            CliArgSpec(flags=flags, dest=dest, route=route_list, kwargs=kwargs)
        )

    return CliSpec(meta=meta, args=parsed_args)


def routes_include(arg: CliArgSpec, route: str) -> bool:
    return route in arg.route


def filter_args_by_route(spec: CliSpec, route: str) -> list[CliArgSpec]:
    return [a for a in spec.args if routes_include(a, route)]


def load_cli_spec_file(path: str) -> CliSpec:
    with open(path, 'r', encoding='utf-8') as f:
        return parse_cli_spec(f.read())


def add_args_to_parser(
    parser: argparse.ArgumentParser,
    args: list[CliArgSpec],
) -> None:
    for a in args:
        parser.add_argument(*a.flags, dest=a.dest, **a.kwargs)
