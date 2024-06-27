import argparse
import sys

from mache.sync import diags


def main():
    """
    Defines the ``mache sync`` command
    """

    parser = argparse.ArgumentParser(
        description="Perform synchronization between supported machines",
        usage='''
    mache sync <command> [<args>]
    The available mache commands are:
        diags    Synchronize diagnostics files between supported machines
     To get help on an individual command, run:
        mache sync <command> --help
        ''')

    parser.add_argument('command', help='command to run')
    if len(sys.argv) == 2:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(sys.argv[2:3])

    commands = {'diags': diags.main}

    if args.command not in commands:
        print(f'Unrecognized command {args.command}')
        parser.print_help()
        exit(1)

    # call the function associated with the requested command
    commands[args.command]()
