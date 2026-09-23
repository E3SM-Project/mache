import logging
import os
import shlex
import subprocess

from mache.spack.shared import PATH_LIKE_ENV_VARS
from mache.version import __version__

#: How load scripts activate a Spack environment: ``captured`` sources a file
#: written at build time; ``dynamic`` runs ``spack env activate``
ACTIVATION_MODES = ('captured', 'dynamic')

logger = logging.getLogger(__name__)


def capture_activation(
    *,
    spack_path,
    env_name,
    prologue_path,
    work_dir,
):
    """
    Run ``spack env activate --sh`` for an environment in a fresh login shell
    and rewrite its output relative to that shell's environment.

    Parameters
    ----------
    spack_path : str
        The Spack checkout (``$SPACK_ROOT``)

    env_name : str
        The managed environment to capture

    prologue_path : str
        The shell script with the module loads and variables the environment
        was built with

    work_dir : str
        Where ``<env_name>.env_before`` and ``<env_name>.raw_activate.sh`` are
        written

    Returns
    -------
    modifications : list of tuple
        The rewritten modifications, see :py:func:`rewrite_modifications`
    """
    env_before_path = os.path.join(work_dir, f'{env_name}.env_before')
    raw_path = os.path.join(work_dir, f'{env_name}.raw_activate.sh')
    setup_env = os.path.join(spack_path, 'share', 'spack', 'setup-env.sh')
    commands = (
        'set -e\n'
        f'source {shlex.quote(prologue_path)}\n'
        f'source {shlex.quote(setup_env)}\n'
        f'env -0 > {shlex.quote(env_before_path)}\n'
        f'spack env activate --sh {shlex.quote(env_name)} '
        f'> {shlex.quote(raw_path)}\n'
    )
    # a fresh login shell, as for the build, so nothing from the calling
    # environment (conda, pixi) leaks into the captured values
    result = subprocess.run(
        ['env', '-i', 'bash', '-l', '-c', commands],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f'Capturing the activation of Spack environment {env_name} '
            f'failed with exit code {result.returncode}:\n'
            f'{result.stdout}\n{result.stderr}'
        )

    with open(env_before_path, 'rb') as handle:
        env_before = parse_env_before(handle.read())
    with open(raw_path) as handle:
        raw = parse_raw_activation(handle.read())
    return rewrite_modifications(raw, env_before)


def parse_env_before(data):
    """
    Parse the NUL-separated output of ``env -0``.

    Parameters
    ----------
    data : bytes
        The output of ``env -0``

    Returns
    -------
    env : dict
        Variable names to values
    """
    env = {}
    for entry in data.split(b'\0'):
        if not entry:
            continue
        name, sep, value = entry.decode('utf-8', 'surrogateescape').partition(
            '='
        )
        if sep:
            env[name] = value
    return env


def parse_raw_activation(text):
    """
    Parse the output of ``spack env activate --sh``.

    Parameters
    ----------
    text : str
        Lines of the form ``export NAME=VALUE;``, ``unset NAME;`` or
        ``alias ...;``

    Returns
    -------
    raw : list of tuple
        ``('export', name, value)`` and ``('unset', name)`` entries in order;
        aliases are dropped
    """
    raw: list[tuple] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(';'):
            line = line[:-1]
        words = shlex.split(line)
        if not words or words[0] == 'alias':
            continue
        if words[0] == 'export' and len(words) == 2 and '=' in words[1]:
            name, _, value = words[1].partition('=')
            raw.append(('export', name, value))
        elif words[0] == 'unset' and len(words) == 2:
            raw.append(('unset', words[1]))
        else:
            raise ValueError(
                f'Unexpected line in spack env activate output: {line!r}'
            )
    return raw


def rewrite_modifications(raw, env_before):
    """
    Rewrite raw activation entries relative to the capturing shell.

    A path-like variable (``PATH_LIKE_ENV_VARS``) becomes a prepend of the
    elements that were not in its value before activation, in order; other
    variables are set to their literal values.

    Parameters
    ----------
    raw : list of tuple
        From :py:func:`parse_raw_activation`

    env_before : dict
        From :py:func:`parse_env_before`

    Returns
    -------
    modifications : list of tuple
        ``('prepend', name, elements)``, ``('set', name, value)`` and
        ``('unset', name)`` entries
    """
    modifications: list[tuple] = []
    for entry in raw:
        if entry[0] == 'unset':
            modifications.append(entry)
            continue
        _, name, value = entry
        if name not in PATH_LIKE_ENV_VARS:
            modifications.append(('set', name, value))
            continue

        old_value = env_before.get(name, '')
        old_elements = old_value.split(os.pathsep) if old_value else []
        new_elements = value.split(os.pathsep)
        if name == 'MANPATH' and new_elements and new_elements[-1] == '':
            # spack appends a trailing colon so man keeps its default path;
            # the rendered prepend restores it
            new_elements = new_elements[:-1]

        # spack normalizes every element of the variable (an empty element
        # becomes '.'), so compare against the normalized old elements too
        old_set = set(old_elements)
        old_set.update(os.path.normpath(element) for element in old_elements)
        prepend = []
        for element in new_elements:
            if element not in old_set and element not in prepend:
                prepend.append(element)

        new_set = set(new_elements)
        lost = [
            element
            for element in old_elements
            if element not in new_set
            and os.path.normpath(element) not in new_set
        ]
        if lost:
            logger.warning(
                'Activation of the Spack environment removes these elements '
                'of %s, which the captured activation keeps: %s',
                name,
                os.pathsep.join(lost),
            )
        if prepend:
            modifications.append(('prepend', name, prepend))
    return modifications


