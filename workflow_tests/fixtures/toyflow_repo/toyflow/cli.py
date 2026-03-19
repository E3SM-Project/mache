import argparse

from toyflow.version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog='toyflow')
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return
    print(f'toyflow {__version__}')
