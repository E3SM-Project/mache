from __future__ import annotations

import argparse
import os

from .init import init_repo


def add_deploy_subparser(subparsers: argparse._SubParsersAction) -> None:
    deploy = subparsers.add_parser(
        'deploy', help='Deploy E3SM software environments'
    )
    deploy_sub = deploy.add_subparsers(dest='deploy_cmd', required=True)

    p_init = deploy_sub.add_parser(
        'init', help='Initialize deploy files in a repo'
    )
    p_init.add_argument(
        '--repo-root',
        default='.',
        help='Path to target repo root, default is .',
    )
    p_init.add_argument(
        '--software',
        required=True,
        help='Target software name (e.g. polaris)',
    )
    p_init.add_argument(
        '--mache-version',
        help='Pinned mache version for this repo, default is the current '
        'mache version',
    )
    p_init.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing deploy files',
    )

    # placeholders
    deploy_sub.add_parser(
        'update',
        help='(placeholder) Update deploy files to a new mache version',
    )
    deploy_sub.add_parser('', help='(placeholder) Run deployment')

    deploy.set_defaults(func=_dispatch_deploy)


def _dispatch_deploy(args: argparse.Namespace) -> None:
    if args.deploy_cmd == 'init':
        init_repo(
            repo_root=args.repo_root,
            software=args.software,
            mache_version=args.mache_version,
            overwrite=args.overwrite,
        )
        print(f'Initialized deploy files in {os.path.abspath(args.repo_root)}')
        return

    raise NotImplementedError(
        'Not implemented yet: mache deploy ' + str(args.deploy_cmd)
    )
