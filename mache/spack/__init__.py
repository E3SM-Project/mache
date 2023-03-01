import os
import subprocess
import sys
from typing import TYPE_CHECKING

from jinja2 import Template

if TYPE_CHECKING or sys.version_info > (3, 8, 0):
    from importlib import resources as importlib_resources
else:
    # python <= 3.8
    import importlib_resources

import yaml

from mache.machine_info import MachineInfo, discover_machine
from mache.version import __version__


def make_spack_env(spack_path, env_name, spack_specs, compiler, mpi,
                   machine=None, include_e3sm_lapack=False,
                   include_e3sm_hdf5_netcdf=False, yaml_template=None,
                   tmpdir=None, spack_mirror=None):
    """
    Clone the ``spack_for_mache_{{version}}`` branch from
    `E3SM's spack clone <https://github.com/E3SM-Project/spack>`_ and build
    a spack environment for the given machine, compiler and MPI library.

    Parameters
    ----------
    spack_path : str
        The base path where spack has been (or will be) cloned

    env_name : str
        The name of the spack environment to be created or recreated

    spack_specs : list of str
        A list of spack package specs to include in the environment

    compiler : str
        One of the E3SM supported compilers for the ``machine``

    mpi : str
        One of the E3SM supported MPI libraries for the given ``compiler`` and
        ``machine``

    machine : str, optional
        The name of an E3SM supported machine.  If none is given, the machine
        will be detected automatically via the host name.

    include_e3sm_lapack : bool, optional
        Whether to include the same lapack (typically from MKL) as used in E3SM

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

    yaml_template : str, optional
        A jinja template for a yaml file to be used for the environment instead
        of the mache template.  This allows you to use compilers and other
        modules that differ from E3SM.

    tmpdir : str, optional
        A temporary directory for building spack packages

    spack_mirror : str, optional
        The absolute path to a local spack mirror (e.g. for files a given
        machine isn't allowed to download)
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    section = config['spack']

    with_modules = (section.getboolean('modules_before') or
                    section.getboolean('modules_after'))

    # add the package specs to the appropriate template
    specs = ''.join([f'  - {spec}\n' for spec in spack_specs])

    yaml_data = _get_yaml_data(machine, compiler, mpi, include_e3sm_lapack,
                               include_e3sm_hdf5_netcdf, specs, yaml_template)

    yaml_filename = os.path.abspath(f'{env_name}.yaml')
    with open(yaml_filename, 'w') as handle:
        handle.write(yaml_data)

    if with_modules:
        mods = _get_modules(yaml_data)
        modules = f'module purge\n' \
                  f'{mods}'
    else:
        modules = ''

    for shell_filename in [f'{machine}.sh',
                           f'{machine}_{compiler}_{mpi}.sh']:
        # load modules, etc. for this machine
        path = \
            importlib_resources.files('mache.spack') / shell_filename
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        bash_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)

        modules = f'{modules}\n{bash_script}'

    path = \
        importlib_resources.files('mache.spack') / 'build_spack_env.template'
    with open(str(path)) as fp:
        template = Template(fp.read())
    if tmpdir is not None:
        modules = f'{modules}\n' \
                  f'export TMPDIR={tmpdir}'

    template_args = dict(modules=modules, version=__version__,
                         spack_path=spack_path, env_name=env_name,
                         yaml_filename=yaml_filename)

    if spack_mirror is not None:
        template_args['spack_mirror'] = spack_mirror

    build_file = template.render(**template_args)
    build_filename = f'build_{env_name}.bash'
    with open(build_filename, 'w') as handle:
        handle.write(build_file)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i bash -l {build_filename}', shell=True)


def get_spack_script(spack_path, env_name, compiler, mpi, shell, machine=None,
                     include_e3sm_lapack=False, include_e3sm_hdf5_netcdf=False,
                     yaml_template=None):
    """
    Build a snippet of a load script for the given spack environment

    Parameters
    ----------
    spack_path : str
        The base path where spack has been (or will be) cloned

    env_name : str
        The name of the spack environment to be created or recreated

    compiler : str
        One of the E3SM supported compilers for the ``machine``

    mpi : str
        One of the E3SM supported MPI libraries for the given ``compiler`` and
        ``machine``

    shell : {'sh', 'csh'}
        Which shell the script is for

    machine : str, optional
        The name of an E3SM supported machine.  If none is given, the machine
        will be detected automatically via the host name.

    include_e3sm_lapack : bool, optional
        Whether to include the same lapack (typically from MKL) as used in E3SM

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

    yaml_template : str, optional
        A jinja template for a yaml file to be used for the environment instead
        of the mache template.  This allows you to use compilers and other
        modules that differ from E3SM.

    Returns
    -------
    load_script : str
        A snippet of a shell script that will load the given spack
        environment and add any additional steps required for using the
        environment such as setting environment variables or loading modules
        not handled by the spack environment directly
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    section = config['spack']

    modules_before = section.getboolean('modules_before')
    modules_after = section.getboolean('modules_after')

    yaml_data = _get_yaml_data(
        machine, compiler, mpi, include_e3sm_lapack, include_e3sm_hdf5_netcdf,
        specs='', yaml_template=yaml_template)

    if modules_before or modules_after:
        load_script = 'module purge\n'
        if modules_before:
            mods = _get_modules(yaml_data)
            load_script = f'{load_script}\n{mods}\n'
    else:
        load_script = ''

    load_script = f'{load_script}' \
                  f'source {spack_path}/share/spack/setup-env.{shell}\n' \
                  f'spack env activate {env_name}'

    for shell_filename in [f'{machine}.{shell}',
                           f'{machine}_{compiler}_{mpi}.{shell}']:
        # load modules, etc. for this machine
        path = \
            importlib_resources.files('mache.spack') / shell_filename
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        shell_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)
        load_script = f'{load_script}\n{shell_script}'

    if modules_after:
        mods = _get_modules(yaml_data)
        load_script = f'{load_script}\n{mods}'

    return load_script


