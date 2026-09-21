import os
import shlex
from importlib import resources as importlib_resources

from jinja2 import Template

from mache.spack.pins import (
    checkout_command,
    package_repo_clone_path,
    render_repos_yaml,
)
from mache.version import __version__


def render_install_script(
    *,
    spack_path,
    env_name,
    yaml_path,
    prologue,
    pins,
    work_dir,
    mirror=None,
    custom_spack='',
    build_jobs=None,
):
    """
    Render the bash script that checks out Spack and builds an environment.

    Parameters
    ----------
    spack_path : str
        The Spack checkout (``$SPACK_ROOT``), created if absent

    env_name : str
        The managed environment to (re)create

    yaml_path : str
        The rendered ``spack.yaml`` for the environment

    prologue : str
        Shell commands that load modules and set variables before Spack runs

    pins : dict
        Validated pins from :py:func:`mache.spack.pins.load_pins`

    work_dir : str
        Where ``spack.lock`` and ``provenance.yaml`` are copied after the
        build

    mirror : str, optional
        A local Spack source mirror

    custom_spack : str, optional
        Spack commands to run after the environment is installed

    build_jobs : int, optional
        Passed to ``spack install -j``

    Returns
    -------
    script : str
        The rendered bash script
    """
    path = (
        importlib_resources.files('mache.spack.templates')
        / 'spack_install.bash.j2'
    )
    with open(str(path)) as handle:
        template = Template(handle.read(), keep_trailing_newline=True)

    repo_checkouts = []
    repo_provenance = []
    for name, entry in pins['repos'].items():
        clone_path = package_repo_clone_path(spack_path, name)
        repo_checkouts.append((name, checkout_command(entry, clone_path)))
        repo_provenance.append((name, entry['git'], shlex.quote(clone_path)))

    return template.render(
        mache_version=__version__,
        env_name=env_name,
        env_name_q=shlex.quote(env_name),
        spack_path_q=shlex.quote(spack_path),
        prologue=prologue.strip(),
        spack_checkout=checkout_command(pins['spack'], spack_path),
        spack_git=pins['spack']['git'],
        repo_checkouts=repo_checkouts,
        repo_names=list(pins['repos']),
        repo_provenance=repo_provenance,
        repos_yaml=render_repos_yaml(spack_path, pins).rstrip(),
        yaml_path_q=shlex.quote(yaml_path),
        lock_path_q=shlex.quote(
            os.path.join(work_dir, f'{env_name}.spack.lock')
        ),
        provenance_path_q=shlex.quote(
            os.path.join(work_dir, f'{env_name}.provenance.yaml')
        ),
        mirror=mirror,
        custom_spack=custom_spack.strip(),
        build_jobs=build_jobs,
    )


def write_prologue(work_dir, env_name, prologue):
    """
    Write the build prologue to ``<env_name>.prologue.sh`` in the work
    directory, for the activation capture step to source.

    Parameters
    ----------
    work_dir : str
        The work directory

    env_name : str
        The environment the prologue belongs to

    prologue : str
        Shell commands that load modules and set variables before Spack runs

    Returns
    -------
    path : str
        The path to the prologue
    """
    path = prologue_path(work_dir, env_name)
    with open(path, 'w') as handle:
        handle.write(f'{prologue.strip()}\n')
    return path


def prologue_path(work_dir, env_name):
    """The path of the build prologue for an environment."""
    return os.path.join(work_dir, f'{env_name}.prologue.sh')
