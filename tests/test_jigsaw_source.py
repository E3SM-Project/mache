"""
Tests for getting the ``jigsaw-python`` source at the ref a project uses.

A project such as polaris pins the JIGSAW-Python commit it is tested with,
so ``mache jigsaw install --jigsaw-python-ref`` clones that commit, and
refuses to build an existing checkout that is at a different one.
"""

import os
import subprocess
from pathlib import Path

import pytest

import mache.jigsaw as jigsaw


def test_jigsaw_python_is_cloned_over_https():
    """An SSH URL needs a GitHub key, which many users do not have."""
    assert jigsaw.JIGSAW_PYTHON_URL.startswith('https://')


def test_a_missing_source_is_cloned_at_the_ref(monkeypatch, tmp_path):
    upstream, first, _ = _upstream_with_two_commits(tmp_path)
    monkeypatch.setattr(jigsaw, 'JIGSAW_PYTHON_URL', upstream.as_uri())
    repo_root = tmp_path / 'project'
    repo_root.mkdir()

    _ensure_source(repo_root, ref=first[:10])

    assert _head(repo_root / 'jigsaw-python') == first


def test_a_missing_source_is_cloned_at_the_default_branch_without_a_ref(
    monkeypatch, tmp_path
):
    upstream, _, second = _upstream_with_two_commits(tmp_path)
    monkeypatch.setattr(jigsaw, 'JIGSAW_PYTHON_URL', upstream.as_uri())
    repo_root = tmp_path / 'project'
    repo_root.mkdir()

    _ensure_source(repo_root, ref=None)

    assert _head(repo_root / 'jigsaw-python') == second


def test_an_existing_checkout_at_the_ref_is_used(tmp_path):
    upstream, first, _ = _upstream_with_two_commits(tmp_path)
    repo_root = tmp_path / 'project'
    _clone(upstream, repo_root / 'jigsaw-python', first)

    _ensure_source(repo_root, ref=first)

    assert _head(repo_root / 'jigsaw-python') == first


def test_an_existing_checkout_at_another_commit_is_not_built(tmp_path):
    upstream, first, second = _upstream_with_two_commits(tmp_path)
    repo_root = tmp_path / 'project'
    _clone(upstream, repo_root / 'jigsaw-python', second)

    with pytest.raises(RuntimeError, match='not at the requested ref'):
        _ensure_source(repo_root, ref=first)

    # the checkout is left as it was
    assert _head(repo_root / 'jigsaw-python') == second


def test_an_existing_checkout_without_the_ref_is_not_built(tmp_path):
    upstream, first, _ = _upstream_with_two_commits(tmp_path)
    repo_root = tmp_path / 'project'
    _clone(upstream, repo_root / 'jigsaw-python', first)

    with pytest.raises(RuntimeError, match='does not have the requested'):
        _ensure_source(repo_root, ref='no-such-ref')


def _ensure_source(repo_root: Path, *, ref: str | None) -> None:
    jigsaw._ensure_jigsaw_python_source(
        repo_root=repo_root,
        jigsaw_python_dir=repo_root / 'jigsaw-python',
        rel_path='jigsaw-python',
        log_filename=os.devnull,
        quiet=True,
        ref=ref,
    )


def _upstream_with_two_commits(tmp_path: Path) -> tuple[Path, str, str]:
    """A stand-in for the jigsaw-python repository on GitHub"""
    upstream = tmp_path / 'upstream'
    upstream.mkdir()
    _git(upstream, 'init', '--quiet')
    commits = []
    for version in ('1.1.0', '1.1.1'):
        (upstream / 'pyproject.toml').write_text(
            f'[project]\nversion = "{version}"\n', encoding='utf-8'
        )
        _git(upstream, 'add', 'pyproject.toml')
        _git(upstream, 'commit', '--quiet', '-m', f'Version {version}')
        commits.append(_head(upstream))
    # allow a partial (blobless) clone, as GitHub does
    _git(upstream, 'config', 'uploadpack.allowFilter', 'true')
    return upstream, commits[0], commits[1]


def _clone(upstream: Path, path: Path, commit: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ['git', 'clone', '--quiet', str(upstream), str(path)]
    )
    _git(path, 'checkout', '--quiet', '--detach', commit)


def _head(repo: Path) -> str:
    return _git(repo, 'rev-parse', 'HEAD')


def _git(repo: Path, *args: str) -> str:
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME='test',
        GIT_AUTHOR_EMAIL='test@example.com',
        GIT_COMMITTER_NAME='test',
        GIT_COMMITTER_EMAIL='test@example.com',
    )
    return subprocess.check_output(
        ['git', '-C', str(repo), *args], text=True, env=env
    ).strip()
