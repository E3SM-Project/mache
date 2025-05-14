import re
from collections import defaultdict

from lxml import etree


def extract_machine_config(xml_file, machine, compiler, mpilib):
    """
    Extract the machine configuration from the XML file.

    Parameters
    ----------
    xml_file : str
        Path to the XML file.
    machine : str
        Machine name.
    compiler : str
        Compiler name.
    mpilib : str
        MPI library name.

    Returns
    -------
    etree.Element or None
        The XML element of the machine configuration if found, otherwise None.
    """
    tree = etree.parse(xml_file)
    root = tree.getroot()

    for mach in root.findall('machine'):
        if mach.get('MACH') == machine:
            for mod_sys in mach.findall('module_system'):
                for mod in mod_sys.findall('modules'):
                    if not (
                        re.match(mod.get('compiler', '.*'), compiler)
                        and re.match(mod.get('mpilib', '.*'), mpilib)
                        and re.match(mod.get('DEBUG', '.*'), 'FALSE')
                    ):
                        mod_sys.remove(mod)
            for env_vars in mach.findall('environment_variables'):
                if not (
                    re.match(env_vars.get('compiler', '.*'), compiler)
                    and re.match(env_vars.get('mpilib', '.*'), mpilib)
                    and re.match(env_vars.get('DEBUG', '.*'), 'FALSE')
                ):
                    mach.remove(env_vars)
            return mach
    return None


def config_to_shell_script(config, shell_type):
    """
    Convert the machine configuration to a shell script.

    Parameters
    ----------
    config : etree.Element
        The XML element of the machine configuration.
    shell_type : str
        The type of shell script to generate ('sh' or 'csh').

    Returns
    -------
    str
        The shell script as a string.
    """
    script_lines = []

    # TODO: possibly replace \: with :
    init_path = None
    for init in config.findall('.//module_system/init_path'):
        if init.get('lang') == shell_type:
            init_path = init.text
            break

    if init_path is not None:
        init_path = init_path.replace(';', '\n')
        script_lines.append(f'source {init_path}')
        script_lines.append('')

    module_commands = defaultdict(list)
    e3sm_hdf5_netcdf_modules = defaultdict(list)
    for module in config.findall('.//module_system/modules'):
        for command in module.findall('command'):
            name = command.get('name')
            value = command.text
            if value:
                if 'command' != 'unload' and 'python' in value:
                    # we don't want to load E3SM's python module
                    continue
                elif 'command' != 'unload' and re.search(
                    r'hdf5|netcdf', value, re.IGNORECASE
                ):
                    # we want to remove hdf5 and netcdf in all cases
                    e3sm_hdf5_netcdf_modules[name].append(value)
                else:
                    module_commands[name].append(value)
            elif name not in module_commands:
                module_commands[name] = []

    script_lines.extend(
        _convert_module_commands_to_script_lines(module_commands, shell_type)
    )
    script_lines.append('')

    if e3sm_hdf5_netcdf_modules:
        script_lines.append('{% if e3sm_hdf5_netcdf %}')
        script_lines.extend(
            _convert_module_commands_to_script_lines(
                e3sm_hdf5_netcdf_modules, shell_type
            )
        )
        script_lines.append('{% endif %}')
        script_lines.append('')

    script_lines.extend(_convert_env_vars_to_script_lines(config, shell_type))

    script_lines.append('')

    return '\n'.join(script_lines)


def extract_spack_from_config_machines(
    machine, compiler, mpilib, shell, output
):
    """
    Extract machine configuration from XML and write it to a shell script.

    Parameters
    ----------
    machine : str
        Machine name.
    compiler : str
        Compiler name.
    mpilib : str
        MPI library name.
    shell : str
        Shell script type ('sh' or 'csh').
    output : str
        Output file to write the shell script.
    """
    config_filename = 'mache/cime_machine_config/config_machines.xml'

    config = extract_machine_config(config_filename, machine, compiler, mpilib)
    if config is None:
        raise ValueError(
            f'No configuration found for machine={machine}, '
            f'compiler={compiler}, mpilib={mpilib}'
        )

    script = config_to_shell_script(config, shell)
    with open(output, 'w') as f:
        f.write(script)


def _convert_module_commands_to_script_lines(module_commands, shell_type):
    """
    Convert module commands to script lines.

    Parameters
    ----------
    module_commands : dict
        Dictionary of module commands.
    shell_type : str
        The type of shell script to generate ('sh' or 'csh').

    Returns
    -------
    list
        List of script lines.
    """
    script_lines = []
    for i, (name, values) in enumerate(module_commands.items()):
        if name == 'unload':
            name = 'rm'
            # the module rm commands produce distracting output so we
            # silence them
            suffix = ' &> /dev/null'
        else:
            suffix = ''
        if values:
            # same code regardless of shell
            if name == 'switch':
                # switch commands need to be handled one at a time
                for value in values:
                    script_lines.append(f'module {name} {value}')
            else:
                script_lines.append(f'module {name} \\')
                for value in values:
                    script_lines.append(f'    {value} \\')
                script_lines[-1] = script_lines[-1].rstrip(' \\') + suffix
        else:
            script_lines.append(f'module {name}{suffix}')
        if i < len(module_commands) - 1:
            script_lines.append('')
    return script_lines


def _convert_env_vars_to_script_lines(config, shell_type):
    """
    Convert environment variables to script lines.

    Parameters
    ----------
    config : etree.Element
        The XML element of the machine configuration.
    shell_type : str
        The type of shell script to generate ('sh' or 'csh').

    Returns
    -------
    list
        List of script lines.
    """
    script_lines = []
    e3sm_hdf5_netcdf_env_vars = []
    for env_var in config.findall('.//environment_variables/env'):
        name = env_var.get('name')
        value = env_var.text
        if value is None:
            value = ''
        if '$SHELL' in value:
            # at least for now, these $SHELL environment variables are
            # E3SM-specific so we'll leave them out
            continue
        if 'perl' in value:
            # we don't want to add E3SM's perl path
            continue
        if name.startswith('OMP_'):
            # OpenMP environment variables cause trouble with ESMF
            continue

        value = re.sub(r'\$ENV{([^}]+)}', r'${\1}', value)
        if 'NETCDF' in name and 'PATH' in name:
            e3sm_hdf5_netcdf_env_vars.append((name, value))
            if name == 'NETCDF_PATH':
                # also set the NETCDF_C_PATH and NETCDF_FORTRAN_PATH, needed
                # by MPAS standalone components
                e3sm_hdf5_netcdf_env_vars.append(('NETCDF_C_PATH', value))
                e3sm_hdf5_netcdf_env_vars.append(
                    ('NETCDF_FORTRAN_PATH', value)
                )
        else:
            if shell_type == 'sh':
                script_lines.append(f'export {name}="{value}"')
            elif shell_type == 'csh':
                script_lines.append(f'setenv {name} "{value}"')

    script_lines.append('')

    if e3sm_hdf5_netcdf_env_vars:
        script_lines.append('{% if e3sm_hdf5_netcdf %}')
        for name, value in e3sm_hdf5_netcdf_env_vars:
            if shell_type == 'sh':
                script_lines.append(f'export {name}="{value}"')
            elif shell_type == 'csh':
                script_lines.append(f'setenv {name} "{value}"')
        script_lines.append('{% endif %}')

    return script_lines
