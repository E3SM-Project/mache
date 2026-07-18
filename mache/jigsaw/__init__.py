from __future__ import annotations

import fcntl
import hashlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from mache.deploy.bootstrap import (
    build_pixi_env_unset_prefix,
    check_call,
    check_call_with_retries,
)

JIGSAW_PYTHON_URL = 'git@github.com:dengwirda/jigsaw-python.git'

CONDA_PLATFORM_MAP = {
    ('linux', 'x86_64'): 'linux-64',
    ('linux', 'aarch64'): 'linux-aarch64',
    ('linux', 'ppc64le'): 'linux-ppc64le',
    ('osx', 'x86_64'): 'osx-64',
    ('osx', 'arm64'): 'osx-arm64',
}

PYTHON_VARIANTS = {
    '3.10': '3.10.* *_cpython',
    '3.11': '3.11.* *_cpython',
    '3.12': '3.12.* *_cpython',
    '3.13': '3.13.* *_cp313',
    '3.14': '3.14.* *_cp314',
}

# How long to wait for another process to finish building before giving up,
# and how often to re-check while waiting, in seconds. A build takes a
# couple of minutes; the timeout only needs to be comfortably longer.
JIGSAW_LOCK_TIMEOUT = 3600.0
JIGSAW_LOCK_POLL = 2.0

# Characters of the cache key used to name a build's cache directory. See
# _jigsaw_slot_dir for why this is truncated rather than the full key.
JIGSAW_SLOT_KEY_LEN = 16


@dataclass(frozen=True)
class JigsawBuildResult:
    channel_uri: str
    channel_dir: Path
    cache_key: str
    cache_hit: bool
    jigsaw_version: str
    cache_root: Path | None = None


def deploy_jigsawpy(
    *,
    jigsaw_python_path: str = 'jigsaw-python',
    repo_root: str = '.',
    log_filename: str | None = None,
    quiet: bool = False,
    python_version: str | None = None,
    backend: str = 'auto',
    pixi_exe: str | None = None,
    pixi_manifest: str | None = None,
    pixi_feature: str | None = None,
    pixi_local: bool = False,
    conda_exe: str | None = None,
    conda_prefix: str | None = None,
) -> JigsawBuildResult:
    """
    Build and install ``jigsawpy`` in one call.

    This convenience wrapper first builds a local conda package for
    ``jigsawpy`` (including the bundled JIGSAW dependency) and then installs
    that package into either a pixi or conda environment. The resolved
    backend is used for both the build and install stages.

    Parameters
    ----------
    jigsaw_python_path : str
        Path to the ``jigsaw-python`` source relative to ``repo_root``.
        Defaults to ``"jigsaw-python"``.
    repo_root : str
        Root directory containing the target source tree. Defaults to
        ``"."``.
    log_filename : str, optional
        Log file path passed through to shell command execution. If
        ``None``, logs are discarded (written to ``os.devnull``).
    quiet : bool
        If ``True``, suppress command echo to stdout and log only.
        Defaults to ``False``.
    python_version : str, optional
        Python major/minor version used to select the build variant
        (for example ``"3.14"``). If omitted, the version is inferred
        from the active Python interpreter.
    backend : {"auto", "pixi", "conda"}, optional
        Backend used for both build and install stages. ``"auto"`` infers
        backend from environment variables.
    pixi_exe : str, optional
        Path to the ``pixi`` executable when backend resolves to ``"pixi"``.
    pixi_manifest : str, optional
        Pixi manifest path used when installing with backend ``"pixi"``.
        If omitted, ``PIXI_PROJECT_MANIFEST`` is used.
    pixi_feature : str, optional
        Explicit pixi feature to target when installing with backend
        ``"pixi"``. If omitted, a matching active pixi environment name is
        used when possible.
    pixi_local : bool, optional
        If ``True`` and backend resolves to ``"pixi"``, install into a
        local copied manifest under
        ``<repo_root>/.mache_cache/jigsaw/pixi-local`` instead of mutating
        the source manifest directly.
    conda_exe : str, optional
        Conda executable used when installing with backend ``"conda"``.
    conda_prefix : str, optional
        Target conda prefix used when backend is ``"conda"``. If omitted,
        ``CONDA_PREFIX`` is used.

    Returns
    -------
    JigsawBuildResult
        Metadata describing the produced local package channel and cache
        status.

    Raises
    ------
    ValueError
        If backend-specific required arguments are missing or invalid.
    RuntimeError
        If source discovery, backend detection, or build/install steps fail.
    """
    selected_backend = detect_install_backend(backend=backend)
    resolved_python_version = python_version or _detect_python_version()
    resolved_log_filename = log_filename or os.devnull
    resolved_pixi_exe = pixi_exe
    if selected_backend == 'pixi' and resolved_pixi_exe is None:
        resolved_pixi_exe = 'pixi'
    resolved_conda_exe = conda_exe
    if selected_backend == 'conda' and resolved_conda_exe is None:
        resolved_conda_exe = _resolve_conda_executable(conda_exe)

    result = build_jigsawpy_package(
        pixi_exe=resolved_pixi_exe,
        python_version=resolved_python_version,
        jigsaw_python_path=jigsaw_python_path,
        repo_root=repo_root,
        log_filename=resolved_log_filename,
        quiet=quiet,
        backend=selected_backend,
        conda_exe=resolved_conda_exe,
    )

    install_jigsawpy_package(
        channel_uri=result.channel_uri,
        log_filename=resolved_log_filename,
        quiet=quiet,
        jigsaw_version=result.jigsaw_version,
        backend=selected_backend,
        pixi_exe=resolved_pixi_exe,
        pixi_manifest=pixi_manifest,
        pixi_feature=pixi_feature,
        pixi_local=pixi_local,
        repo_root=repo_root,
        conda_exe=resolved_conda_exe,
        conda_prefix=conda_prefix,
    )
    return result


