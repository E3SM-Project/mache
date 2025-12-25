from __future__ import annotations

import argparse

from mache.sync.diags import add_diags_subparser


def add_sync_subparser(subparsers: argparse._SubParsersAction) -> None:
    sync = subparsers.add_parser(
        'sync',
        help='Sync files between supported machines',
    )

    sync_sub = sync.add_subparsers(dest='sync_cmd', required=True)
    add_diags_subparser(sync_sub)

    # If you ever want `mache sync` itself to do something later, this is where
    # you would set a default handler.
