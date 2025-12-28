from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .bootstrap import check_call

JIGSAW_PYTHON_URL = 'git@github.com:dengwirda/jigsaw-python.git'


def install_jigsaw(
    config: dict,
    activate_bootstrap_env: str,
    activate_install_env: str,
    install_env_path: str,
    repo_root: str,
    log_filename: str,
    quiet: bool,
) -> None:
    """
    Optionally install JIGSAW and JIGSAW-Python in the deployment env.

    The workflow is as follows:

      - ensure the JIGSAW-Python source exists (submodule init or clone)
      - remove any conda-provided jigsaw/jigsawpy to avoid conflicts
      - build the bundled external/jigsaw with conda-forge compilers
      - install jigsawpy in editable mode and copy bundled binaries into
        $CONDA_PREFIX/bin

    Config keys (all under the top-level `jigsaw` mapping):

      - enabled: bool (default False)
      - jigsaw_python_path: str (default "jigsaw-python")

    Parameters
    ----------
    config : dict
        The full deployment configuration dictionary.
    activate_bootstrap_env : str
        The command to activate the bootstrap conda environment.
    activate_install_env : str
        The command to activate the target software's conda environment.
    install_env_path : str
        The path to the target software's conda environment.
    repo_root : str
        The path to the target software repository root.
    log_filename : str
        The path to the log file.
    quiet : bool
        Whether to suppress output to stdout.
    """

    jigsaw_cfg = (config or {}).get('jigsaw') or {}
    enabled = bool(jigsaw_cfg.get('enabled', False))
    if not enabled:
        return

    repo_root_path = Path(repo_root).resolve()
    rel_path = jigsaw_cfg.get('jigsaw_python_path', None)
    if not rel_path:
        raise ValueError(
            'Invalid config: jigsaw.jigsaw_python_path is missing'
        )

    jigsaw_python_dir = (repo_root_path / rel_path).resolve()

    # build with the bootstrap env
    _ensure_jigsaw_python_source(
        repo_root=repo_root_path,
        jigsaw_python_dir=jigsaw_python_dir,
        rel_path=rel_path,
        activate_env=activate_bootstrap_env,
        log_filename=log_filename,
        quiet=quiet,
    )

    _build_external_jigsaw(
        activate_env=activate_bootstrap_env,
        install_env_path=install_env_path,
        jigsaw_python_dir=jigsaw_python_dir,
        log_filename=log_filename,
        quiet=quiet,
    )

    # install into the target software env
    _remove_conda_jigsaw_packages(
        activate_env=activate_install_env,
        log_filename=log_filename,
        quiet=quiet,
    )

    _install_jigsaw_python(
        activate_env=activate_install_env,
        jigsaw_python_dir=jigsaw_python_dir,
        log_filename=log_filename,
        quiet=quiet,
    )


def _ensure_jigsaw_python_source(
    repo_root: Path,
    jigsaw_python_dir: Path,
    rel_path: str,
    activate_env: str,
    log_filename: str,
    quiet: bool,
) -> None:
    has_submodule = False
    if os.path.exists('.gitmodules'):
        # let's see of a line has "path = <rel_path>"
        with open('.gitmodules', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('path = ') and rel_path in line:
                    has_submodule = True
                    break

    if has_submodule:
        if not os.path.exists(f'{jigsaw_python_dir}/.git'):
            # only init if not already done to avoid undoing development edits
            commands = (
                f'{activate_env} && '
                f'cd "{repo_root}" && '
                f'git submodule update --init "{rel_path}"'
            )
            check_call(commands, log_filename=log_filename, quiet=quiet)

    elif not jigsaw_python_dir.is_dir():
        commands = (
            f'{activate_env} && '
            f'cd "{repo_root}" && '
            f'git clone --depth 1 "{JIGSAW_PYTHON_URL}" "{rel_path}"'
        )
        check_call(commands, log_filename=log_filename, quiet=quiet)

    if not jigsaw_python_dir.is_dir():
        raise RuntimeError(
            f'Failed to acquire JIGSAW-Python at {jigsaw_python_dir} '
            f'(clone_url={JIGSAW_PYTHON_URL}).'
        )


def _remove_conda_jigsaw_packages(
    activate_env: str,
    log_filename: str,
    quiet: bool,
) -> None:
    commands = (
        f'{activate_env} && conda remove -y --force-remove jigsaw jigsawpy'
    )
    try:
        check_call(commands, log_filename=log_filename, quiet=quiet)
    except subprocess.CalledProcessError:
        # Fine if not installed.
        pass


def _build_external_jigsaw(
    activate_env: str,
    install_env_path: str,
    jigsaw_python_dir: Path,
    log_filename: str,
    quiet: bool,
) -> None:
    print('Building JIGSAW')

    jigsaw_build_deps = 'cxx-compiler cmake make'
    system = platform.system()
    if system == 'Linux':
        jigsaw_build_deps = f'{jigsaw_build_deps} sysroot_linux-64=2.17'
        netcdf_lib = f'{install_env_path}/lib/libnetcdf.so'
    elif system == 'Darwin':
        jigsaw_build_deps = (
            f'{jigsaw_build_deps} macosx_deployment_target_osx-64=10.13'
        )
        netcdf_lib = f'{install_env_path}/lib/libnetcdf.dylib'
    else:
        raise ValueError(f'Unsupported platform for JIGSAW build: {system!r}')

    if not os.path.exists(netcdf_lib):
        raise RuntimeError(
            f'Expected NetCDF library not found at {netcdf_lib} '
            f'(is NetCDF installed in the target environment?)'
        )

    cmake_args = f'-DCMAKE_BUILD_TYPE=Release -DNETCDF_LIBRARY={netcdf_lib}'

    external_jigsaw_dir = jigsaw_python_dir / 'external' / 'jigsaw'
    if not external_jigsaw_dir.is_dir():
        raise RuntimeError(
            'Expected JIGSAW source not found at '
            f'{external_jigsaw_dir} (is your JIGSAW-Python checkout complete?)'
        )

    commands = (
        f'{activate_env} && '
        f'conda install -y {jigsaw_build_deps} && '
        f'cd "{external_jigsaw_dir}" && '
        f'rm -rf tmp && mkdir tmp && cd tmp && '
        f'cmake .. {cmake_args} && '
        f'cmake --build . --config Release --target install --parallel 4 && '
        f'cd "{jigsaw_python_dir}" && '
        f'rm -rf jigsawpy/_bin jigsawpy/_lib && '
        f'cp -r external/jigsaw/bin/ jigsawpy/_bin && '
        f'cp -r external/jigsaw/lib/ jigsawpy/_lib'
    )
    check_call(commands, log_filename=log_filename, quiet=quiet)


def _install_jigsaw_python(
    activate_env: str,
    jigsaw_python_dir: Path,
    log_filename: str,
    quiet: bool,
) -> None:
    print('Installing JIGSAW and JIGSAW-Python')
    commands = (
        f'{activate_env} && '
        f'cd "{jigsaw_python_dir}" && '
        f'python -m pip install --no-deps --no-build-isolation -e . && '
        f'cp jigsawpy/_bin/* "${{CONDA_PREFIX}}/bin"'
    )
    check_call(commands, log_filename=log_filename, quiet=quiet)
