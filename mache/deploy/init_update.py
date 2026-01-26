from __future__ import annotations

import os
import stat
from importlib import resources
from pathlib import Path

from jinja2 import Template

from mache.deploy.jinja import define_square_bracket_environment
from mache.version import __version__

TEMPLATE_DIR = 'templates'


def init_or_update_repo(
    repo_root: str,
    software: str,
    mache_version: str | None,
    update: bool = False,
    overwrite: bool = False,
) -> None:
    """
    Init: Create/refresh the deploy starter kit in a target-software repo.
    Update: Update only a subset of deployed files for a new mache version.

    Writes:
      - deploy.py (repo root)
      - deploy/cli_spec.json
      - deploy/pins.cfg (init only)
      - deploy/config.yaml.j2 (init only)
      - deploy/spack.yaml.j2 (init only)
      - deploy/hooks.py (init only, example-only)

    Parameters
    ----------
    repo_root : str
        Path to target repo root.
    software : str
        Target software name (e.g. polaris).
    mache_version : str | None
        Pinned mache version for this repo, default is the current mache
        version.
    update : bool, optional
        If True, perform an update rather than an init.
    overwrite : bool, optional
        If True, overwrite existing deploy files.
    """
    root = Path(repo_root).resolve()
    deploy_dir = root / 'deploy'

    if mache_version is None:
        mache_version = __version__

    # Render cli_spec first; we also use it to decide overwrite policies.
    cli_spec_template = _read_pkg_template(f'{TEMPLATE_DIR}/cli_spec.json.j2')
    rendered_cli_spec = _render_jinja_template(
        cli_spec_template,
        {
            'software': software,
            'mache_version': mache_version,
            # add more placeholders as you like
        },
    )

    # Write cli_spec.json
    _write_text(
        deploy_dir / 'cli_spec.json', rendered_cli_spec, overwrite=overwrite
    )

    # deploy.py.j2 rendered -> deploy.py at repo root
    deploy_py_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/deploy.py.j2')
    deploy_py_rendered = _render_jinja_template(
        deploy_py_tmpl,
        {
            'software': software,
            'mache_version': mache_version,
        },
    )
    deploy_py_path = root / 'deploy.py'
    _write_text(deploy_py_path, deploy_py_rendered, overwrite=overwrite)
    _make_executable(deploy_py_path)

    if not update:
        # pins.cfg.j2 rendered
        pins_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/pins.cfg.j2')
        pins_rendered = _render_jinja_template(
            pins_tmpl,
            {
                'software': software,
                'mache_version': mache_version,
            },
        )
        _write_text(
            deploy_dir / 'pins.cfg', pins_rendered, overwrite=overwrite
        )

        # pixi.toml.j2.j2 rendered once using square-bracket
        # delimiters so any remaining curly-brace Jinja (deployment-time) stays
        # untouched. Not yet used by deploy.py, but shipped so repos can start
        # iterating.
        pixi_toml_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/pixi.toml.j2.j2')
        pixi_toml_rendered = _render_double_jinja_template_square_brackets(
            pixi_toml_tmpl,
            {
                'software': software,
                'mache_version': mache_version,
            },
        )
        _write_text(
            deploy_dir / 'pixi.toml.j2',
            pixi_toml_rendered,
            overwrite=overwrite,
        )

        # config.yaml.j2.j2 rendered once using square-bracket delimiters so
        # any remaining curly-brace Jinja (deployment-time) stays untouched.
        config_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/config.yaml.j2.j2')
        config_rendered = _render_double_jinja_template_square_brackets(
            config_tmpl,
            {
                'software': software,
                'mache_version': mache_version,
            },
        )
        _write_text(
            deploy_dir / 'config.yaml.j2',
            config_rendered,
            overwrite=overwrite,
        )

        # spack.yaml.j2 is a runtime (deployment-time) Jinja template owned by
        # the target repo.
        spack_specs_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/spack.yaml.j2')
        _write_text(
            deploy_dir / 'spack.yaml.j2',
            spack_specs_tmpl,
            overwrite=overwrite,
        )

        # Optional example hook module (not enabled by default).
        hooks_py_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/hooks.py.j2')
        _write_text(
            deploy_dir / 'hooks.py',
            hooks_py_tmpl,
            overwrite=overwrite,
        )

        load_sh = (
            '# bash snippet for adding Polaris-specific environment '
            'variables\n'
        )
        _write_text(
            deploy_dir / 'load.sh',
            load_sh,
            overwrite=overwrite,
        )


def _read_pkg_template(relpath: str) -> str:
    # relpath like "templates/deploy.py.j2"
    package = __package__  # "mache.deploy"
    return (
        resources.files(package).joinpath(relpath).read_text(encoding='utf-8')
    )


def _render_jinja_template(template_text: str, context: dict) -> str:
    template = Template(template_text)
    rendered = template.render(**dict(context)) + '\n'
    return rendered


def _render_double_jinja_template_square_brackets(
    template_text: str, context: dict
) -> str:
    env = define_square_bracket_environment()
    tmpl = env.from_string(template_text)
    rendered = tmpl.render(**dict(context)) + '\n'
    return rendered


def _write_text(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f'Refusing to overwrite existing file: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _make_executable(path: Path) -> None:
    """Make a file executable (chmod +x), preserving existing permissions."""

    # On Windows, chmod execute bits are not meaningful in the same way.
    if os.name == 'nt':
        return

    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
