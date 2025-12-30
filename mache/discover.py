import configparser
import importlib
import os
import re
import socket
import sys
from dataclasses import dataclass
from importlib import resources as importlib_resources
from typing import Iterable, List, Optional


def discover_machine(
    quiet: bool = False,
    package: Optional[str] = None,
    path: Optional[str] = None,
):
    """Figure out the machine from the host name.

    Parameters
    ----------
    quiet : bool, optional
        Whether to print warnings if the machine name is ambiguous

    package : str, optional
        An additional Python package to search for machine config files
        (``*.cfg``) that include a ``[discovery] hostname_re`` entry.

    path : str, optional
        An additional directory to search for machine config files (``*.cfg``)
        that include a ``[discovery] hostname_re`` entry.

    Returns
    -------
    machine : str
        The name of the current machine
    """

    hostname = socket.gethostname()
    machine = None

    rules = _get_discovery_rules(package=package, path=path)
    matches: List[_DiscoveryRule] = []
    for rule in rules:
        try:
            pattern = re.compile(rule.hostname_re)
        except re.error:
            if not quiet:
                print(
                    f'Warning: invalid hostname_re {rule.hostname_re!r} '
                    f'for machine {rule.machine!r} from {rule.source}',
                    file=sys.stderr,
                )
            continue
        if pattern.match(hostname):
            matches.append(rule)

    if matches:
        machine = matches[0].machine
        if len(matches) > 1 and not quiet:
            others = ', '.join(sorted({rule.machine for rule in matches[1:]}))
            print(
                f'Warning: hostname {hostname!r} matches multiple machines; '
                f'choosing {machine!r}. Other matches: {others}',
                file=sys.stderr,
            )

    if machine is None and 'LMOD_SYSTEM_NAME' in os.environ:
        hostname = os.environ['LMOD_SYSTEM_NAME']
        if hostname == 'frontier':
            # frontier's hostname is too generic to detect, so relying on
            # LMOD_SYSTEM_NAME
            machine = 'frontier'

    if machine is None and 'NERSC_HOST' in os.environ:
        hostname = os.environ['NERSC_HOST']
        if hostname == 'perlmutter':
            # perlmutter's hostname is too generic to detect, so relying on
            # $NERSC_HOST
            machine = 'pm-cpu'
        elif hostname == 'unknown':
            raise ValueError(
                'You appear to have $NERSC_HOST=unknown.  This typically '
                'indicates that you \n'
                'have an outdated .bash_profile.ext or similar.  Please '
                'either delete or \n'
                'edit that file so it no longer defines $NERSC_HOST, log out, '
                'log back in, \n'
                'and try again.'
            )

    # As a last resort (e.g. on a compute node), try getting the machine from
    # a file created on install
    if machine is None and 'CONDA_PREFIX' in os.environ:
        prefix = os.environ['CONDA_PREFIX']
        machine_filename = os.path.join(
            prefix, 'share', 'mache', 'machine.txt'
        )
        if os.path.exists(machine_filename):
            with open(machine_filename) as fp:
                machine = fp.read().replace('\n', '').strip()

    return machine


@dataclass(frozen=True)
class _DiscoveryRule:
    machine: str
    hostname_re: str
    source: str


def _parse_hostname_re_value(hostname_re: str) -> List[str]:
    """Parse one or more hostname regex patterns from a config value.

    We support comma-separated and/or newline-separated entries.
    """
    patterns: List[str] = []
    for line in hostname_re.splitlines():
        line = line.strip()
        if not line:
            continue
        # Split only on comma+whitespace so patterns like `{1,4}` are safe.
        for entry in re.split(r',\s+', line):
            entry = entry.strip()
            if entry:
                patterns.append(entry)
    return patterns


def _read_discovery_rules_from_cfg(
    cfg_path: str, machine: str, source: str
) -> List[_DiscoveryRule]:
    # Do NOT enable interpolation here: regex patterns commonly contain '$'.
    config = configparser.RawConfigParser()
    config.read(cfg_path)
    if not config.has_option('discovery', 'hostname_re'):
        return []
    raw_value = config.get(
        'discovery', 'hostname_re', raw=True, fallback=''
    ).strip()
    if not raw_value:
        return []
    return [
        _DiscoveryRule(machine=machine, hostname_re=pattern, source=source)
        for pattern in _parse_hostname_re_value(raw_value)
    ]


def _iter_cfgs_in_package(package: str) -> Iterable[tuple[str, str]]:
    """Yield (machine_name, cfg_path) from a package containing *.cfg files."""
    module = importlib.import_module(package)
    root = importlib_resources.files(module)
    for child in root.iterdir():
        if not child.is_file():
            continue
        name = child.name
        if not name.endswith('.cfg'):
            continue
        machine = os.path.splitext(name)[0]
        yield machine, str(child)


def _iter_cfgs_in_path(path: str) -> Iterable[tuple[str, str]]:
    """Yield (machine_name, cfg_path) from a directory of ``*.cfg`` files."""
    if not os.path.isdir(path):
        return
    for name in sorted(os.listdir(path)):
        if not name.endswith('.cfg'):
            continue
        machine = os.path.splitext(name)[0]
        yield machine, os.path.join(path, name)


def _get_discovery_rules(
    *,
    package: Optional[str] = None,
    path: Optional[str] = None,
    builtin_package: str = 'mache.machines',
) -> List[_DiscoveryRule]:
    """Get hostname discovery rules.

    Precedence is:
      1) rules from ``path`` (if provided)
      2) rules from ``package`` (if provided)
      3) rules from the built-in machines package
    """
    rules: List[_DiscoveryRule] = []

    if path is not None:
        for machine, cfg_path in _iter_cfgs_in_path(path):
            rules.extend(
                _read_discovery_rules_from_cfg(
                    cfg_path=cfg_path,
                    machine=machine,
                    source=f'path:{path}',
                )
            )

    if package is not None:
        for machine, cfg_path in _iter_cfgs_in_package(package):
            rules.extend(
                _read_discovery_rules_from_cfg(
                    cfg_path=cfg_path,
                    machine=machine,
                    source=f'package:{package}',
                )
            )

    for machine, cfg_path in _iter_cfgs_in_package(builtin_package):
        rules.extend(
            _read_discovery_rules_from_cfg(
                cfg_path=cfg_path,
                machine=machine,
                source=f'package:{builtin_package}',
            )
        )

    return rules
