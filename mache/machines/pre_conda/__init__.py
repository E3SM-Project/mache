from importlib.resources import read_text


def load_pre_conda_script(machine, ext):
    """
    Return the contents of a shell script to prepend before loading conda

    Parameters
    ----------
    machine : str
        The name of the machine to load the script for.
    ext : str
        The file extension of the script, either 'sh' or 'csh'.

    Returns
    -------
    str
        The contents of the shell script.
    """
    try:
        return read_text('mache.machines.pre_conda', f'{machine}.{ext}')
    except FileNotFoundError:
        return ''
