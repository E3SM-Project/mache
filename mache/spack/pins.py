import os
import shlex
from collections.abc import Mapping, Sequence
from importlib import resources as importlib_resources

from packaging.version import Version
from yaml import safe_dump, safe_load

#: The keys that can pin a repository; each entry must have exactly one
REF_KEYS = ('tag', 'commit', 'branch')

#: Where a mache release may pin sources from
RELEASE_GIT_PREFIXES = (
    'https://github.com/spack/',
    'https://github.com/E3SM-Project/',
)

#: Where each package repository is cloned, relative to ``spack_path``
PACKAGE_REPOS_SUBDIR = os.path.join('var', 'spack', 'package_repos')


def load_pins(overrides=None):
    """
    Load the packaged ``pins.yaml`` and apply overrides.

    Parameters
    ----------
    overrides : mapping, str, os.PathLike or sequence of these, optional
        Overrides to merge into the packaged pins, lowest precedence first.
        Each is either a mapping in the ``pins.yaml`` schema or the path to a
        YAML file holding one.  Overrides merge per repository: naming a
        ``tag``, ``commit`` or ``branch`` for a repository replaces the
        repository's existing ref, and overrides cannot add or remove
        repositories.

    Returns
    -------
    pins : dict
        The merged and validated pins with keys ``spack`` and ``repos``
    """
    path = importlib_resources.files('mache.spack') / 'pins.yaml'
    with open(str(path)) as handle:
        pins = safe_load(handle)

    if overrides is None:
        overrides = []
    elif isinstance(overrides, (Mapping, str, os.PathLike)):
        overrides = [overrides]
    elif not isinstance(overrides, Sequence):
        raise TypeError(
            'pins overrides must be a mapping, a path or a sequence of these'
        )

    for override in overrides:
        if override is None:
            continue
        if isinstance(override, (str, os.PathLike)):
            with open(override) as handle:
                override = safe_load(handle)
            if override is None:
                continue
        pins = merge_pins(pins, override)

    validate_pins(pins)
    return pins


def merge_pins(base, override):
    """
    Merge pin overrides into a base set of pins, per repository.

    Parameters
    ----------
    base : dict
        Pins in the ``pins.yaml`` schema

    override : mapping
        A mapping with any of the keys ``spack`` and ``repos``; entries
        merge into the matching entries of ``base``.  Naming a ref key
        (``tag``, ``commit`` or ``branch``) replaces the existing ref.

    Returns
    -------
    merged : dict
        A new set of pins
    """
    if not isinstance(override, Mapping):
        raise TypeError('pins overrides must be a mapping')

    unknown = set(override) - {'spack', 'repos'}
    if unknown:
        raise ValueError(
            f'Unknown top-level keys in pins override: {sorted(unknown)}. '
            'Expected "spack" and/or "repos".'
        )

    merged = {
        'spack': dict(base['spack']),
        'repos': {name: dict(entry) for name, entry in base['repos'].items()},
    }

    if 'spack' in override:
        merged['spack'] = _merge_entry(
            'spack', merged['spack'], override['spack']
        )

    repos_override = override.get('repos')
    if repos_override is None:
        return merged
    if not isinstance(repos_override, Mapping):
        raise ValueError('pins override "repos" must be a mapping')

    missing = set(repos_override) - set(merged['repos'])
    if missing:
        raise ValueError(
            f'Pins override names repositories that are not pinned: '
            f'{sorted(missing)}. Overrides cannot add repositories; the '
            f'known ones are {list(merged["repos"])}.'
        )
    for name, entry in repos_override.items():
        merged['repos'][name] = _merge_entry(
            name, merged['repos'][name], entry
        )
    return merged


def validate_pins(pins):
    """
    Check that pins have the expected structure and one ref per repository.

    Parameters
    ----------
    pins : dict
        Pins in the ``pins.yaml`` schema

    Raises
    ------
    ValueError
        If the structure is wrong or an entry does not have exactly one of
        ``tag``, ``commit`` and ``branch``
    """
    if not isinstance(pins, Mapping):
        raise ValueError('pins must be a mapping')
    for key in ('spack', 'repos'):
        if key not in pins:
            raise ValueError(f'pins are missing the "{key}" key')
    _validate_ref('spack', pins['spack'])
    repos = pins['repos']
    if not isinstance(repos, Mapping) or not repos:
        raise ValueError('pins "repos" must be a non-empty mapping')
    for name, entry in repos.items():
        _validate_ref(name, entry)


