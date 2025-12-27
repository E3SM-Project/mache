from __future__ import annotations

import argparse
import os
import sys

from .cli_spec import (
    add_args_to_parser,
    filter_args_by_route,
    load_cli_spec_file,
)


def run_deploy() -> None:
    # require that CWD is the repo root
    spec_path = os.path.join(os.getcwd(), 'deploy', 'cli_spec.json')

    spec = load_cli_spec_file(spec_path)

    # Build a dedicated parser for "run" using the repo’s spec.
    parser = argparse.ArgumentParser(
        prog='mache deploy run',
        description=spec.meta.get('description', 'Run deployment'),
    )

    run_args = filter_args_by_route(spec, 'run')
    add_args_to_parser(parser, run_args)

    # Important: parse ONLY the argv after `deploy run`.
    argv = _deploy_run_argv(sys.argv[1:])

    # If someone runs `mache deploy run --help`, show the dynamic help.
    # argparse handles that automatically as long as we parse argv.
    parsed = parser.parse_args(argv)  # noqa: F841

    # Placeholder for now:
    # Next: read config.yaml.j2, conda-spec.txt.j2, spack, etc.
    raise NotImplementedError(
        'mache deploy run is wired. Next step: implement deployment using '
        'parsed args.'
    )


def _deploy_run_argv(argv: list[str]) -> list[str]:
    """
    Extract args after `deploy run` from the full mache argv.
    Example:
      mache deploy run --conda /path --recreate
    argv seen by python is likely:
      ["deploy", "run", "--conda", "/path", "--recreate"]
    """
    try:
        i = argv.index('deploy')
    except ValueError:
        return argv

    # Expect: deploy <cmd> ...
    if len(argv) >= i + 2 and argv[i + 1] == 'run':
        return argv[i + 2 :]

    # If someone called run_deploy directly, just return argv.
    return argv
