import os
import stat
from types import SimpleNamespace

from mache import permissions


def test_update_permissions_removes_group_write_bits(tmp_path, monkeypatch):
    shared_dir = tmp_path / 'shared'
    shared_dir.mkdir()
    shared_file = shared_dir / 'data.txt'
    shared_file.write_text('demo\n', encoding='utf-8')

    shared_dir.chmod(0o775)
    shared_file.chmod(0o664)

    monkeypatch.setattr(
        permissions.grp,
        'getgrnam',
        lambda _group: SimpleNamespace(gr_gid=os.getgid()),
    )
    monkeypatch.setattr(permissions.os, 'chown', lambda *_args: None)

    permissions.update_permissions(
        str(shared_dir),
        'e3sm',
        show_progress=False,
        group_writable=False,
        other_readable=True,
        recursive=True,
    )

    assert stat.S_IMODE(shared_dir.stat().st_mode) == 0o755
    assert stat.S_IMODE(shared_file.stat().st_mode) == 0o644


def test_owner_write_removed_and_restored(tmp_path, monkeypatch):
    shared_dir = tmp_path / 'shared'
    sub_dir = shared_dir / 'bin'
    sub_dir.mkdir(parents=True)
    data_file = shared_dir / 'data.txt'
    data_file.write_text('demo\n', encoding='utf-8')
    exe_file = sub_dir / 'tool'
    exe_file.write_text('#!/bin/sh\n', encoding='utf-8')
    exe_file.chmod(0o755)
    (shared_dir / 'link').symlink_to(data_file)

    monkeypatch.setattr(
        permissions.grp,
        'getgrnam',
        lambda _group: SimpleNamespace(gr_gid=os.getgid()),
    )
    monkeypatch.setattr(permissions.os, 'chown', lambda *_args: None)

    permissions.update_permissions(
        str(shared_dir),
        'e3sm',
        show_progress=False,
        owner_writable=False,
    )

    modes = {
        path: stat.S_IMODE(path.stat().st_mode)
        for path in (shared_dir, sub_dir, data_file, exe_file)
    }
    assert modes == {
        shared_dir: 0o555,
        sub_dir: 0o555,
        data_file: 0o444,
        exe_file: 0o555,
    }

    permissions.restore_owner_write(
        [str(shared_dir), str(tmp_path / 'missing')], show_progress=False
    )

    modes = {
        path: stat.S_IMODE(path.stat().st_mode)
        for path in (shared_dir, sub_dir, data_file, exe_file)
    }
    assert modes == {
        shared_dir: 0o755,
        sub_dir: 0o755,
        data_file: 0o644,
        exe_file: 0o755,
    }


def test_restore_owner_write_skips_writable_directory(tmp_path):
    # an owner-writable top directory means it was never made read-only, so
    # nothing below it is visited
    shared_dir = tmp_path / 'shared'
    shared_dir.mkdir()
    data_file = shared_dir / 'data.txt'
    data_file.write_text('demo\n', encoding='utf-8')
    data_file.chmod(0o444)

    permissions.restore_owner_write(str(shared_dir), show_progress=False)

    assert stat.S_IMODE(data_file.stat().st_mode) == 0o444


def test_update_permissions_skips_symlinks_while_traversing(
    tmp_path, monkeypatch
):
    # like e3smu_latest_for_nco, a directory of links to read-only
    # environments elsewhere: updating it must leave the targets alone
    env_dir = tmp_path / 'env'
    env_dir.mkdir()
    env_file = tmp_path / 'private.txt'
    env_file.write_text('demo\n', encoding='utf-8')
    env_file.chmod(0o600)
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    (links_dir / 'env').symlink_to(env_dir)
    (links_dir / 'file').symlink_to(env_file)
    env_dir.chmod(0o555)

    monkeypatch.setattr(
        permissions.grp,
        'getgrnam',
        lambda _group: SimpleNamespace(gr_gid=os.getgid()),
    )
    monkeypatch.setattr(permissions.os, 'chown', lambda *_args: None)

    try:
        permissions.update_permissions(
            str(links_dir),
            'e3sm',
            show_progress=False,
            group_writable=True,
            owner_writable=True,
            recursive=True,
        )

        assert stat.S_IMODE(links_dir.stat().st_mode) == 0o775
        assert stat.S_IMODE(env_dir.stat().st_mode) == 0o555
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    finally:
        env_dir.chmod(0o755)
