from __future__ import annotations

import os
import subprocess
from importlib import resources
from pathlib import Path

import tomllib

from mache.deploy.bootstrap import check_call
from mache.deploy.conda import get_conda_platform_and_system
from mache.deploy.jinja import define_square_bracket_environment

JIGSAW_PYTHON_URL = 'git@github.com:dengwirda/jigsaw-python.git'

PYTHON_VARIANTS = {
    '3.10': '3.10.* *_cpython',
    '3.11': '3.11.* *_cpython',
    '3.12': '3.12.* *_cpython',
    '3.13': '3.13.* *_cp313',
    '3.14': '3.14.* *_cp314',
}


def install_jigsaw(
    config: dict,
    activate_bootstrap_env: str,
    activate_install_env: str,
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

    python_version = _get_python_major_minor_version(
        activate_env=activate_install_env,
        log_filename=log_filename,
        quiet=quiet,
    )

    # build with the bootstrap env
    _ensure_jigsaw_python_source(
        repo_root=repo_root_path,
        jigsaw_python_dir=jigsaw_python_dir,
        rel_path=rel_path,
        activate_env=activate_bootstrap_env,
        log_filename=log_filename,
        quiet=quiet,
    )

    jigsaw_version = _get_jigsaw_version(jigsaw_python_dir)

    _build_external_jigsaw(
        activate_env=activate_bootstrap_env,
        jigsaw_python_dir=jigsaw_python_dir,
        python_version=python_version,
        jigsaw_version=jigsaw_version,
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
        log_filename=log_filename,
        quiet=quiet,
    )


def _get_python_major_minor_version(
    activate_env: str,
    log_filename: str,
    quiet: bool,
) -> str:
    commands = (
        f'{activate_env} && '
        f'python -c "import sys; print(\'.\'.join(map(str, sys.version_info[:2])))"'  # noqa: E501
    )
    result = check_call(
        commands, log_filename=log_filename, quiet=quiet, capture_output=True
    )
    stdout = result.stdout
    if isinstance(stdout, bytes):
        python_version = stdout.decode().strip()
    else:
        assert isinstance(stdout, str)
        python_version = stdout.strip()
    return python_version


def _get_jigsaw_version(jigsaw_python_dir: Path) -> str:
    version_file = jigsaw_python_dir / 'pyproject.toml'
    # parse the version from the porject section of pyproject.toml

    with open(version_file, 'rb') as f:
        pyproject_data = tomllib.load(f)
    version = pyproject_data.get('project', {}).get('version', '').strip()

    if not version:
        raise RuntimeError(
            f'Failed to determine JIGSAW-Python version from {version_file}.'
        )
    return version


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

    os.makedirs('deploy_tmp/jigsaw_build/recipe', exist_ok=True)
    os.makedirs('deploy_tmp/jigsaw_build/variant', exist_ok=True)

    # render the recipe and variant file for the rattler build

    # first the recipe.yaml, which is a double Jinja template.  We only want
    # to replace the square-bracket delimiters here
    env = define_square_bracket_environment()
    with resources.open_text('mache.deploy.jigsaw', 'recipe.yaml.j2') as f:
        recipe_template = env.from_string(f.read())

    recipe = (
        recipe_template.render(
            jigsaw_version=jigsaw_version,
            jigsaw_python_src_dir=str(jigsaw_python_dir),
        )
        + '\n'
    )
    recipe_file = 'deploy_tmp/jigsaw_build/recipe/recipe.yaml'
    with open(recipe_file, 'w', encoding='utf-8') as f:
        f.write(recipe)

    # then "copy" the build.sh script
    with resources.open_text('mache.deploy.jigsaw', 'build.sh') as f:
        build_sh = f.read()
    build_sh_file = 'deploy_tmp/jigsaw_build/recipe/build.sh'
    with open(build_sh_file, 'w', encoding='utf-8') as f:
        f.write(build_sh)

    # now the variant for the platfform, where we also use square-bracket
    # delimiters for consistency
    platform, _ = get_conda_platform_and_system()

    try:
        with resources.open_text(
            'mache.deploy.jigsaw', f'{platform}.yaml.j2'
        ) as f:
            variant_template = env.from_string(f.read())
    except FileNotFoundError as e:
        raise ValueError(
            f'Unsupported platform for JIGSAW build: {platform}'
        ) from e

    variant = variant_template.render(python_variant=python_variant) + '\n'
    variant_file = f'deploy_tmp/jigsaw_build/variant/{platform}.yaml'
    with open(variant_file, 'w', encoding='utf-8') as f:
        f.write(variant)

    command = (
        f'{activate_env} && '
        f'conda install -y rattler-build pixi && '
        f'rattler-build build '
        f'--recipe-dir deploy_tmp/jigsaw_build/recipe '
        f'--variant-config {variant_file} '
        f'--output-dir deploy_tmp/jigsaw_build/output '
    )
    check_call(command, log_filename=log_filename, quiet=quiet)


def _install_jigsaw_python(
    activate_env: str,
    log_filename: str,
    quiet: bool,
) -> None:
    print('Installing JIGSAW and JIGSAW-Python')
    output_dir = Path('deploy_tmp/jigsaw_build/output').resolve()
    if not output_dir.is_dir():
        raise RuntimeError(
            f'JIGSAW build output directory not found: {output_dir}'
        )
    platform, _ = get_conda_platform_and_system()
    repodata = output_dir / platform / 'repodata.json'

    if not repodata.is_file():
        raise RuntimeError(
            f'JIGSAW build output repodata not found: {repodata}'
        )

    commands = (
        f'{activate_env} && '
        f'conda install -y -c "{output_dir}" -c conda-forge jigsawpy'
    )
    check_call(commands, log_filename=log_filename, quiet=quiet)