def render_activation(modifications, shell, spack_path):
    """
    Render an activation snippet for a shell.

    Parameters
    ----------
    modifications : list of tuple
        From :py:func:`rewrite_modifications`

    shell : {'sh', 'csh'}
        The shell to render for

    spack_path : str
        The Spack checkout; the snippet sets ``SPACK_ROOT`` and puts its
        ``bin`` on ``PATH`` so the plain ``spack`` executable is available

    Returns
    -------
    text : str
        The snippet
    """
    if shell not in ('sh', 'csh'):
        raise ValueError(f'Unexpected shell: {shell}')
    header = [
        ('set', 'SPACK_ROOT', spack_path),
        ('prepend', 'PATH', [os.path.join(spack_path, 'bin')]),
    ]
    lines = [
        f'# Spack environment activation captured by mache {__version__}.',
        '# Sourcing this file replaces `spack env activate`; it prepends to',
        '# path-like variables and sets the rest.',
    ]
    for modification in header + list(modifications):
        lines.append(_render_modification(modification, shell))
    return '\n'.join(lines) + '\n'


def write_activation_files(*, spack_path, env_name, modifications):
    """
    Write ``activate.sh`` and ``activate.csh`` into the environment directory.

    Parameters
    ----------
    spack_path : str
        The Spack checkout

    env_name : str
        The managed environment

    modifications : list of tuple
        From :py:func:`rewrite_modifications`

    Returns
    -------
    paths : tuple of str
        The paths of the ``sh`` and ``csh`` files
    """
    paths = []
    for shell in ('sh', 'csh'):
        path = activation_file_path(spack_path, env_name, shell)
        with open(path, 'w') as handle:
            handle.write(render_activation(modifications, shell, spack_path))
        paths.append(path)
    return tuple(paths)


def activation_file_path(spack_path, env_name, shell):
    """The path of the captured activation file for a shell."""
    return os.path.join(
        spack_path,
        'var',
        'spack',
        'environments',
        env_name,
        f'activate.{shell}',
    )


def activation_source_line(spack_path, env_name, shell):
    """The line a load script uses to source the captured activation."""
    return f'source {activation_file_path(spack_path, env_name, shell)}'


def _render_modification(modification, shell):
    kind, name = modification[0], modification[1]
    if kind == 'unset':
        if shell == 'sh':
            return f'unset {name}'
        return f'unsetenv {name}'
    if kind == 'set':
        value = modification[2]
        if shell == 'sh':
            return f'export {name}={_sh_quote(value)}'
        return f'setenv {name} {_csh_quote(value)}'
    if kind == 'prepend':
        joined = os.pathsep.join(modification[2])
        if shell == 'sh':
            # MANPATH keeps a trailing colon when it was unset so man still
            # searches its default path
            if name == 'MANPATH':
                suffix = ':${MANPATH:-}'
            else:
                suffix = '${' + name + ':+:$' + name + '}'
            return f'export {name}={_sh_quote(joined, suffix=suffix)}'
        unset_value = f'{joined}:' if name == 'MANPATH' else joined
        return (
            f'if ($?{name}) then\n'
            f'  setenv {name} {_csh_quote(joined, suffix="$" + name)}\n'
            f'else\n'
            f'  setenv {name} {_csh_quote(unset_value)}\n'
            f'endif'
        )
    raise ValueError(f'Unexpected modification: {modification}')


def _sh_quote(value, suffix=''):
    """Double-quote a value for sh, with an optional expansion tail."""
    escaped = (
        value.replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('$', '\\$')
        .replace('`', '\\`')
    )
    return f'"{escaped}{suffix}"'


def _csh_quote(value, suffix=''):
    """Double-quote a value for csh, with an optional expansion tail."""
    escaped = (
        value.replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('$', '\\$')
        .replace('!', '\\!')
    )
    if suffix:
        return f'"{escaped}:{suffix}"'
    return f'"{escaped}"'
