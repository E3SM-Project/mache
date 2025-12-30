from __future__ import annotations

import argparse
import logging
import os
import shlex
import shutil
from configparser import ConfigParser
from importlib import resources
from typing import Any

from jinja2 import Template
from yaml import safe_load

from .bootstrap import (
    check_call,
    check_location,
    install_dev_mache,
)
from .conda import get_conda_platform_and_system
from .hooks import DeployContext, configparser_to_nested_dict, load_hooks
from .jigsaw import install_jigsaw
from .machine import get_machine, get_machine_config


def run_deploy(args: argparse.Namespace) -> None:
    """
    Docstring for run_deploy
    """
    # The target software name is stored in deploy/config.yaml.j2.
    # We parse it early so check_location can provide a helpful error.
    pins = _read_pins('deploy/pins.cfg')
    platform, system = get_conda_platform_and_system()
    replacements: dict[str, Any] = {
        'platform': platform,
        'system': system,
    }

    _add_pins_to_replacements(replacements, pins, sections=['pixi', 'all'])
    config = _render_config_yaml('deploy/config.yaml.j2', replacements)

    software = str(config.get('project', {}).get('software', '')).strip()
    if not software:
        raise ValueError(
            "'software' not found or empty in [project] section of "
            'deploy/config.yaml.j2'
        )
    check_location(software=software)

    install_dev_software = config.get('pixi', {}).get(
        'install_dev_software', False
    )

    quiet = args.quiet

    machine, machine_config = _get_machine_and_config(
        config=config,
        args=args,
        platform=platform,
        quiet=quiet,
    )

    os.makedirs('deploy_tmp', exist_ok=True)
    os.makedirs('deploy_tmp/logs', exist_ok=True)
    log_filename = 'deploy_tmp/logs/mache_deploy_run.log'

    logger = _get_deploy_logger(log_filename=log_filename, quiet=args.quiet)

    if not _is_deploy_enabled(config):
        return

    repo_root = os.path.abspath(os.getcwd())
    deploy_dir = os.path.join(repo_root, 'deploy')
    work_dir = os.path.join(repo_root, 'deploy_tmp')

    # Hooks are optional and only run during `mache deploy run`.
    # Behavior: `post_deploy` is invoked only on success.
    hook_registry = load_hooks(
        config=config,
        repo_root=repo_root,
        logger=logger,
    )

    pixi_exe = _get_pixi_executable(getattr(args, 'pixi', None))

    using_mache_fork = (
        getattr(args, 'mache_fork', None) is not None
        and getattr(args, 'mache_branch', None) is not None
    )

    prefix = getattr(args, 'prefix', None)
    if prefix is None:
        prefix = config.get('pixi', {}).get('prefix')
    if not prefix:
        raise ValueError(
            "'prefix' not found in [pixi] section of deploy/config.yaml.j2 "
            'and --prefix not provided'
        )
    prefix = os.path.abspath(
        os.path.expanduser(os.path.expandvars(str(prefix)))
    )

    pixi_cfg = config.get('pixi')
    if not isinstance(pixi_cfg, dict):
        raise ValueError(
            "'pixi' section missing or invalid in deploy/config.yaml.j2"
        )

    ctx = DeployContext(
        software=software,
        machine=machine,
        repo_root=repo_root,
        deploy_dir=deploy_dir,
        work_dir=work_dir,
        config=config,
        pins=configparser_to_nested_dict(pins),
        machine_config=machine_config,
        args=args,
        logger=logger,
    )

    hook_registry.run_hook('pre_pixi', ctx)

    # Runtime overrides (v1): hooks can override specific values via
    # ctx.runtime, falling back to rendered config.
    software_version = _resolve_software_version(
        config=config,
        runtime=ctx.runtime,
    )
    runtime_version_cmd = _resolve_runtime_version_cmd(
        config=config,
        runtime=ctx.runtime,
    )
    mpi, mpi_prefix = _resolve_pixi_mpi(
        pixi_cfg=pixi_cfg,
        runtime=ctx.runtime,
    )

    python_version = args.python
    if python_version is None:
        python_version = pins.get('pixi', 'python')

        if python_version is None:
            raise ValueError(
                'Python version is required to deploy the pixi environment. '
                'Set it in deploy/pins.cfg ([pixi] python = ...) or pass '
                '--python.'
            )

    if 'channels' not in pixi_cfg:
        raise ValueError(
            "'channels' not found in [pixi] section of deploy/config.yaml.j2"
        )
    channels = pixi_cfg.get('channels')
    if (
        not isinstance(channels, list)
        or not channels
        or not all(isinstance(c, str) and c.strip() for c in channels)
    ):
        raise ValueError('pixi.channels must be a non-empty list of strings')

    jigsaw_enabled = bool(config.get('jigsaw', {}).get('enabled'))

    # Determine which mache to put in the deployed environment.
    # - If using a fork/branch, do NOT install conda-forge mache; we'll install
    #   mache from source into the environment after creation.
    # - Otherwise, include a pinned conda-forge mache.
    mache_version_arg = getattr(args, 'mache_version', None)
    if mache_version_arg is not None and str(mache_version_arg).strip():
        replacements['mache'] = str(mache_version_arg).strip()

    include_mache = not using_mache_fork
    if include_mache and not str(replacements.get('mache', '')).strip():
        raise ValueError(
            'mache version is required to include mache in the deployed pixi '
            'environment. Set it in deploy/pins.cfg ([pixi] mache = ...) or '
            'pass --mache-version.'
        )

    # First, install a base environment without jigsawpy. If jigsaw is enabled,
    # we will build jigsawpy from source and then add it from a local channel.
    replacements.update(
        {
            'python': python_version,
            'pixi_channels': channels,
            'mpi': mpi,
            'mpi_prefix': mpi_prefix,
            'include_mache': include_mache,
            'include_jigsaw': False,
        }
    )

    _write_pixi_toml(
        template_path='deploy/pixi.toml.j2',
        replacements=replacements,
        output_dir=prefix,
    )

    _pixi_install(
        pixi_exe=pixi_exe,
        project_dir=prefix,
        recreate=args.recreate,
        log_filename=log_filename,
        quiet=quiet,
    )

    if using_mache_fork:
        prefix_pixi_toml = os.path.join(os.path.abspath(prefix), 'pixi.toml')
        pixi_run_bash_lc_prefix = (
            'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
            f'{shlex.quote(pixi_exe)} run -m {shlex.quote(prefix_pixi_toml)} '
            'bash -lc'
        )
        install_dev_mache(
            pixi_run_bash_lc_prefix=pixi_run_bash_lc_prefix,
            log_filename=log_filename,
            quiet=quiet,
        )

    if jigsaw_enabled:
        local_channel = install_jigsaw(
            config=config,
            pixi_exe=pixi_exe,
            python_version=python_version,
            repo_root='.',
            log_filename=log_filename,
            quiet=quiet,
        )

        channels_with_local = [local_channel] + [
            c for c in channels if c != local_channel
        ]
        replacements.update(
            {
                'pixi_channels': channels_with_local,
                'include_jigsaw': True,
            }
        )
        _write_pixi_toml(
            template_path='deploy/pixi.toml.j2',
            replacements=replacements,
            output_dir=prefix,
        )
        _pixi_install(
            pixi_exe=pixi_exe,
            project_dir=prefix,
            recreate=False,
            log_filename=log_filename,
            quiet=quiet,
        )

    hook_registry.run_hook('post_pixi', ctx)

    # Future wiring: spack stages (no-ops unless implemented/configured)
    hook_registry.run_hook('pre_spack', ctx)
    # TODO: spack deployment would go here
    hook_registry.run_hook('post_spack', ctx)

    if install_dev_software:
        _install_software_in_dev_mode(
            pixi_exe=pixi_exe,
            prefix=prefix,
            log_filename=log_filename,
            quiet=quiet,
        )

    load_script_path = _write_load_script(
        prefix=prefix,
        pixi_exe=pixi_exe,
        software=software,
        software_version=software_version,
        runtime_version_cmd=runtime_version_cmd,
    )
    if not quiet:
        print(f'Wrote load script: {load_script_path}')

    hook_registry.run_hook('post_deploy', ctx)


