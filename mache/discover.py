import socket
import warnings
import os


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
    if hostname.startswith('acme1'):
        machine = 'acme1'
    elif hostname.startswith('andes'):
        machine = 'andes'
    elif hostname.startswith('blueslogin'):
        machine = 'anvil'
    elif hostname.startswith('ba-fe'):
        machine = 'badger'
    elif hostname.startswith('ch-fe'):
        if not quiet:
            warnings.warn('defaulting to chicoma-cpu.  Use -m chicoma-gpu if '
                          'you wish to run on GPUs.')
        machine = 'chicoma-cpu'
    elif hostname.startswith('chrlogin'):
        machine = 'chrysalis'
    elif hostname.startswith('compy'):
        machine = 'compy'
    elif hostname.startswith('cooley'):
        machine = 'cooley'
    elif hostname.startswith('cori'):
        if not quiet:
            warnings.warn('defaulting to cori-haswell.  Explicitly specify '
                          'cori-knl as the machine if you wish to run on KNL.')
        machine = 'cori-haswell'
    elif 'NERSC_HOST' in os.environ:
        hostname = os.environ['NERSC_HOST']
        if hostname == 'perlmutter':
            # perlmutter's hostname is too generic to detect, so relying on
            # $NERSC_HOST
            if not quiet:
                warnings.warn('defaulting to pm-cpu.  Explicitly specify '
                              'pm-gpu as the machine if you wish to run on '
                              'GPUs.')
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
