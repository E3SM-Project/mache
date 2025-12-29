from __future__ import annotations

import os
import re
import shlex
from importlib import resources
from pathlib import Path

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
    pixi_exe: str,
    python_req: str,
    repo_root: str,
    log_filename: str,
    quiet: bool,
) -> str:
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
    pixi_exe : str
        Path to the pixi executable.
    python_req : str
        The pixi python version requirement (e.g. "3.14.*").
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
        raise RuntimeError(
            'install_jigsaw() called but config["jigsaw"]["enabled"] is false'
        )

    repo_root_path = Path(repo_root).resolve()
    rel_path = jigsaw_cfg.get('jigsaw_python_path', None)
    if not rel_path:
        raise ValueError(
            'Invalid config: jigsaw.jigsaw_python_path is missing'
        )

    jigsaw_python_dir = (repo_root_path / rel_path).resolve()

    python_version = _extract_major_minor_from_requirement(python_req)
    if not python_version:
        raise ValueError(
            'Unable to determine python major.minor for JIGSAW build from '
            f'pixi.python requirement: {python_req!r}. '
            'Use a pinned major.minor (e.g. "3.14" or "3.14.*").'
        )

    _ensure_jigsaw_python_source(
        repo_root=repo_root_path,
        jigsaw_python_dir=jigsaw_python_dir,
        rel_path=rel_path,
        log_filename=log_filename,
        quiet=quiet,
    )

    jigsaw_version = _get_jigsaw_version(jigsaw_python_dir)

    _build_external_jigsaw(
        pixi_exe=pixi_exe,
        jigsaw_python_dir=jigsaw_python_dir,
        python_version=python_version,
        jigsaw_version=jigsaw_version,
        log_filename=log_filename,
        quiet=quiet,
    )

    # Return the local conda channel that contains the freshly-built package.
    # The caller should add this channel (ahead of conda-forge) and run
    # `pixi install` to bring jigsawpy into the environment.
    #
    # NOTE: a pixi/conda environment does not reference the cache or channel
    # at runtime; these are install-time only.
    return _get_local_channel_uri()


def _extract_major_minor_from_requirement(req: str) -> str:
    """Extract python major.minor (e.g. '3.14') from a pixi requirement."""
    m = re.search(r'(?<!\d)(\d+\.\d+)(?!\d)', str(req))
    return m.group(1) if m else ''


def _get_jigsaw_version(jigsaw_python_dir: Path) -> str:
    version_file = jigsaw_python_dir / 'pyproject.toml'
    version = _parse_pyproject_version(version_file)

    if not version:
        raise RuntimeError(
            f'Failed to determine JIGSAW-Python version from {version_file}.'
        )
    return version


def _parse_pyproject_version(pyproject_path: Path) -> str:
    """Parse project.version from a pyproject.toml without tomllib.

    We intentionally avoid tomllib/tomli here to keep dependencies minimal and
    avoid relying on stdlib tomllib (Py>=3.11).
    """
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

        m = re.match(r'^version\s*=\s*(["\'])(.+)\1\s*$', line)
        if m:
            version = m.group(2).strip()
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


def _build_external_jigsaw(
    pixi_exe: str,
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

    bootstrap_project_dir = Path('deploy_tmp/bootstrap_pixi').resolve()
    if not (bootstrap_project_dir / 'pixi.toml').is_file():
        raise RuntimeError(
            'Expected bootstrap pixi project at '
            f'{bootstrap_project_dir} but pixi.toml was not found. '
            'Run the deploy bootstrap step first.'
        )

    command = (
        f'cd {shlex.quote(str(bootstrap_project_dir))} && '
        'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
        f'{shlex.quote(pixi_exe)} run rattler-build build '
        f'--recipe-dir '
        f'{shlex.quote(os.path.abspath("deploy_tmp/jigsaw_build/recipe"))} '
        f'--variant-config {shlex.quote(os.path.abspath(variant_file))} '
        f'--output-dir '
        f'{shlex.quote(os.path.abspath("deploy_tmp/jigsaw_build/output"))} '
    )
    check_call(command, log_filename=log_filename, quiet=quiet)


def _get_local_channel_uri() -> str:
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

    return output_dir.as_uri()