def _get_deploy_logger(*, log_filename: str, quiet: bool) -> logging.Logger:
    """Get a logger for deploy-run messages.

    We keep this lightweight: hooks get a standard ``logging.Logger`` while
    the rest of the deploy flow continues to use the existing `check_call`
    logging-to-file behavior.
    """

    logger = logging.getLogger('mache.deploy.run')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter(
            fmt='%(message)s',
        )

        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        if not quiet:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(fmt)
            logger.addHandler(stream_handler)

    return logger


def _get_machine_and_config(
    *,
    config: dict[str, Any],
    args: argparse.Namespace,
    platform: str,
    quiet: bool,
) -> tuple[str | None, ConfigParser]:
    machines_path = None
    machines_cfg = config.get('machines')
    if isinstance(machines_cfg, dict):
        machines_path = machines_cfg.get('path')

    if machines_path is not None:
        machines_path = os.path.abspath(
            os.path.expanduser(os.path.expandvars(str(machines_path)))
        )

    requested_machine = _resolve_requested_machine(config=config, args=args)

    machine = get_machine(
        requested_machine=requested_machine,
        machines_path=machines_path,
        quiet=quiet,
    )

    machine_config = get_machine_config(
        machine=machine,
        machines_path=machines_path,
        platform=platform,
        quiet=quiet,
    )

    return machine, machine_config


