import os
import re
import socket


def discover_machine(quiet=False):
    """
    Figure out the machine from the host name

    Parameters
    ----------
    quiet : bool, optional
        Whether to print warnings if the machine name is ambiguous

    Returns
    -------
    machine : str
        The name of the current machine
    """
    hostname = socket.gethostname()
    machine = None
    machines_by_host_re = {
        r'^acme1': 'acme1',
        r'^andes': 'andes',
        r'^blueslogin': 'anvil',
        r'^b\d{3}': 'anvil',
        r'^ch-fe': 'chicoma-cpu',
        r'^chrlogin': 'chrysalis',
        r'^chr-\d{4}': 'chrysalis',
        r'^compy': 'compy',
        r'^n\d{4}': 'anvil',
        r'^cooley': 'cooley'
    }
    for host_re, mach in machines_by_host_re.items():
        p = re.compile(host_re)
        if p.match(hostname):
            machine = mach
            break
    if machine is None and 'LMOD_SYSTEM_NAME' in os.environ:
        hostname = os.environ['LMOD_SYSTEM_NAME']
        if hostname == 'frontier':
            # frontier's hostname is too generic to detect, so relying on
            # LMOD_SYSTEM_NAME
            machine = 'frontier'
    if machine is None and 'NERSC_HOST' in os.environ:
        hostname = os.environ['NERSC_HOST']
        if hostname == 'perlmutter':
            # perlmutter's hostname is too generic to detect, so relying on
            # $NERSC_HOST
            machine = 'pm-cpu'
        elif hostname == 'unknown':
            raise ValueError(
                'You appear to have $NERSC_HOST=unknown.  This typically '
                'indicates that you \n'
                'have an outdated .bash_profile.ext or similar.  Please '
                'either delete or \n'
                'edit that file so it no longer defines $NERSC_HOST, log out, '
                'log back in, \n'
                'and try again.')

    # As a last resort (e.g. on a compute node), try getting the machine from
    # a file created on install
    if machine is None and 'CONDA_PREFIX' in os.environ:
        prefix = os.environ['CONDA_PREFIX']
        machine_filename = os.path.join(
            prefix, 'share', 'mache', 'machine.txt')
        if os.path.exists(machine_filename):
            with open(machine_filename) as fp:
                machine = fp.read().replace('\n', '').strip()

    return machine
