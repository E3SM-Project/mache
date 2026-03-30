#!/usr/bin/env python3

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List  # noqa: F401

CONDA_PLATFORM_MAP = {
    ('linux', 'x86_64'): 'linux-64',
    ('linux', 'aarch64'): 'linux-aarch64',
    ('linux', 'ppc64le'): 'linux-ppc64le',
    ('osx', 'x86_64'): 'osx-64',
    ('osx', 'arm64'): 'osx-arm64',
}

LOCAL_MACHE_SOURCE_ENV = 'MACHE_LOCAL_SOURCE_PATH'
PIXI_ENV_VARS_TO_UNSET = (
    'PIXI_PROJECT_MANIFEST',
    'PIXI_PROJECT_ROOT',
    'PIXI_ENVIRONMENT_NAME',
    'PIXI_IN_SHELL',
)
BOOTSTRAP_SETUPTOOLS_SPEC = '>=60'
BOOTSTRAP_WHEEL_SPEC = '*'
CONDA_FORGE_LABEL_ROOT = 'https://conda.anaconda.org/conda-forge/label'
MACHE_DEV_LABEL = f'{CONDA_FORGE_LABEL_ROOT}/mache_dev'


def check_call(
    commands,
    log_filename,
    quiet,
    *,
    capture_output=False,
    check=True,
    **popen_kwargs,
):
    """
    Wrapper for making a shell call with logging and error management.

    This function is intentionally similar to :py:func:`subprocess.run`, while
    still providing the project-specific logging and "tee" behavior.

    Parameters
    ----------
    commands : str or list[str]
        Either a single shell command string (possibly chaining commands with
        "&&" or ";") or an argv-style command list for direct execution
        without a shell.

    log_filename : str
        The path to the log file to append to

    quiet : bool
        If True, only log to the log file, not to the terminal

    capture_output : bool, optional
        If True, capture stdout (and merged stderr) and return it in the
        returned :class:`subprocess.CompletedProcess`.

    check : bool, optional
        If True (default), raise :class:`subprocess.CalledProcessError` when
        the command returns a nonzero status.

    **popen_kwargs
        Additional keyword arguments passed through to
        :class:`subprocess.Popen`.

    Returns
    -------
    result : subprocess.CompletedProcess
        The result of the command. When ``capture_output`` is True, the
        combined output is available as ``result.stdout``.
    """

    if capture_output and (
        'stdout' in popen_kwargs
        or 'stderr' in popen_kwargs
        or 'capture_output' in popen_kwargs
    ):
        raise ValueError(
            'capture_output=True cannot be used with stdout/stderr/'
            'capture_output in popen_kwargs.'
        )

    if (capture_output or not quiet) and (
        'stdout' in popen_kwargs or 'stderr' in popen_kwargs
    ):
        raise ValueError(
            'stdout/stderr cannot be set when capture_output=True or '
            'quiet=False because this wrapper needs to stream output for '
            'logging/tee behavior.'
        )

    # Determine whether stdout is text or bytes (match subprocess defaults,
    # but keep this wrapper text-friendly by default).
    text, popen_kwargs = _normalize_popen_text_kwargs(popen_kwargs)
    bufsize = popen_kwargs.get('bufsize', 1 if text else 0)

    # Echo the commands being run (like a lightweight trace) so the log is
    # self-contained and debuggable.
    # Keep nested quoted commands intact (e.g. bash -c '... && ...').
    if isinstance(commands, str):
        command_list = _split_shell_on_andand(commands)
        if command_list:
            print_command = '\n   '.join(command_list)
        else:
            print_command = commands
    else:
        print_command = ' '.join(shlex.quote(str(arg)) for arg in commands)
    print_command = f'\n Running:\n   {print_command}\n'

    os.makedirs(os.path.dirname(os.path.abspath(log_filename)), exist_ok=True)

    log_mode = 'a' if text else 'ab'
    log_encoding = 'utf-8' if text else None

    # append to log file
    with open(log_filename, log_mode, encoding=log_encoding) as log_file:
        if text:
            log_file.write(print_command + '\n')
        else:
            log_file.write((print_command + '\n').encode('utf-8'))

    if not quiet:
        print(print_command)

    stdout_data = None

    base_popen_kwargs = {
        'universal_newlines': text,
        'bufsize': bufsize,
    }
    if isinstance(commands, str):
        base_popen_kwargs.update(
            {
                'executable': '/bin/bash',
                'shell': True,
            }
        )
    else:
        base_popen_kwargs.setdefault('shell', False)
    # Allow callers to override defaults.
    base_popen_kwargs.update(popen_kwargs)

    if capture_output or not quiet:
        # We'll stream stdout ourselves so we can tee to the log and terminal
        # and optionally capture output.
        base_popen_kwargs.setdefault('stdout', subprocess.PIPE)
        base_popen_kwargs.setdefault('stderr', subprocess.STDOUT)

        with open(log_filename, log_mode, encoding=log_encoding) as log_file:
            process = subprocess.Popen(commands, **base_popen_kwargs)

            assert process.stdout is not None
            captured_chunks = []

            for chunk in process.stdout:
                # chunk is str (text=True) or bytes (text=False)
                if capture_output:
                    captured_chunks.append(chunk)

                if text:
                    log_file.write(chunk)
                    log_file.flush()
                    if not quiet:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                else:
                    if isinstance(chunk, str):
                        chunk_bytes = chunk.encode('utf-8')
                    else:
                        chunk_bytes = chunk

                    log_file.write(chunk_bytes)
                    log_file.flush()
                    if not quiet:
                        sys.stdout.buffer.write(chunk_bytes)
                        sys.stdout.buffer.flush()

            process.wait()

        if capture_output:
            if text:
                stdout_data = ''.join(
                    chunk if isinstance(chunk, str) else chunk.decode('utf-8')
                    for chunk in captured_chunks
                )
            else:
                stdout_bytes = b''.join(
                    chunk.encode('utf-8') if isinstance(chunk, str) else chunk
                    for chunk in captured_chunks
                )
                # Keep this wrapper text-friendly: even when text=False, decode
                # captured output so stdout_data remains str.
                stdout_data = stdout_bytes.decode('utf-8', errors='replace')
    else:
        # Fast path: let the subprocess write directly to the log.
        base_popen_kwargs.setdefault('stdout', None)
        base_popen_kwargs.setdefault('stderr', subprocess.STDOUT)
        with open(log_filename, log_mode, encoding=log_encoding) as log_file:
            base_popen_kwargs['stdout'] = log_file
            process = subprocess.Popen(commands, **base_popen_kwargs)
            process.wait()

    result = subprocess.CompletedProcess(
        args=commands,
        returncode=process.returncode,
        stdout=stdout_data,
        stderr=None,
    )

    if check and process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, commands, output=stdout_data
        )

    return result


