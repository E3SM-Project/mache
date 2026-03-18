#!/usr/bin/env python3

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


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
    commands : str
        A single shell command string (possibly chaining commands with "&&" or
        ";")

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
    # Keep nested quoted commands intact (e.g. bash -lc '... && ...').
    command_list = _split_shell_on_andand(commands)
    if command_list:
        print_command = '\n   '.join(command_list)
    else:
        print_command = commands
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
        'executable': '/bin/bash',
        'shell': True,
        'universal_newlines': text,
        'bufsize': bufsize,
    }
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


def build_pixi_shell_hook_prefix(*, pixi_exe: str, pixi_toml: str) -> str:
    """Build a shell prefix to activate a pixi env in the current shell.

    Uses `pixi shell-hook` so activation applies to this shell rather than
    running a nested shell process.
    """
    hook_cmd = (
        'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
        f'{shlex.quote(pixi_exe)} shell-hook -s bash -m '
        f'{shlex.quote(pixi_toml)}'
    )
    return f'eval "$({hook_cmd})" &&'


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
        )

        cmd_install = (
            f'cd "{bootstrap_dir}" && '
            'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
            f'"{pixi_exe}" install'
        )
        check_call(cmd_install, log_filename, quiet)

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

        cmd_install = (
            f'cd "{bootstrap_dir}" && '
            'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
            f'"{pixi_exe}" install'
        )
        check_call(cmd_install, log_filename, quiet)


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
        '--prefix',
        dest='prefix',
        help='Install the environment into this prefix (directory). '
        'This is a deploy-time option; bootstrap accepts it for CLI '
        'contract compatibility but does not use it.',
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
    quoted sub-commands (e.g. bash -lc '... && ...').
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
    lines = [
        '[workspace]',
        f'name = "{name}"',
        'channels = ["conda-forge"]',
        'channel-priority = "strict"',
        '',
        '[dependencies]',
        f'python = "{python_version}.*"',
        'pip = "*"',
        'rattler-build = "*"',
        f'mache = "=={mache_version}"',
    ]
    pixi_toml_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _copy_mache_pixi_toml(*, dest_pixi_toml, source_repo_dir):
    src = Path(source_repo_dir) / 'pixi.toml'
    if not src.is_file():
        raise RuntimeError(
            f'Expected mache pixi.toml not found in cloned repo: {src}'
        )
    shutil.copyfile(str(src), str(dest_pixi_toml))


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

    commands = (
        f'cd "{build_root!s}" && '
        + "GIT_SSH_COMMAND='ssh -oBatchMode=yes' git clone "
        + f'--depth 1 --single-branch -b "{mache_branch}" '
        + f'"git@github.com:{mache_fork}.git" mache'
    )
    check_call(commands, log_filename, quiet)


if __name__ == '__main__':
    main()