def _normalize_machine_request(value: Any) -> str | None:
    if value is None:
        return None

    candidate = str(value).strip()
    if candidate.lower() in ('', 'none', 'null', 'dynamic'):
        return None

    return candidate


def _resolve_requested_machine(
    *,
    config: dict[str, Any],
    args: argparse.Namespace,
) -> str | None:
    """Resolve machine selection input.

    Priority:
    1. CLI `--machine` (if provided)
    2. config['project']['machine']
    3. None (auto-detect)
    """

    cli_raw = getattr(args, 'machine', None)
    if cli_raw is not None:
        return _normalize_machine_request(cli_raw)

    project_cfg = config.get('project')
    project_machine = None
    if isinstance(project_cfg, dict):
        project_machine = project_cfg.get('machine')

    return _normalize_machine_request(project_machine)


def _resolve_software_version(
    *,
    config: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    override = None
    runtime_project = runtime.get('project')
    if isinstance(runtime_project, dict):
        override = runtime_project.get('version')
    if override is not None:
        value = str(override).strip()
    else:
        value = str(config.get('project', {}).get('version', '')).strip()

    if not value:
        raise ValueError(
            'Software version is required. Set project.version in '
            "deploy/config.yaml.j2 or provide runtime['project']['version'] "
            'from a pre_pixi hook.'
        )

    return value


def _resolve_runtime_version_cmd(
    *,
    config: dict[str, Any],
    runtime: dict[str, Any],
) -> str | None:
    """Resolve an optional runtime version probe command.

    If provided, this is embedded into the generated load script and executed
    via `pixi run -m <pixi.toml> bash -lc <cmd>` before activation.

    Priority:
    1. runtime['project']['runtime_version_cmd'] (set by hooks)
    2. config['project']['runtime_version_cmd']
    3. None
    """

    override = None
    runtime_project = runtime.get('project')
    if isinstance(runtime_project, dict):
        override = runtime_project.get('runtime_version_cmd')

    if override is not None:
        value = str(override).strip()
    else:
        value = str(
            config.get('project', {}).get('runtime_version_cmd', '')
        ).strip()

    return value or None


def _resolve_pixi_mpi(
    *,
    pixi_cfg: dict[str, Any],
    runtime: dict[str, Any],
) -> tuple[str, str]:
    mpi_override = None
    runtime_pixi = runtime.get('pixi')
    if isinstance(runtime_pixi, dict):
        mpi_override = runtime_pixi.get('mpi')
    if mpi_override is not None:
        mpi_cfg: dict[str, Any] = {'mpi': str(mpi_override)}
    else:
        mpi_cfg = pixi_cfg
    return _get_mpi_settings(pixi_cfg=mpi_cfg)


def _get_pixi_executable(pixi: str | None) -> str:
    if pixi:
        pixi = os.path.abspath(os.path.expanduser(pixi))
        if not os.path.exists(pixi):
            raise FileNotFoundError(f'pixi executable not found: {pixi}')
        return pixi

    which = shutil.which('pixi')
    if which is None:
        raise FileNotFoundError(
            'pixi executable not found on PATH. Install pixi or pass --pixi.'
        )
    return which


def _write_load_script(
    *,
    prefix: str,
    pixi_exe: str,
    software: str,
    software_version: str,
    runtime_version_cmd: str | None,
) -> str:
    """Write a simple "load" script that launches a pixi shell.

    Unlike conda, pixi doesn't currently have a universally-supported way to
    "activate" into the *current* shell without eval/shell-hook support.
    This script therefore launches a new interactive shell within the pixi
    environment.
    """

    prefix_abs = os.path.abspath(
        os.path.expanduser(os.path.expandvars(prefix))
    )
    pixi_toml = os.path.join(prefix_abs, 'pixi.toml')

    # Keep the script name stable and discoverable.
    safe_software = software.strip() or 'software'
    script_path = f'load_{safe_software}.sh'

    template_text = (
        resources.files(__package__)
        .joinpath('templates/load.sh.j2')
        .read_text(encoding='utf-8')
    )
    tmpl = Template(template_text, keep_trailing_newline=True)

    software_upper = safe_software.upper().replace('-', '_')
    source_path = os.path.abspath(os.getcwd())

    rendered = tmpl.render(
        software=software,
        software_upper=software_upper,
        prefix=prefix_abs,
        pixi_toml=pixi_toml,
        pixi_exe=pixi_exe,
        source_path=source_path,
        software_version=software_version,
        runtime_version_cmd_sh=shlex.quote(runtime_version_cmd or ''),
    )

    os.makedirs(prefix_abs, exist_ok=True)
    with open(script_path, 'w', encoding='utf-8') as file_handle:
        file_handle.write(rendered)

    # Intentionally *not* executable: developers should `source` this script.
    # Also clear any existing exec bits from previous generations.
    os.chmod(script_path, 0o644)
    return script_path


def _read_pins(pins_path: str) -> ConfigParser:
    """Read pins configuration from a file."""
    pins = ConfigParser()
    pins.read(pins_path)
    return pins


def _add_pins_to_replacements(
    replacements: dict[str, Any],
    pins: ConfigParser,
    sections: list[str],
) -> None:
    """Convert a ConfigParser section into a Jinja2 replacements mapping."""
    for section in sections:
        if section not in pins:
            continue
        section_obj = pins[section]
        replacements.update(
            {key: str(section_obj[key]) for key in section_obj}
        )


def _render_config_yaml(
    template_path: str,
    replacements: dict[str, Any],
) -> dict:
    """Render a YAML Jinja2 template and parse the resulting YAML."""
    with open(template_path, 'r', encoding='utf-8') as file_handle:
        config_tmpl = Template(file_handle.read())
    rendered = config_tmpl.render(**replacements)
    return safe_load(rendered)


def _is_deploy_enabled(config: dict) -> bool:
    """Return True if deploy is enabled in the rendered config."""
    pixi_config = config.get('pixi', {})
    if 'deploy' not in pixi_config:
        raise ValueError(
            "'deploy' not found in [pixi] section of deploy/config.yaml.j2"
        )
    return bool(pixi_config.get('deploy'))


def _write_pixi_toml(
    template_path: str,
    replacements: dict[str, Any],
    output_dir: str,
) -> None:
    with open(template_path, 'r', encoding='utf-8') as file_handle:
        pixi_tmpl = Template(file_handle.read())
    rendered = pixi_tmpl.render(**replacements)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'pixi.toml')
    with open(output_path, 'w', encoding='utf-8') as file_handle:
        file_handle.write(rendered)


