import argparse

from mache.jigsaw import deploy_jigsawpy
from meshflow.version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog='meshflow')
    parser.add_argument('--version', action='store_true')
    subparsers = parser.add_subparsers(dest='command')

    jigsaw = subparsers.add_parser('jigsaw')
    jigsaw_subparsers = jigsaw.add_subparsers(dest='jigsaw_cmd', required=True)
    jigsaw_subparsers.add_parser('install')

    args = parser.parse_args()
    if args.version:
        print(__version__)
        return

    if args.command == 'jigsaw' and args.jigsaw_cmd == 'install':
        deploy_jigsawpy(
            backend='pixi',
            pixi_local=True,
            quiet=False,
        )
        return

    print(f'meshflow {__version__}')
