from __future__ import annotations

import os
import shlex
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template
from yaml import safe_load

from mache.deploy.bootstrap import check_call
from mache.deploy.hooks import DeployContext
from mache.spack.activation import (
    ACTIVATION_MODES,
    activation_file_path,
    capture_activation,
    write_activation_files,
)
from mache.spack.install import (
    prologue_path,
    render_install_script,
    write_prologue,
)
from mache.spack.pins import load_pins
from mache.spack.script import get_spack_script
from mache.spack.shared import (
    _get_yaml_data,
    normalize_excluded_packages,
    resolve_e3sm_hdf5_netcdf,
)


@dataclass(frozen=True)
class SpackDeployResult:
    """Result of deploying a Spack environment for one toolchain pair.

    ``activation`` is always the dynamic form (``source setup-env.sh`` plus
    ``spack env activate``), which hooks can run before the captured
    activation exists.  ``load_activation`` is what the generated load
    scripts use: a ``source`` of the captured ``activate.sh`` when
    ``spack.activation`` is ``captured`` (the default), otherwise the same as
    ``activation``.
    """

    compiler: str
    mpi: str
    env_name: str
    spack_path: str
    view_path: str
    activation: str
    load_activation: str = ''

    def __post_init__(self) -> None:
        if not self.load_activation:
            object.__setattr__(self, 'load_activation', self.activation)


@dataclass(frozen=True)
class SpackSoftwareEnvResult:
    """Result of deploying a Spack "software" environment.

    This environment is intended to provide executables, so load scripts should
    add its view's ``bin`` directory to ``PATH`` rather than activating it.
    """

    compiler: str
    mpi: str
    env_name: str
    spack_path: str
    view_path: str
    path_setup: str


def get_effective_spack_config(*, ctx: DeployContext) -> dict:
    """Return deploy config merged with runtime Spack overrides."""

    spack_cfg = ctx.config.get('spack', {})
    if not isinstance(spack_cfg, dict):
        spack_cfg = {}

    merged = dict(spack_cfg)

    software_cfg = merged.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if isinstance(software_cfg, dict):
        merged['software'] = dict(software_cfg)

    runtime_spack = ctx.runtime.get('spack', {})
    if not isinstance(runtime_spack, dict):
        return merged

    for key, value in runtime_spack.items():
        if key == 'software' and isinstance(value, dict):
            base = merged.get('software', {})
            if not isinstance(base, dict):
                base = {}
            merged['software'] = {**base, **value}
        else:
            merged[key] = value

    return merged


def spack_disabled_for_run(*, ctx: DeployContext) -> bool:
    """Return True when the CLI explicitly disables all Spack use."""

    return bool(getattr(ctx.args, 'no_spack', False))


def spack_should_deploy_for_run(
    *, ctx: DeployContext, spack_cfg: dict
) -> bool:
    """Return True when Spack environments should be deployed for this run."""

    if spack_disabled_for_run(ctx=ctx):
        return False

    if bool(getattr(ctx.args, 'deploy_spack', False)):
        return True

    return bool(spack_cfg.get('deploy'))