def detect_install_backend(*, backend: str = 'auto') -> str:
    """
    Resolve the jigsaw installation backend.

    Parameters
    ----------
    backend : {"auto", "pixi", "conda"}, optional
        Explicit backend selection. When set to ``"auto"``, backend is
        inferred from environment variables.

    Returns
    -------
    str
        Resolved backend name, either ``"pixi"`` or ``"conda"``.

    Raises
    ------
    ValueError
        If ``backend`` is not one of ``"auto"``, ``"pixi"``, or
        ``"conda"``.
    RuntimeError
        If ``backend="auto"`` and no supported environment variables are
        detected.

    Notes
    -----
    Auto-detection currently prefers pixi when either
    ``PIXI_PROJECT_MANIFEST`` or ``PIXI_PROJECT_ROOT`` is set; otherwise it
    falls back to conda when ``CONDA_PREFIX`` is set.
    """
    if backend not in ('auto', 'pixi', 'conda'):
        raise ValueError(
            f'Unsupported backend {backend!r}. Expected auto, pixi, or conda.'
        )

    if backend != 'auto':
        return backend

    if os.environ.get('PIXI_PROJECT_MANIFEST') or os.environ.get(
        'PIXI_PROJECT_ROOT'
    ):
        return 'pixi'

    if os.environ.get('CONDA_PREFIX'):
        return 'conda'

    raise RuntimeError(
        'Could not infer install backend from environment. '
        'Set backend explicitly to "pixi" or "conda".'
    )


def install_jigsawpy_package(
    *,
    channel_uri: str,
    log_filename: str,
    quiet: bool,
    jigsaw_version: str | None = None,
    backend: str = 'auto',
    pixi_exe: str | None = None,
    pixi_manifest: str | None = None,
    pixi_feature: str | None = None,
    pixi_local: bool = False,
    repo_root: str = '.',
    conda_exe: str | None = None,
    conda_prefix: str | None = None,
) -> str:
    """
    Install ``jigsawpy`` from a local conda channel.

    Parameters
    ----------
    channel_uri : str
        URI for a local conda channel containing the built ``jigsawpy``
        package.
    log_filename : str
        Log file path passed through to shell command execution.
    quiet : bool
        If ``True``, suppress command echo to stdout and log only.
    jigsaw_version : str, optional
        Version of ``jigsawpy`` to install. When provided, installation
        is pinned to this built version.
    backend : {"auto", "pixi", "conda"}, optional
        Installation backend. ``"auto"`` infers backend from environment.
    pixi_exe : str, optional
        Pixi executable used when backend resolves to ``"pixi"``.
    pixi_manifest : str, optional
        Pixi manifest path used with backend ``"pixi"``.
    pixi_feature : str, optional
        Explicit pixi feature to target when using backend ``"pixi"``.
    pixi_local : bool, optional
        If ``True`` and backend resolves to ``"pixi"``, install into a
        local copied manifest under
        ``<repo_root>/.mache_cache/jigsaw/pixi-local`` instead of mutating
        the source manifest directly.
    repo_root : str
        Root directory containing the target source tree, used to locate
        the ``pixi-local`` manifest copy. Defaults to ``"."``.
    conda_exe : str, optional
        Conda executable used when backend resolves to ``"conda"``.
    conda_prefix : str, optional
        Conda prefix used when backend resolves to ``"conda"``.

    Returns
    -------
    str
        Resolved backend used for installation, either ``"pixi"`` or
        ``"conda"``.

    Raises
    ------
    ValueError
        If required backend-specific arguments are missing or invalid.
    RuntimeError
        If backend auto-detection fails.
    """
    selected_backend = detect_install_backend(backend=backend)

    if selected_backend == 'pixi':
        if not pixi_exe:
            raise ValueError('pixi_exe is required when backend="pixi".')
        resolved_manifest = pixi_manifest
        resolved_feature = pixi_feature
        if pixi_local:
            (
                resolved_manifest,
                inferred_local_feature,
            ) = _prepare_local_pixi_manifest_copy(
                pixi_manifest=pixi_manifest,
                workspace_root=_get_jigsaw_workspace_dir(
                    repo_root=Path(repo_root).resolve()
                ),
            )
            if resolved_feature is None:
                resolved_feature = inferred_local_feature
            if not quiet:
                print(f'Using local pixi manifest copy: {resolved_manifest}')
        _install_into_pixi(
            pixi_exe=pixi_exe,
            pixi_manifest=resolved_manifest,
            pixi_feature=resolved_feature,
            channel_uri=channel_uri,
            jigsaw_version=jigsaw_version,
            log_filename=log_filename,
            quiet=quiet,
        )
    else:
        _install_into_conda(
            conda_exe=conda_exe,
            conda_prefix=conda_prefix,
            channel_uri=channel_uri,
            jigsaw_version=jigsaw_version,
            log_filename=log_filename,
            quiet=quiet,
        )

    return selected_backend


