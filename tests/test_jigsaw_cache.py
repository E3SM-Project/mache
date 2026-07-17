"""
Tests for the JIGSAW build cache: source-revision detection, where the cache
is anchored, how build artifacts are laid out, and the build lock.

The cache is shared across git worktrees of the same clone, so most of these
tests build real (tiny) git repositories in ``tmp_path``.
"""

from __future__ import annotations

import shutil
import subprocess
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