def get_modules_env_vars_and_mpi_compilers(machine, compiler, mpi, shell,
                                           include_e3sm_lapack=False,
                                           include_e3sm_hdf5_netcdf=False,
                                           yaml_template=None):
    """
    Get the non-spack modules, environment variables and compiler names for a
    given machine, compiler and MPI library.

    Parameters
    ----------
    compiler : str
        One of the E3SM supported compilers for the ``machine``

    mpi : str
        One of the E3SM supported MPI libraries for the given ``compiler`` and
        ``machine``

    machine : str, optional
        The name of an E3SM supported machine.  If none is given, the machine
        will be detected automatically via the host name.

    shell : {'sh', 'csh'}
        Which shell the script is for

    include_e3sm_lapack : bool, optional
        Whether to include the same lapack (typically from MKL) as used in E3SM

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

    yaml_template : str, optional
        A jinja template for a yaml file to be used for the environment instead
        of the mache template.  This allows you to use compilers and other
        modules that differ from E3SM.

    Returns
    -------
    mpicc : str
        The MPI c compiler for this machine

    mpicxx : str
        The MPI c++ compiler for this machine

    mpifc : str
        The MPI Fortran compiler for this machine

    mod_env_commands : str
        Modules and environment variables needed to set up the compilers, MPI
        libraries and other dependencies like NetCDF and PNetCDF
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

        with_modules = (section.getboolean('modules_before') or
                        section.getboolean('modules_after'))
        if config.has_option('spack', 'cray_compilers'):
            cray_compilers = section.getboolean('cray_compilers')
    else:
        with_modules = False

    mod_env_commands = 'module purge\n'
    if with_modules:
        yaml_data = _get_yaml_data(
            machine, compiler, mpi, include_e3sm_lapack,
            include_e3sm_hdf5_netcdf, specs='',
            yaml_template=yaml_template)
        mods = _get_modules(yaml_data)
        mod_env_commands = f'{mod_env_commands}\n{mods}\n'

    for shell_filename in [f'{machine}.{shell}',
                           f'{machine}_{compiler}_{mpi}.{shell}']:
        path = \
            importlib_resources.files('mache.spack') / shell_filename
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        shell_script = template.render(
            e3sm_lapack=include_e3sm_lapack,
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)
        mod_env_commands = f'{mod_env_commands}\n{shell_script}'

    mpicc, mpicxx, mpifc = _get_mpi_compilers(machine, compiler, mpi,
                                              cray_compilers)

    return mpicc, mpicxx, mpifc, mod_env_commands


def _get_yaml_data(machine, compiler, mpi, include_e3sm_lapack,
                   include_e3sm_hdf5_netcdf, specs, yaml_template):
    """ Get the data from the jinja-templated yaml file based on settings """
    if yaml_template is None:
        template_filename = f'{machine}_{compiler}_{mpi}.yaml'
        path = \
            importlib_resources.files('mache.spack') / template_filename
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError:
            raise ValueError(f'Spack template not available for {compiler} '
                             f'and {mpi} on {machine}.')
    else:
        with open(yaml_template) as f:
            template = Template(f.read())

    yaml_data = template.render(specs=specs,
                                e3sm_lapack=include_e3sm_lapack,
                                e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)
    return yaml_data


def _get_modules(yaml_string):
    """ Get a list of modules from a yaml file """
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
    """ Get a list of compilers from a yaml file """

    mpi_compilers = {'gnu': {'mpicc': 'mpicc',
                             'mpicxx': 'mpicxx',
                             'mpifc': 'mpif90'},
                     'intel': {'mpicc': 'mpicc',
                               'mpicxx': 'mpicxx',
                               'mpifc': 'mpif90'},
                     'impi': {'mpicc': 'mpiicc',
                              'mpicxx': 'mpiicpc',
                              'mpifc': 'mpiifort'},
                     'cray': {'mpicc': 'cc',
                              'mpicxx': 'CC',
                              'mpifc': 'ftn'}}

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
        raise ValueError(f"Couldn't figure out MPI compilers for {machine} "
                         f"{compiler} {mpi}")

    return mpi_compiler['mpicc'], mpi_compiler['mpicxx'], mpi_compiler['mpifc']
