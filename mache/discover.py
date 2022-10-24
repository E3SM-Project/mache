import socket
import warnings
import os


def discover_machine():
    """
    Figure out the machine from the host name

    Returns
    -------
    machine : str
        The name of the current machine
    """
    hostname = socket.gethostname()
    if hostname.startswith('acme1'):
        machine = 'acme1'
    elif hostname.startswith('andes'):
        machine = 'andes'
    elif hostname.startswith('blueslogin'):
        machine = 'anvil'
    elif hostname.startswith('ba-fe'):
        machine = 'badger'
    elif hostname.startswith('chrlogin'):
        machine = 'chrysalis'
    elif hostname.startswith('compy'):
        machine = 'compy'
    elif hostname.startswith('cooley'):
        machine = 'cooley'
    elif hostname.startswith('cori'):
        warnings.warn('defaulting to cori-haswell.  Explicitly specify '
                      'cori-knl as the machine if you wish to run on KNL.')
        machine = 'cori-haswell'
    elif hostname.startswith('gr-fe'):
        machine = 'grizzly'
    else:
        if 'LMOD_SYSTEM_NAME' in os.environ and \
                os.environ['LMOD_SYSTEM_NAME'] == 'perlmutter':
            # perlmutter's hostname is too generic to detect, so relying on an
            # env. variable

            warnings.warn('defaulting to pm-cpu.  Explicitly specify pm-gpu '
                          'as the machine if you wish to run on GPUs.')
            machine = 'pm-cpu'
        else:
            machine = None
    return machine