def check_call_with_retries(
    commands,
    log_filename,
    quiet,
    *,
    retries=3,
    retry_delay=2.0,
    **popen_kwargs,
):
    """Run a command with a few retries for transient pixi/network failures."""

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return check_call(commands, log_filename, quiet, **popen_kwargs)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt >= retries:
                raise

            message = (
                f'Command failed on attempt {attempt}/{retries}; '
                f'retrying in {retry_delay:.0f}s...\n'
            )
            with open(log_filename, 'a', encoding='utf-8') as log_file:
                log_file.write(message)
            if not quiet:
                print(message)
            time.sleep(retry_delay)

    if last_error is not None:
        raise last_error


def build_pixi_shell_hook_prefix(*, pixi_exe: str, pixi_toml: str) -> str:
    """Build a shell prefix to activate a pixi env in the current shell.

    Uses `pixi shell-hook` so activation applies to this shell rather than
    running a nested shell process.
    """
    hook_cmd = (
        f'{build_pixi_env_unset_prefix()} '
        f'{shlex.quote(pixi_exe)} shell-hook -s bash -m '
        f'{shlex.quote(pixi_toml)}'
    )
    return f'eval "$({hook_cmd})" &&'


def build_pixi_env(base_env=None):
    """Build an environment with pixi nesting variables removed."""
    env = dict(os.environ if base_env is None else base_env)
    for var in PIXI_ENV_VARS_TO_UNSET:
        env.pop(var, None)
    return env