def build_jigsawpy_package(
    *,
    python_version: str,
    jigsaw_python_path: str,
    repo_root: str,
    log_filename: str,
    quiet: bool,
    backend: str = 'auto',
    pixi_exe: str | None = None,
    conda_exe: str | None = None,
) -> JigsawBuildResult:
    """
    Build a local conda package for ``jigsawpy``.

    The function ensures the ``jigsaw-python`` source is available,
    computes a cache key, reuses cached output when valid, and otherwise
    runs ``rattler-build`` using the resolved backend.

    The cache lives in the clone that ``repo_root`` belongs to, so every
    git worktree of that clone shares one build. See
    ``_get_jigsaw_shared_cache_dir``.

    Parameters
    ----------
    python_version : str
        Python major/minor version used to select the variant matrix.
    jigsaw_python_path : str
        Path to ``jigsaw-python`` relative to ``repo_root``.
    repo_root : str
        Root directory containing the source tree.
    log_filename : str
        Log file path passed through to shell command execution.
    quiet : bool
        If ``True``, suppress command echo to stdout and log only.
    backend : {"auto", "pixi", "conda"}, optional
        Backend used to run ``rattler-build``.
    pixi_exe : str, optional
        Path to the ``pixi`` executable when backend resolves to ``"pixi"``.
    conda_exe : str, optional
        Conda executable used when backend resolves to ``"conda"``.

    Returns
    -------
    JigsawBuildResult
        Build metadata including channel URI, cache key, cache hit flag,
        and resolved jigsawpy version.

    Raises
    ------
    ValueError
        If ``python_version`` or platform-specific build configuration is
        unsupported.
    RuntimeError
        If source acquisition, metadata extraction, or build validation
        fails.
    """
    repo_root_path = Path(repo_root).resolve()
    jigsaw_python_dir = (repo_root_path / jigsaw_python_path).resolve()

    _ensure_jigsaw_python_source(
        repo_root=repo_root_path,
        jigsaw_python_dir=jigsaw_python_dir,
        rel_path=jigsaw_python_path,
        log_filename=log_filename,
        quiet=quiet,
    )

    cache_key = _compute_jigsaw_cache_key(
        jigsaw_python_dir=jigsaw_python_dir,
        python_version=python_version,
    )

    jigsaw_version = _get_jigsaw_version(jigsaw_python_dir)

    shared_root = _get_jigsaw_shared_cache_dir(repo_root=repo_root_path)
    slot_dir = _jigsaw_slot_dir(shared_root=shared_root, cache_key=cache_key)

    cache_hit = _is_cached_jigsaw_build_valid(
        slot_dir=slot_dir, cache_key=cache_key
    )
    if cache_hit:
        if not quiet:
            print(f'Using cached JIGSAW build: {slot_dir}')
    else:
        selected_backend = detect_install_backend(backend=backend)

        with _jigsaw_cache_lock(shared_root=shared_root, quiet=quiet):
            # Another worktree may have built this while we waited.
            cache_hit = _is_cached_jigsaw_build_valid(
                slot_dir=slot_dir, cache_key=cache_key
            )
            if cache_hit:
                if not quiet:
                    print(f'Using cached JIGSAW build: {slot_dir}')
            else:
                _build_external_jigsaw(
                    backend=selected_backend,
                    pixi_exe=pixi_exe,
                    conda_exe=conda_exe,
                    jigsaw_python_dir=jigsaw_python_dir,
                    python_version=python_version,
                    jigsaw_version=jigsaw_version,
                    log_filename=log_filename,
                    quiet=quiet,
                    slot_dir=slot_dir,
                    tools_dir=_jigsaw_tools_dir(shared_root=shared_root),
                )

                # Written last: the sentinel is what marks the slot usable,
                # so a slot mid-build never reads as a cache hit.
                _write_jigsaw_cache_key(slot_dir=slot_dir, cache_key=cache_key)

    return JigsawBuildResult(
        channel_uri=_get_local_channel_uri(output_dir=slot_dir),
        channel_dir=slot_dir,
        cache_key=cache_key,
        cache_hit=cache_hit,
        jigsaw_version=jigsaw_version,
        cache_root=shared_root,
    )


