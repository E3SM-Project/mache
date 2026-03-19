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

from mache.jigsaw import deploy_jigsawpy

from .bootstrap import (
    build_pixi_shell_hook_prefix,
    check_call,
    check_location,
    install_dev_mache,
)
from .conda import get_conda_platform_and_system
from .hooks import DeployContext, configparser_to_nested_dict, load_hooks
from .machine import get_machine, get_machine_config
from .spack import (
    deploy_spack_envs,
    deploy_spack_software_env,
    load_existing_spack_envs,
    load_existing_spack_software_env,
)


def run_deploy(args: argparse.Namespace) -> None:
    """
    Run the full deployment workflow for the current project.

    This is the main entry point for ``mache deploy run``. It renders the
    deployment configuration, validates the target software location,
    provisions pixi and optional Spack environments, and writes load scripts.
    Optional deploy hooks are executed at the documented lifecycle stages.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line options for the deploy run. Expected attributes
        include ``quiet`` and may include deploy overrides such as machine,
        prefix, pixi executable, toolchain values, and Spack options.
    """
    check_location()

    pins = _read_pins('deploy/pins.cfg')
    platform, system = get_conda_platform_and_system()
    replacements: dict[str, Any] = {
        'platform': platform,
        'system': system,
    }

    _add_pins_to_replacements(
        replacements, pins, sections=['pixi', 'spack', 'all']
    )
    config = _render_config_yaml('deploy/config.yaml.j2', replacements)

    software = str(config.get('project', {}).get('software', '')).strip()
    if not software:
        raise ValueError(
            "'software' not found or empty in [project] section of "
            'deploy/config.yaml.j2'
        )

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

    toolchain_pairs = _resolve_toolchain_pairs(
        config=config,
        runtime=ctx.runtime,
        machine_config=machine_config,
        args=args,
        quiet=quiet,
    )
    # Make toolchain selection available to hooks and future Spack stages.
    ctx.runtime.setdefault('toolchain', {})
    ctx.runtime['toolchain']['pairs'] = [
        {'compiler': c, 'mpi': m} for c, m in toolchain_pairs
    ]

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

    python_version = _resolve_pixi_python_version(args=args, pins=pins)
    channels = _resolve_pixi_channels(pixi_cfg=pixi_cfg)

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

    # First, install a base environment without jigsawpy.
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
        pixi_shell_hook_prefix = build_pixi_shell_hook_prefix(
            pixi_exe=pixi_exe,
            pixi_toml=prefix_pixi_toml,
        )
        install_dev_mache(
            pixi_shell_hook_prefix=pixi_shell_hook_prefix,
            log_filename=log_filename,
            quiet=quiet,
        )

    _maybe_deploy_jigsaw(
        enabled=jigsaw_enabled,
        config=config,
        pixi_exe=pixi_exe,
        python_version=python_version,
        prefix=prefix,
        log_filename=log_filename,
        quiet=quiet,
    )

    hook_registry.run_hook('post_pixi', ctx)

    # Future wiring: spack stages (no-ops unless implemented/configured)
    hook_registry.run_hook('pre_spack', ctx)

    spack_cfg = config.get('spack', {})
    if not isinstance(spack_cfg, dict):
        spack_cfg = {}

    deploy_spack = bool(spack_cfg.get('deploy')) or bool(
        getattr(args, 'deploy_spack', False)
    )

    if deploy_spack:
        spack_results = deploy_spack_envs(
            ctx=ctx,
            toolchain_pairs=toolchain_pairs,
            log_filename=log_filename,
            quiet=quiet,
        )

        spack_software_env = deploy_spack_software_env(
            ctx=ctx,
            log_filename=log_filename,
            quiet=quiet,
        )
    else:
        spack_results = load_existing_spack_envs(
            ctx=ctx,
            toolchain_pairs=toolchain_pairs,
        )

        spack_software_env = load_existing_spack_software_env(
            ctx=ctx,
        )

    hook_registry.run_hook('post_spack', ctx)

    if install_dev_software:
        _install_software_in_dev_mode(
            pixi_exe=pixi_exe,
            prefix=prefix,
            log_filename=log_filename,
            quiet=quiet,
        )

    _write_load_scripts(
        prefix=prefix,
        pixi_exe=pixi_exe,
        software=software,
        software_version=software_version,
        runtime_version_cmd=runtime_version_cmd,
        machine=machine,
        toolchain_pairs=toolchain_pairs,
        spack_results=spack_results,
        spack_software_env=spack_software_env,
        quiet=quiet,
    )

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