def check_location(software=None):
    """
    Ensure that the script is being run from the root of the target software
    repository.

    Parameters
    ----------
    software : str, optional
        The target software name, used for a more specific error message.
        If not provided, a generic message is used.
    """
    expected_files = [
        'deploy.py',
        'deploy/cli_spec.json',
        'deploy/config.yaml.j2',
        'deploy/pins.cfg',
    ]
    missing_files = []
    for filename in expected_files:
        if not os.path.exists(filename):
            missing_files.append(filename)

    if missing_files:
        missing_str = '\n  - '.join(missing_files)
        if software:
            location_desc = f'the root of the local {software} branch'
        else:
            location_desc = 'the root of the target software repository'
        raise RuntimeError(
            f'The deploy script must be run from {location_desc}. '
            f'Expected files that were not found:\n  - {missing_str}'
        )


def install_dev_mache(
    pixi_shell_hook_prefix,
    log_filename,
    quiet,
    *,
    repo_root=None,
    src_dir=None,
):
    """
    Install mache from a fork and branch for development and testing
    """
    print('Clone and install local mache\n')

    # NOTE: We use `pixi shell-hook` to activate the environment in this
    # shell, then run pip install within that environment.
    # Also, the caller may have `cd`'d into the bootstrap pixi project, so we
    # explicitly `cd` back to the repo root first.
    if repo_root is None:
        repo_root = os.path.abspath(os.getcwd())
    else:
        repo_root = os.path.abspath(os.path.expanduser(str(repo_root)))

    if src_dir is None:
        src_dir = os.path.join(repo_root, 'deploy_tmp', 'build_mache', 'mache')
    else:
        src_dir = os.path.abspath(os.path.expanduser(str(src_dir)))

    if not os.path.isdir(src_dir):
        raise FileNotFoundError(
            'Expected mache source clone not found at '
            f'{src_dir}. This should have been created during bootstrap when '
            'using --mache-fork/--mache-branch.'
        )

    bash_cmd = (
        f'cd {shlex.quote(src_dir)} && '
        'python -m pip install --no-deps --no-build-isolation .'
    )
    commands = f'{pixi_shell_hook_prefix} {bash_cmd}'

    try:
        check_call(commands, log_filename, quiet)
    except subprocess.CalledProcessError:
        if quiet:
            print(
                f'Failed to clone and install local mache.  See '
                f'{log_filename} for details.\n'
            )
        raise


def main():
    """
    Entry point for the configure script
    """
    os.makedirs(name='deploy_tmp/logs', exist_ok=True)

    log_filename = 'deploy_tmp/logs/bootstrap.log'
    if os.path.exists(log_filename):
        os.remove(log_filename)

    try:
        _run(log_filename)
    except subprocess.CalledProcessError as e:
        _print_failure_summary(e, log_filename)
        raise
    except Exception as e:
        # unexpected python-level failures: missing perms, bad paths, etc.
        _print_failure_summary(e, log_filename)
        raise