def render_repos_yaml(spack_path, pins):
    """
    Render the ``repos.yaml`` for a Spack instance from pins.

    Parameters
    ----------
    spack_path : str
        The Spack checkout (``$SPACK_ROOT``)

    pins : dict
        Validated pins

    Returns
    -------
    text : str
        YAML with path-based ``repos`` entries in the search order of
        ``pins['repos']``
    """
    repos = {
        name: package_repo_path(spack_path, name) for name in pins['repos']
    }
    return safe_dump({'repos': repos}, sort_keys=False)


def package_repo_clone_path(spack_path, name):
    """The directory a pinned package repository is cloned into."""
    return os.path.join(spack_path, PACKAGE_REPOS_SUBDIR, name)


def package_repo_path(spack_path, name):
    """The path Spack registers for a pinned package repository."""
    return os.path.join(
        package_repo_clone_path(spack_path, name), 'repos', 'spack_repo', name
    )


def checkout_ref(entry):
    """
    The git ref to reset a clone to for a pin entry.

    Parameters
    ----------
    entry : dict
        A validated pin entry

    Returns
    -------
    ref : str
        ``refs/tags/<tag>``, the commit hash, or ``origin/<branch>``
    """
    if 'tag' in entry:
        return f'refs/tags/{entry["tag"]}'
    if 'commit' in entry:
        return str(entry['commit'])
    return f'origin/{entry["branch"]}'


def checkout_command(entry, dest):
    """
    Bash commands that make ``dest`` a clean checkout of a pin entry.

    The clone is created if it is absent and fetched otherwise, then
    detached and hard-reset to the pinned ref, so any local changes (such as
    the ``etc/spack/include.yaml`` that ``spack isolate`` rewrites) are
    discarded.

    Parameters
    ----------
    entry : dict
        A validated pin entry

    dest : str
        The directory to clone into

    Returns
    -------
    commands : str
        Bash commands
    """
    dest_q = shlex.quote(dest)
    git_q = shlex.quote(str(entry['git']))
    ref_q = shlex.quote(checkout_ref(entry))
    return (
        f'if [ -d {dest_q}/.git ]; then\n'
        f'  git -C {dest_q} fetch --tags origin\n'
        f'else\n'
        f'  git clone {git_q} {dest_q}\n'
        f'fi\n'
        f'git -C {dest_q} checkout --detach\n'
        f'git -C {dest_q} reset --hard {ref_q}\n'
    )


def release_pins_are_valid(pins, version):
    """
    Whether pins are acceptable for the given mache version.

    A pre-release may pin anything.  A release must pin tags only, from
    ``github.com/spack/`` or ``github.com/E3SM-Project/``.

    Parameters
    ----------
    pins : dict
        Validated pins

    version : str
        A mache version

    Returns
    -------
    valid : bool
    """
    if Version(version).is_prerelease:
        return True
    entries = [pins['spack'], *pins['repos'].values()]
    for entry in entries:
        if 'tag' not in entry:
            return False
        git = str(entry['git'])
        if not git.startswith(RELEASE_GIT_PREFIXES):
            return False
    return True


def _merge_entry(name, base_entry, override_entry):
    if not isinstance(override_entry, Mapping):
        raise ValueError(f'pins override for "{name}" must be a mapping')
    merged = dict(base_entry)
    if any(key in override_entry for key in REF_KEYS):
        for key in REF_KEYS:
            merged.pop(key, None)
    merged.update(override_entry)
    return merged


def _validate_ref(name, entry):
    if not isinstance(entry, Mapping):
        raise ValueError(f'pins entry "{name}" must be a mapping')
    if not entry.get('git'):
        raise ValueError(f'pins entry "{name}" is missing "git"')
    refs = [key for key in REF_KEYS if key in entry]
    if len(refs) != 1:
        raise ValueError(
            f'pins entry "{name}" must have exactly one of '
            f'{", ".join(REF_KEYS)}; got {refs or "none"}.'
        )
    if not entry[refs[0]]:
        raise ValueError(f'pins entry "{name}" has an empty "{refs[0]}"')
