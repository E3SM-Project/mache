import os as os
import subprocess as subprocess
from importlib import resources as importlib_resources

import yaml as yaml
from jinja2 import Template as Template

from mache.machine_info import (
    MachineInfo as MachineInfo,
)
from mache.machine_info import (
    discover_machine as discover_machine,
)
from mache.spack.config_machines import (
    config_to_shell_script as config_to_shell_script,
)
from mache.spack.config_machines import (
    extract_machine_config as extract_machine_config,
)
from mache.spack.config_machines import (
    extract_spack_from_config_machines as extract_spack_from_config_machines,
)
from mache.spack.list import (
    list_machine_compiler_mpilib as list_machine_compiler_mpilib,
)
from mache.version import __version__ as __version__


def make_spack_env(
    spack_path,
    env_name,
    spack_specs,
    compiler,
    mpi,
    machine=None,
    config_file=None,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=False,
    yaml_template=None,
    tmpdir=None,
    spack_mirror=None,
    custom_spack='',
):
    """
    Build a Spack environment for a given machine, compiler, and MPI library.

    This function automates the creation of a Spack environment with the
    specified packages and configuration, including support for
    machine-specific modules and environment variables.

    Parameters
    ----------
    spack_path : str
        Path to the Spack clone to use.

    env_name : str
        Name for the Spack environment.

    spack_specs : list of str
        List of Spack package specs to include in the environment.

    compiler : str
        Compiler name.

    mpi : str
        MPI library name.

    machine : str, optional
        Machine name (auto-detected if not provided).

    config_file : str, optional
        Path to a machine config file.

    include_e3sm_lapack : bool, optional
        Whether to include E3SM-specific LAPACK.

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include E3SM-specific HDF5/NetCDF packages.

    yaml_template : str, optional
        Path to a custom Jinja2 YAML template.

    tmpdir : str, optional
        Temporary directory for builds.

    spack_mirror : str, optional
        Path to a local Spack mirror.

    custom_spack : str, optional
        Additional Spack commands to run after environment creation.

    Behavior
    --------
    - Writes a YAML file describing the environment.
    - Generates and runs a shell script to create the Spack environment.
    - Loads required modules and sets up environment variables as needed.
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    if config_file is not None:
        config.read(config_file)

    section = config['spack']

    with_modules = section.getboolean('modules_before') or section.getboolean(
        'modules_after'
    )

    yaml_data = _get_yaml_data(
        machine,
        compiler,
        mpi,
        include_e3sm_lapack,
        include_e3sm_hdf5_netcdf,
        spack_specs,
        yaml_template,
    )

    yaml_filename = os.path.abspath(f'{env_name}.yaml')
    with open(yaml_filename, 'w') as handle:
        handle.write(yaml_data)

    if with_modules:
        mods = _get_modules(yaml_data)
        modules = f'module purge\n{mods}'
    else:
        modules = ''

    for shell_filename in [f'{machine}.sh', f'{machine}_{compiler}_{mpi}.sh']:
        # load modules, etc. for this machine
        path = (
            importlib_resources.files('mache.spack.templates') / shell_filename
        )
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        bash_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf,
        )

        modules = f'{modules}\n{bash_script}'

    path = (
        importlib_resources.files('mache.spack.templates')
        / 'build_spack_env.template'
    )
    with open(str(path)) as fp:
        template = Template(fp.read())
    if tmpdir is not None:
        modules = f'{modules}\nexport TMPDIR={tmpdir}'

    template_args = dict(
        modules=modules,
        version=__version__,
        spack_path=spack_path,
        env_name=env_name,
        yaml_filename=yaml_filename,
        custom_spack=custom_spack,
    )

    if spack_mirror is not None:
        template_args['spack_mirror'] = spack_mirror

    build_file = template.render(**template_args)
    build_filename = f'build_{env_name}.bash'
    with open(build_filename, 'w') as handle:
        handle.write(build_file)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i bash -l {build_filename}', shell=True)


def get_spack_script(
    spack_path,
    env_name,
    compiler,
    mpi,
    shell,
    machine=None,
    config_file=None,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=False,
    yaml_template=None,
):
    """
    Generate a shell script snippet to activate a Spack environment.

    This function returns a string containing shell commands to load required
    modules, source the Spack setup script, activate the specified Spack
    environment, and set any additional environment variables.

    Parameters
    ----------
    spack_path : str
        Path to the Spack clone to use.

    env_name : str
        Name of the Spack environment.

    compiler : str
        Compiler name.

    mpi : str
        MPI library name.

    shell : {'sh', 'csh'}
        Shell type for the script.

    machine : str, optional
        Machine name (auto-detected if not provided).

    config_file : str, optional
        Path to a machine config file.

    include_e3sm_lapack : bool, optional
        Whether to include E3SM-specific LAPACK.

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include E3SM-specific HDF5/NetCDF packages.

    yaml_template : str, optional
        Path to a custom Jinja2 YAML template.

    Returns
    -------
    load_script : str
        Shell commands to load modules, activate the Spack environment, and
        set up the environment for use.
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    if config_file is not None:
        config.read(config_file)

    section = config['spack']

    modules_before = section.getboolean('modules_before')
    modules_after = section.getboolean('modules_after')

    yaml_data = _get_yaml_data(
        machine,
        compiler,
        mpi,
        include_e3sm_lapack,
        include_e3sm_hdf5_netcdf,
        specs=[],
        yaml_template=yaml_template,
    )

    if modules_before or modules_after:
        load_script = 'module purge\n'
        if modules_before:
            mods = _get_modules(yaml_data)
            load_script = f'{load_script}\n{mods}\n'
    else:
        load_script = ''

    load_script = (
        f'{load_script}'
        f'source {spack_path}/share/spack/setup-env.{shell}\n'
        f'spack env activate {env_name}'
    )

    for shell_filename in [
        f'{machine}.{shell}',
        f'{machine}_{compiler}_{mpi}.{shell}',
    ]:
        # load modules, etc. for this machine
        path = (
            importlib_resources.files('mache.spack.templates') / shell_filename
        )
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        shell_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf,
        )
        load_script = f'{load_script}\n{shell_script}'

    if modules_after:
        mods = _get_modules(yaml_data)
        load_script = f'{load_script}\n{mods}'

    return load_script


