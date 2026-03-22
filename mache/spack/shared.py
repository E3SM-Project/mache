import re
from collections.abc import Iterable
from importlib import resources as importlib_resources

from jinja2 import Template
from yaml import safe_dump, safe_load

E3SM_HDF5_NETCDF_PACKAGES = frozenset(
    {'hdf5', 'netcdf-c', 'netcdf-fortran', 'parallel-netcdf'}
)
E3SM_HDF5_NETCDF_ALIASES = frozenset({'e3sm_hdf5_netcdf', 'hdf5_netcdf'})
SHELL_GROUP_RULES = (
    (
        'cmake',
        {
            'condition_packages': ('cmake',),
            'module_patterns': (r'(^|[ /_-])cmake($|[ /@._-])',),
            'env_name_patterns': (r'^CMAKE_', r'^ACLOCAL_PATH$'),
            'env_value_patterns': (r'(^|/)cmake($|/|-)',),
        },
    ),
    (
        'hdf5',
        {
            'condition_packages': ('hdf5',),
            'module_patterns': (r'(^|[ /_-])hdf5($|[ /@._-])',),
            'env_name_patterns': (r'^HDF5_', r'^PHDF5_'),
            'env_value_patterns': (r'(^|/)hdf5($|/|-)',),
        },
    ),
    (
        'parallel-netcdf',
        {
            'condition_packages': ('parallel-netcdf',),
            'module_patterns': (
                r'(^|[ /_-])pnetcdf($|[ /@._-])',
                r'parallel-netcdf',
            ),
            'env_name_patterns': (r'^PNETCDF_',),
            'env_value_patterns': (
                r'(^|/)pnetcdf($|/|-)',
                r'parallel-netcdf',
            ),
        },
    ),
    (
        'netcdf',
        {
            'condition_packages': ('netcdf-c', 'netcdf-fortran'),
            'module_patterns': (
                r'(^|[ /_-])netcdf($|[ /@._-])',
                r'netcdf-hdf5parallel',
            ),
            'env_name_patterns': (
                r'^NETCDF_',
                r'^NETCDF_C_',
                r'^NETCDF_FORTRAN_',
            ),
            'env_value_patterns': (
                r'(^|/)netcdf($|/|-)',
                r'netcdf-hdf5parallel',
            ),
        },
    ),
)
PATH_LIKE_ENV_VARS = frozenset(
    {
        'PATH',
        'LD_LIBRARY_PATH',
        'LIBRARY_PATH',
        'CPATH',
        'C_INCLUDE_PATH',
        'CPLUS_INCLUDE_PATH',
        'F_INCLUDE_PATH',
        'PKG_CONFIG_PATH',
        'MANPATH',
        'ACLOCAL_PATH',
        'CMAKE_PREFIX_PATH',
    }
)


def normalize_excluded_packages(exclude_packages):
    """Normalize a package opt-out list into a set of package names."""

    if exclude_packages is None:
        return set()

    if isinstance(exclude_packages, str):
        entries = exclude_packages.replace(',', ' ').split()
    elif isinstance(exclude_packages, Iterable):
        entries = []
        for item in exclude_packages:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError(
                    'exclude_packages entries must be strings, got '
                    f'{type(item).__name__}.'
                )
            entries.extend(item.replace(',', ' ').split())
    else:
        raise TypeError(
            'exclude_packages must be a string or an iterable of strings.'
        )

    excluded: set[str] = set()
    for entry in entries:
        package = entry.strip().lower()
        if not package:
            continue
        if package in E3SM_HDF5_NETCDF_ALIASES:
            excluded.update(E3SM_HDF5_NETCDF_PACKAGES)
        else:
            excluded.add(package)

    return excluded


def use_system_package(package, exclude_packages):
    """Return whether the system-provided package should remain enabled."""

    requested = normalize_excluded_packages([package])
    excluded = normalize_excluded_packages(exclude_packages)
    return not bool(requested & excluded)


def use_system_packages(*packages, exclude_packages):
    """Return whether all requested system packages remain enabled."""

    return all(
        use_system_package(package, exclude_packages) for package in packages
    )


def _matches_patterns(text, patterns):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def classify_module_command_package_group(value):
    """Classify a module command by the system-package group it belongs to."""

    for group_name, rule in SHELL_GROUP_RULES:
        if _matches_patterns(value, rule['module_patterns']):
            return group_name
    return None


def classify_env_var_package_group(name, value=''):
    """Classify an environment variable by the system-package group it uses."""

    for group_name, rule in SHELL_GROUP_RULES:
        if _matches_patterns(name, rule['env_name_patterns']):
            return group_name
        if value and _matches_patterns(value, rule['env_value_patterns']):
            return group_name
    return None


def use_system_package_group(group_name, exclude_packages):
    """Return whether a shell-side system-package group remains enabled."""

    for candidate, rule in SHELL_GROUP_RULES:
        if candidate == group_name:
            return use_system_packages(
                *rule['condition_packages'],
                exclude_packages=exclude_packages,
            )
    raise ValueError(f'Unknown system-package group: {group_name}')