def _pixi_install(
    pixi_exe: str,
    project_dir: str,
    recreate: bool,
    log_filename: str,
    quiet: bool,
) -> None:
    project_dir = os.path.abspath(project_dir)

    pixi_dir = os.path.join(project_dir, '.pixi')
    if recreate and os.path.exists(pixi_dir):
        shutil.rmtree(pixi_dir)

    # Do not force cache/home locations here.
    # - Users/site admins can set PIXI_HOME / RATTLER_CACHE_DIR /
    #   PIXI_CACHE_DIR in shell startup or modulefiles.
    # - Otherwise pixi uses its own defaults (typically under $HOME).
    cmd = (
        f'cd {shlex.quote(project_dir)} && '
        'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
        f'{shlex.quote(pixi_exe)} install'
    )
    check_call(cmd, log_filename=log_filename, quiet=quiet)


def _get_mpi_settings(
    pixi_cfg: dict[str, Any],
) -> tuple[str, str]:
    """Determine MPI-related template replacements.

    Returns
    -------
    mpi : str
        The conda package name for MPI (e.g. "mpich", "openmpi", or "nompi").
    mpi_prefix : str
        The conda-forge variant prefix used in build-string selectors
        (e.g. "nompi", "mpi_mpich", "mpi_openmpi").
    """

    if 'mpi' not in pixi_cfg:
        raise ValueError(
            "'mpi' not found in [pixi] section of deploy/config.yaml.j2"
        )

    mpi_raw = pixi_cfg.get('mpi')
    mpi = str(mpi_raw).strip().lower() if mpi_raw is not None else ''
    if not mpi:
        raise ValueError(
            "'mpi' in [pixi] section of deploy/config.yaml.j2 is empty"
        )
    if any(ch.isspace() for ch in mpi):
        raise ValueError(
            "'mpi' in [pixi] section of deploy/config.yaml.j2 must not "
            'contain whitespace'
        )

    # Legacy Polaris deploy behavior:
    #   - nompi -> "nompi"
    #   - otherwise -> "mpi_<mpi>" (e.g. mpi_mpich, mpi_openmpi)
    mpi_prefix = 'nompi' if mpi == 'nompi' else f'mpi_{mpi}'

    return mpi, mpi_prefix


def _install_software_in_dev_mode(
    *,
    pixi_exe: str,
    prefix: str,
    log_filename: str,
    quiet: bool,
) -> None:
    """Install the target software in development mode into the pixi env."""
    prefix_pixi_toml = os.path.join(os.path.abspath(prefix), 'pixi.toml')
    pixi_run_bash_lc_prefix = (
        'env -u PIXI_PROJECT_MANIFEST -u PIXI_PROJECT_ROOT '
        f'{shlex.quote(pixi_exe)} run -m {shlex.quote(prefix_pixi_toml)} '
        'bash -lc'
    )

    cmd_install_software = (
        f'{pixi_run_bash_lc_prefix} '
        f'"pip install  --no-deps --no-build-isolation -e ."'
    )

    check_call(
        cmd_install_software,
        log_filename=log_filename,
        quiet=quiet,
    )
