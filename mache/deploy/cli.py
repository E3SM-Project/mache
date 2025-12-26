from __future__ import annotations

import argparse
import os

from .init_update import init_or_update_repo
from .run import run_deploy


def add_deploy_subparser(subparsers: argparse._SubParsersAction) -> None:
    deploy = subparsers.add_parser(
        'deploy', help='Deploy E3SM software environments'
    )
    deploy_sub = deploy.add_subparsers(dest='deploy_cmd', required=True)

    p_init = deploy_sub.add_parser(
        'init', help='Initialize deploy files in a repo'
    )
    p_update = deploy_sub.add_parser(
        'update',
        help='Update deploy files to a new mache version',
    )

    for parser in (p_init, p_update):
        # common args for init and update

        parser.add_argument(
            '--repo-root',
            default='.',
            help='Path to target repo root, default is .',
        )
        parser.add_argument(
            '--software',
            required=True,
            help='Target software name (e.g. polaris)',
        )
        parser.add_argument(
            '--mache-version',
            help='Pinned mache version for this repo, default is the current '
            'mache version',
        )

    p_init.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing deploy files',
    )

    deploy_sub.add_parser(
        'run',
        help='Run deployment (typically invoked by a target-software '
        'deploy.py)',
    )

    deploy.set_defaults(func=_dispatch_deploy)


def _dispatch_deploy(args: argparse.Namespace) -> None:
    if args.deploy_cmd == 'init':
        init_or_update_repo(
            repo_root=args.repo_root,
            software=args.software,
            mache_version=args.mache_version,
            update=False,
            overwrite=args.overwrite,
        )
        print(f'Initialized deploy files in {os.path.abspath(args.repo_root)}')
        return

    if args.deploy_cmd == 'update':
        init_or_update_repo(
            repo_root=args.repo_root,
            software=args.software,
            mache_version=args.mache_version,
            update=True,
            overwrite=True,
        )
        print(f'Updated deploy files in {os.path.abspath(args.repo_root)}')
        return

    if args.deploy_cmd == 'run':
        run_deploy()
        return

    raise NotImplementedError(
        'Not implemented yet: mache deploy ' + str(args.deploy_cmd)
    )
