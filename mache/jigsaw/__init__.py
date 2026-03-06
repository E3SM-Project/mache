from __future__ import annotations

import hashlib
import os
import platform
import re
import shlex
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from mache.deploy.bootstrap import check_call

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


@dataclass(frozen=True)
class JigsawBuildResult:
    channel_uri: str
    channel_dir: Path
    cache_key: str
    cache_hit: bool
    jigsaw_version: str


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
        python_version=resolved_python_version,
        jigsaw_version=result.jigsaw_version,
        backend=selected_backend,
        pixi_exe=resolved_pixi_exe,
        pixi_manifest=pixi_manifest,
        pixi_feature=pixi_feature,
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
    python_version: str | None = None,
    jigsaw_version: str | None = None,
    backend: str = 'auto',
    pixi_exe: str | None = None,
    pixi_manifest: str | None = None,
    pixi_feature: str | None = None,
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
    python_version : str, optional
        Python major/minor version retained for API compatibility.
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
        _install_into_pixi(
            pixi_exe=pixi_exe,
            pixi_manifest=pixi_manifest,
            pixi_feature=pixi_feature,
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
    output_dir = _get_jigsaw_cache_dir()

    if _is_cached_jigsaw_build_valid(cache_key=cache_key):
        if not quiet:
            print('Using cached JIGSAW build')
        return JigsawBuildResult(
            channel_uri=_get_local_channel_uri(output_dir=output_dir),
            channel_dir=output_dir,
            cache_key=cache_key,
            cache_hit=True,
            jigsaw_version=jigsaw_version,
        )

    selected_backend = detect_install_backend(backend=backend)

    _build_external_jigsaw(
        backend=selected_backend,
        pixi_exe=pixi_exe,
        conda_exe=conda_exe,
        jigsaw_python_dir=jigsaw_python_dir,
        python_version=python_version,
        jigsaw_version=jigsaw_version,
        log_filename=log_filename,
        quiet=quiet,
    )

    _write_jigsaw_cache_key(cache_key=cache_key)

    return JigsawBuildResult(
        channel_uri=_get_local_channel_uri(output_dir=output_dir),
        channel_dir=output_dir,
        cache_key=cache_key,
        cache_hit=False,
        jigsaw_version=jigsaw_version,
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


def _get_git_head(repo_dir: Path) -> str:
    git_dir = repo_dir / '.git'
    if git_dir.is_dir():
        git_root = git_dir
    elif git_dir.is_file():
        git_file = git_dir.read_text(encoding='utf-8').strip()
        if not git_file.startswith('gitdir:'):
            raise RuntimeError(
                f'Unexpected .git file format in {repo_dir}: {git_file!r}'
            )
        gitdir_path = git_file.split(':', 1)[1].strip()
        git_root = (repo_dir / gitdir_path).resolve()
    else:
        raise RuntimeError(
            f'Expected git checkout at {repo_dir} but .git not found.'
        )

    head_file = git_root / 'HEAD'
    if not head_file.is_file():
        raise RuntimeError(
            f'Expected git checkout at {repo_dir} but HEAD not found in '
            f'{git_root}.'
        )

    head_ref = head_file.read_text(encoding='utf-8').strip()
    if head_ref.startswith('ref:'):
        ref_path = head_ref.split(' ', 1)[1].strip()
        ref_file = git_root / ref_path
        if not ref_file.is_file():
            raise RuntimeError(f'Git ref {ref_path} not found in {git_root}.')
        return ref_file.read_text(encoding='utf-8').strip()

    return head_ref


def _compute_jigsaw_cache_key(
    *,
    jigsaw_python_dir: Path,
    python_version: str,
) -> str:
    platform_name, _ = _get_conda_platform_and_system()
    jigsaw_version = _get_jigsaw_version(jigsaw_python_dir)
    git_head = _get_git_head(jigsaw_python_dir)
    python_variant = PYTHON_VARIANTS.get(python_version, '')

    payload = {
        'git_head': git_head,
        'jigsaw_version': jigsaw_version,
        'python_version': python_version,
        'python_variant': python_variant,
        'platform': platform_name,
    }

    digest = hashlib.sha256()
    for key in sorted(payload):
        digest.update(f'{key}={payload[key]}\n'.encode('utf-8'))
    return digest.hexdigest()


def _cache_key_path() -> Path:
    return _get_jigsaw_cache_dir() / '.jigsaw_cache_key'


def _get_jigsaw_cache_dir() -> Path:
    return Path('.mache_cache/jigsaw').resolve()


def _read_jigsaw_cache_key() -> str | None:
    cache_path = _cache_key_path()
    if not cache_path.is_file():
        return None
    return cache_path.read_text(encoding='utf-8').strip() or None


def _write_jigsaw_cache_key(*, cache_key: str) -> None:
    cache_path = _cache_key_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(f'{cache_key}\n', encoding='utf-8')


def _is_cached_jigsaw_build_valid(*, cache_key: str) -> bool:
    cached_key = _read_jigsaw_cache_key()
    if cached_key != cache_key:
        return False

    output_dir = _get_jigsaw_cache_dir()
    if not output_dir.is_dir():
        return False

    platform_name, _ = _get_conda_platform_and_system()
    repodata = output_dir / platform_name / 'repodata.json'
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
) -> None:
    print('Building JIGSAW')

    if python_version not in PYTHON_VARIANTS:
        raise ValueError(f'Unsupported python version: {python_version}')

    python_variant = PYTHON_VARIANTS.get(python_version)
    build_root = (_get_jigsaw_cache_dir() / 'build').resolve()
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

    output_dir = _get_jigsaw_cache_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    if backend == 'pixi':
        if not pixi_exe:
            raise ValueError('pixi_exe is required when backend="pixi".')
        pixi_toml = _write_build_manifest(
            build_root=build_root,
            platform_name=platform_name,
        )
        command = (
            'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
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
) -> str:
    conda = _resolve_conda_executable(conda_exe)
    tool_prefix = _get_jigsaw_cache_dir() / 'build' / 'conda-rattler-build'
    if not (tool_prefix / 'conda-meta').is_dir():
        tool_prefix.parent.mkdir(parents=True, exist_ok=True)
        command = (
            f'{shlex.quote(conda)} create --yes '
            f'--prefix {shlex.quote(str(tool_prefix))} '
            '--channel conda-forge '
            'rattler-build'
        )
        check_call(command, log_filename=log_filename, quiet=quiet)

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
        f'{shlex.quote(pixi_exe)} workspace channel add '
        f'--manifest-path {shlex.quote(manifest)} '
        f'{feature_arg}'
        '--prepend '
        f'{shlex.quote(channel_uri)}'
    )
    check_call(add_channel_command, log_filename=log_filename, quiet=quiet)

    add_package_command = (
        f'{shlex.quote(pixi_exe)} add '
        f'--manifest-path {shlex.quote(manifest)} '
        f'{platform_arg}'
        f'{feature_arg}'
        f'{shlex.quote(package_spec)}'
    )
    check_call(add_package_command, log_filename=log_filename, quiet=quiet)


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