def _resolve_pixi_python_version(
    *,
    args: argparse.Namespace,
    pins: ConfigParser,
) -> str:
    python_version = args.python
    if python_version is not None:
        return python_version

    if not pins.has_section('pixi') or not pins.has_option('pixi', 'python'):
        raise ValueError(
            'Python version is required to deploy the pixi environment. '
            'Set it in deploy/pins.cfg ([pixi] python = ...) or pass '
            '--python.'
        )
    python_version = pins.get('pixi', 'python')
    return python_version


def _resolve_pixi_channels(*, pixi_cfg: dict[str, Any]) -> list[str]:
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

    return channels


def _maybe_deploy_jigsaw(
    *,
    enabled: bool,
    config: dict[str, Any],
    pixi_exe: str,
    python_version: str,
    prefix: str,
    log_filename: str,
    quiet: bool,
) -> None:
    if not enabled:
        return

    jigsaw_cfg = config.get('jigsaw')
    if not isinstance(jigsaw_cfg, dict):
        raise ValueError(
            "'jigsaw' section missing or invalid in deploy/config.yaml.j2"
        )
    jigsaw_python_path = jigsaw_cfg.get('jigsaw_python_path')
    if not isinstance(jigsaw_python_path, str) or not jigsaw_python_path:
        raise ValueError(
            'jigsaw.jigsaw_python_path must be a non-empty string'
        )

    deploy_jigsawpy(
        pixi_exe=pixi_exe,
        python_version=python_version,
        jigsaw_python_path=jigsaw_python_path,
        repo_root='.',
        log_filename=log_filename,
        quiet=quiet,
        backend='pixi',
        pixi_manifest=os.path.join(
            os.path.abspath(prefix),
            'pixi.toml',
        ),
    )


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
    via a pixi shell-hook before activation.

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


def _normalize_optional_token(value: Any) -> str | None:
    """Normalize optional string-ish config/CLI values.

    Treats common sentinels as None: '', 'none', 'null', 'dynamic'.
    """

    if value is None:
        return None

    candidate = str(value).strip()
    if not candidate:
        return None

    if candidate.lower() in ('none', 'null', 'dynamic'):
        return None

    return candidate


def _normalize_optional_tokens(value: Any) -> list[str] | None:
    """Normalize a CLI/config value into a list of strings.

    Accepts:
      - None
      - a single string
      - a list/tuple of strings

    Treats '', 'none', 'null', 'dynamic' as empty/None.
    """

    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        tokens: list[str] = []
        for item in value:
            t = _normalize_optional_token(item)
            if t is not None:
                tokens.append(t)
        return tokens or None

    token = _normalize_optional_token(value)
    if token is None:
        return None
    return [token]


def _sanitize_script_tag(value: str) -> str:
    """Make a filesystem-safe token for use in script filenames."""

    v = str(value).strip()
    if not v:
        return 'unknown'

    out_chars: list[str] = []
    for ch in v:
        if ch.isalnum() or ch in ('-', '_', '.'):
            out_chars.append(ch)
        else:
            out_chars.append('_')

    tag = ''.join(out_chars)
    while '__' in tag:
        tag = tag.replace('__', '_')
    return tag.strip('_') or 'unknown'