def _run(log_filename):
    """
    Run the bootstrap process with the given log file
    """
    args = _parse_args()
    software = args.software
    quiet = args.quiet
    mache_version = args.mache_version

    check_location(software)

    os.makedirs('deploy_tmp', exist_ok=True)

    pixi_exe = _get_pixi_executable(
        args.pixi, log_filename=log_filename, quiet=quiet
    )

    bootstrap_dir = Path('deploy_tmp/bootstrap_pixi').resolve()
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    _write_bootstrap_pixi_config(bootstrap_dir=bootstrap_dir)

    if args.recreate and (bootstrap_dir / '.pixi').exists():
        shutil.rmtree(bootstrap_dir / '.pixi')

    # Create/update the bootstrap env
    if args.mache_fork is not None and args.mache_branch is not None:
        _clone_mache_repo(
            mache_fork=args.mache_fork,
            mache_branch=args.mache_branch,
            log_filename=log_filename,
            quiet=quiet,
            recreate=args.recreate,
        )

        # Developer-style install path: use mache's own pixi.toml to create
        # the environment, then install mache from source without PyPI deps.
        pixi_toml_path = bootstrap_dir / 'pixi.toml'
        _copy_mache_pixi_toml(
            dest_pixi_toml=pixi_toml_path,
            source_repo_dir=Path('deploy_tmp/build_mache/mache'),
            python_version=args.python,
        )

        cmd_install = [pixi_exe, 'install']
        check_call_with_retries(
            cmd_install,
            log_filename,
            quiet,
            cwd=str(bootstrap_dir),
            env=build_pixi_env(),
        )

        pixi_toml = str(pixi_toml_path.resolve())
        pixi_shell_hook_prefix = build_pixi_shell_hook_prefix(
            pixi_exe=pixi_exe,
            pixi_toml=pixi_toml,
        )
        install_dev_mache(
            pixi_shell_hook_prefix=pixi_shell_hook_prefix,
            log_filename=log_filename,
            quiet=quiet,
        )
    else:
        # Release/tag install path: install mache from conda-forge directly.
        pixi_toml_path = bootstrap_dir / 'pixi.toml'
        _write_bootstrap_pixi_toml_with_mache(
            pixi_toml_path=pixi_toml_path,
            software=software,
            mache_version=mache_version,
            python_version=args.python,
        )

        cmd_install = [pixi_exe, 'install']
        check_call_with_retries(
            cmd_install,
            log_filename,
            quiet,
            cwd=str(bootstrap_dir),
            env=build_pixi_env(),
        )


def _parse_args():
    """
    Parse arguments from the configure conda environment script call
    """

    parser = argparse.ArgumentParser(
        description='Bootstrap a pixi environment for running mache deploy'
    )
    parser.add_argument(
        '--software',
        dest='software',
        required=True,
        help='The name of the target software.',
    )
    parser.add_argument(
        '--pixi',
        dest='pixi',
        help='Path to the pixi executable. If not provided, pixi is found '
        'on PATH.',
    )
    parser.add_argument(
        '--pixi-path',
        '--prefix',
        dest='pixi_path',
        help='Install the pixi environment at this path (directory). '
        'This is a deploy-time option; bootstrap accepts it for CLI '
        'contract compatibility but does not use it. `--prefix` is '
        'deprecated.',
    )
    parser.add_argument(
        '--recreate',
        dest='recreate',
        action='store_true',
        help='Recreate the environment if it exists.',
    )
    parser.add_argument(
        '--mache-fork',
        dest='mache_fork',
        help='Point to a mache org/fork (and branch) for testing. '
        'Example: E3SM-Project/mache',
    )
    parser.add_argument(
        '--mache-branch',
        dest='mache_branch',
        help='Point to a mache branch (and fork) for testing.',
    )
    parser.add_argument(
        '--mache-version',
        dest='mache_version',
        help='The version of mache to install if not from a branch.',
    )
    parser.add_argument(
        '--python',
        dest='python',
        required=True,
        help='The python major and minor version to use.',
    )
    parser.add_argument(
        '--quiet',
        dest='quiet',
        action='store_true',
        help='Only print output to log files, not to the terminal.',
    )

    args = parser.parse_args(sys.argv[1:])

    if (args.mache_fork is None) != (args.mache_branch is None):
        raise ValueError(
            'You must supply both or neither of '
            '--mache-fork and --mache-branch'
        )

    if (
        args.mache_version is None
        and args.mache_fork is None
        and args.mache_branch is None
    ):
        raise ValueError(
            'You must supply --mache-version and/or both --mache-fork '
            'and --mache-branch.'
        )

    return args


def _normalize_popen_text_kwargs(popen_kwargs):
    """Translate subprocess text-mode kwargs for Python 3.6 compatibility."""
    normalized = dict(popen_kwargs)
    text = normalized.pop('text', None)
    universal_newlines = normalized.get('universal_newlines')

    if text is not None and universal_newlines is not None:
        if bool(text) != bool(universal_newlines):
            raise ValueError(
                'text and universal_newlines must match when both are set.'
            )

    if text is None:
        text = universal_newlines
    if text is None:
        text = True

    normalized['universal_newlines'] = text
    return text, normalized


