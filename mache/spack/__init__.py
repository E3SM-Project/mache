import os
import subprocess
from jinja2 import Template
from importlib import resources
import yaml

from mache.machine_info import discover_machine, MachineInfo
from mache.version import __version__


def make_spack_env(spack_path, env_name, spack_specs, compiler, mpi,
                   machine=None, include_e3sm_hdf5_netcdf=False):
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

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM
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

    if not os.path.exists(spack_path):
        # we need to clone the spack repo
        clone = f'git clone -b spack_for_mache_{__version__} ' \
                f'git@github.com:E3SM-Project/spack.git {spack_path}'
    else:
        clone = ''

    # add the package specs to the appropriate template
    specs = ''.join([f'  - {spec}\n' for spec in spack_specs])

    template_filename = f'{machine}_{compiler}_{mpi}.yaml'
    try:
        template = Template(
            resources.read_text('mache.spack', template_filename))
    except FileNotFoundError:
        raise ValueError(f'Spack template not available for {compiler} and '
                         f'{mpi} on {machine}.')
    yaml_file = template.render(specs=specs,
                                e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)
    yaml_filename = os.path.abspath(f'{env_name}.yaml')
    with open(yaml_filename, 'w') as handle:
        handle.write(yaml_file)

    if with_modules:
        mods = _get_modules(machine, compiler, mpi, include_e3sm_hdf5_netcdf)
        modules = f'module purge\n' \
                  f'{mods}'
    else:
        modules = ''

    for shell_filename in [f'{machine}.sh',
                           f'{machine}_{compiler}_{mpi}.sh']:
        # load modules, etc. for this machine
        try:
            template = Template(
                resources.read_text('mache.spack', shell_filename))
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        bash_script = template.render(
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)

        modules = f'{modules}\n{bash_script}'

    template = Template(
        resources.read_text('mache.spack', 'build_spack_env.template'))
    build_file = template.render(modules=modules, clone=clone,
                                 spack_path=spack_path, env_name=env_name,
                                 yaml_filename=yaml_filename)
    build_filename = f'build_{env_name}.bash'
    with open(build_filename, 'w') as handle:
        handle.write(build_file)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i bash -l {build_filename}', shell=True)


def get_spack_script(spack_path, env_name, compiler, mpi, shell, machine=None,
                     include_e3sm_hdf5_netcdf=False):
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

    include_e3sm_hdf5_netcdf : bool, optional
        Whether to include the same hdf5, netcdf-c, netcdf-fortran and pnetcdf
        as used in E3SM

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

    if modules_before or modules_after:
        load_script = 'module purge\n'
        if modules_before:
            mods = _get_modules(machine, compiler, mpi,
                                include_e3sm_hdf5_netcdf)
            load_script = f'{load_script}\n{mods}\n'
    else:
        load_script = ''

    load_script = f'{load_script}' \
                  f'source {spack_path}/share/spack/setup-env.{shell}\n' \
                  f'spack env activate {env_name}'

    for shell_filename in [f'{machine}.{shell}',
                           f'{machine}_{compiler}_{mpi}.{shell}']:
        # load modules, etc. for this machine
        try:
            template = Template(
                resources.read_text('mache.spack', shell_filename))
        except FileNotFoundError:
            # there's nothing to add, which is fine
            continue
        bash_script = template.render(
            e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf)
        load_script = f'{load_script}\n{bash_script}'

    if modules_after:
        mods = _get_modules(machine, compiler, mpi, include_e3sm_hdf5_netcdf)
        load_script = f'{load_script}\n{mods}'

    return load_script


def _get_modules(machine, compiler, mpi, include_e3sm_hdf5_netcdf):
    """ Get a list of modules from a yaml file """
    template_filename = f'{machine}_{compiler}_{mpi}.yaml'
    try:
        template = Template(
            resources.read_text('mache.spack', template_filename))
    except FileNotFoundError:
        raise ValueError(f'Spack template not available for {compiler} and '
                         f'{mpi} on {machine}.')
    yaml_data = yaml.safe_load(
        template.render(specs='', e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf))

    mods = []
    if 'spack' in yaml_data and 'packages' in yaml_data['spack']:
        package_data = yaml_data['spack']['packages']
        for package in package_data.values():
            if 'externals' in package:
                for item in package['externals']:
                    if 'modules' in item:
                        for mod in item['modules']:
                            mods.append(f'module load {mod}')

    mods = '\n'.join(mods)

    return mods
