from __future__ import annotations

import argparse

from mache.jigsaw import deploy_jigsawpy


def add_jigsaw_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``mache jigsaw`` command group to the top-level CLI."""
    jigsaw = subparsers.add_parser(
        'jigsaw',
        help='Build and install JIGSAW/JIGSAW-Python',
    )

    jigsaw_sub = jigsaw.add_subparsers(dest='jigsaw_cmd', required=True)

    p_install = jigsaw_sub.add_parser(
        'install',
        help='Build and install jigsawpy into pixi or conda',
    )
    p_install.add_argument(
        '--jigsaw-python-path',
        default='jigsaw-python',
        help='Path to jigsaw-python source relative to --repo-root.',
    )
    p_install.add_argument(
        '--repo-root',
        default='.',
        help='Repository root containing jigsaw-python.',
    )
    p_install.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress command output to stdout and only write logs.',
    )

    jigsaw.set_defaults(func=_dispatch_jigsaw)


def _dispatch_jigsaw(args: argparse.Namespace) -> None:
    if args.jigsaw_cmd == 'install':
        deploy_jigsawpy(
            jigsaw_python_path=args.jigsaw_python_path,
            repo_root=args.repo_root,
            log_filename=None,
            quiet=args.quiet,
        )
        return

    raise NotImplementedError(
        'Not implemented yet: mache jigsaw ' + str(args.jigsaw_cmd)
    )