def _get_conda_platform_and_system() -> tuple[str, str]:
    system = platform.system().lower()
    if system == 'darwin':
        system = 'osx'
    machine = platform.machine().lower()
    if (system, machine) in CONDA_PLATFORM_MAP:
        conda_platform = CONDA_PLATFORM_MAP[(system, machine)]
    else:
        raise ValueError(f'Unsupported platform for conda: {system} {machine}')
    return conda_platform, system


def _detect_python_version() -> str:
    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
    if python_version not in PYTHON_VARIANTS:
        raise ValueError(
            'Unsupported active Python version '
            f'{python_version!r} for jigsaw build variants. '
            'Pass python_version explicitly to deploy_jigsawpy() or call '
            'build_jigsawpy_package() directly with a supported version.'
        )
    return python_version


def _define_square_bracket_environment() -> Environment:
    return Environment(
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        variable_start_string='[[',
        variable_end_string=']]',
        block_start_string='[%',
        block_end_string='%]',
        comment_start_string='[#',
        comment_end_string='#]',
    )


def _get_jigsaw_version(jigsaw_python_dir: Path) -> str:
    version_file = jigsaw_python_dir / 'pyproject.toml'
    version = _parse_pyproject_version(version_file)

    if not version:
        raise RuntimeError(
            f'Failed to determine JIGSAW-Python version from {version_file}.'
        )
    return version