def deploy_spack_software_env(
    *,
    ctx: DeployContext,
    log_filename: str,
    quiet: bool,
) -> SpackSoftwareEnvResult | None:
    """Deploy an optional Spack "software" environment.

        This environment is built with a single ``(compiler, mpi)`` pair,
        typically defined in the merged machine config under
        ``[deploy] software_compiler`` and
        ``[deploy] mpi_<software_compiler>``.

    No CLI flags control this environment.
    """

    spack_cfg = get_effective_spack_config(ctx=ctx)
    if not isinstance(spack_cfg, dict):
        return None

    software_cfg = spack_cfg.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if not isinstance(software_cfg, dict):
        raise ValueError('spack.software must be a mapping if provided')

    deploy_spack = spack_should_deploy_for_run(ctx=ctx, spack_cfg=spack_cfg)

    software_supported = bool(software_cfg.get('supported'))

    if not deploy_spack or not software_supported:
        return None

    if ctx.machine is None:
        raise ValueError(
            'Spack software environment deployment was requested but machine '
            'is not known.'
        )

    compiler, mpi = _resolve_software_toolchain(
        machine_config=ctx.machine_config, machine=ctx.machine
    )

    e3sm_hdf5_netcdf = _get_machine_bool(
        machine_config=ctx.machine_config,
        section='deploy',
        option='use_e3sm_hdf5_netcdf',
        default=False,
    )
    exclude_packages = _get_excluded_spack_packages(spack_cfg)
    e3sm_hdf5_netcdf, exclude_packages = resolve_e3sm_hdf5_netcdf(
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    spack_path = _resolve_spack_path(
        ctx=ctx,
        spack_cfg=spack_cfg,
        reason='deployment is enabled',
    )

    env_name = str(software_cfg.get('env_name') or '').strip()
    if not env_name:
        env_name = f'{ctx.software}_software'
    if any(ch.isspace() for ch in env_name):
        raise ValueError('spack.software.env_name must be a single token')

    specs_template = str(
        spack_cfg.get('specs_template') or 'deploy/spack.yaml.j2'
    )
    specs_template = os.path.abspath(
        os.path.join(
            ctx.repo_root,
            os.path.expanduser(os.path.expandvars(specs_template)),
        )
    )

    specs = _render_spack_specs(
        template_path=specs_template,
        ctx=ctx,
        compiler=compiler,
        mpi=mpi,
        section='software',
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    yaml_path = _write_mache_spack_env_yaml(
        ctx=ctx,
        machine=ctx.machine,
        compiler=compiler,
        mpi=mpi,
        env_name=env_name,
        spack_specs=specs,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    _install_spack_env(
        ctx=ctx,
        spack_path=spack_path,
        env_name=env_name,
        yaml_path=str(yaml_path),
        compiler=compiler,
        mpi=mpi,
        tmpdir=_normalize_optional_token(spack_cfg.get('tmpdir')),
        mirror=_normalize_optional_token(spack_cfg.get('mirror')),
        custom_spack=str(spack_cfg.get('custom_spack') or ''),
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        pins=_load_spack_pins(ctx=ctx),
        build_jobs=_get_build_jobs(spack_cfg),
        log_filename=log_filename,
        quiet=quiet,
    )

    view_path = os.path.join(
        spack_path,
        'var',
        'spack',
        'environments',
        env_name,
        '.spack-env',
        'view',
    )
    view_path_sh = shlex.quote(view_path)
    path_setup = (
        '# Spack software environment PATH (no activation)\n'
        f'_MACHE_SPACK_SOFTWARE_VIEW={view_path_sh}\n'
        'if [[ -d "${_MACHE_SPACK_SOFTWARE_VIEW}/bin" ]]; then\n'
        '  export PATH="${_MACHE_SPACK_SOFTWARE_VIEW}/bin:${PATH}"\n'
        'fi\n'
        'unset _MACHE_SPACK_SOFTWARE_VIEW\n'
    )

    return SpackSoftwareEnvResult(
        compiler=compiler,
        mpi=mpi,
        env_name=env_name,
        spack_path=spack_path,
        view_path=view_path,
        path_setup=path_setup,
    )


def deploy_spack_envs(
    *,
    ctx: DeployContext,
    toolchain_pairs: list[tuple[str, str]],
    log_filename: str,
    quiet: bool,
) -> list[SpackDeployResult]:
    """Deploy one Spack environment per (compiler, mpi) toolchain pair.

    This function is a thin orchestration layer. It reads deploy config from
    ``ctx.config['spack']``, renders ``deploy/spack.yaml.j2`` to obtain the
    spec list, uses mache's Spack environment templates
    (``mache/spack/templates/*.yaml``) to construct a full environment YAML,
    runs Spack to concretize and install the environment, and produces a shell
    snippet for the generated load scripts.

    Notes
    -----
    This is intentionally "E3SM flavored": it uses `get_spack_script()` to
    load compiler/MPI modules and settings from config_machines.xml.

    Returns
    -------
    results
        A list of SpackDeployResult, one per (compiler, mpi)
    """

    spack_cfg = get_effective_spack_config(ctx=ctx)
    if not isinstance(spack_cfg, dict):
        return []

    software_cfg = spack_cfg.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if not isinstance(software_cfg, dict):
        raise ValueError('spack.software must be a mapping if provided')

    deploy_spack = spack_should_deploy_for_run(ctx=ctx, spack_cfg=spack_cfg)

    library_supported = bool(spack_cfg.get('supported'))

    if not deploy_spack or not library_supported:
        return []

    if not toolchain_pairs:
        raise ValueError(
            'Spack library environment deployment was requested but no '
            'toolchain pairs were resolved. Provide toolchain.compiler/'
            'toolchain.mpi or --compiler/--mpi.'
        )

    spack_path = _resolve_spack_path(
        ctx=ctx,
        spack_cfg=spack_cfg,
        reason='deployment is enabled',
    )

    e3sm_hdf5_netcdf = _get_machine_bool(
        machine_config=ctx.machine_config,
        section='deploy',
        option='use_e3sm_hdf5_netcdf',
        default=False,
    )
    exclude_packages = _get_excluded_spack_packages(spack_cfg)
    e3sm_hdf5_netcdf, exclude_packages = resolve_e3sm_hdf5_netcdf(
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    env_name_prefix = str(
        spack_cfg.get('env_name_prefix') or 'spack_env'
    ).strip()
    if not env_name_prefix or any(ch.isspace() for ch in env_name_prefix):
        raise ValueError('spack.env_name_prefix must be a non-empty token')

    specs_template = str(
        spack_cfg.get('specs_template') or 'deploy/spack.yaml.j2'
    )
    specs_template = os.path.abspath(
        os.path.join(
            ctx.repo_root,
            os.path.expanduser(os.path.expandvars(specs_template)),
        )
    )

    tmpdir = spack_cfg.get('tmpdir')
    if tmpdir is not None and str(tmpdir).strip():
        tmpdir = os.path.abspath(
            os.path.expanduser(os.path.expandvars(str(tmpdir)))
        )
    else:
        tmpdir = None

    mirror = spack_cfg.get('mirror')
    if mirror is not None and str(mirror).strip():
        mirror = os.path.abspath(
            os.path.expanduser(os.path.expandvars(str(mirror)))
        )
    else:
        mirror = None

    custom_spack = str(spack_cfg.get('custom_spack') or '')
    pins = _load_spack_pins(ctx=ctx)
    build_jobs = _get_build_jobs(spack_cfg)
    activation_mode = get_spack_activation_mode(spack_cfg)

    results: list[SpackDeployResult] = []

    for compiler, mpi in toolchain_pairs:
        env_name = f'{env_name_prefix}_{compiler}_{mpi}'
        specs = _render_spack_specs(
            template_path=specs_template,
            ctx=ctx,
            compiler=compiler,
            mpi=mpi,
            section='library',
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            exclude_packages=exclude_packages,
        )

        yaml_path = _write_mache_spack_env_yaml(
            ctx=ctx,
            machine=ctx.machine,
            compiler=compiler,
            mpi=mpi,
            env_name=env_name,
            spack_specs=specs,
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            exclude_packages=exclude_packages,
        )

        _install_spack_env(
            ctx=ctx,
            spack_path=spack_path,
            env_name=env_name,
            yaml_path=str(yaml_path),
            compiler=compiler,
            mpi=mpi,
            tmpdir=tmpdir,
            mirror=mirror,
            custom_spack=custom_spack,
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            pins=pins,
            build_jobs=build_jobs,
            log_filename=log_filename,
            quiet=quiet,
        )

        results.append(
            _make_spack_deploy_result(
                ctx=ctx,
                spack_path=spack_path,
                env_name=env_name,
                compiler=compiler,
                mpi=mpi,
                e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
                activation_mode=activation_mode,
            )
        )

    return results


def capture_spack_activations(
    *,
    ctx: DeployContext,
    results: list[SpackDeployResult],
) -> None:
    """Capture the activation of each deployed library environment.

    This runs after the ``post_spack`` hooks, so changes a hook makes to the
    environment (for example to ``modules:prefix_inspections``) are
    reflected.  It writes ``activate.sh`` and ``activate.csh`` into each
    environment directory; ``SpackDeployResult.load_activation`` already
    sources them.  Nothing happens when ``spack.activation`` is ``dynamic``.
    """

    spack_cfg = get_effective_spack_config(ctx=ctx)
    if get_spack_activation_mode(spack_cfg) != 'captured':
        return

    work = Path(ctx.work_dir) / 'spack'
    for result in results:
        ctx.logger.info(
            f'Capturing activation of Spack environment {result.env_name}'
        )
        modifications = capture_activation(
            spack_path=result.spack_path,
            env_name=result.env_name,
            prologue_path=prologue_path(str(work), result.env_name),
            work_dir=str(work),
        )
        write_activation_files(
            spack_path=result.spack_path,
            env_name=result.env_name,
            modifications=modifications,
        )


def get_spack_activation_mode(spack_cfg: dict) -> str:
    """Return the effective ``spack.activation`` setting."""

    # not _normalize_optional_token(): "dynamic" is a real value here
    value = spack_cfg.get('activation')
    mode = str(value).strip().lower() if value is not None else ''
    if mode in ('', 'none', 'null'):
        return 'captured'
    if mode not in ACTIVATION_MODES:
        raise ValueError(
            f'spack.activation must be one of {ACTIVATION_MODES}, '
            f'got {spack_cfg.get("activation")!r}'
        )
    return mode


def load_existing_spack_envs(
    *,
    ctx: DeployContext,
    toolchain_pairs: list[tuple[str, str]],
) -> list[SpackDeployResult]:
    """Load pre-existing Spack library environments for load scripts."""

    spack_cfg = get_effective_spack_config(ctx=ctx)
    if not isinstance(spack_cfg, dict):
        return []

    library_supported = bool(spack_cfg.get('supported'))
    if not library_supported:
        return []

    if not toolchain_pairs:
        raise ValueError(
            'Spack library environments are enabled for this run but no '
            'toolchain pairs were resolved. Provide toolchain.compiler/'
            'toolchain.mpi or --compiler/--mpi, or disable Spack for this '
            'run with --no-spack or a pre_spack hook.'
        )

    spack_path = _resolve_spack_path(
        ctx=ctx,
        spack_cfg=spack_cfg,
        reason='support is enabled for this run (load scripts will reuse '
        'existing envs)',
    )

    e3sm_hdf5_netcdf = _get_machine_bool(
        machine_config=ctx.machine_config,
        section='deploy',
        option='use_e3sm_hdf5_netcdf',
        default=False,
    )
    exclude_packages = _get_excluded_spack_packages(spack_cfg)
    e3sm_hdf5_netcdf, _ = resolve_e3sm_hdf5_netcdf(
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    env_name_prefix = str(
        spack_cfg.get('env_name_prefix') or 'spack_env'
    ).strip()
    if not env_name_prefix or any(ch.isspace() for ch in env_name_prefix):
        raise ValueError('spack.env_name_prefix must be a non-empty token')

    activation_mode = get_spack_activation_mode(spack_cfg)

    results: list[SpackDeployResult] = []

    for compiler, mpi in toolchain_pairs:
        env_name = f'{env_name_prefix}_{compiler}_{mpi}'
        _ensure_spack_env_exists(spack_path=spack_path, env_name=env_name)
        if activation_mode == 'captured':
            _ensure_spack_activation_exists(
                spack_path=spack_path, env_name=env_name
            )

        results.append(
            _make_spack_deploy_result(
                ctx=ctx,
                spack_path=spack_path,
                env_name=env_name,
                compiler=compiler,
                mpi=mpi,
                e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
                activation_mode=activation_mode,
            )
        )

    return results


def load_existing_spack_software_env(
    *,
    ctx: DeployContext,
) -> SpackSoftwareEnvResult | None:
    """Load a pre-existing Spack software environment for load scripts."""

    spack_cfg = get_effective_spack_config(ctx=ctx)
    if not isinstance(spack_cfg, dict):
        return None

    software_cfg = spack_cfg.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if not isinstance(software_cfg, dict):
        raise ValueError('spack.software must be a mapping if provided')

    software_supported = bool(software_cfg.get('supported'))
    if not software_supported:
        return None

    if ctx.machine is None:
        raise ValueError(
            'Spack software environment is enabled for this run but machine '
            'is not known. Pass --no-spack or disable '
            'spack.software.supported '
            'in a pre_spack hook for Pixi-only runs.'
        )

    spack_path = _resolve_spack_path(
        ctx=ctx,
        spack_cfg=spack_cfg,
        reason='support is enabled for this run (load scripts will reuse '
        'existing envs)',
    )

    compiler, mpi = _resolve_software_toolchain(
        machine_config=ctx.machine_config, machine=ctx.machine
    )

    env_name = str(software_cfg.get('env_name') or '').strip()
    if not env_name:
        env_name = f'{ctx.software}_software'
    if any(ch.isspace() for ch in env_name):
        raise ValueError('spack.software.env_name must be a single token')

    _ensure_spack_env_exists(spack_path=spack_path, env_name=env_name)

    view_path = os.path.join(
        spack_path,
        'var',
        'spack',
        'environments',
        env_name,
        '.spack-env',
        'view',
    )
    view_path_sh = shlex.quote(view_path)
    path_setup = (
        '# Spack software environment PATH (no activation)\n'
        f'_MACHE_SPACK_SOFTWARE_VIEW={view_path_sh}\n'
        'if [[ -d "${_MACHE_SPACK_SOFTWARE_VIEW}/bin" ]]; then\n'
        '  export PATH="${_MACHE_SPACK_SOFTWARE_VIEW}/bin:${PATH}"\n'
        'fi\n'
        'unset _MACHE_SPACK_SOFTWARE_VIEW\n'
    )

    return SpackSoftwareEnvResult(
        compiler=compiler,
        mpi=mpi,
        env_name=env_name,
        spack_path=spack_path,
        view_path=view_path,
        path_setup=path_setup,
    )


def _make_spack_deploy_result(
    *,
    ctx: DeployContext,
    spack_path: str,
    env_name: str,
    compiler: str,
    mpi: str,
    e3sm_hdf5_netcdf: bool,
    activation_mode: str,
) -> SpackDeployResult:
    view_path = os.path.join(
        spack_path,
        'var',
        'spack',
        'environments',
        env_name,
        '.spack-env',
        'view',
    )

    activations = {}
    for mode in ACTIVATION_MODES:
        activations[mode] = get_spack_script(
            spack_path=spack_path,
            env_name=env_name,
            compiler=compiler,
            mpi=mpi,
            shell='sh',
            machine=ctx.machine,
            include_e3sm_lapack=False,
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            load_spack_env=True,
            activation=mode,
        )

    return SpackDeployResult(
        compiler=compiler,
        mpi=mpi,
        env_name=env_name,
        spack_path=spack_path,
        view_path=view_path,
        activation=activations['dynamic'],
        load_activation=activations[activation_mode],
    )


def _load_spack_pins(*, ctx: DeployContext) -> dict:
    """Load the pinned Spack sources with overrides, lowest precedence first.

    Precedence, highest first: ``--spack-pins <file>``, then
    ``ctx.runtime['spack']['pins']`` from a hook, then ``spack.pins`` in
    ``deploy/config.yaml.j2``, then the ``pins.yaml`` packaged with mache.
    """

    overrides: list = []

    spack_cfg = ctx.config.get('spack', {})
    if isinstance(spack_cfg, dict) and spack_cfg.get('pins'):
        overrides.append(spack_cfg['pins'])

    rt_spack_cfg = ctx.runtime.get('spack', {})
    if isinstance(rt_spack_cfg, dict) and rt_spack_cfg.get('pins'):
        overrides.append(rt_spack_cfg['pins'])

    cli_pins = _normalize_optional_token(getattr(ctx.args, 'spack_pins', None))
    if cli_pins is not None:
        overrides.append(
            os.path.abspath(os.path.expanduser(os.path.expandvars(cli_pins)))
        )

    return load_pins(overrides)


def _get_build_jobs(spack_cfg: dict) -> int | None:
    """Read ``spack.build_jobs`` (for ``spack install -j``) if set."""

    value = _normalize_optional_token(spack_cfg.get('build_jobs'))
    if value is None:
        return None
    try:
        build_jobs = int(value)
    except ValueError as exc:
        raise ValueError(
            f'spack.build_jobs must be a positive integer, got {value!r}'
        ) from exc
    if build_jobs < 1:
        raise ValueError(
            f'spack.build_jobs must be a positive integer, got {value!r}'
        )
    return build_jobs


def _normalize_optional_token(value: object) -> str | None:
    """Normalize optional config/runtime values.

    Treat '', None, and common sentinels ('none', 'null', 'dynamic') as None.
    """

    if value is None:
        return None

    candidate = str(value).strip()
    if not candidate:
        return None

    if candidate.lower() in ('none', 'null', 'dynamic'):
        return None

    return candidate


def _resolve_spack_path(
    *,
    ctx: DeployContext,
    spack_cfg: dict,
    reason: str,
) -> str:
    """Resolve spack checkout path.

    Priority order:
      1. CLI ``--spack-path``
      2. Hook/runtime override ``ctx.runtime['spack']['spack_path']``
      3. Config ``spack.spack_path``
    """

    spack_path = _normalize_optional_token(
        getattr(ctx.args, 'spack_path', None)
    )

    rt_spack_cfg = ctx.runtime.get('spack', {})
    if rt_spack_cfg is None:
        rt_spack_cfg = {}
    if not isinstance(rt_spack_cfg, dict):
        raise ValueError('runtime.spack must be a mapping if provided')

    if spack_path is None:
        spack_path = _normalize_optional_token(rt_spack_cfg.get('spack_path'))

    if spack_path is None:
        spack_path = _normalize_optional_token(spack_cfg.get('spack_path'))

    spack_path = str(spack_path or '').strip()
    if not spack_path:
        raise ValueError(
            f'Spack {reason} but spack_path is not set. Set '
            '--spack-path, '
            "ctx.runtime['spack']['spack_path']"
            ' in a hook (preferred) or set spack.spack_path in '
            'deploy/config.yaml.j2. To bypass Spack entirely for this run, '
            'pass --no-spack.'
        )
    return os.path.abspath(os.path.expanduser(os.path.expandvars(spack_path)))


def _ensure_spack_activation_exists(*, spack_path: str, env_name: str) -> str:
    path = activation_file_path(spack_path, env_name, 'sh')
    if not os.path.isfile(path):
        raise ValueError(
            f'Captured activation not found at {path}. The environment was '
            'built by an older mache or its build did not finish; redeploy '
            'it with --deploy-spack, or set spack.activation to "dynamic".'
        )
    return path


def _ensure_spack_env_exists(*, spack_path: str, env_name: str) -> str:
    env_dir = os.path.join(
        spack_path,
        'var',
        'spack',
        'environments',
        env_name,
    )
    if not os.path.isdir(env_dir):
        raise ValueError(
            'Spack environment not found at '
            f'{env_dir}. Please contact the site administrator or '
            'deployment maintainer.'
        )
    return env_dir


def _resolve_software_toolchain(
    *,
    machine_config: ConfigParser,
    machine: str,
) -> tuple[str, str]:
    """Resolve the single (compiler, mpi) used for the software environment."""

    if not machine_config.has_section('deploy'):
        raise ValueError(
            'Spack software environment is enabled for '
            f"machine '{machine}' but merged machine config has no "
            '[deploy] section.'
        )

    if not machine_config.has_option('deploy', 'software_compiler'):
        raise ValueError(
            'Spack software environment is enabled for '
            f"machine '{machine}' but [deploy] software_compiler is not "
            'set in merged machine config. Set [deploy] '
            'software_compiler and the matching [deploy] '
            'mpi_<software_compiler>.'
        )

    compiler = machine_config.get('deploy', 'software_compiler').strip()
    if not compiler:
        raise ValueError(
            f"[deploy] software_compiler is empty for machine '{machine}'"
        )

    mpi_option = f'mpi_{compiler.replace("-", "_")}'
    if not machine_config.has_option('deploy', mpi_option):
        raise ValueError(
            f"Spack software environment is enabled for machine '{machine}' "
            f'but merged machine config is missing [deploy] {mpi_option} '
            f'(MPI for '
            f'software_compiler={compiler}).'
        )
    mpi = machine_config.get('deploy', mpi_option).strip()
    if not mpi:
        raise ValueError(
            f"[deploy] {mpi_option} is empty for machine '{machine}'"
        )

    return compiler, mpi


def _get_excluded_spack_packages(spack_cfg: dict) -> set[str]:
    """Read the opt-out list for machine-provided Spack packages."""

    return normalize_excluded_packages(spack_cfg.get('exclude_packages'))


def _render_spack_specs(
    *,
    template_path: str,
    ctx: DeployContext,
    compiler: str,
    mpi: str,
    section: str,
    e3sm_hdf5_netcdf: bool,
    exclude_packages: set[str],
) -> list[str]:
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f'Spack specs template not found: {template_path}. '
            'Expected deploy/spack.yaml.j2 in the target repo.'
        )

    with open(template_path, 'r', encoding='utf-8') as handle:
        template_text = handle.read()

    pins = ctx.pins if isinstance(ctx.pins, dict) else {}

    rendered = Template(template_text, keep_trailing_newline=True).render(
        pins=pins,
        spack=pins.get('spack', {}),
        pixi=pins.get('pixi', {}),
        all=pins.get('all', {}),
        software=ctx.software,
        machine=ctx.machine or '',
        compiler=compiler,
        mpi=mpi,
        exclude_packages=sorted(exclude_packages),
        # Naming: prefer e3sm_hdf5_netcdf in templates; keep use_* to align
        # with the machine-config option name.
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        use_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    )

    data = safe_load(rendered)

    if data is None:
        data = []

    # Backward compatible behavior:
    # - If `deploy/spack.yaml.j2` renders to a list, interpret it as the
    #   library-env specs.
    # New behavior:
    # - If it renders to a mapping, expect per-env lists under:
    #     library:  [...]
    #     software: [...]
    if isinstance(data, dict):
        if section in data:
            data = data[section]
        elif section == 'library':
            # allow a little flexibility
            if 'specs' in data:
                data = data['specs']
            elif 'spack_specs' in data:
                data = data['spack_specs']
            else:
                data = []
        else:
            data = []

    if isinstance(data, list):
        if section != 'library' and not data:
            # keep empty as empty for now; we'll error below for required envs
            pass
    else:
        raise ValueError(
            'deploy/spack.yaml.j2 must render to either: '
            '(1) a YAML list[str] (interpreted as library specs), or '
            '(2) a YAML mapping with keys "library" and/or "software" each '
            'containing a list[str].'
        )

    if not isinstance(data, list) or not all(isinstance(s, str) for s in data):
        raise ValueError(
            f'Spack specs for section={section!r} must be a YAML list[str].'
        )

    specs = [s.strip() for s in data if str(s).strip()]
    if not specs:
        raise ValueError(
            f'deploy/spack.yaml.j2 rendered to an empty specs list for '
            f'section={section!r}. Provide at least one spack spec string.'
        )

    return specs


def _write_mache_spack_env_yaml(
    *,
    ctx: DeployContext,
    machine: str | None,
    compiler: str,
    mpi: str,
    env_name: str,
    spack_specs: list[str],
    e3sm_hdf5_netcdf: bool,
    exclude_packages: set[str],
) -> Path:
    """Write the full spack environment YAML using mache's templates."""

    work = Path(ctx.work_dir) / 'spack'
    work.mkdir(parents=True, exist_ok=True)

    if machine is None:
        raise ValueError(
            'Cannot write mache spack env YAML: machine is not known.'
        )

    yaml_template: str | None = None
    template_path = os.path.join(
        'deploy', 'spack', f'{machine}_{compiler}_{mpi}.yaml'
    )
    if os.path.exists(template_path):
        yaml_template = template_path

    yaml_text = _get_yaml_data(
        ctx.machine,
        compiler,
        mpi,
        include_e3sm_lapack=False,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        specs=spack_specs,
        yaml_template=yaml_template,
        exclude_packages=exclude_packages,
    )

    yaml_path = work / f'{env_name}.yaml'
    yaml_path.write_text(yaml_text, encoding='utf-8')
    return yaml_path


def _install_spack_env(
    *,
    ctx: DeployContext,
    spack_path: str,
    env_name: str,
    yaml_path: str,
    compiler: str,
    mpi: str,
    tmpdir: str | None,
    mirror: str | None,
    custom_spack: str,
    e3sm_hdf5_netcdf: bool,
    pins: dict,
    build_jobs: int | None,
    log_filename: str,
    quiet: bool,
) -> None:
    """Check out the pinned Spack sources and build/install the environment."""

    # Render the module-load / env-var setup snippet (no spack activation)
    prologue = get_spack_script(
        spack_path=spack_path,
        env_name=env_name,
        compiler=compiler,
        mpi=mpi,
        shell='sh',
        machine=ctx.machine,
        include_e3sm_lapack=False,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        load_spack_env=False,
    )
    if tmpdir is not None:
        prologue = f'{prologue}\nexport TMPDIR={tmpdir}'

    work = Path(ctx.work_dir) / 'spack'
    work.mkdir(parents=True, exist_ok=True)
    # kept for the activation capture step, which runs after post_spack hooks
    write_prologue(str(work), env_name, prologue)

    script = render_install_script(
        spack_path=spack_path,
        env_name=env_name,
        yaml_path=yaml_path,
        prologue=prologue,
        pins=pins,
        work_dir=str(work),
        mirror=mirror,
        custom_spack=custom_spack,
        build_jobs=build_jobs,
    )
    script_path = work / f'build_{env_name}.bash'
    script_path.write_text(script, encoding='utf-8')

    # Clear environment variables and start fresh with those from login so
    # spack doesn't get confused by conda.
    cmd = f'env -i bash -l {shlex.quote(str(script_path))}'
    check_call(cmd, log_filename=log_filename, quiet=quiet)


def _get_machine_bool(
    *,
    machine_config: ConfigParser,
    section: str,
    option: str,
    default: bool,
) -> bool:
    """Read a boolean option from merged machine config with a default."""

    if not machine_config.has_section(section):
        return default
    if not machine_config.has_option(section, option):
        return default
    try:
        return machine_config.getboolean(section, option)
    except ValueError as exc:
        raw = machine_config.get(section, option)
        raise ValueError(
            f'Invalid boolean for [{section}] {option}: {raw!r}'
        ) from exc