def _resolve_toolchain_pairs(
    *,
    config: dict[str, Any],
    runtime: dict[str, Any],
    machine_config: ConfigParser,
    args: argparse.Namespace,
    quiet: bool,
) -> list[tuple[str, str]]:
    """Resolve toolchain compiler/MPI pairs.

    Priority order for each dimension:
        1. CLI flags (--compiler/--mpi)
        2. runtime overrides from hooks (runtime['toolchain'])
        3. rendered deploy/config.yaml.j2 (config['toolchain'])
        4. merged machine config [deploy]

    Pairing rules:
        - If both lists have the same length, they are zipped.
        - If one list has length 1, it is broadcast across the other.
        - If MPI is omitted, default MPI is resolved per-compiler via:
                mpi_<compiler> (preferred), else mpi.

    If no compiler is resolved, returns an empty list.
    """

    # 1) CLI
    cli_compilers = _normalize_optional_tokens(getattr(args, 'compiler', None))
    cli_mpis = _normalize_optional_tokens(getattr(args, 'mpi', None))
    compiler_from_cli = cli_compilers is not None

    # 2) runtime overrides (set by hooks)
    rt_toolchain = runtime.get('toolchain')
    rt_compilers = None
    rt_mpis = None
    if isinstance(rt_toolchain, dict):
        rt_compilers = _normalize_optional_tokens(rt_toolchain.get('compiler'))
        rt_mpis = _normalize_optional_tokens(rt_toolchain.get('mpi'))

    # 3) rendered config
    cfg_toolchain = config.get('toolchain')
    cfg_compilers = None
    cfg_mpis = None
    if isinstance(cfg_toolchain, dict):
        cfg_compilers = _normalize_optional_tokens(
            cfg_toolchain.get('compiler')
        )
        cfg_mpis = _normalize_optional_tokens(cfg_toolchain.get('mpi'))

    compilers = cli_compilers or rt_compilers or cfg_compilers
    mpis = cli_mpis or rt_mpis or cfg_mpis

    # 4) machine-config defaults
    if compilers is None and machine_config.has_option('deploy', 'compiler'):
        default_comp = _normalize_optional_token(
            machine_config.get('deploy', 'compiler')
        )
        compilers = [default_comp] if default_comp else None

    if not compilers:
        # pixi-only deployments can legitimately skip toolchain
        return []

    if mpis is None:
        # Derive an MPI per compiler when possible.
        derived: list[str] = []
        for compiler in compilers:
            compiler_underscore = compiler.replace('-', '_')
            mpi_key = f'mpi_{compiler_underscore}'
            mpi_val = None
            if machine_config.has_option('deploy', mpi_key):
                mpi_val = _normalize_optional_token(
                    machine_config.get('deploy', mpi_key)
                )
            elif machine_config.has_option('deploy', 'mpi'):
                mpi_val = _normalize_optional_token(
                    machine_config.get('deploy', 'mpi')
                )
            if mpi_val is None:
                derived = []
                break
            derived.append(mpi_val)
        mpis = derived or None

    if not mpis:
        msg = (
            'Toolchain MPI library is not set. Provide --mpi (or set '
            'toolchain.mpi), or set [deploy] mpi_<compiler> (or mpi) in '
            'machine config.'
        )
        if compiler_from_cli and cli_mpis is None:
            raise ValueError(msg)
        if not quiet:
            print(f'Warning: {msg}')
        return []

    # Pairing
    if len(compilers) == len(mpis):
        return list(zip(compilers, mpis, strict=False))

    if len(compilers) == 1 and len(mpis) > 1:
        return [(compilers[0], mpi) for mpi in mpis]

    if len(mpis) == 1 and len(compilers) > 1:
        return [(compiler, mpis[0]) for compiler in compilers]

    raise ValueError(
        'Cannot pair compilers and MPI libraries: got '
        f'{len(compilers)} compiler(s) and {len(mpis)} mpi value(s). '
        'Provide equal-length lists, or a single value for one side to '
        'broadcast across the other.'
    )


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
    machine: str | None,
    toolchain_compiler: str | None,
    toolchain_mpi: str | None,
    spack_library_view: str | None,
    spack_activation: str,
) -> str:
    """
    Write a simple "load" script for activating the pixi environment.

    Unlike conda, pixi doesn't currently have a universally supported way to
    "activate" into the *current* shell without eval/shell-hook support.
    The generated script is intended to be *sourced* (not executed) so that
    it can use ``pixi shell-hook`` + ``eval`` to activate the environment in
    the calling shell.
    """

    prefix_abs = os.path.abspath(
        os.path.expanduser(os.path.expandvars(prefix))
    )
    pixi_toml = os.path.join(prefix_abs, 'pixi.toml')

    if toolchain_compiler and toolchain_mpi:
        if machine is None:
            raise ValueError(
                'Cannot include toolchain in load script name without machine.'
                ' Set a machine in deploy/config.yaml.j2 or pass --machine.'
            )
        machine_tag = _sanitize_script_tag(machine)
        compiler_tag = _sanitize_script_tag(toolchain_compiler)
        mpi_tag = _sanitize_script_tag(toolchain_mpi)
        script_path = (
            f'load_{software}_{machine_tag}_{compiler_tag}_{mpi_tag}.sh'
        )
    else:
        script_path = f'load_{software}.sh'

    template_text = (
        resources.files(__package__)
        .joinpath('templates/load.sh.j2')
        .read_text(encoding='utf-8')
    )
    tmpl = Template(template_text, keep_trailing_newline=True)

    software_upper = software.upper().replace('-', '_')
    source_path = os.path.abspath(os.getcwd())
    target_load_snippet = os.path.join(source_path, 'deploy', 'load.sh')

    rendered = tmpl.render(
        software=software,
        software_upper=software_upper,
        prefix=prefix_abs,
        pixi_toml=pixi_toml,
        pixi_exe=pixi_exe,
        source_path=source_path,
        software_version=software_version,
        runtime_version_cmd_sh=shlex.quote(runtime_version_cmd or ''),
        machine=machine or '',
        load_script=os.path.abspath(script_path),
        toolchain_compiler=toolchain_compiler or '',
        toolchain_mpi=toolchain_mpi or '',
        spack_library_view=spack_library_view or '',
        spack_activation=spack_activation,
        target_load_snippet=target_load_snippet,
    )

    os.makedirs(prefix_abs, exist_ok=True)
    with open(script_path, 'w', encoding='utf-8') as file_handle:
        file_handle.write(rendered)

    # Intentionally *not* executable: developers should `source` this script.
    # Also clear any existing exec bits from previous generations.
    os.chmod(script_path, 0o644)
    return script_path


