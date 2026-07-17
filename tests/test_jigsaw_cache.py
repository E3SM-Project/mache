"""
Tests for the JIGSAW build cache: source-revision detection, where the cache
is anchored, how build artifacts are laid out, and the build lock.

The cache is shared across git worktrees of the same clone, so most of these
tests build real (tiny) git repositories in ``tmp_path``.
"""

from __future__ import annotations

import errno
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import mache.jigsaw as jigsaw

pytestmark = pytest.mark.skipif(
    shutil.which('git') is None, reason='git is required for cache tests'
)


def _git(*args: str, cwd: Path) -> str:
    env = {
        'GIT_AUTHOR_NAME': 'mache tests',
        'GIT_AUTHOR_EMAIL': 'mache@example.com',
        'GIT_COMMITTER_NAME': 'mache tests',
        'GIT_COMMITTER_EMAIL': 'mache@example.com',
        'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_CONFIG_SYSTEM': '/dev/null',
        'PATH': '/usr/bin:/bin:/usr/local/bin',
        'HOME': str(cwd),
    }
    return subprocess.check_output(
        ['git', '-C', str(cwd), *args], text=True, env=env
    ).strip()


def _make_clone(root: Path) -> Path:
    """Create a git clone with a single commit and return its path."""
    root.mkdir(parents=True, exist_ok=True)
    _git('init', '--initial-branch=main', cwd=root)
    (root / 'README.md').write_text('demo\n', encoding='utf-8')
    _git('add', 'README.md', cwd=root)
    _git('commit', '-m', 'initial', cwd=root)
    return root


def _add_worktree(clone: Path, path: Path, branch: str) -> Path:
    _git('worktree', 'add', '-b', branch, str(path), 'main', cwd=clone)
    return path


def _platform_name() -> str:
    platform_name, _ = jigsaw._get_conda_platform_and_system()
    return platform_name


def _fake_out_build(
    monkeypatch,
    cache_key: str = 'a' * 64,
    builds: list[dict] | None = None,
) -> list[dict]:
    """
    Stub out everything that would touch the network or run rattler-build,
    leaving the cache layout itself under test. Returns a list that
    records the kwargs of each _build_external_jigsaw call; pass ``builds``
    to keep recording across a change of cache key.
    """
    if builds is None:
        builds = []

    def _fake_build_external_jigsaw(**kwargs):
        builds.append(kwargs)
        slot_dir = kwargs['slot_dir']
        channel = slot_dir / _platform_name()
        channel.mkdir(parents=True, exist_ok=True)
        (channel / 'repodata.json').write_text('{}\n', encoding='utf-8')
        # rattler-build also leaves scratch behind in its output dir
        (slot_dir / 'bld').mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        jigsaw, '_ensure_jigsaw_python_source', lambda **_: None
    )
    monkeypatch.setattr(
        jigsaw, '_compute_jigsaw_cache_key', lambda **_: cache_key
    )
    monkeypatch.setattr(jigsaw, '_get_jigsaw_version', lambda *_: '0.0.1')
    monkeypatch.setattr(
        jigsaw, '_build_external_jigsaw', _fake_build_external_jigsaw
    )
    return builds


def _build(repo_root: Path):
    return jigsaw.build_jigsawpy_package(
        python_version='3.14',
        jigsaw_python_path='jigsaw-python',
        repo_root=str(repo_root),
        log_filename='test.log',
        quiet=True,
        backend='conda',
        conda_exe='conda',
    )


def test_get_git_head_matches_rev_parse(tmp_path: Path):
    clone = _make_clone(tmp_path / 'clone')
    expected = _git('rev-parse', 'HEAD', cwd=clone)

    assert jigsaw._get_git_head(clone) == expected


def test_get_git_head_reads_packed_refs(tmp_path: Path):
    """
    Branch refs may be packed rather than stored as loose ref files.
    """
    clone = _make_clone(tmp_path / 'clone')
    expected = _git('rev-parse', 'HEAD', cwd=clone)

    _git('pack-refs', '--all', cwd=clone)
    loose_ref = clone / '.git' / 'refs' / 'heads' / 'main'
    if loose_ref.is_file():
        loose_ref.unlink()

    assert jigsaw._get_git_head(clone) == expected


def test_get_git_head_in_linked_worktree(tmp_path: Path):
    """
    In a linked worktree, loose refs live in the common dir, not in the
    worktree's own gitdir.
    """
    clone = _make_clone(tmp_path / 'clone')
    worktree = _add_worktree(clone, tmp_path / 'wt', 'feature')
    expected = _git('rev-parse', 'HEAD', cwd=worktree)

    assert jigsaw._get_git_head(worktree) == expected


