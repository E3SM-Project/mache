from __future__ import annotations

import os
import stat
from importlib import resources
from pathlib import Path

from jinja2 import Environment, StrictUndefined, Template

from mache.version import __version__

TEMPLATE_DIR = 'templates'


def init_repo(
    repo_root: str,
    software: str,
    mache_version: str | None,
    overwrite: bool = False,
) -> None:
    """
    Create/refresh the deploy starter kit in a target-software repo.

    Writes:
      - deploy.py (repo root)
      - deploy/cli_spec.json
      - deploy/pins.cfg
            - deploy/config.yaml.j2
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

    # pins.cfg.j2 rendered
    pins_tmpl = _read_pkg_template(f'{TEMPLATE_DIR}/pins.cfg.j2')
    pins_rendered = _render_jinja_template(
        pins_tmpl,
        {
            'software': software,
            'mache_version': mache_version,
        },
    )
    _write_text(deploy_dir / 'pins.cfg', pins_rendered, overwrite=overwrite)

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

    # config.yaml.j2.j2 rendered once using square-bracket delimiters so any
    # remaining curly-brace Jinja (deployment-time) stays untouched.
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
    """Render a template once using square-bracket Jinja delimiters.

    This is used for templates that themselves contain *deployment-time* Jinja
    using the standard curly delimiters (e.g. ``{{ var }}``, ``{% if %}``).
    By switching *all* delimiters (variables, blocks, comments) to
    square-bracket forms, we can safely render placeholders like
    ``[[ software ]]`` while leaving all curly-brace Jinja untouched for later.
    """

    env = Environment(
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        variable_start_string='[[',
        variable_end_string=']]',
        block_start_string='[%',
        block_end_string='%]',
        comment_start_string='[#',
        comment_end_string='#]',
    )
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
