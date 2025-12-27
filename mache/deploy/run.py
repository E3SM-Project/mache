from __future__ import annotations

import os
import subprocess
from configparser import ConfigParser

from jinja2 import Template
from yaml import safe_load


def run_deploy(env_name: str | None = None) -> None:
    """
    Docstring for run_deploy
    """
    pins = _read_pins('deploy/pins.cfg')
    replacements = _pins_to_replacements(pins, section='conda')
    config = _render_config_yaml('deploy/config.yaml.j2', replacements)

    if not _is_deploy_enabled(config):
        return

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


def _read_pins(pins_path: str) -> ConfigParser:
    """Read pins configuration from a file."""
    pins = ConfigParser()
    pins.read(pins_path)
    return pins


def _pins_to_replacements(pins: ConfigParser, section: str) -> dict[str, str]:
    """Convert a ConfigParser section into a Jinja2 replacements mapping."""
    section_obj = pins[section]
    return {key: section_obj[key] for key in section_obj}


def _render_config_yaml(
    template_path: str,
    replacements: dict[str, str],
) -> dict:
    """Render a YAML Jinja2 template and parse the resulting YAML."""
    with open(template_path, 'r', encoding='utf-8') as file_handle:
        config_tmpl = Template(file_handle.read())
    rendered = config_tmpl.render(**replacements)
    return safe_load(rendered)


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

    if env_name is None:
        env_name = conda_config['env_name']

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
