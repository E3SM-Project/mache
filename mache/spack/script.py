from importlib import resources as importlib_resources

from jinja2 import Template

from mache.machine_info import MachineInfo, discover_machine
from mache.spack.shared import _get_modules, _get_yaml_data


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