def test_get_git_head_outside_git_checkout(tmp_path: Path):
    plain = tmp_path / 'plain'
    plain.mkdir()

    with pytest.raises(RuntimeError, match='could not read HEAD'):
        jigsaw._get_git_head(plain)


def test_shared_cache_dir_uses_git_common_dir_parent(tmp_path: Path):
    """
    A worktree must resolve to its clone's cache, not to its own.

    This is the whole point of sharing the cache: deploying in a new
    worktree reuses the build that some other worktree already paid for.
    """
    clone = _make_clone(tmp_path / 'clone')
    worktree = _add_worktree(clone, tmp_path / 'wt', 'feature')

    shared = jigsaw._get_jigsaw_shared_cache_dir(repo_root=worktree)

    assert shared == clone / '.mache_cache' / 'jigsaw'
    assert shared == jigsaw._get_jigsaw_shared_cache_dir(repo_root=clone)


def test_shared_cache_dir_for_original_clone_is_unchanged(tmp_path: Path):
    """
    In the original clone the shared cache is where the cache has always
    been, so upgrading needs no migration.
    """
    clone = _make_clone(tmp_path / 'clone')

    shared = jigsaw._get_jigsaw_shared_cache_dir(repo_root=clone)

    assert shared == jigsaw._get_jigsaw_workspace_dir(repo_root=clone)
    assert shared == clone / '.mache_cache' / 'jigsaw'


def test_shared_cache_dir_falls_back_outside_git(monkeypatch, tmp_path: Path):
    """
    Tarball installs have no clone to anchor to and keep today's layout.
    """
    plain = tmp_path / 'plain'
    plain.mkdir()
    # Keep git from finding a repository somewhere above tmp_path.
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path))

    shared = jigsaw._get_jigsaw_shared_cache_dir(repo_root=plain)

    assert shared == plain / '.mache_cache' / 'jigsaw'


def test_shared_cache_dir_falls_back_when_repo_root_is_not_toplevel(
    tmp_path: Path,
):
    """
    A repo_root nested inside an unrelated checkout must not anchor to
    that checkout's clone.
    """
    clone = _make_clone(tmp_path / 'clone')
    nested = clone / 'subdir'
    nested.mkdir()

    shared = jigsaw._get_jigsaw_shared_cache_dir(repo_root=nested)

    assert shared == nested / '.mache_cache' / 'jigsaw'


def test_build_writes_slot_and_sentinel(monkeypatch, tmp_path: Path):
    clone = _make_clone(tmp_path / 'clone')
    _fake_out_build(monkeypatch)

    result = _build(clone)

    shared = clone / '.mache_cache' / 'jigsaw'
    slot = shared / ('a' * 64)
    assert result.cache_hit is False
    assert result.cache_root == shared
    assert result.channel_dir == slot
    assert result.channel_uri == slot.as_uri()
    sentinel = slot / '.jigsaw_cache_key'
    assert sentinel.read_text(encoding='utf-8').strip() == 'a' * 64


def test_second_worktree_hits_cache_built_by_first(
    monkeypatch, tmp_path: Path
):
    """
    The point of the whole change: a fresh worktree reuses the build that
    another worktree of the same clone already paid for.
    """
    clone = _make_clone(tmp_path / 'clone')
    worktree_a = _add_worktree(clone, tmp_path / 'wt_a', 'branch_a')
    worktree_b = _add_worktree(clone, tmp_path / 'wt_b', 'branch_b')
    builds = _fake_out_build(monkeypatch)

    first = _build(worktree_a)
    second = _build(worktree_b)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(builds) == 1
    assert second.channel_dir == first.channel_dir
    assert first.channel_dir == clone / '.mache_cache' / 'jigsaw' / ('a' * 64)
    # Nothing was written into either worktree.
    assert not (worktree_a / '.mache_cache').exists()
    assert not (worktree_b / '.mache_cache').exists()


def test_second_build_in_same_clone_hits_cache(monkeypatch, tmp_path: Path):
    clone = _make_clone(tmp_path / 'clone')
    builds = _fake_out_build(monkeypatch)

    _build(clone)
    second = _build(clone)

    assert second.cache_hit is True
    assert len(builds) == 1


