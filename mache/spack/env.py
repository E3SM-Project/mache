import os
import subprocess
import warnings

from mache.machine_info import MachineInfo, discover_machine
from mache.spack.activation import (
    ACTIVATION_MODES,
    capture_activation,
    write_activation_files,
)
from mache.spack.install import render_install_script, write_prologue
from mache.spack.pins import load_pins
from mache.spack.script import get_spack_script
from mache.spack.shared import _get_yaml_data, resolve_e3sm_hdf5_netcdf

MPI_COMPILERS = {
    'gnu': {'mpicc': 'mpicc', 'mpicxx': 'mpicxx', 'mpifc': 'mpif90'},
    'intel': {'mpicc': 'mpicc', 'mpicxx': 'mpicxx', 'mpifc': 'mpif90'},
    'intel-classic': {'mpicc': 'mpicc', 'mpicxx': 'mpicxx', 'mpifc': 'mpif90'},
    'impi': {'mpicc': 'mpiicc', 'mpicxx': 'mpiicpc', 'mpifc': 'mpiifort'},
    'cray': {'mpicc': 'cc', 'mpicxx': 'CC', 'mpifc': 'ftn'},
}


def make_spack_env(
    spack_path,
    env_name,
    spack_specs,
    compiler,
    mpi,
    *,
    machine=None,
    config_file=None,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=None,
    e3sm_hdf5_netcdf=None,
    yaml_template=None,
    exclude_packages=None,
    tmpdir=None,
    spack_mirror=None,
    custom_spack='',
    pins=None,
    activation='captured',
    build_jobs=None,
):
    """
    Check out Spack and the package repositories pinned by this release of
    mache (see ``mache/spack/pins.yaml``) and build a spack environment for
    the given machine, compiler and MPI library.  The environment YAML,
    build script, build prologue, ``spack.lock`` and provenance are written
    to the current directory.

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

    e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

    include_e3sm_hdf5_netcdf : bool, optional
        Deprecated alias for ``e3sm_hdf5_netcdf``.

    yaml_template : str, optional
        A jinja template for a yaml file to be used for the environment instead
        of the mache template.  This allows you to use compilers and other
        modules that differ from E3SM.

    exclude_packages : sequence of str or str, optional
        System-provided Spack packages to opt out of when rendering the
        machine template.  These package entries are removed from the rendered
        YAML so Spack can build them instead.  The aliases
        ``e3sm_hdf5_netcdf`` and ``hdf5_netcdf`` exclude the machine-provided
        HDF5/NetCDF bundle.

    tmpdir : str, optional
        A temporary directory for building spack packages

    spack_mirror : str, optional
        The absolute path to a local spack mirror (e.g. for files a given
        machine isn't allowed to download)

    custom_spack : str, optional
        Spack commands to run at the end of the script after the environment
        has been installed.

    pins : dict or str, optional
        Overrides for the pinned Spack sources, either a mapping in the
        ``pins.yaml`` schema or the path to a YAML file holding one.  Each
        override names a ``tag``, ``commit`` or ``branch`` for one of the
        pinned repositories.

    activation : {'captured', 'dynamic'}, optional
        Whether to capture ``spack env activate`` into ``activate.sh`` and
        ``activate.csh`` in the environment directory after the build, so
        that load scripts can source them instead of running Spack.

    build_jobs : int, optional
        The number of parallel build jobs, passed to ``spack install -j``
    """

    if include_e3sm_hdf5_netcdf is not None:
        warnings.warn(
            'include_e3sm_hdf5_netcdf is deprecated; use e3sm_hdf5_netcdf',
            DeprecationWarning,
            stacklevel=2,
        )

    if e3sm_hdf5_netcdf is not None:
        if include_e3sm_hdf5_netcdf is not None and bool(
            include_e3sm_hdf5_netcdf
        ) != bool(e3sm_hdf5_netcdf):
            raise ValueError(
                'Got conflicting values for e3sm_hdf5_netcdf and '
                'include_e3sm_hdf5_netcdf.'
            )
        e3sm_hdf5_netcdf = bool(e3sm_hdf5_netcdf)
    else:
        e3sm_hdf5_netcdf = bool(include_e3sm_hdf5_netcdf)
    e3sm_hdf5_netcdf, exclude_packages = resolve_e3sm_hdf5_netcdf(
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

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
        e3sm_hdf5_netcdf,
        spack_specs,
        yaml_template,
        exclude_packages=exclude_packages,
    )

    if activation not in ACTIVATION_MODES:
        raise ValueError(
            f'activation must be one of {ACTIVATION_MODES}, got {activation!r}'
        )

    work_dir = os.path.abspath(os.getcwd())
    yaml_filename = os.path.join(work_dir, f'{env_name}.yaml')
    with open(yaml_filename, 'w') as handle:
        handle.write(yaml_data)

    prologue = get_spack_script(
        spack_path,
        env_name,
        compiler,
        mpi,
        'sh',
        machine,
        include_e3sm_lapack,
        load_spack_env=False,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )
    if tmpdir is not None:
        if not os.path.exists(tmpdir):
            os.mkdir(tmpdir)
        prologue = f'{prologue}\nexport TMPDIR={tmpdir}'
    prologue_path = write_prologue(work_dir, env_name, prologue)

    build_file = render_install_script(
        spack_path=spack_path,
        env_name=env_name,
        yaml_path=yaml_filename,
        prologue=prologue,
        pins=load_pins(pins),
        work_dir=work_dir,
        mirror=spack_mirror,
        custom_spack=custom_spack,
        build_jobs=build_jobs,
    )
    build_filename = os.path.join(work_dir, f'build_{env_name}.bash')
    with open(build_filename, 'w') as handle:
        handle.write(build_file)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i bash -l {build_filename}', shell=True)

    if activation == 'captured':
        modifications = capture_activation(
            spack_path=spack_path,
            env_name=env_name,
            prologue_path=prologue_path,
            work_dir=work_dir,
        )
        write_activation_files(
            spack_path=spack_path,
            env_name=env_name,
            modifications=modifications,
        )


