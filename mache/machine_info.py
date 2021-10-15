from lxml import etree
from importlib.resources import path
import configparser
import os
import pwd

from mache.discover import discover_machine


class MachineInfo:
    """
    An object containing information about an E3SM supported machine

    Attributes
    ----------
    machine : str
        The name of an E3SM supported machine

    config : configparser.ConfigParser
        Config options for this machine

    e3sm_supported : bool
        Whether this machine supports running E3SM itself, and therefore has
        a list of compilers, MPI libraries, and the modules needed to load them

    compilers : list
        A list of compilers for this machine if ``e3sm_supported == True``

    mpilibs : list
        A list of MPI libraries for this machine if ``e3sm_supported == True``

    os : str
        The machine's operating system if ``e3sm_supported == True``

    e3sm_unified_mpi : {'nompi', 'system', None}
        Which MPI type is included in the E3SM-Unified environment (if one is
        loaded)

    e3sm_unified_base : str
        The base path where E3SM-Unified and its activation scripts are
        installed if ``e3sm_unified`` is not ``None``

    e3sm_unified_activation : str
        The activation script used to activate E3SM-Unified if ``e3sm_unified``
        is not ``None``

    diagnostics_base : str
        The base directory for diagnostics data

    web_portal_base : str
        The base directory for the web portal

    web_portal_url : str
        The base URL for the web portal

    username : str
        The name of the current user, for use in web-portal directories. This
        value is also added to the ``web_portal`` and ``username`` option of
        the ``config`` attribute.
    """

    def __init__(self, machine=None):
        """
        Create an object with information about the E3SM supported machine

        Parameters
        ----------
        machine : str, optional
            The name of an E3SM supported machine.  By default, the machine
            will be inferred from the host name
        """
        if machine is None:
            machine = discover_machine()
            if machine is None:
                raise ValueError('Unable to discover machine form host name')
        self.machine = machine

        self.config = self._get_config()

        self.e3sm_supported = False
        self.compilers = None
        self.mpilibs = None
        self.os = None
        self._parse_compilers_and_mpi()

        self.e3sm_unified_mpi = None
        self.e3sm_unified_base = None
        self.e3sm_unified_activation = None
        self._detect_e3sm_unified()

        self.diagnostics_base = None
        self._get_diagnostics_info()

        self.web_portal_base = None
        self.web_portal_url = None

        self.username = pwd.getpwuid(os.getuid()).pw_name
        if not self.config.has_section('web_portal'):
            self.config.add_section('web_portal')
        self.config.set('web_portal', 'username', self.username)

    def __str__(self):
        """
        Convert the info to a format that is good for printing

        Returns
        -------
        info : str
            The contents as a string for printing to the terminal
        """

        info = f'Machine: {self.machine}\n' \
               f'  E3SM Supported Machine: {self.e3sm_supported}'

        if self.e3sm_supported:
            info = f'{info}\n' \
                   f'  Compilers: {", ".join(self.compilers)}\n' \
                   f'  MPI libraries: {", ".join(self.mpilibs)}\n' \
                   f'  OS: {self.os}'

        info = f'{info}\n'

        print_unified = (self.e3sm_unified_activation is not None or
                         self.e3sm_unified_base is not None or
                         self.e3sm_unified_mpi is not None)
        if print_unified:
            info = f'{info}\n' \
                   f'E3SM-Unified:'

            if self.e3sm_unified_activation is None:
                info = f'{info}\n' \
                       f'  E3SM-Unified is not currently loaded'
            else:
                info = f'{info}\n' \
                       f'  Activation: {self.e3sm_unified_activation}'
            if self.e3sm_unified_base is not None:
                info = f'{info}\n' \
                       f'  Base path: {self.e3sm_unified_base}'
            if self.e3sm_unified_mpi is not None:
                info = f'{info}\n' \
                       f'  MPI type: {self.e3sm_unified_mpi}'
            info = f'{info}\n'

        print_diags = self.diagnostics_base is not None
        if print_diags:
            info = f'{info}\n' \
                   f'Diagnostics:'

            if self.diagnostics_base is not None:
                info = f'{info}\n' \
                       f'  Base path: {self.diagnostics_base}'
            info = f'{info}\n'

        info = f'{info}\n' \
               f'Config options:'
        for section in self.config.sections():
            info = f'{info}\n' \
                   f'  [{section}]'
            for key, value in self.config.items(section):
                info = f'{info}\n' \
                       f'    {key} = {value}'
            info = f'{info}\n'
        return info

    def get_modules_and_mpi_compilers(self, compiler, mpilib, debug=False,
                                      smp_present=False):
        """
        Get the the modules and MPI compiler commands for a given compiler and
        MPI library

        Parameters
        ----------
        compiler : str
            One of the compilers for this machine, given in the ``compilers``
            attribute

        mpilib : str
            One of the MPI libraries for this machine, , given in the
            ``mpilibs`` attribute

        debug : bool, optional
            Whether code will be compiled in debug mode

        smp_present : bool, optional
            Whether code will be compiled with OpenMP threading

        Returns
        -------
        mpicc : str
            The MPI c compiler for this machine

        mpicxx : str
            The MPI c++ compiler for this machine

        mpifc : str
            The MPI Fortran compiler for this machine

        mod_commands : str
            Modules to load to set up the compilers, MPI libraries and other
            dependencies like NetCDF and PNetCDF

        env_vars : dict
            A dictionary of environment variables that should be set for the
            given compiler and MPI library
        """

        machine = self.machine
        if not self.e3sm_supported:
            raise ValueError(f'{machine} does not appear to be an E3SM '
                             f'supported machine')

        if compiler not in self.compilers:
            raise ValueError(f'{compiler} does not appear to be one of the '
                             f'compilers for this machine: {self.compilers}')

        if mpilib not in self.mpilibs:
            raise ValueError(f'{mpilib} does not appear to be one of the MPI'
                             f'libraries for this machine: {self.mpilibs}')

        with path('mache.cime_machine_config',
                  'config_machines.xml') as xml_path:
            root = etree.parse(str(xml_path))

            machines = next(root.iter('config_machines'))

            mach = None
            for mach in machines:
                if mach.tag == 'machine' and mach.attrib['MACH'] == machine:
                    break

            if mach is None:
                raise ValueError(f'{machine} does not appear to be an E3SM '
                                 f'supported machine')

            mod_commands = []
            modules = next(mach.iter('module_system'))
            for module in modules:
                if module.tag == 'modules':
                    include = True
                    if 'compiler' in module.attrib and \
                            module.attrib['compiler'] != compiler:
                        include = False
                    if 'mpilib' in module.attrib and \
                            module.attrib['mpilib'] != mpilib and \
                            module.attrib['mpilib'] != '!mpi-serial':
                        include = False
                    if include:
                        for command in module:
                            if command.tag == 'command':
                                cmd = command.attrib['name']
                                text = f'module {cmd}'
                                if command.text is not None:
                                    text = f'{text} {command.text}'
                                mod_commands.append(text)

            env_vars = dict()
            for vars in mach:
                if vars.tag != 'environment_variables':
                    continue
                if 'compiler' in vars.attrib and \
                        vars.attrib['compiler'] != compiler:
                    continue
                if 'mpilib' in vars.attrib and \
                        vars.attrib['mpilib'] != mpilib:
                    continue
                if 'DEBUG' in vars.attrib:
                    var_debug = vars.attrib['DEBUG'] == 'TRUE'
                    if var_debug != debug:
                        continue

                if 'SMP_PRESENT' in vars.attrib:
                    var_smp_present = vars.attrib['SMP_PRESENT'] == 'TRUE'
                    if var_smp_present != smp_present:
                        continue

                for var in vars:
                    if var.tag != 'env':
                        continue
                    var_name = var.attrib['name']
                    value = var.text
                    # go from the XML syntax to bash variable syntax
                    value = value.replace('$ENV{', '${')

                    env_vars[var_name] = value

        with path('mache.cime_machine_config',
                  'config_compilers.xml') as xml_path:
            root = etree.parse(str(xml_path))

            compilers = next(root.iter('config_compilers'))

            mpicc = None
            mpifc = None
            mpicxx = None
            for comp in compilers:
                if comp.tag != 'compiler':
                    continue
                if 'COMPILER' in comp.attrib and \
                        comp.attrib['COMPILER'] != compiler:
                    continue
                if 'OS' in comp.attrib and \
                        comp.attrib['OS'] != self.os:
                    continue
                if 'MACH' in comp.attrib and comp.attrib['MACH'] != machine:
                    continue

                # okay, this is either a "generic" compiler section or one for
                # this machine

                for child in comp:
                    if 'MPILIB' in child.attrib:
                        mpi = child.attrib['MPILIB']
                        if mpi[0] == '!':
                            mpi_match = mpi[1:] != mpilib
                        else:
                            mpi_match = mpi == mpilib
                    else:
                        mpi_match = True

                    if not mpi_match:
                        continue

                    if child.tag == 'MPICC':
                        mpicc = child.text.strip()
                    elif child.tag == 'MPICXX':
                        mpicxx = child.text.strip()
                    elif child.tag == 'MPIFC':
                        mpifc = child.text.strip()

        return mpicc, mpicxx, mpifc, mod_commands, env_vars

    def get_account_defaults(self):
        """
        Get default account, partition and quality of service (QOS) for
        this machine.

        Returns
        -------
        account : str
            The E3SM account on the machine

        partition : str
            The default partition on the machine, or ``None`` if no partition
            should be specified

        configuration : str
            The default configuration on the machine, or ``None`` if no
            configuration should be specified

        qos : str
            The default quality of service on the machine, or ``None`` if no
            QOS should be specified
        """
        config = self.config
        if config.has_option('parallel', 'account'):
            account = config.get('parallel', 'account')
        else:
            account = None

        if config.has_option('parallel', 'partitions'):
            partition = config.get('parallel', 'partitions')
            # take the first entry
            partition = partition.split(',')[0].strip()
        else:
            partition = None

        if config.has_option('parallel', 'configurations'):
            configuration = config.get('parallel', 'configurations')
            # take the first entry
            configuration = configuration.split(',')[0].strip()
        else:
            configuration = None

        if config.has_option('parallel', 'qos'):
            qos = config.get('parallel', 'qos')
            # take the first entry
            qos = qos.split(',')[0].strip()
        else:
            qos = None

        return account, partition, configuration, qos

    def _get_config(self):
        """ get a parser for config options """

        config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation())

        machine = self.machine
        try:
            with path('mache.machines', f'{machine}.cfg') as cfg_path:
                config.read(cfg_path)
        except FileNotFoundError:
            # this isn't a known machine so use the default
            with path('mache.machines', 'default.cfg') as cfg_path:
                config.read(cfg_path)

        return config

    def _parse_compilers_and_mpi(self):
        """ Parse the compilers and mpi modules from XML config files """
        machine = self.machine

        with path('mache.cime_machine_config',
                  'config_machines.xml') as xml_path:
            root = etree.parse(str(xml_path))

            machines = next(root.iter('config_machines'))

            mach = None
            found = False
            for mach in machines:
                if mach.tag == 'machine' and mach.attrib['MACH'] == machine:
                    found = True
                    break

            if not found:
                # this is not an E3SM supported machine, so we're done
                self.e3sm_supported = False
                return

            self.e3sm_supported = True
            compilers = None
            for child in mach:
                if child.tag == 'COMPILERS':
                    compilers = child.text.split(',')
                    break

            self.compilers = compilers

            mpilibs = None
            for child in mach:
                if child.tag == 'MPILIBS':
                    mpilibs = child.text.split(',')
                    break

            self.mpilibs = mpilibs

            machine_os = None
            for child in mach:
                if child.tag == 'OS':
                    machine_os = child.text
                    break

            self.os = machine_os

    def _detect_e3sm_unified(self):
        """ Read E3SM-Unified base path and detect whether it is running """
        config = self.config

        if config is not None and \
                config.has_option('e3sm_unified', 'base_path'):
            self.e3sm_unified_base = config.get('e3sm_unified', 'base_path')

        if 'E3SMU_SCRIPT' in os.environ:
            self.e3sm_unified_activation = os.environ['E3SMU_SCRIPT']

        if 'E3SMU_MPI' in os.environ:
            self.e3sm_unified_mpi = os.environ['E3SMU_MPI'].lower()

    def _get_diagnostics_info(self):
        """ Get config options related to diagnostics data """

        config = self.config

        if config is not None and \
                config.has_option('diagnostics', 'base_path'):
            self.diagnostics_base = config.get('diagnostics', 'base_path')
