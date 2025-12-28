from __future__ import annotations

import argparse
import os
import subprocess
from configparser import ConfigParser

from jinja2 import Template
from yaml import safe_load

from .bootstrap import (
    check_location,
    get_conda_base,
    install_dev_mache,
    install_miniforge,
)
from .conda import get_conda_platform_and_system
from .jigsaw import install_jigsaw


def run_deploy(args: argparse.Namespace) -> None:
    """
    Docstring for run_deploy
    """
    check_location(software='polaris')

    pins = _read_pins('deploy/pins.cfg')
    replacements = _get_default_replacements()
    # we don't want mache from conda if we will install it from an
    # org/fork/branch
    mache_from_fork = args.mache_fork is not None
    _add_pins_to_replacements(
        replacements,
        pins,
        sections=['conda', 'all'],
        exclude_mache=mache_from_fork,
    )
    config = _render_config_yaml('deploy/config.yaml.j2', replacements)
    _update_replacements_from_config(replacements, config)

    if not _is_deploy_enabled(config):
        return

    quiet = args.quiet
    env_name = args.env_name
    if env_name is None:
        env_name = config['conda']['env_name']
        if env_name is None:
            raise ValueError(
                "'env_name' not found in [conda] section of "
                'deploy/config.yaml.j2 and --env-name not provided'
            )

    os.makedirs('deploy_tmp', exist_ok=True)
    os.makedirs('deploy_tmp/logs', exist_ok=True)
    log_filename = 'deploy_tmp/logs/mache_deploy_run.log'

    conda_base = args.conda
    # TODO: need to get conda base from config options if installing to shared
    # space

    conda_base = get_conda_base(conda_base)
    conda_base = os.path.abspath(conda_base)

    source_activation_scripts = f'source "{conda_base}/etc/profile.d/conda.sh"'

    activate_base = f'{source_activation_scripts} && conda activate base'

    # install miniforge if needed
    install_miniforge(
        conda_base=conda_base,
        activate_base=activate_base,
        log_filename=log_filename,
        quiet=quiet,
        update_base=args.update_base,
    )

    activate_install_env = (
        f'{source_activation_scripts} && conda activate "{env_name}"'
    )

    # install miniforge if needed
    install_miniforge(
        conda_base, activate_base, log_filename, quiet, args.update_base
    )

    source_activation_scripts = f'source "{conda_base}/etc/profile.d/conda.sh"'

    activate_base = f'{source_activation_scripts} && conda activate base'

    activate_bootstrap_env = (
        f'{source_activation_scripts} && conda activate "mache_deploy"'
    )
    activate_install_env = (
        f'{source_activation_scripts} && conda activate "{env_name}"'
    )

    _write_conda_spec(
        'deploy/conda-spec.txt.j2',
        replacements,
        'deploy_tmp/conda-spec.txt',
    )
    _create_conda_environment(
        config,
        env_name=env_name,
        spec_file='deploy_tmp/conda-spec.txt',
    )

    if mache_from_fork:
        install_dev_mache(
            activate_install_env=activate_install_env,
            mache_fork=args.mache_fork,
            mache_branch=args.mache_branch,
            log_filename=log_filename,
            quiet=quiet,
        )

    install_jigsaw(
        config=config,
        activate_bootstrap_env=activate_bootstrap_env,
        activate_install_env=activate_install_env,
        repo_root=os.getcwd(),
        log_filename=log_filename,
        quiet=quiet,
    )


def _read_pins(pins_path: str) -> ConfigParser:
    """Read pins configuration from a file."""
    pins = ConfigParser()
    pins.read(pins_path)
    return pins


def _get_default_replacements() -> dict[str, str]:
    """Get default replacements such as machine architecture."""
    conda_platform, system = get_conda_platform_and_system()
    replacements = {
        'platform': conda_platform,
        'system': system,
    }
    return replacements


def _add_pins_to_replacements(
    replacements: dict[str, str],
    pins: ConfigParser,
    sections: list[str],
    exclude_mache: bool,
) -> None:
    """Convert a ConfigParser section into a Jinja2 replacements mapping."""
    for section in sections:
        if section not in pins:
            continue
        section_obj = pins[section]
        replacements.update({key: section_obj[key] for key in section_obj})
    if exclude_mache and 'mache' in replacements:
        del replacements['mache']


def _render_config_yaml(
    template_path: str,
    replacements: dict[str, str],
) -> dict:
    """Render a YAML Jinja2 template and parse the resulting YAML."""
    with open(template_path, 'r', encoding='utf-8') as file_handle:
        config_tmpl = Template(file_handle.read())
    rendered = config_tmpl.render(**replacements)
    return safe_load(rendered)


def _update_replacements_from_config(
    replacements: dict[str, str],
    config: dict,
) -> None:
    """Update replacements mapping with values from the rendered config."""
    conda_config = config['conda']
    if 'mpi' in conda_config:
        mpi = conda_config['mpi']
        if mpi not in ['nompi', 'openmpi', 'mpich']:
            raise ValueError(
                f'Invalid MPI option in deploy/config.yaml.j2: {mpi!r}'
            )
        mpi_prefix = 'nompi' if mpi == 'nompi' else f'mpi_{mpi}'
        replacements['mpi'] = mpi
        replacements['mpi_prefix'] = mpi_prefix
    for key in ['mpi']:
        if key in conda_config:
            replacements[key] = conda_config[key]


def _is_deploy_enabled(config: dict) -> bool:
    """Return True if deploy is enabled in the rendered config."""
    conda_config = config['conda']
    if 'deploy' not in conda_config:
        raise ValueError(
            "'deploy' not found in [conda] section of deploy/config.yaml.j2"
        )
    return bool(conda_config.get('deploy'))


def _write_conda_spec(
    template_path: str,
    replacements: dict[str, str],
    output_path: str,
) -> None:
    """Render the conda spec template into the deploy_tmp spec file."""
    with open(template_path, 'r', encoding='utf-8') as file_handle:
        conda_spec_tmpl = Template(file_handle.read())
    conda_spec_rendered = conda_spec_tmpl.render(**replacements)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as file_handle:
        file_handle.write(conda_spec_rendered)


def _create_conda_environment(
    config: dict,
    env_name: str | None,
    spec_file: str,
) -> None:
    """Create the conda environment described by the rendered config."""
    conda_config = config['conda']

    if 'channels' not in conda_config:
        raise ValueError(
            "'channels' not found in [conda] section of deploy/config.yaml.j2"
        )
    channels = conda_config['channels']
    channels_str = ' -c '.join(channels)

    command = (
        f'conda create -y -n {env_name} -c {channels_str} --file {spec_file}'
    )
    print(f'Running command: {command}')
    subprocess.run(command, shell=True, check=True)