def _split_shell_on_andand(commands):
    """Split a shell command string on top-level '&&' (quote-aware).

    This is used only for logging/pretty-printing in check_call(). It is not a
    full shell parser; it is a best-effort splitter that avoids breaking
    quoted sub-commands (e.g. bash -c '... && ...').
    """
    parts = []
    buf = []
    quote = None
    i = 0
    n = len(commands)

    while i < n:
        ch = commands[i]

        if quote is not None:
            # In double quotes, backslash can escape characters.
            if quote == '"' and ch == '\\' and i + 1 < n:
                buf.append(ch)
                buf.append(commands[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            buf.append(ch)
            i += 1
            continue

        # Not currently in a quote
        if ch == "'" or ch == '"':
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == '&' and i + 1 < n and commands[i + 1] == '&':
            part = ''.join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 2
            continue

        buf.append(ch)
        i += 1

    last = ''.join(buf).strip()
    if last:
        parts.append(last)

    return parts


def _print_failure_summary(err, log_filename, tail_lines=60):
    print('\nERROR: bootstrap failed.')
    print(f'See log: {os.path.abspath(log_filename)}')

    if isinstance(err, subprocess.CalledProcessError):
        print('\nFailing command:')
        print(err.cmd)
    else:
        print('\nDetails:')
        print(repr(err))

    try:
        with open(log_filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        tail = ''.join(lines[-tail_lines:])
        print(f'\nLast {min(tail_lines, len(lines))} log lines:\n{tail}')
    except OSError:
        pass


def _default_pixi_path():
    home = os.path.expanduser('~')
    return os.path.join(home, '.pixi', 'bin', 'pixi')


def build_pixi_env_unset_prefix():
    return 'env ' + ' '.join(f'-u {name}' for name in PIXI_ENV_VARS_TO_UNSET)


def _get_pixi_platform():
    system = platform.system().lower()
    if system == 'darwin':
        system = 'osx'
    machine = platform.machine().lower()
    try:
        return CONDA_PLATFORM_MAP[(system, machine)]
    except KeyError as exc:
        raise ValueError(
            f'Unsupported platform for pixi bootstrap: {system} {machine}'
        ) from exc


def _install_pixi(*, log_filename, quiet, pixi_bin_dir=None):
    env_prefix_parts = [
        # Avoid modifying shell rc files during bootstrap.
        'PIXI_NO_PATH_UPDATE=1',
    ]
    if pixi_bin_dir is not None:
        env_prefix_parts.append(f'PIXI_BIN_DIR={shlex.quote(pixi_bin_dir)}')

    env_prefix = ' '.join(env_prefix_parts)

    cmd_curl = f'{env_prefix} curl -fsSL https://pixi.sh/install.sh | sh'
    cmd_wget = f'{env_prefix} wget -qO- https://pixi.sh/install.sh | sh'

    try:
        check_call(cmd_curl, log_filename, quiet)
    except subprocess.CalledProcessError:
        # Fallback path, matching pixi installation instructions.
        check_call(cmd_wget, log_filename, quiet)


def _get_pixi_executable(pixi, *, log_filename, quiet):
    """Find pixi, installing it if needed.

    Behavior
    --------
    - If ``--pixi`` points to an existing executable, use it.
    - If ``--pixi`` is supplied but does not exist, treat it as the desired
      install location and install pixi there.
    - If ``--pixi`` is not supplied and pixi is not on PATH, install pixi
        in the default location (typically ``~/.pixi/bin``).

    The upstream installer supports choosing a destination via environment
    variables (not flags): ``PIXI_BIN_DIR`` and ``PIXI_HOME``.
    """

    # 1) Explicit path
    if pixi:
        pixi_path = os.path.abspath(os.path.expanduser(str(pixi)))

        if os.path.isfile(pixi_path) and os.access(pixi_path, os.X_OK):
            return pixi_path

        # Not an existing executable: treat as install target.
        if pixi_path.endswith(os.sep) or os.path.isdir(pixi_path):
            pixi_bin_dir = os.path.abspath(pixi_path)
            expected_exec = os.path.join(pixi_bin_dir, 'pixi')
        else:
            pixi_bin_dir = os.path.dirname(pixi_path)
            expected_exec = pixi_path

        _install_pixi(
            log_filename=log_filename, quiet=quiet, pixi_bin_dir=pixi_bin_dir
        )

        if os.path.isfile(expected_exec) and os.access(expected_exec, os.X_OK):
            return expected_exec

        raise RuntimeError(
            'pixi was installed but the executable was not found where '
            f'expected. Looked for: {expected_exec}'
        )

    # 2) PATH
    which = shutil.which('pixi')
    if which is not None:
        return which

    # 3) Default path
    if os.path.isfile(_default_pixi_path()) and os.access(
        _default_pixi_path(), os.X_OK
    ):
        return _default_pixi_path()

    # 4) Auto-install default
    _install_pixi(log_filename=log_filename, quiet=quiet, pixi_bin_dir=None)

    if os.path.isfile(_default_pixi_path()) and os.access(
        _default_pixi_path(), os.X_OK
    ):
        return _default_pixi_path()

    which = shutil.which('pixi')
    if which is not None:
        return which

    raise RuntimeError(
        'pixi was installed but could not be found. Expected it in the '
        "default location (e.g. '~/.pixi/bin') or on PATH."
    )


def _write_bootstrap_pixi_toml_with_mache(
    *,
    pixi_toml_path,
    software,
    mache_version,
    python_version,
):
    name = f'{software}-mache-bootstrap'
    channels = _get_bootstrap_channels_for_mache_version(mache_version)
    lines = [
        '[workspace]',
        f'name = "{name}"',
        f'channels = [{", ".join(json.dumps(c) for c in channels)}]',
        f'platforms = ["{_get_pixi_platform()}"]',
        'channel-priority = "strict"',
        '',
        '[dependencies]',
        f'python = "{python_version}.*"',
        'pip = "*"',
        'rattler-build = "*"',
        f'mache = "{_format_pixi_version_specifier(mache_version)}"',
    ]
    pixi_toml_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _write_bootstrap_pixi_config(*, bootstrap_dir: Path) -> None:
    config_dir = bootstrap_dir / '.pixi'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_toml = config_dir / 'config.toml'
    lines = [
        '# Keep conda-forge label channels on Anaconda because prefix.dev',
        '# does not currently mirror public conda-forge labels such as ',
        '# mache_dev.',
        '[mirrors]',
        f'"{CONDA_FORGE_LABEL_ROOT}" = [',
        f'  "{CONDA_FORGE_LABEL_ROOT}",',
        ']',
    ]
    config_toml.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _get_bootstrap_channels_for_mache_version(mache_version: str) -> List[str]:
    normalized = str(mache_version).strip().lower()
    if 'rc' in normalized:
        return [MACHE_DEV_LABEL, 'conda-forge']

    return ['conda-forge']


def _format_pixi_version_specifier(version: str) -> str:
    """Return a pixi version specifier from a mache version pin.

    Pixi dependency values expect a version specifier, not a full conda
    matchspec. Exact pins use ``==`` while wildcard pins already use the
    correct ``3.0.2.*``-style form.
    """

    normalized = str(version).strip()
    if normalized.endswith('.*'):
        return normalized
    return f'=={normalized}'


def _copy_mache_pixi_toml(*, dest_pixi_toml, source_repo_dir, python_version):
    src = Path(source_repo_dir) / 'pixi.toml'
    if not src.is_file():
        raise RuntimeError(
            f'Expected mache pixi.toml not found in cloned repo: {src}'
        )
    source_text = src.read_text(encoding='utf-8')
    channels = _get_pixi_channels_from_text(source_text)
    dependencies = _get_pixi_dependencies_from_text(source_text)

    _write_bootstrap_pixi_toml_with_local_source(
        pixi_toml_path=Path(dest_pixi_toml),
        channels=channels,
        dependencies=dependencies,
        python_version=python_version,
    )


def _write_bootstrap_pixi_toml_with_local_source(
    *,
    pixi_toml_path: Path,
    channels: List[str],
    dependencies: Dict[str, str],
    python_version: str,
) -> None:
    """Write a slim bootstrap pixi manifest for a local mache source tree.

    The full repo ``pixi.toml`` may contain CI-only features, named
    environments, and multiple platforms. The bootstrap environment only needs
    the current platform, the requested Python, and the runtime/build
    dependencies required to install the local mache checkout.
    """

    merged_channels = channels[:] if channels else ['conda-forge']
    merged_dependencies = dict(dependencies)
    merged_dependencies.setdefault('pip', '*')
    merged_dependencies.setdefault('rattler-build', '*')
    merged_dependencies.setdefault('setuptools', BOOTSTRAP_SETUPTOOLS_SPEC)
    merged_dependencies.setdefault('wheel', BOOTSTRAP_WHEEL_SPEC)

    lines = [
        '[workspace]',
        'name = "mache-bootstrap-local"',
        f'channels = [{", ".join(json.dumps(c) for c in merged_channels)}]',
        f'platforms = ["{_get_pixi_platform()}"]',
        'channel-priority = "strict"',
        '',
        '[dependencies]',
        f'python = "{python_version}.*"',
    ]

    for name, spec in merged_dependencies.items():
        if name == 'python':
            continue
        lines.append(f'{name} = {json.dumps(spec)}')

    pixi_toml_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def merge_pixi_toml_dependencies(
    *,
    target_pixi_toml: str,
    source_repo_dir: str,
    python_version: str,
) -> None:
    """Merge pixi channels and dependencies from a source repo into a target.

    This is used when deploying a local/forked ``mache`` branch into a
    downstream pixi environment. The source repo's ``pixi.toml`` is treated as
    the authoritative dependency set, including non-PyPI tools such as
    ``rsync``.
    """

    source_pixi_toml = Path(source_repo_dir) / 'pixi.toml'
    if not source_pixi_toml.is_file():
        raise RuntimeError(
            f'Expected mache pixi.toml not found in cloned repo: '
            f'{source_pixi_toml}'
        )

    source_text = source_pixi_toml.read_text(encoding='utf-8')
    channels = _get_pixi_channels_from_text(source_text)
    dependencies = _get_pixi_dependencies_from_text(source_text)

    target_path = Path(target_pixi_toml)
    text = target_path.read_text(encoding='utf-8')
    text = _merge_workspace_channels(text=text, channels=channels)
    text = _merge_dependencies_table(text=text, dependencies=dependencies)
    target_path.write_text(text, encoding='utf-8')


def _get_pixi_channels_from_text(source_text):
    section = _find_toml_table_block(text=source_text, table='workspace')
    if section is None:
        return []

    start, end = section
    workspace_text = source_text[start:end]
    match = re.search(r'(?ms)^channels\s*=\s*\[(.*?)\]', workspace_text)
    if match is None:
        return []

    return re.findall(r'"([^"]+)"', match.group(1))


def _get_pixi_dependencies_from_text(source_text):
    dependencies = {}  # type: Dict[str, str]

    section = _find_toml_table_block(text=source_text, table='dependencies')
    if section is None:
        return dependencies

    start, end = section
    section_text = source_text[start:end]
    for match in re.finditer(
        r'(?m)^([A-Za-z0-9_.-]+)\s*=\s*"([^"\n]+)"\s*$',
        section_text,
    ):
        name = match.group(1)
        spec = match.group(2)
        if name == 'python':
            continue
        dependencies.setdefault(name, spec)

    return dependencies


def _merge_workspace_channels(*, text, channels):
    if not channels:
        return text

    section = _find_toml_table_block(text=text, table='workspace')
    if section is None:
        return text

    start, end = section
    workspace_text = text[start:end]
    match = re.search(r'(?ms)^channels\s*=\s*\[(.*?)\]', workspace_text)
    if match is None:
        return text

    existing = re.findall(r'"([^"]+)"', match.group(1))
    merged = existing[:]
    for channel in channels:
        if channel not in merged:
            merged.append(channel)

    replacement = (
        'channels = [' + ', '.join(json.dumps(c) for c in merged) + ']'
    )
    updated_workspace = (
        workspace_text[: match.start()]
        + replacement
        + workspace_text[match.end() :]
    )
    return text[:start] + updated_workspace + text[end:]


def _merge_dependencies_table(*, text, dependencies):
    if not dependencies:
        return text

    section = _find_toml_table_block(text=text, table='dependencies')
    if section is None:
        return text

    start, end = section
    deps_text = text[start:end]
    existing = {
        match.group(1)
        for match in re.finditer(
            r'(?m)^([A-Za-z0-9_.-]+)\s*=',
            deps_text,
        )
    }

    additions = [
        f'{name} = {json.dumps(spec)}'
        for name, spec in dependencies.items()
        if name not in existing
    ]
    if not additions:
        return text

    if deps_text and not deps_text.endswith('\n'):
        deps_text += '\n'
    deps_text += '\n'.join(additions) + '\n'
    return text[:start] + deps_text + text[end:]


def _find_toml_table_block(*, text, table):
    header = re.compile(rf'(?m)^\[{re.escape(table)}\]\s*$')
    match = header.search(text)
    if match is None:
        return None

    start = match.end()
    next_header = re.compile(r'(?m)^\[[^\]]+\]\s*$')
    next_match = next_header.search(text, start)
    end = next_match.start() if next_match else len(text)
    return start, end


def _clone_mache_repo(
    *,
    mache_fork,
    mache_branch,
    log_filename,
    quiet,
    recreate,
):
    build_root = Path('deploy_tmp/build_mache').resolve()
    repo_dir = build_root / 'mache'

    if recreate and build_root.exists():
        shutil.rmtree(str(build_root))

    if repo_dir.exists():
        # Avoid clobbering developer edits in an existing clone.
        return

    build_root.mkdir(parents=True, exist_ok=True)

    local_source = os.environ.get(LOCAL_MACHE_SOURCE_ENV)
    if local_source:
        source_repo = Path(
            os.path.abspath(os.path.expanduser(local_source))
        ).resolve()
        if not source_repo.is_dir():
            raise RuntimeError(
                f'Local mache source override does not exist: {source_repo}'
            )

        _copy_local_mache_source_snapshot(
            source_repo=source_repo,
            repo_dir=repo_dir,
        )
        return

    env = build_pixi_env()
    env['GIT_SSH_COMMAND'] = 'ssh -oBatchMode=yes'
    commands = [
        'git',
        'clone',
        '--depth',
        '1',
        '--single-branch',
        '-b',
        mache_branch,
        f'git@github.com:{mache_fork}.git',
        'mache',
    ]
    check_call(
        commands,
        log_filename,
        quiet,
        cwd=str(build_root),
        env=env,
    )


def _copy_local_mache_source_snapshot(
    *, source_repo: Path, repo_dir: Path
) -> None:
    """Copy a clean local source snapshot for bootstrap installs.

    Using the live developer worktree directly can pull in untracked files or
    local symlinks that break setuptools packaging. Prefer a tracked-file
    snapshot when the source is a git checkout, and fall back to a filtered
    copytree otherwise.
    """

    try:
        tracked = subprocess.check_output(
            ['git', '-C', str(source_repo), 'ls-files', '-z'],
            text=False,
        )
    except (OSError, subprocess.CalledProcessError):
        shutil.copytree(
            source_repo,
            repo_dir,
            ignore=shutil.ignore_patterns(
                '.git',
                '.pixi',
                'deploy_tmp',
                '__pycache__',
                '*.pyc',
            ),
        )
        return

    repo_dir.mkdir(parents=True, exist_ok=True)
    for raw_path in tracked.split(b'\x00'):
        if not raw_path:
            continue
        rel_path = Path(raw_path.decode('utf-8'))
        src_path = source_repo / rel_path
        dest_path = repo_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.is_symlink():
            os.symlink(os.readlink(src_path), dest_path)
        else:
            shutil.copy2(src_path, dest_path)


if __name__ == '__main__':
    main()