def _write_load_scripts(
    *,
    prefix: str,
    pixi_exe: str,
    software: str,
    software_version: str,
    runtime_version_cmd: str | None,
    machine: str | None,
    toolchain_pairs: list[tuple[str, str]],
    spack_results: Any,
    spack_software_env: Any,
    quiet: bool,
) -> list[str]:
    """Write one load script per toolchain pair, or a single default script."""

    software_setup = ''
    if spack_software_env is not None:
        software_setup = str(
            getattr(spack_software_env, 'path_setup', '') or ''
        )

    spack_snippet_by_pair: dict[tuple[str, str], str] = {}
    spack_view_by_pair: dict[tuple[str, str], str] = {}
    if spack_results is not None:
        for result in spack_results:
            key = (result.compiler, result.mpi)
            spack_snippet_by_pair[key] = result.activation
            spack_view_by_pair[key] = result.view_path

    paths: list[str] = []
    if toolchain_pairs:
        for compiler, mpilib in toolchain_pairs:
            spack_activation = spack_snippet_by_pair.get(
                (compiler, mpilib), ''
            )
            spack_library_view = spack_view_by_pair.get((compiler, mpilib), '')

            combined_spack = ''
            if software_setup:
                combined_spack += software_setup.rstrip() + '\n'
            if spack_activation:
                combined_spack += spack_activation.rstrip() + '\n'

            paths.append(
                _write_load_script(
                    prefix=prefix,
                    pixi_exe=pixi_exe,
                    software=software,
                    software_version=software_version,
                    runtime_version_cmd=runtime_version_cmd,
                    machine=machine,
                    toolchain_compiler=compiler,
                    toolchain_mpi=mpilib,
                    spack_library_view=spack_library_view,
                    spack_activation=combined_spack,
                )
            )
    else:
        combined_spack = ''
        if software_setup:
            combined_spack += software_setup.rstrip() + '\n'
        paths.append(
            _write_load_script(
                prefix=prefix,
                pixi_exe=pixi_exe,
                software=software,
                software_version=software_version,
                runtime_version_cmd=runtime_version_cmd,
                machine=machine,
                toolchain_compiler=None,
                toolchain_mpi=None,
                spack_library_view=None,
                spack_activation=combined_spack,
            )
        )

    if not quiet:
        for p in paths:
            print(f'Wrote load script: {p}')

    return paths


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
    pixi_shell_hook_prefix = build_pixi_shell_hook_prefix(
        pixi_exe=pixi_exe,
        pixi_toml=prefix_pixi_toml,
    )

    cmd_install_software = (
        f'{pixi_shell_hook_prefix} '
        f'pip install --no-deps --no-build-isolation -e .'
    )

    check_call(
        cmd_install_software,
        log_filename=log_filename,
        quiet=quiet,
    )