def _run_git(args: list[str], *, cwd: Path) -> str | None:
    try:
        output = subprocess.check_output(
            ['git', '-C', str(cwd), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return output.strip() or None


def _get_git_head(repo_dir: Path) -> str:
    head = _run_git(['rev-parse', 'HEAD'], cwd=repo_dir)
    if head is None:
        raise RuntimeError(
            f'Expected git checkout at {repo_dir} but could not read HEAD.'
        )
    return head


def _get_git_worktree_hash(repo_dir: Path) -> str | None:
    """
    Content hash of the working tree at ``repo_dir``, including any
    uncommitted changes, or None if it cannot be computed.

    Committing must not be a prerequisite for rebuilding JIGSAW: a developer
    who edits the JIGSAW source in place has to get a fresh build, so the
    cache key has to reflect the working tree and not just HEAD. We stage the
    whole tree into a throwaway index -- leaving the developer's real index
    untouched -- and let ``git write-tree`` hash it. Ignored paths such as
    the build cache itself are excluded, exactly as they are from a commit.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp_dir, 'index'))
        try:
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'add', '-A'],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tree = subprocess.check_output(
                ['git', '-C', str(repo_dir), 'write-tree'],
                env=env,
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
    return tree.strip() or None


def _get_jigsaw_source_id(repo_dir: Path) -> str:
    """
    Identify the JIGSAW source to build: its committed HEAD plus a hash of
    the working tree, so that uncommitted edits trigger a rebuild instead of
    reusing a stale cached build. On a clean checkout the working-tree hash
    is a stable function of HEAD, so the id does not churn between builds.
    """
    head = _get_git_head(repo_dir)
    worktree = _get_git_worktree_hash(repo_dir)
    if worktree is None:
        return head
    return f'{head}:{worktree}'


def _get_build_recipe_id(platform_name: str) -> str:
    """
    Hash of the mache-owned files that define how JIGSAW is built: the
    recipe, the build script, and the platform's dependency pins. These are
    not part of the JIGSAW source, so changing them (e.g. bumping a
    dependency) would otherwise leave the cache key unchanged and reuse a
    stale build.
    """
    digest = hashlib.sha256()
    for name in ('recipe.yaml.j2', 'build.sh', f'{platform_name}.yaml.j2'):
        try:
            contents = resources.read_text('mache.jigsaw', name)
        except FileNotFoundError:
            contents = ''
        digest.update(f'{name}\0'.encode('utf-8'))
        digest.update(contents.encode('utf-8'))
        digest.update(b'\0')
    return digest.hexdigest()


def _compute_jigsaw_cache_key(
    *,
    jigsaw_python_dir: Path,
    python_version: str,
) -> str:
    platform_name, _ = _get_conda_platform_and_system()
    jigsaw_version = _get_jigsaw_version(jigsaw_python_dir)
    jigsaw_source = _get_jigsaw_source_id(jigsaw_python_dir)
    python_variant = PYTHON_VARIANTS.get(python_version, '')

    payload = {
        'jigsaw_source': jigsaw_source,
        'jigsaw_version': jigsaw_version,
        'python_version': python_version,
        'python_variant': python_variant,
        'platform': platform_name,
        'build_recipe': _get_build_recipe_id(platform_name),
    }

    digest = hashlib.sha256()
    for key in sorted(payload):
        digest.update(f'{key}={payload[key]}\n'.encode('utf-8'))
    return digest.hexdigest()


def _cache_key_path(*, slot_dir: Path) -> Path:
    return slot_dir / '.jigsaw_cache_key'


def _find_git_clone_root(repo_root: Path) -> Path | None:
    """
    Find the original clone that ``repo_root`` belongs to, or None if
    ``repo_root`` is not itself the top of a git work tree.

    For a linked worktree this is the clone the worktree was created from,
    which is what lets every worktree share one build cache.
    """
    repo_root = repo_root.resolve()
    toplevel = _run_git(['rev-parse', '--show-toplevel'], cwd=repo_root)
    if toplevel is None or Path(toplevel).resolve() != repo_root:
        # repo_root is not a work-tree top, so a surrounding repository is
        # some unrelated checkout we must not anchor to.
        return None

    common_dir = _run_git(['rev-parse', '--git-common-dir'], cwd=repo_root)
    if common_dir is None:
        return None

    # --git-common-dir is relative ('.git') for an original clone but
    # absolute for a linked worktree.
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = repo_root / common_path

    return common_path.resolve().parent


def _get_jigsaw_shared_cache_dir(*, repo_root: Path) -> Path:
    """
    The build cache shared by every worktree of ``repo_root``'s clone.
    """
    clone_root = _find_git_clone_root(repo_root)
    if clone_root is None:
        return _get_jigsaw_workspace_dir(repo_root=repo_root)
    return (clone_root / '.mache_cache' / 'jigsaw').resolve()


def _get_jigsaw_workspace_dir(*, repo_root: Path) -> Path:
    """
    Per-worktree scratch space, for things derived from this checkout
    rather than from the cache key.
    """
    return (repo_root / '.mache_cache' / 'jigsaw').resolve()


def _jigsaw_slot_dir(*, shared_root: Path, cache_key: str) -> Path:
    # The slot name is part of the build path, and rattler-build has to fit
    # its build prefix inside conda's 255-character limit, so keep it short.
    # The full key still lives in the slot's sentinel for exact matching;
    # 16 hex characters (64 bits) is far more than enough to keep the
    # handful of builds a clone ever holds from colliding.
    return shared_root / cache_key[:JIGSAW_SLOT_KEY_LEN]


def _jigsaw_tools_dir(*, shared_root: Path) -> Path:
    """
    Tool environments that every build shares.

    These depend on the platform rather than on the cache key, so they are
    deliberately kept outside the per-key slots: they are by far the
    largest thing in the cache, and duplicating them per key would undo
    most of the benefit of sharing it.
    """
    return shared_root / 'tools'


@contextmanager
def _jigsaw_cache_lock(*, shared_root: Path, quiet: bool) -> Iterator[bool]:
    """
    Serialize builds that share a cache, yielding whether the lock is held.

    Worktrees of one clone share a cache directory, so two deploys running
    at once would otherwise write the same build tree. On a filesystem
    without working ``flock`` we warn and proceed anyway: that is no worse
    than the unlocked behavior this replaces, and failing the deploy
    outright would be.
    """
    lock_path = shared_root / '.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    held = False
    try:
        deadline = time.monotonic() + JIGSAW_LOCK_TIMEOUT
        announced = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except BlockingIOError:
                if not announced:
                    if not quiet:
                        print(
                            'Waiting for another mache JIGSAW build to '
                            f'finish (lock: {lock_path})'
                        )
                    announced = True
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f'Timed out after {JIGSAW_LOCK_TIMEOUT:.0f}s waiting '
                        f'for the JIGSAW build lock at {lock_path}. If no '
                        'build is running, it is safe to delete that file.'
                    ) from None
                time.sleep(JIGSAW_LOCK_POLL)
            except OSError as e:
                # e.g. NFS without lockd, or a mount with -o nolock
                print(
                    f'Warning: could not lock {lock_path} ({e.strerror}); '
                    'proceeding without a build lock.'
                )
                break

        yield held
    finally:
        # Closing the descriptor releases the lock, if we hold it.
        os.close(fd)


def _read_jigsaw_cache_key(*, slot_dir: Path) -> str | None:
    cache_path = _cache_key_path(slot_dir=slot_dir)
    if not cache_path.is_file():
        return None
    return cache_path.read_text(encoding='utf-8').strip() or None


def _write_jigsaw_cache_key(*, slot_dir: Path, cache_key: str) -> None:
    cache_path = _cache_key_path(slot_dir=slot_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(f'{cache_key}\n', encoding='utf-8')


def _is_cached_jigsaw_build_valid(*, slot_dir: Path, cache_key: str) -> bool:
    cached_key = _read_jigsaw_cache_key(slot_dir=slot_dir)
    if cached_key != cache_key:
        return False

    if not slot_dir.is_dir():
        return False

    platform_name, _ = _get_conda_platform_and_system()
    repodata = slot_dir / platform_name / 'repodata.json'
    return repodata.is_file()


def _parse_pyproject_version(pyproject_path: Path) -> str:
    in_project = False
    version = ''
    try:
        text = pyproject_path.read_text(encoding='utf-8')
    except OSError as e:
        raise RuntimeError(
            f'Failed to read {pyproject_path} to determine version: {e!r}'
        ) from e

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        if line.startswith('[') and line.endswith(']'):
            in_project = line == '[project]'
            continue

        if not in_project:
            continue

        match = re.match(r'^version\s*=\s*(["\'])(.+)\1\s*$', line)
        if match:
            version = match.group(2).strip()
            break

    return version


def _ensure_jigsaw_python_source(
    repo_root: Path,
    jigsaw_python_dir: Path,
    rel_path: str,
    log_filename: str,
    quiet: bool,
) -> None:
    has_submodule = False
    gitmodules_path = repo_root / '.gitmodules'
    if gitmodules_path.is_file():
        with open(gitmodules_path, 'r', encoding='utf-8') as file_handle:
            for line in file_handle:
                line = line.strip()
                if not line.startswith('path = '):
                    continue
                path = line.split('=', 1)[1].strip()
                if path == rel_path:
                    has_submodule = True
                    break

    if has_submodule:
        if not (jigsaw_python_dir / '.git').exists():
            commands = (
                f'cd "{repo_root}" && git submodule update --init "{rel_path}"'
            )
            check_call(commands, log_filename=log_filename, quiet=quiet)

    elif not jigsaw_python_dir.is_dir():
        commands = (
            f'cd "{repo_root}" && '
            f'git clone --depth 1 "{JIGSAW_PYTHON_URL}" "{rel_path}"'
        )
        check_call(commands, log_filename=log_filename, quiet=quiet)

    if not jigsaw_python_dir.is_dir():
        raise RuntimeError(
            f'Failed to acquire JIGSAW-Python at {jigsaw_python_dir} '
            f'(clone_url={JIGSAW_PYTHON_URL}).'
        )


def _write_build_manifest(*, build_root: Path, platform_name: str) -> Path:
    bootstrap_project_dir = build_root / 'bootstrap_pixi'
    bootstrap_project_dir.mkdir(parents=True, exist_ok=True)
    pixi_toml = bootstrap_project_dir / 'pixi.toml'
    manifest = (
        '[workspace]\n'
        'name = "mache-jigsaw-build"\n'
        'channels = ["conda-forge"]\n'
        f'platforms = ["{platform_name}"]\n'
        'channel-priority = "strict"\n\n'
        '[dependencies]\n'
        'rattler-build = "*"\n'
    )
    pixi_toml.write_text(manifest, encoding='utf-8')
    return pixi_toml


def _build_external_jigsaw(
    backend: str,
    pixi_exe: str | None,
    conda_exe: str | None,
    python_version: str,
    jigsaw_version: str,
    jigsaw_python_dir: Path,
    log_filename: str,
    quiet: bool,
    slot_dir: Path,
    tools_dir: Path,
) -> None:
    print('Building JIGSAW')

    if python_version not in PYTHON_VARIANTS:
        raise ValueError(f'Unsupported python version: {python_version}')

    python_variant = PYTHON_VARIANTS.get(python_version)
    build_root = (slot_dir / 'build').resolve()
    recipe_dir = build_root / 'recipe'
    variant_dir = build_root / 'variant'
    recipe_dir.mkdir(parents=True, exist_ok=True)
    variant_dir.mkdir(parents=True, exist_ok=True)

    env = _define_square_bracket_environment()
    with resources.open_text('mache.jigsaw', 'recipe.yaml.j2') as file_handle:
        recipe_template = env.from_string(file_handle.read())

    recipe = (
        recipe_template.render(
            jigsaw_version=jigsaw_version,
            jigsaw_python_src_dir=str(jigsaw_python_dir),
        )
        + '\n'
    )
    recipe_file = recipe_dir / 'recipe.yaml'
    with open(recipe_file, 'w', encoding='utf-8') as file_handle:
        file_handle.write(recipe)

    with resources.open_text('mache.jigsaw', 'build.sh') as file_handle:
        build_sh = file_handle.read()
    build_sh_file = recipe_dir / 'build.sh'
    with open(build_sh_file, 'w', encoding='utf-8') as file_handle:
        file_handle.write(build_sh)

    platform_name, _ = _get_conda_platform_and_system()

    try:
        with resources.open_text(
            'mache.jigsaw', f'{platform_name}.yaml.j2'
        ) as file_handle:
            variant_template = env.from_string(file_handle.read())
    except FileNotFoundError as e:
        raise ValueError(
            f'Unsupported platform for JIGSAW build: {platform_name}'
        ) from e

    variant = variant_template.render(python_variant=python_variant) + '\n'
    variant_file = variant_dir / f'{platform_name}.yaml'
    with open(variant_file, 'w', encoding='utf-8') as file_handle:
        file_handle.write(variant)

    output_dir = slot_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if backend == 'pixi':
        if not pixi_exe:
            raise ValueError('pixi_exe is required when backend="pixi".')
        pixi_toml = _write_build_manifest(
            build_root=tools_dir,
            platform_name=platform_name,
        )
        command = (
            f'{build_pixi_env_unset_prefix()} '
            f'{shlex.quote(pixi_exe)} run -m {shlex.quote(str(pixi_toml))} '
            'rattler-build build '
            f'--recipe-dir {shlex.quote(str(recipe_dir.resolve()))} '
            f'--variant-config {shlex.quote(str(variant_file.resolve()))} '
            f'--output-dir {shlex.quote(str(output_dir))} '
        )
    elif backend == 'conda':
        conda_runner = _ensure_conda_rattler_build_env(
            conda_exe=conda_exe,
            log_filename=log_filename,
            quiet=quiet,
            tools_dir=tools_dir,
        )
        command = (
            f'{conda_runner} rattler-build build '
            f'--recipe-dir {shlex.quote(str(recipe_dir.resolve()))} '
            f'--variant-config {shlex.quote(str(variant_file.resolve()))} '
            f'--output-dir {shlex.quote(str(output_dir))} '
        )
    else:
        raise ValueError(
            f'Unsupported backend {backend!r}. Expected pixi or conda.'
        )

    check_call(command, log_filename=log_filename, quiet=quiet)


def _ensure_conda_rattler_build_env(
    *,
    conda_exe: str | None,
    log_filename: str,
    quiet: bool,
    tools_dir: Path,
) -> str:
    conda = _resolve_conda_executable(conda_exe)
    tool_prefix = tools_dir / 'conda-rattler-build'
    if not (tool_prefix / 'conda-meta').is_dir():
        tool_prefix.parent.mkdir(parents=True, exist_ok=True)
        command = (
            f'{shlex.quote(conda)} create --yes '
            f'--prefix {shlex.quote(str(tool_prefix))} '
            '--channel conda-forge '
            'rattler-build'
        )
        check_call_with_retries(
            command,
            log_filename=log_filename,
            quiet=quiet,
        )

    return f'{shlex.quote(conda)} run --prefix {shlex.quote(str(tool_prefix))}'


def _resolve_pixi_manifest(pixi_manifest: str | None) -> str:
    if pixi_manifest:
        resolved = os.path.abspath(os.path.expanduser(pixi_manifest))
    else:
        env_manifest = os.environ.get('PIXI_PROJECT_MANIFEST')
        if not env_manifest:
            raise ValueError(
                'pixi_manifest is required when backend="pixi" unless '
                'PIXI_PROJECT_MANIFEST is set.'
            )
        resolved = os.path.abspath(os.path.expanduser(env_manifest))

    if os.path.isdir(resolved):
        pixi_toml = os.path.join(resolved, 'pixi.toml')
        pyproject_toml = os.path.join(resolved, 'pyproject.toml')
        if os.path.isfile(pixi_toml):
            return pixi_toml
        if os.path.isfile(pyproject_toml):
            return pyproject_toml
        raise ValueError(
            'pixi manifest directory must contain pixi.toml or '
            f'pyproject.toml: {resolved}'
        )

    if not os.path.isfile(resolved):
        raise ValueError(f'pixi manifest not found: {resolved}')

    return resolved


def _prepare_local_pixi_manifest_copy(
    *, pixi_manifest: str | None, workspace_root: Path
) -> tuple[str, str | None]:
    source_manifest = _resolve_pixi_manifest(pixi_manifest)
    source_path = Path(source_manifest)

    # This copy derives from the source manifest, which is per-worktree,
    # rather than from the cache key, so it stays out of the shared cache.
    local_dir = workspace_root / 'pixi-local'
    local_dir.mkdir(parents=True, exist_ok=True)

    # pixi recognizes these manifest basenames.
    target_name = source_path.name
    if target_name not in ('pixi.toml', 'pyproject.toml'):
        target_name = 'pixi.toml'
    target_manifest = local_dir / target_name

    if source_path.resolve() != target_manifest.resolve():
        shutil.copyfile(source_path, target_manifest)

    local_feature = _ensure_local_pixi_jigsaw_feature(
        manifest_path=target_manifest
    )

    return str(target_manifest), local_feature


def _ensure_local_pixi_jigsaw_feature(*, manifest_path: Path) -> str | None:
    """Ensure local pixi copy has an isolated jigsaw feature/environment.

    For multi-environment pixi manifests, adding jigsawpy to the default
    feature can force all environments to solve against a single python_abi.
    In local mode we avoid that by targeting feature/environment ``jigsaw``.
    """
    if manifest_path.name != 'pixi.toml':
        return None

    try:
        text = manifest_path.read_text(encoding='utf-8')
    except OSError:
        return None

    if _toml_table_range(text, 'environments') is None:
        return None

    changed = False
    feature_tables = (
        'feature.jigsaw',
        'feature.jigsaw.dependencies',
        'feature.jigsaw.pypi-dependencies',
    )
    if not any(
        _toml_table_range(text, table) is not None for table in feature_tables
    ):
        if text and not text.endswith('\n'):
            text += '\n'
        text += '\n[feature.jigsaw.dependencies]\n'
        changed = True

    text, added_env = _append_toml_assignment_to_table(
        text=text,
        table='environments',
        key='jigsaw',
        assignment='jigsaw = ["jigsaw"]',
    )
    changed = changed or added_env

    if changed:
        manifest_path.write_text(text, encoding='utf-8')

    return 'jigsaw'


def _toml_table_range(text: str, table: str) -> tuple[int, int] | None:
    header = re.compile(rf'(?m)^\[{re.escape(table)}\]\s*$')
    match = header.search(text)
    if match is None:
        return None

    start = match.end()
    next_header = re.compile(r'(?m)^\[[^\]]+\]\s*$')
    next_match = next_header.search(text, start)
    end = next_match.start() if next_match else len(text)
    return start, end


def _append_toml_assignment_to_table(
    *, text: str, table: str, key: str, assignment: str
) -> tuple[str, bool]:
    table_range = _toml_table_range(text, table)
    if table_range is None:
        return text, False

    start, end = table_range
    section_text = text[start:end]
    if re.search(rf'(?m)^\s*{re.escape(key)}\s*=', section_text):
        return text, False

    if end == len(text):
        if text and not text.endswith('\n'):
            text += '\n'
        return text + f'{assignment}\n', True

    return text[:end] + f'{assignment}\n' + text[end:], True


def _resolve_conda_prefix(conda_prefix: str | None) -> str:
    prefix = conda_prefix or os.environ.get('CONDA_PREFIX')
    if not prefix:
        raise ValueError(
            'conda_prefix is required when backend="conda" unless '
            'CONDA_PREFIX is set.'
        )
    return os.path.abspath(os.path.expanduser(prefix))


def _resolve_conda_executable(conda_exe: str | None) -> str:
    return conda_exe or os.environ.get('CONDA_EXE') or 'conda'


def _install_into_pixi(
    *,
    pixi_exe: str,
    pixi_manifest: str | None,
    pixi_feature: str | None,
    channel_uri: str,
    jigsaw_version: str | None,
    log_filename: str,
    quiet: bool,
) -> None:
    manifest = _resolve_pixi_manifest(pixi_manifest)
    feature = pixi_feature or _infer_pixi_feature_for_active_environment(
        manifest=manifest
    )
    feature_arg = f'--feature {shlex.quote(feature)} ' if feature else ''
    platform_name, _ = _get_conda_platform_and_system()
    platform_arg = f'--platform {shlex.quote(platform_name)} '
    package_spec = _format_pixi_jigsaw_spec(jigsaw_version)

    add_channel_command = (
        f'{build_pixi_env_unset_prefix()} '
        f'{shlex.quote(pixi_exe)} workspace channel add '
        f'--manifest-path {shlex.quote(manifest)} '
        f'{feature_arg}'
        '--prepend '
        f'{shlex.quote(channel_uri)}'
    )
    check_call_with_retries(
        add_channel_command,
        log_filename=log_filename,
        quiet=quiet,
    )

    add_package_command = (
        f'{build_pixi_env_unset_prefix()} '
        f'{shlex.quote(pixi_exe)} add '
        f'--manifest-path {shlex.quote(manifest)} '
        f'{platform_arg}'
        f'{feature_arg}'
        f'{shlex.quote(package_spec)}'
    )
    check_call_with_retries(
        add_package_command,
        log_filename=log_filename,
        quiet=quiet,
    )


def _infer_pixi_feature_for_active_environment(
    *,
    manifest: str,
) -> str | None:
    environment_name = os.environ.get('PIXI_ENVIRONMENT_NAME')
    if not environment_name or environment_name == 'default':
        return None

    section_markers = [
        f'[feature.{environment_name}]',
        f'[feature.{environment_name}.dependencies]',
        f'[feature.{environment_name}.pypi-dependencies]',
    ]

    try:
        text = Path(manifest).read_text(encoding='utf-8')
    except OSError:
        return None

    for marker in section_markers:
        if marker in text:
            return environment_name

    return None


def _install_into_conda(
    *,
    conda_exe: str | None,
    conda_prefix: str | None,
    channel_uri: str,
    jigsaw_version: str | None,
    log_filename: str,
    quiet: bool,
) -> None:
    executable = _resolve_conda_executable(conda_exe)
    prefix = _resolve_conda_prefix(conda_prefix)
    package_spec = _format_conda_jigsaw_spec(jigsaw_version)
    command = (
        f'{shlex.quote(executable)} install --yes '
        f'--prefix {shlex.quote(prefix)} '
        f'--channel {shlex.quote(channel_uri)} '
        '--channel conda-forge '
        f'{shlex.quote(package_spec)}'
    )
    check_call(command, log_filename=log_filename, quiet=quiet)


def _format_pixi_jigsaw_spec(jigsaw_version: str | None) -> str:
    if not jigsaw_version:
        return 'jigsawpy'

    # Pin to the built version series, e.g. 1.1.0 -> jigsawpy=1.1.0.*
    return f'jigsawpy={jigsaw_version}.*'


def _format_conda_jigsaw_spec(jigsaw_version: str | None) -> str:
    if not jigsaw_version:
        return 'jigsawpy'

    return f'jigsawpy={jigsaw_version}'


def _get_local_channel_uri(*, output_dir: Path) -> str:
    if not output_dir.is_dir():
        raise RuntimeError(
            f'JIGSAW build output directory not found: {output_dir}'
        )
    platform_name, _ = _get_conda_platform_and_system()
    repodata = output_dir / platform_name / 'repodata.json'
    if not repodata.is_file():
        raise RuntimeError(
            f'JIGSAW build output repodata not found: {repodata}'
        )

    return output_dir.as_uri()