def get_modules_env_vars_and_mpi_compilers(
    machine,
    compiler,
    mpi,
    shell,
    include_e3sm_lapack=False,
    include_e3sm_hdf5_netcdf=None,
    *,
    e3sm_hdf5_netcdf=None,
    exclude_packages=None,
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

    e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

    include_e3sm_hdf5_netcdf : bool, optional
        Deprecated alias for ``e3sm_hdf5_netcdf``.

    exclude_packages : sequence of str or str, optional
        System-provided Spack packages to opt out of.  For this function, the
        package bundle that affects shell setup is ``e3sm_hdf5_netcdf`` (or
        ``hdf5_netcdf``), which disables the machine-provided HDF5/NetCDF
        module and environment-variable setup.

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

    if include_e3sm_hdf5_netcdf is not None:
        warnings.warn(
            'include_e3sm_hdf5_netcdf is deprecated; use e3sm_hdf5_netcdf',
            DeprecationWarning,
            stacklevel=2,
        )

    if e3sm_hdf5_netcdf is not None:
        if include_e3sm_hdf5_netcdf is not None and bool(
            include_e3sm_hdf5_netcdf
        ) != bool(e3sm_hdf5_netcdf):
            raise ValueError(
                'Got conflicting values for e3sm_hdf5_netcdf and '
                'include_e3sm_hdf5_netcdf.'
            )
        e3sm_hdf5_netcdf = bool(e3sm_hdf5_netcdf)
    else:
        e3sm_hdf5_netcdf = bool(include_e3sm_hdf5_netcdf)
    e3sm_hdf5_netcdf, exclude_packages = resolve_e3sm_hdf5_netcdf(
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

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

    mod_env_commands = get_spack_script(
        spack_path=None,
        env_name=None,
        compiler=compiler,
        mpi=mpi,
        shell=shell,
        machine=machine,
        load_spack_env=False,
        include_e3sm_lapack=include_e3sm_lapack,
        e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        exclude_packages=exclude_packages,
    )

    mpicc, mpicxx, mpifc = _get_mpi_compilers(
        machine, compiler, mpi, cray_compilers
    )

    return mpicc, mpicxx, mpifc, mod_env_commands


def _get_mpi_compilers(machine, compiler, mpi, cray_compilers):
    """Get a list of compilers from a yaml file"""

    mpi_compiler = None
    # first, get mpi compilers based on compiler
    if compiler in MPI_COMPILERS:
        mpi_compiler = MPI_COMPILERS[compiler]

    # next, get mpi compilers based on mpi (higher priority)
    if mpi in MPI_COMPILERS:
        mpi_compiler = MPI_COMPILERS[mpi]

    # finally, get mpi compilers if this is a cray machine (highest priority)
    if cray_compilers:
        mpi_compiler = MPI_COMPILERS['cray']

    if mpi_compiler is None:
        raise ValueError(
            f"Couldn't figure out MPI compiler wrappers for {machine} "
            f'{compiler} {mpi}'
        )

    return mpi_compiler['mpicc'], mpi_compiler['mpicxx'], mpi_compiler['mpifc']