def get_modules_env_vars_and_mpi_compilers(
    machine,
    compiler,
    mpi,
    shell,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=False,
    yaml_template=None,
):
    """
    Query modules, environment variables, and MPI compiler wrappers for a given
    machine, compiler, and MPI library.

    This function returns the names of the MPI compiler wrappers and a shell
    snippet to load modules and set environment variables needed for building
    or running MPI-dependent software.

    Parameters
    ----------
    machine : str
        Machine name (auto-detected if not provided).

    compiler : str
        Compiler name.

    mpi : str
        MPI library name.

    shell : {'sh', 'csh'}
        Shell type for the script.

    include_e3sm_lapack : bool, optional
        Whether to include E3SM-specific LAPACK.

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include E3SM-specific HDF5/NetCDF packages.

    yaml_template : str, optional
        Path to a custom Jinja2 YAML template.

    Returns
    -------
    mpicc : str
        Name of the MPI C compiler wrapper.

    mpicxx : str
        Name of the MPI C++ compiler wrapper.

    mpifc : str
        Name of the MPI Fortran compiler wrapper.

    mod_env_commands : str
        Shell commands to load modules and set environment variables.
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    cray_compilers = False
    if config.has_section('spack'):
        section = config['spack']

        with_modules = section.getboolean(
            'modules_before'
        ) or section.getboolean('modules_after')
        if config.has_option('spack', 'cray_compilers'):
            cray_compilers = section.getboolean('cray_compilers')
    else:
        with_modules = False

    mod_env_commands = 'module purge\n'
    if with_modules:
        yaml_data = _get_yaml_data(
            machine,
            compiler,
            mpi,
            include_e3sm_lapack,
            include_e3sm_hdf5_netcdf,
            specs=[],
            yaml_template=yaml_template,
        )
        mods = _get_modules(yaml_data)
        mod_env_commands = f'{mod_env_commands}\n{mods}\n'

    for shell_filename in [
        f'{machine}.{shell}',
        f'{machine}_{compiler}_{mpi}.{shell}',
    ]:
        path = (
            importlib_resources.files('mache.spack.templates') / shell_filename
        )
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        shell_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf,
        )
        mod_env_commands = f'{mod_env_commands}\n{shell_script}'

    mpicc, mpicxx, mpifc = _get_mpi_compilers(
        machine, compiler, mpi, cray_compilers
    )

    return mpicc, mpicxx, mpifc, mod_env_commands


def _get_yaml_data(
    machine,
    compiler,
    mpi,
    include_e3sm_lapack,
    include_e3sm_hdf5_netcdf,
    specs,
    yaml_template,
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
        e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf,
    )
    return yaml_data


def _get_modules(yaml_string):
    """Get a list of modules from a yaml file"""
    yaml_data = yaml.safe_load(yaml_string)
    mods = []
    if 'spack' in yaml_data and 'packages' in yaml_data['spack']:
        package_data = yaml_data['spack']['packages']
        for package in package_data.values():
            if 'externals' in package:
                for item in package['externals']:
                    if 'modules' in item:
                        for mod in item['modules']:
                            mods.append(f'module load {mod}')

    mods_str = '\n'.join(mods)

    return mods_str


def _get_mpi_compilers(machine, compiler, mpi, cray_compilers):
    """Get a list of compilers from a yaml file"""

    mpi_compilers = {
        'gnu': {'mpicc': 'mpicc', 'mpicxx': 'mpicxx', 'mpifc': 'mpif90'},
        'intel': {'mpicc': 'mpicc', 'mpicxx': 'mpicxx', 'mpifc': 'mpif90'},
        'impi': {'mpicc': 'mpiicc', 'mpicxx': 'mpiicpc', 'mpifc': 'mpiifort'},
        'cray': {'mpicc': 'cc', 'mpicxx': 'CC', 'mpifc': 'ftn'},
    }

    mpi_compiler = None
    # first, get mpi compilers based on compiler
    if compiler in mpi_compilers:
        mpi_compiler = mpi_compilers[compiler]

    # next, get mpi compilers based on mpi (higher priority)
    if mpi in mpi_compilers:
        mpi_compiler = mpi_compilers[mpi]

    # finally, get mpi compilers if this is a cray machine (highest priority)
    if cray_compilers:
        mpi_compiler = mpi_compilers['cray']

    if mpi_compiler is None:
        raise ValueError(
            f"Couldn't figure out MPI compilers for {machine} {compiler} {mpi}"
        )

    return mpi_compiler['mpicc'], mpi_compiler['mpicxx'], mpi_compiler['mpifc']
