import argparse
import sys

import mache.version
from mache import sync


def main():
    """
    Entry point for the main script ``mache``
    """

    parser = argparse.ArgumentParser(
        description="Perform mache commands",
        usage='''
mache <command> [<args>]
The available mache commands are:
    sync    Sync files between supported machines
 To get help on an individual command, run:
    mache <command> --help
    ''')

    parser.add_argument('command', help='command to run')
    parser.add_argument('-v', '--version',
                        action='version',
                        version='mache {}'.format(mache.version.__version__),
                        help="Show version number and exit")
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(sys.argv[1:2])

    commands = {'sync': sync.main}

    if args.command not in commands:
        print('Unrecognized command {}'.format(args.command))
        parser.print_help()
        exit(1)

    # call the function associated with the requested command
    commands[args.command]()
