from lxml import etree
try:
    from importlib import resources as importlib_resources
except ImportError:
    # python<=3.8
    import importlib_resources
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

    def __init__(self, machine=None, quiet=False):
        """
        Create an object with information about the E3SM supported machine

        Parameters
        ----------
        machine : str, optional
            The name of an E3SM supported machine.  By default, the machine
            will be inferred from the host name

        quiet : bool, optional
            Whether to print warnings if the machine name is ambiguous

        """
        if machine is None:
            machine = discover_machine(quiet=quiet)
            if machine is None:
                raise ValueError('Unable to discover machine from host name')
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

        constraint : str
            The default constraint on the machine, or ``None`` if no
            constraint should be specified

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

        if config.has_option('parallel', 'constraints'):
            constraint = config.get('parallel', 'constraints')
            # take the first entry
            constraint = constraint.split(',')[0].strip()
        else:
            constraint = None

        if config.has_option('parallel', 'qos'):
            qos = config.get('parallel', 'qos')
            # take the first entry
            qos = qos.split(',')[0].strip()
        else:
            qos = None

        return account, partition, constraint, qos

    def _get_config(self):
        """ get a parser for config options """

        config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation())

        machine = self.machine
        try:
            cfg_path = \
                importlib_resources.files('mache.machines') / f'{machine}.cfg'
            config.read(cfg_path)
        except FileNotFoundError:
            # this isn't a known machine so use the default
            cfg_path = \
                importlib_resources.files('mache.machines') / 'default.cfg'
            config.read(cfg_path)

        return config

    def _parse_compilers_and_mpi(self):
        """ Parse the compilers and mpi modules from XML config files """
        machine = self.machine

        xml_path = (importlib_resources.files('mache.cime_machine_config') /
                    'config_machines.xml')

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
