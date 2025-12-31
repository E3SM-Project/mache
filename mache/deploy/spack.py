from __future__ import annotations

import os
import shlex
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template
from packaging.version import Version
from yaml import safe_load

from mache.deploy.bootstrap import check_call
from mache.deploy.hooks import DeployContext
from mache.spack.script import get_spack_script
from mache.spack.shared import _get_yaml_data
from mache.version import __version__


@dataclass(frozen=True)
class SpackDeployResult:
    """Result of deploying a Spack environment for one toolchain pair."""

    compiler: str
    mpi: str
    env_name: str
    spack_path: str
    activation: str


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


def deploy_spack_software_env(
    *,
    ctx: DeployContext,
    log_filename: str,
    quiet: bool,
) -> SpackSoftwareEnvResult | None:
    """Deploy an optional Spack "software" environment.

    This environment is built with a single (compiler, mpi) pair, typically
    defined in the merged machine config under:
      [deploy] software_compiler
      [deploy] mpi_<software_compiler>

    No CLI flags control this environment.
    """

    spack_cfg = ctx.config.get('spack', {})
    if not isinstance(spack_cfg, dict):
        return None

    software_cfg = spack_cfg.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if not isinstance(software_cfg, dict):
        raise ValueError('spack.software must be a mapping if provided')

    deploy_spack = bool(spack_cfg.get('deploy')) or bool(
        getattr(ctx.args, 'deploy_spack', False)
    )

    software_supported = bool(software_cfg.get('supported'))

    if not deploy_spack or not software_supported:
        return None

    if ctx.machine is None:
        raise ValueError(
            'Spack software environment deployment was requested but machine '
            'is not known.'
        )

    compiler, mpi = _resolve_software_toolchain(
        machine_config=ctx.machine_config
    )

    e3sm_hdf5_netcdf = _get_machine_bool(
        machine_config=ctx.machine_config,
        section='deploy',
        option='use_e3sm_hdf5_netcdf',
        default=False,
    )

    spack_path = _resolve_spack_path(ctx=ctx, spack_cfg=spack_cfg)

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
    )

    yaml_path = _write_mache_spack_env_yaml(
        ctx=ctx,
        machine=ctx.machine,
        compiler=compiler,
        mpi=mpi,
        env_name=env_name,
        spack_specs=specs,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
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

    This function is a thin orchestration layer:
      - Reads deploy config (ctx.config['spack'])
      - Renders `deploy/spack.yaml.j2` to get a list of spec strings
      - Uses mache's Spack env templates (mache/spack/templates/*.yaml)
        to construct a full spack environment YAML
      - Runs spack to concretize/install the environment
      - Produces a shell snippet for load scripts

    Notes
    -----
    This is intentionally "E3SM flavored": it uses `get_spack_script()` to
    load compiler/MPI modules and settings from config_machines.xml.

    Returns
    -------
    results
        A list of SpackDeployResult, one per (compiler, mpi)
    """

    spack_cfg = ctx.config.get('spack', {})
    if not isinstance(spack_cfg, dict):
        return []

    software_cfg = spack_cfg.get('software', {})
    if software_cfg is None:
        software_cfg = {}
    if not isinstance(software_cfg, dict):
        raise ValueError('spack.software must be a mapping if provided')

    deploy_spack = bool(spack_cfg.get('deploy')) or bool(
        getattr(ctx.args, 'deploy_spack', False)
    )

    library_supported = bool(spack_cfg.get('supported'))

    if not deploy_spack or not library_supported:
        return []

    if not toolchain_pairs:
        raise ValueError(
            'Spack library environment deployment was requested but no '
            'toolchain pairs were resolved. Provide toolchain.compiler/'
            'toolchain.mpi or --compiler/--mpi.'
        )

    spack_path = _resolve_spack_path(ctx=ctx, spack_cfg=spack_cfg)

    e3sm_hdf5_netcdf = _get_machine_bool(
        machine_config=ctx.machine_config,
        section='deploy',
        option='use_e3sm_hdf5_netcdf',
        default=False,
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
        )

        yaml_path = _write_mache_spack_env_yaml(
            ctx=ctx,
            machine=ctx.machine,
            compiler=compiler,
            mpi=mpi,
            env_name=env_name,
            spack_specs=specs,
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
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
            log_filename=log_filename,
            quiet=quiet,
        )

        activation = get_spack_script(
            spack_path=spack_path,
            env_name=env_name,
            compiler=compiler,
            mpi=mpi,
            shell='sh',
            machine=ctx.machine,
            include_e3sm_lapack=False,
            e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            load_spack_env=True,
        )

        results.append(
            SpackDeployResult(
                compiler=compiler,
                mpi=mpi,
                env_name=env_name,
                spack_path=spack_path,
                activation=activation,
            )
        )

    return results


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


def _resolve_spack_path(*, ctx: DeployContext, spack_cfg: dict) -> str:
    """Resolve spack checkout path, preferring hook/runtime overrides."""

    rt_spack_cfg = ctx.runtime.get('spack', {})
    if rt_spack_cfg is None:
        rt_spack_cfg = {}
    if not isinstance(rt_spack_cfg, dict):
        raise ValueError('runtime.spack must be a mapping if provided')

    spack_path = _normalize_optional_token(rt_spack_cfg.get('spack_path'))
    if spack_path is None:
        spack_path = _normalize_optional_token(spack_cfg.get('spack_path'))
    spack_path = str(spack_path or '').strip()
    if not spack_path:
        raise ValueError(
            'spack deploy is enabled but spack_path is not set. Set '
            "ctx.runtime['spack']['spack_path']"
            'in a hook (preferred) or set spack.spack_path in '
            'deploy/config.yaml.j2'
        )
    return os.path.abspath(os.path.expanduser(os.path.expandvars(spack_path)))


def _resolve_software_toolchain(
    *,
    machine_config: ConfigParser,
) -> tuple[str, str]:
    """Resolve the single (compiler, mpi) used for the software environment."""

    if not machine_config.has_section('deploy'):
        raise ValueError(
            'Spack software environment is enabled but machine config has no '
            '[deploy] section.'
        )

    if not machine_config.has_option('deploy', 'software_compiler'):
        raise ValueError(
            'Spack software environment is enabled but [deploy] '
            'software_compiler is not set in merged machine config.'
        )

    compiler = machine_config.get('deploy', 'software_compiler').strip()
    if not compiler:
        raise ValueError('[deploy] software_compiler is empty')

    mpi_option = f'mpi_{compiler.replace("-", "_")}'
    if not machine_config.has_option('deploy', mpi_option):
        raise ValueError(
            f'Spack software environment is enabled but machine config is '
            f'missing [deploy] {mpi_option} (MPI for '
            f'software_compiler={compiler}).'
        )
    mpi = machine_config.get('deploy', mpi_option).strip()
    if not mpi:
        raise ValueError(f'[deploy] {mpi_option} is empty')

    return compiler, mpi


def _render_spack_specs(
    *,
    template_path: str,
    ctx: DeployContext,
    compiler: str,
    mpi: str,
    section: str,
    e3sm_hdf5_netcdf: bool,
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
    log_filename: str,
    quiet: bool,
) -> None:
    """Create/update a spack checkout and build/install the environment."""

    # Render the module-load / env-var setup snippet (no spack activation)
    modules = get_spack_script(
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

    env_lines = modules
    if tmpdir is not None:
        env_lines = f'{env_lines}\nexport TMPDIR={tmpdir}'

    # Use PEP 440 parsing to strip any pre/dev/post release tags and keep only
    # the base release version.
    mache_version = Version(__version__).base_version

    # Prefer https clone to avoid requiring GitHub SSH keys.
    spack_repo = 'https://github.com/E3SM-Project/spack.git'
    branch = f'spack_for_mache_{mache_version}'

    mirror_cmds = ''
    if mirror is not None:
        mirror_cmds = (
            'spack mirror remove spack_mirror >& /dev/null || true\n'
            f'spack mirror add spack_mirror file://{mirror}'
        )

    script = (
        '#!/bin/bash\n\n'
        f'{env_lines}\n\n'
        'set -e\n\n'
        f'if [ -d {shlex.quote(spack_path)} ]; then\n'
        f'  cd {shlex.quote(spack_path)}\n'
        '  git fetch origin\n'
        f'  git reset --hard origin/{branch}\n'
        'else\n'
        f'  git clone -b {shlex.quote(branch)} {shlex.quote(spack_repo)} '
        f'{shlex.quote(spack_path)}\n'
        f'  cd {shlex.quote(spack_path)}\n'
        'fi\n'
        'source share/spack/setup-env.sh\n\n'
        f'{mirror_cmds}\n\n'
        f'spack env remove -y {shlex.quote(env_name)} >& /dev/null && '
        f'echo "recreating environment: {env_name}" || '
        f'echo "creating new environment: {env_name}"\n'
        f'spack env create {shlex.quote(env_name)} {shlex.quote(yaml_path)}\n'
        f'spack env activate {shlex.quote(env_name)}\n'
        'spack install\n'
    )

    if custom_spack.strip():
        script += f'\n{custom_spack.strip()}\n'

    work = Path(ctx.work_dir) / 'spack'
    work.mkdir(parents=True, exist_ok=True)
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
