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
