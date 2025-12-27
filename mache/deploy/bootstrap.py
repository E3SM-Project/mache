#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import sys
from urllib.request import Request, urlopen


def check_call(commands, log_filename, quiet):
    """
    Wrapper for making a shell call with logging and error management

    Parameters
    ----------
    commands : str
        A single shell command string (possibly chaining commands with "&&" or
        ";")

    log_filename : str
        The path to the log file to append to

    quiet : bool
        If True, only log to the log file, not to the terminal
    """

    # Echo the commands being run (like a lightweight trace) so the log is
    # self-contained and debuggable.
    command_list = commands.replace(' && ', '; ').split('; ')

    print_command = '\n   '.join(command_list)
    print_command = f'\n Running:\n   {print_command}\n'

    os.makedirs(os.path.dirname(os.path.abspath(log_filename)), exist_ok=True)

    # append to log file
    with open(log_filename, 'a', encoding='utf-8') as log_file:
        log_file.write(print_command + '\n')

    if not quiet:
        print(print_command)

    if quiet:
        # Fast path: let the subprocess write directly to the log.
        with open(log_filename, 'a', encoding='utf-8') as log_file:
            process = subprocess.Popen(
                commands,
                executable='/bin/bash',
                shell=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            process.wait()
    else:
        # Tee-like behavior without spawning a separate `tee` process.
        # Merge stderr into stdout to preserve ordering.
        with open(log_filename, 'a', encoding='utf-8') as log_file:
            process = subprocess.Popen(
                commands,
                executable='/bin/bash',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert process.stdout is not None
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                sys.stdout.write(line)
                sys.stdout.flush()

            process.wait()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, commands)


def check_location(software):
    """
    Ensure that the bootstrap script is being run from the root of the target
    software

    Parameters
    ----------
    software : str
        The target software name
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
        raise RuntimeError(
            f'The bootstrap script must be run from the '
            f'root of the local {software} branch. '
            f'Expected files that were not found:\n  - {missing_str}'
        )


def get_conda_base(conda_base):
    """
    Get the absolute path to the files for the conda base environment

    Parameters
    ----------
    conda_base : str
        The relative or absolute path to the conda base files

    Returns
    -------
    conda_base : str
        Path to the conda base environment
    """

    if conda_base is None:
        try:
            conda_base = subprocess.check_output(
                ['conda', 'info', '--base'], text=True
            ).strip()
            print(
                f'\nWarning: --conda path not supplied.  Using conda '
                f'installed at:\n'
                f'   {conda_base}\n'
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(
                'No conda base provided with --conda and '
                'none could be inferred.'
            ) from e
    # handle "~" in the path
    conda_base = os.path.abspath(os.path.expanduser(conda_base))
    return conda_base


def install_miniforge(
    conda_base, activate_base, log_filename, quiet, update_base
):
    """
    Install Miniforge if it isn't installed already

    Parameters
    ----------
    conda_base : str
        Absolute path to the conda base environment files

    activate_base : str
        Command to activate the conda base environment

    log_filename : str
        The path to the log file to append to

    quiet : bool
        If True, only log to the log file, not to the terminal
    """

    if not os.path.exists(conda_base):
        print('Installing Miniforge3')
        if platform.system() == 'Darwin':
            system = 'MacOSX'
        else:
            system = 'Linux'
        machine = platform.machine().lower()
        if machine in ('amd64',):
            machine = 'x86_64'
        if machine in ('arm64',) and system == 'Linux':
            # sometimes Linux arm64 should be aarch64 for toolchains
            machine = 'aarch64'
        miniforge = f'Miniforge3-{system}-{machine}.sh'
        url = f'https://github.com/conda-forge/miniforge/releases/latest/download/{miniforge}'  # noqa: E501
        print(url)
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urlopen(req, timeout=60) as f:
                html = f.read()

                first_line = html.splitlines()[0].strip()
                if b'bash' not in first_line:
                    raise RuntimeError(
                        'Downloaded Miniforge installer does not look like a '
                        'shell script. This may indicate a proxy or redirect '
                        'problem.'
                    )
                with open(miniforge, 'wb') as outfile:
                    outfile.write(html)
        except (OSError, TimeoutError) as e:
            raise RuntimeError(
                f'Failed to download the Miniforge installer from {url}. '
                f'You may need to download and install it manually, and use '
                f' the --conda flag to point to the resulting installation.'
            ) from e
        command = f'/bin/bash "{miniforge}" -b -p "{conda_base}"'
        check_call(command, log_filename, quiet)
        os.remove(miniforge)

    # check that "conda" command is available
    try:
        check_call(f'{activate_base} && conda --version', log_filename, quiet)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            'Conda installation failed or conda command not found.'
        ) from e

    print('Update conda config\n')
    commands = (
        f'{activate_base} && '
        f'conda config --add channels conda-forge && '
        f'conda config --set channel_priority strict'
    )

    check_call(commands, log_filename, quiet)

    if update_base:
        print('Update config and base conda environment\n')
        commands = f'{activate_base} && conda update -y --all'

        check_call(commands, log_filename, quiet)


def install_dev_mache(
    activate_install_env, mache_fork, mache_branch, log_filename, quiet
):
    """
    Install mache from a fork and branch for development and testing
    """
    print('Clone and install local mache\n')
    commands = (
        f'{activate_install_env} && '
        f'rm -rf deploy_tmp/build_mache && '
        f'mkdir -p deploy_tmp/build_mache && '
        f'cd deploy_tmp/build_mache && '
        f"GIT_SSH_COMMAND='ssh -oBatchMode=yes' git clone "
        f'--depth 1 --single-branch -b "{mache_branch}" '
        f'"git@github.com:{mache_fork}.git" mache && '
        f'cd mache && '
        f'conda install -y --file spec-file.txt && '
        f'python -m pip install --no-deps --no-build-isolation .'
    )

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

    conda_base = get_conda_base(args.conda)
    conda_base = os.path.abspath(conda_base)

    env_name = 'mache_deploy'

    source_activation_scripts = f'source "{conda_base}/etc/profile.d/conda.sh"'

    activate_base = f'{source_activation_scripts} && conda activate base'

    activate_install_env = (
        f'{source_activation_scripts} && conda activate "{env_name}"'
    )

    # install miniforge if needed
    install_miniforge(
        conda_base, activate_base, log_filename, quiet, args.update_base
    )

    packages = 'pip'
    if mache_version is not None:
        packages = f'{packages} "mache={mache_version}"'

    _setup_install_env(
        env_name,
        activate_base,
        log_filename,
        quiet,
        args.recreate,
        conda_base,
        packages,
        software,
    )

    if mache_version is None:
        install_dev_mache(
            activate_install_env,
            args.mache_fork,
            args.mache_branch,
            log_filename,
            quiet,
        )


def _parse_args():
    """
    Parse arguments from the configure conda environment script call
    """

    parser = argparse.ArgumentParser(
        description='Deploy conda and spack environment'
    )
    parser.add_argument(
        '--software',
        dest='software',
        required=True,
        help='The name of the target software.',
    )
    parser.add_argument(
        '--conda',
        dest='conda',
        help='Path to the conda installation. If not provided, the path '
        'will be determined from "conda info".',
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
        '--quiet',
        dest='quiet',
        action='store_true',
        help='Only print output to log files, not to the terminal.',
    )
    parser.add_argument(
        '--update-base',
        dest='update_base',
        action='store_true',
        help='Update packages in the conda base environment.',
    )

    args = parser.parse_args(sys.argv[1:])

    if (args.mache_fork is None) != (args.mache_branch is None):
        raise ValueError(
            'You must supply both or neither of '
            '--mache-fork and --mache-branch'
        )

    if (args.mache_fork is None) == (args.mache_version is None):
        raise ValueError(
            'You must either supply --mache-version or both --mache-fork '
            'and --mache-branch.'
        )

    return args


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


def _setup_install_env(
    env_name,
    activate_base,
    log_filename,
    quiet,
    recreate,
    conda_base,
    packages,
    software,
):
    """
    Setup a conda environment for installing the target software
    """

    env_path = os.path.join(conda_base, 'envs', env_name)

    channels = '-c conda-forge'

    if recreate or not os.path.exists(env_path):
        print(f'Setting up a conda environment for installing {software}\n')
        conda_command = 'create'
    else:
        print(f'Updating conda environment for installing {software}\n')
        conda_command = 'install'
    commands = (
        f'{activate_base} && '
        f'conda {conda_command} -y -n "{env_name}" {channels} {packages}'
    )

    check_call(commands, log_filename, quiet)


if __name__ == '__main__':
    main()
