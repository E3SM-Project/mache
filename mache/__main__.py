import argparse
import sys

import mache.version
from mache.deploy.cli import add_deploy_subparser
from mache.sync.cli import add_sync_subparser


def main():
    """
    Entry point for the main script ``mache``
    """
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:])

    if not hasattr(args, 'func'):
        parser.print_help()
        raise SystemExit(2)

    args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Perform mache commands',
        prog='mache',
    )

    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version=f'mache {mache.version.__version__}',
        help='Show version number and exit',
    )

    subparsers = parser.add_subparsers(dest='command', required=True)
    add_sync_subparser(subparsers)
    add_deploy_subparser(subparsers)
    return parser
