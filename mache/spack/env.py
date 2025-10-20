import os
import subprocess
from importlib import resources as importlib_resources

from jinja2 import Template

from mache.machine_info import MachineInfo, discover_machine
from mache.spack.script import get_spack_script
from mache.spack.shared import _get_yaml_data
from mache.version import __version__


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

    config_file : str, optional
        The name of a config file to load config options from.

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

    custom_spack : str, optional
        Spack commands to run at the end of the script after the environment
        has been installed.
    """

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    machine_info = MachineInfo(machine)

    config = machine_info.config
    if config_file is not None:
        config.read(config_file)

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

    modules = ''

    bash_script = get_spack_script(
        spack_path,
        env_name,
        compiler,
        mpi,
        'sh',
        machine,
        None,
        include_e3sm_lapack,
        include_e3sm_hdf5_netcdf,
    )
    modules = f'{modules}\n{bash_script}'

    path = (
        importlib_resources.files('mache.spack.templates')
        / 'build_spack_env.template'
    )
    with open(str(path)) as fp:
        template = Template(fp.read())
    if tmpdir is not None:
        if not os.path.exists(tmpdir):
            os.mkdir(tmpdir)

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


def get_modules_env_vars_and_mpi_compilers(
    machine,
    compiler,
    mpi,
    shell,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=False,
):
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

        if config.has_option('spack', 'cray_compilers'):
            cray_compilers = section.getboolean('cray_compilers')

    mod_env_commands = 'module purge\n'

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