def shell_group_condition(group_name):
    """Return a Jinja expression for testing a shell package group."""

    for candidate, rule in SHELL_GROUP_RULES:
        if candidate != group_name:
            continue
        packages = rule['condition_packages']
        if len(packages) == 1:
            return f"use_system_package('{packages[0]}')"
        args = ', '.join(f"'{package}'" for package in packages)
        return f'use_system_packages({args})'
    raise ValueError(f'Unknown system-package group: {group_name}')


def _filter_system_package_path_segments(value, exclude_packages):
    segments = value.split(':')
    filtered = []
    for segment in segments:
        group_name = classify_env_var_package_group('', segment)
        if group_name is not None and not use_system_package_group(
            group_name, exclude_packages
        ):
            continue
        filtered.append(segment)

    while filtered and filtered[0] == '':
        filtered = filtered[1:]
    while filtered and filtered[-1] == '':
        filtered = filtered[:-1]
    return ':'.join(filtered)


def render_env_var(name, value, shell_type, exclude_packages):
    """Render one shell export/setenv line after applying package opt-outs."""

    if name in PATH_LIKE_ENV_VARS:
        value = _filter_system_package_path_segments(value, exclude_packages)
        if not value:
            return ''
    else:
        group_name = classify_env_var_package_group(name, value)
        if group_name is not None and not use_system_package_group(
            group_name, exclude_packages
        ):
            return ''

    if shell_type == 'sh':
        return f'export {name}="{value}"'
    if shell_type == 'csh':
        return f'setenv {name} "{value}"'
    raise ValueError(f'Unexpected shell_type: {shell_type}')


def resolve_e3sm_hdf5_netcdf(
    *,
    e3sm_hdf5_netcdf,
    exclude_packages,
):
    """Resolve the legacy HDF5/NetCDF toggle against package opt-outs."""

    excluded = normalize_excluded_packages(exclude_packages)
    bundle_requested = bool(excluded & E3SM_HDF5_NETCDF_PACKAGES)

    if not e3sm_hdf5_netcdf:
        excluded.update(E3SM_HDF5_NETCDF_PACKAGES)
        return False, excluded

    if bundle_requested:
        excluded.update(E3SM_HDF5_NETCDF_PACKAGES)
        return False, excluded

    return True, excluded


def _extract_spack_package_name(spec):
    if not isinstance(spec, str):
        return None

    match = re.match(r'^\s*"?([A-Za-z0-9][A-Za-z0-9._-]*)', spec)
    if match is None:
        return None
    return match.group(1).lower()


def _filter_yaml_data(yaml_data, exclude_packages):
    excluded = normalize_excluded_packages(exclude_packages)
    if not excluded:
        return yaml_data

    data = safe_load(yaml_data)
    if not isinstance(data, dict):
        return yaml_data

    spack_data = data.get('spack')
    if not isinstance(spack_data, dict):
        return yaml_data

    specs = spack_data.get('specs')
    if isinstance(specs, list):
        spack_data['specs'] = [
            spec
            for spec in specs
            if _extract_spack_package_name(spec) not in excluded
        ]

    packages = spack_data.get('packages')
    if isinstance(packages, dict):
        for package_name in list(packages):
            if package_name.lower() in excluded:
                del packages[package_name]
                continue

            package_data = packages[package_name]
            if package_name != 'all' or not isinstance(package_data, dict):
                continue

            providers = package_data.get('providers')
            if not isinstance(providers, dict):
                continue

            for provider_name in list(providers):
                provider_specs = providers[provider_name]
                if not isinstance(provider_specs, list):
                    continue

                kept_specs = [
                    spec
                    for spec in provider_specs
                    if _extract_spack_package_name(spec) not in excluded
                ]
                if kept_specs:
                    providers[provider_name] = kept_specs
                else:
                    del providers[provider_name]

    filtered = safe_dump(data, sort_keys=False)
    if filtered and not filtered.endswith('\n'):
        filtered = f'{filtered}\n'
    return filtered


def _get_yaml_data(
    machine,
    compiler,
    mpi,
    include_e3sm_lapack,
    e3sm_hdf5_netcdf,
    specs,
    yaml_template,
    exclude_packages=None,
):
    """Get the data from the jinja-templated yaml file based on settings"""
    if yaml_template is None:
        template_filename = f'{machine}_{compiler}_{mpi}.yaml'
        path = (
            importlib_resources.files('mache.spack.templates')
            / template_filename
        )
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError as err:
            raise ValueError(
                f'Spack template not available for {compiler} '
                f'and {mpi} on {machine}.'
            ) from err
    else:
        with open(yaml_template) as f:
            template = Template(f.read())

    yaml_data = template.render(
        specs=specs,
        e3sm_lapack=include_e3sm_lapack,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    )
    return _filter_yaml_data(yaml_data, exclude_packages)
