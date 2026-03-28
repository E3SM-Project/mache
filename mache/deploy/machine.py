from __future__ import annotations

import configparser
import os
from importlib import resources

from mache.discover import discover_machine


def get_known_mache_machines(*, package: str = 'mache.machines') -> set[str]:
    """
    Return the set of machine names known to mache.

    A machine is considered "known" if a corresponding ``<machine>.cfg`` file
    exists in ``mache.machines``.

    Parameters
    ----------
    package
        The package to search for machine config files.

    Returns
    -------
    known
        A set of known machine names.
    """

    known: set[str] = set()
    root = resources.files(package)
    for entry in root.iterdir():
        name = entry.name
        if not name.endswith('.cfg'):
            continue
        machine = name[:-4]
        if machine == 'default' or machine.startswith('default-'):
            continue
        known.add(machine)
    return known


def get_known_target_machines(*, machines_path: str | None) -> set[str]:
    """Return the set of machine names provided by the target software.

    Target machines are read from a directory on disk (no Python imports).

    Parameters
    ----------
    machines_path
        Optional path (absolute or relative to repo root) containing machine
        config files in ini format (e.g. ``deploy/machines``). If
        ``None``/empty, no target machines are considered.

    Returns
    -------
    known
        A set of known machine names.
    """

    if machines_path is None:
        return set()

    path = os.path.abspath(
        os.path.expanduser(os.path.expandvars(machines_path))
    )
    if not os.path.isdir(path):
        return set()

    known: set[str] = set()
    for entry in os.listdir(path):
        if not entry.endswith('.cfg'):
            continue
        machine = entry[:-4]
        if machine == 'default' or machine.startswith('default-'):
            continue
        known.add(machine)
    return known


def get_known_machines(*, machines_path: str | None = None) -> set[str]:
    """
    Return the set of machines known to mache or the target software.

    Parameters
    ----------
    machines_path
        Optional path (absolute or relative to repo root) containing machine
        config files in ini format (e.g. ``deploy/machines``). If
        ``None``/empty, only ``mache.machines`` is used.

    Returns
    -------
    known
        A set of known machine names.
    """

    return get_known_mache_machines() | get_known_target_machines(
        machines_path=machines_path
    )


def get_machine(
    *,
    requested_machine: str | None,
    machines_path: str | None = None,
    quiet: bool = False,
) -> str | None:
    """Get the selected machine.

    If ``requested_machine`` is provided, it must correspond to a machine
    known to mache and/or the target software. If it is unknown, a
    ``ValueError`` is raised.

    If ``requested_machine`` is not provided, we attempt to detect the machine
    using :py:func:`mache.discover.discover_machine`. If detection fails or
    yields an unknown machine, the returned machine is ``None``.

    Parameters
    ----------
    requested_machine
        The requested machine name (known to mache and/or the target software)
        or ``None`` to detect the machine.

    machines_path
        Optional path (absolute or relative to repo root) containing machine
        config files in ini format (e.g. ``deploy/machines``). If
        ``None``/empty, only ``mache.machines`` is used.

    quiet
        If True, suppress warnings.

    Returns
    -------
    machine
        The selected machine name (known to mache and/or the target software)
        or ``None``.
    """

    known = get_known_machines(machines_path=machines_path)

    candidate: str | None
    explicitly_requested = requested_machine is not None
    if explicitly_requested:
        candidate = str(requested_machine).strip()
        if candidate.lower() in ('', 'none', 'null'):
            candidate = None
    else:
        candidate = discover_machine(quiet=quiet, path=machines_path)

    if candidate is None:
        return None

    if candidate not in known:
        if explicitly_requested:
            raise ValueError(
                f"Requested machine '{candidate}' is not known to mache or "
                'target software.'
            )
        if not quiet:
            print(
                f"Warning: detected machine '{candidate}' is not known to "
                'mache or target software; treating machine as None'
            )
        return None

    return candidate


def get_machine_config(
    *,
    machine: str | None,
    machines_path: str | None,
    platform: str,
    quiet: bool = False,
) -> configparser.ConfigParser:
    """
    Load merged machine config from mache + (optional) target software.

    If ``machine`` is not ``None``, load config from ``<machine>.cfg`` files in
    both ``mache.machines`` and the target software (if
    ``machines_path`` is provided). If ``machine`` is ``None``, only
    ``default-<platform>.cfg`` from the target software is loaded (if
    ``machines_path`` is provided).

    Parameters
    ----------
    machine
        The selected machine name (known to mache) or ``None``.

    machines_path
        Optional path (absolute or relative to repo root) containing machine
        config files in ini format (e.g. ``polaris/machines``). If
        ``None``/empty, only ``mache.machines`` is used.

    platform
        The platform string to use when ``machine`` is ``None``, e.g.
        "linux-64".

    quiet
        If True, suppress warnings.

    Returns
    -------
    config
        A ``configparser.ConfigParser`` with config read in precedence order:
        mache first, then target software (later files override earlier ones).
    """

    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    path = str(machines_path).strip() if machines_path else ''

    # Always start with default.cfg (may be empty) from both mache and target
    _read_cfg_from_package(
        config=config,
        package='mache.machines',
        filename='default.cfg',
        quiet=quiet,
    )

    if path:
        _read_cfg_from_path(
            config=config,
            machines_path=path,
            filename='default.cfg',
            quiet=True,
        )

    if machine is not None:
        mache_known = machine in get_known_mache_machines()
        _read_cfg_from_package(
            config=config,
            package='mache.machines',
            filename=f'{machine}.cfg',
            quiet=(quiet or not mache_known),
        )

    if path:
        if machine is not None:
            config_filename = f'{machine}.cfg'
        else:
            config_filename = f'default-{platform}.cfg'
        _read_cfg_from_path(
            config=config,
            machines_path=path,
            filename=config_filename,
            quiet=True,
        )

    return config


def _read_cfg_from_package(
    *,
    config: configparser.ConfigParser,
    package: str,
    filename: str,
    quiet: bool,
) -> None:
    try:
        cfg_path = resources.files(package) / filename
    except ModuleNotFoundError as e:
        if not quiet:
            print(
                f"Warning: could not import machines package '{package}': {e}"
            )
        return

    try:
        config.read(str(cfg_path))
    except FileNotFoundError:
        if not quiet:
            print(
                f"Warning: machine config file not found in '{package}': "
                f'{filename}'
            )
        return


def _read_cfg_from_path(
    *,
    config: configparser.ConfigParser,
    machines_path: str,
    filename: str,
    quiet: bool,
) -> None:
    path = os.path.abspath(
        os.path.expanduser(os.path.expandvars(machines_path))
    )
    cfg_path = os.path.join(path, filename)
    if not os.path.exists(cfg_path):
        if not quiet:
            print(f'Warning: machine config file not found: {cfg_path}')
        return

    config.read(cfg_path)