def test_distinct_keys_get_distinct_slots(monkeypatch, tmp_path: Path):
    """
    Worktrees that disagree on the Python version or JIGSAW-Python commit
    must not evict each other.
    """
    clone = _make_clone(tmp_path / 'clone')
    shared = clone / '.mache_cache' / 'jigsaw'

    _fake_out_build(monkeypatch, cache_key='a' * 64)
    _build(clone)
    _fake_out_build(monkeypatch, cache_key='b' * 64)
    second = _build(clone)

    assert second.cache_hit is False
    assert (shared / ('a' * 64) / '.jigsaw_cache_key').is_file()
    assert (shared / ('b' * 64) / '.jigsaw_cache_key').is_file()


def test_tools_dir_is_shared_across_keys(monkeypatch, tmp_path: Path):
    """
    Tool envs are ~98% of the cache and do not depend on the cache key, so
    they must live outside the per-key slots.
    """
    clone = _make_clone(tmp_path / 'clone')
    shared = clone / '.mache_cache' / 'jigsaw'

    builds = _fake_out_build(monkeypatch, cache_key='a' * 64)
    _build(clone)
    _fake_out_build(monkeypatch, cache_key='b' * 64, builds=builds)
    _build(clone)

    assert len(builds) == 2
    tools_dirs = [build['tools_dir'] for build in builds]
    assert tools_dirs == [shared / 'tools', shared / 'tools']
    slot_dirs = [build['slot_dir'] for build in builds]
    assert slot_dirs == [shared / ('a' * 64), shared / ('b' * 64)]


def test_build_rechecks_cache_after_taking_lock(monkeypatch, tmp_path: Path):
    """
    A deploy that waits on the lock should find the build the process it
    waited for produced, rather than redo it.
    """
    clone = _make_clone(tmp_path / 'clone')
    builds = _fake_out_build(monkeypatch)

    slot = clone / '.mache_cache' / 'jigsaw' / ('a' * 64)
    answers = iter([False, True])

    def _valid_once_locked(**_):
        valid = next(answers)
        if valid:
            # Stand in for the build the process we waited on finished.
            channel = slot / _platform_name()
            channel.mkdir(parents=True, exist_ok=True)
            (channel / 'repodata.json').write_text('{}\n', encoding='utf-8')
        return valid

    monkeypatch.setattr(
        jigsaw, '_is_cached_jigsaw_build_valid', _valid_once_locked
    )

    result = _build(clone)

    assert result.cache_hit is True
    assert result.channel_dir == slot
    assert builds == []


def test_cache_lock_is_exclusive_across_processes(tmp_path: Path):
    shared = tmp_path / 'cache'
    script = (
        'import fcntl, sys\n'
        f'fd = open({str(shared / ".lock")!r}, "r+")\n'
        'try:\n'
        '    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
        'except BlockingIOError:\n'
        '    print("blocked")\n'
        '    sys.exit(0)\n'
        'print("acquired")\n'
    )

    with jigsaw._jigsaw_cache_lock(shared_root=shared, quiet=True) as held:
        assert held is True
        other = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            check=True,
        )

    assert other.stdout.strip() == 'blocked'

    # Released on exit, so a later process can take it.
    after = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert after.stdout.strip() == 'acquired'


def test_build_proceeds_when_locking_unsupported(
    monkeypatch, capsys, tmp_path: Path
):
    """
    Some filesystems cannot flock. Warn, but never fail the deploy over
    it: unlocked is how this worked before the cache was shared.
    """
    clone = _make_clone(tmp_path / 'clone')
    _fake_out_build(monkeypatch)

    def _no_flock(*_args, **_kwargs):
        raise OSError(errno.ENOLCK, 'no locks available')

    monkeypatch.setattr(jigsaw.fcntl, 'flock', _no_flock)

    result = _build(clone)

    assert result.cache_hit is False
    assert (clone / '.mache_cache' / 'jigsaw' / ('a' * 64)).is_dir()
    assert 'proceeding without a build lock' in capsys.readouterr().out


def test_cache_lock_times_out(monkeypatch, tmp_path: Path):
    """
    A build that never releases the lock must not hang a deploy forever.
    """
    shared = tmp_path / 'cache'
    monkeypatch.setattr(jigsaw, 'JIGSAW_LOCK_TIMEOUT', 0.0)
    monkeypatch.setattr(jigsaw, 'JIGSAW_LOCK_POLL', 0.0)

    def _always_contended(*_args, **_kwargs):
        raise BlockingIOError()

    monkeypatch.setattr(jigsaw.fcntl, 'flock', _always_contended)

    with pytest.raises(RuntimeError, match='Timed out'):
        with jigsaw._jigsaw_cache_lock(shared_root=shared, quiet=True):
            pass
