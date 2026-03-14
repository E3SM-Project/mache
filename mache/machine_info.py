import configparser
import os
import pwd
from importlib import resources as importlib_resources
from typing import Dict

from lxml import etree

from mache.discover import discover_machine

SCHEDULER_TARGET_MAP = {
    'queue': 'queues',
    'partition': 'partitions',
    'qos': 'qos',
}


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

        info = (
            f'Machine: {self.machine}\n'
            f'  E3SM Supported Machine: {self.e3sm_supported}'
        )

        if (
            self.e3sm_supported
            and self.compilers is not None
            and self.mpilibs is not None
            and self.os is not None
        ):
            info = (
                f'{info}\n'
                f'  Compilers: {", ".join(self.compilers)}\n'
                f'  MPI libraries: {", ".join(self.mpilibs)}\n'
                f'  OS: {self.os}'
            )

        info = f'{info}\n'

        print_unified = (
            self.e3sm_unified_activation is not None
            or self.e3sm_unified_base is not None
            or self.e3sm_unified_mpi is not None
        )
        if print_unified:
            info = f'{info}\nE3SM-Unified: '

            if self.e3sm_unified_activation is None:
                info = f'{info}\n  E3SM-Unified is not currently loaded'
            else:
                info = f'{info}\n  Activation: {self.e3sm_unified_activation}'
            if self.e3sm_unified_base is not None:
                info = f'{info}\n  Base path: {self.e3sm_unified_base}'
            if self.e3sm_unified_mpi is not None:
                info = f'{info}\n  MPI type: {self.e3sm_unified_mpi}'
            info = f'{info}\n'

        print_diags = self.diagnostics_base is not None
        if print_diags:
            info = f'{info}\nDiagnostics: '

            if self.diagnostics_base is not None:
                info = f'{info}\n  Base path: {self.diagnostics_base}'
            info = f'{info}\n'

        info = f'{info}\nConfig options: '
        for section in self.config.sections():
            info = f'{info}\n  [{section}]'
            for key, value in self.config.items(section):
                info = f'{info}\n    {key} = {value}'
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

    def get_queue_specs(self) -> Dict[str, Dict[str, int | str | None]]:
        """
        Get queue policy metadata for the machine.

        Queue names are taken from ``parallel.queues``. For each queue, this
        method reads optional values from ``[queue.<queue_name>]``:

        - ``min_nodes`` (int)
        - ``max_nodes`` (int)
        - ``max_wallclock`` (str, e.g. ``01:00:00``)

        Returns
        -------
        queue_specs : dict
            Mapping from queue name to queue metadata. If a queue section is
            missing, all metadata values are ``None``.
        """
        return self.get_scheduler_specs(target_type='queue')

    def get_partition_specs(self) -> Dict[str, Dict[str, int | str | None]]:
        """
        Get partition policy metadata for the machine.

        Partition names are taken from ``parallel.partitions``. For each
        partition, this method reads optional values from
        ``[partition.<partition_name>]``:

        - ``min_nodes`` (int)
        - ``max_nodes`` (int)
        - ``max_wallclock`` (str, e.g. ``01:00:00``)

        Returns
        -------
        partition_specs : dict
            Mapping from partition name to partition metadata. If a partition
            section is missing, all metadata values are ``None``.
        """
        return self.get_scheduler_specs(target_type='partition')

    def get_qos_specs(self) -> Dict[str, Dict[str, int | str | None]]:
        """
        Get quality-of-service (QOS) policy metadata for the machine.

        QOS names are taken from ``parallel.qos``. For each QOS, this method
        reads optional values from ``[qos.<qos_name>]``:

        - ``min_nodes`` (int)
        - ``max_nodes`` (int)
        - ``max_wallclock`` (str, e.g. ``01:00:00``)

        Returns
        -------
        qos_specs : dict
            Mapping from QOS name to QOS metadata. If a QOS section is
            missing, all metadata values are ``None``.
        """
        return self.get_scheduler_specs(target_type='qos')

    def get_scheduler_specs(
        self, target_type: str
    ) -> Dict[str, Dict[str, int | str | None]]:
        """
        Get scheduler target metadata for queues or partitions.

        Parameters
        ----------
        target_type : {'queue', 'partition', 'qos'}
            The target type to parse.

        Returns
        -------
        target_specs : dict
            Mapping from target name to metadata with keys ``min_nodes``,
            ``max_nodes`` and ``max_wallclock``. If a target section is
            missing, all metadata values are ``None``.
        """
        if target_type not in SCHEDULER_TARGET_MAP:
            expected = ', '.join(SCHEDULER_TARGET_MAP.keys())
            raise ValueError(
                f'Unexpected target_type: {target_type}. Expected one of: '
                f'{expected}.'
            )

        config = self.config
        parallel_option = SCHEDULER_TARGET_MAP[target_type]
        if not config.has_option('parallel', parallel_option):
            return {}

        targets = [
            target.strip()
            for target in config.get('parallel', parallel_option).split(',')
            if target.strip() != ''
        ]

        target_specs: Dict[str, Dict[str, int | str | None]] = {}
        for target in targets:
            section = f'{target_type}.{target}'
            min_nodes = self._get_scheduler_int(section, 'min_nodes')
            max_nodes = self._get_scheduler_int(section, 'max_nodes')
            max_wallclock = self._get_scheduler_value(section, 'max_wallclock')

            if (
                min_nodes is not None
                and max_nodes is not None
                and min_nodes > max_nodes
            ):
                raise ValueError(
                    f'Invalid {target_type} config [{section}]: min_nodes '
                    f'({min_nodes}) is greater than max_nodes ({max_nodes}).'
                )

            target_specs[target] = {
                'min_nodes': min_nodes,
                'max_nodes': max_nodes,
                'max_wallclock': max_wallclock,
            }

        return target_specs

    def _get_config(self):
        """get a parser for config options"""

        config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )

        machine = self.machine

        # first, read the default configs for all machines, then override with
        # machine-specific configs
        default_cfg_path = (
            importlib_resources.files('mache.machines') / 'default.cfg'
        )
        config.read(str(default_cfg_path))
        try:
            cfg_path = (
                importlib_resources.files('mache.machines') / f'{machine}.cfg'
            )
            config.read(str(cfg_path))
        except FileNotFoundError:
            pass

        return config

    def _parse_compilers_and_mpi(self):
        """Parse the compilers and mpi modules from XML config files"""
        machine = self.machine

        xml_path = (
            importlib_resources.files('mache.cime_machine_config')
            / 'config_machines.xml'
        )

        root = etree.parse(str(xml_path))

        machines = next(root.iter('config_machines'))

        mach = None
        for machine_xml in machines:
            if (
                machine_xml.tag == 'machine'
                and machine_xml.attrib['MACH'] == machine
            ):
                mach = machine_xml
                break

        if mach is None:
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
        """Read E3SM-Unified base path and detect whether it is running"""
        config = self.config

        if config is not None and config.has_option(
            'e3sm_unified', 'base_path'
        ):
            self.e3sm_unified_base = config.get('e3sm_unified', 'base_path')

        if 'E3SMU_SCRIPT' in os.environ:
            self.e3sm_unified_activation = os.environ['E3SMU_SCRIPT']

        if 'E3SMU_MPI' in os.environ:
            self.e3sm_unified_mpi = os.environ['E3SMU_MPI'].lower()

    def _get_diagnostics_info(self):
        """Get config options related to diagnostics data"""

        config = self.config

        if config is not None and config.has_option(
            'diagnostics', 'base_path'
        ):
            self.diagnostics_base = config.get('diagnostics', 'base_path')

    def _get_scheduler_value(self, section: str, option: str) -> str | None:
        """Get a scheduler-target config value, treating empty as unset."""
        config = self.config
        if not config.has_option(section, option):
            return None

        value = config.get(section, option).strip()
        if value == '':
            return None
        return value

    def _get_scheduler_int(self, section: str, option: str) -> int | None:
        """Get an integer scheduler-target config value if set."""
        value = self._get_scheduler_value(section, option)
        if value is None:
            return None
        return int(value)
