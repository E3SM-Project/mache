from importlib import resources as importlib_resources


def get_supported_machines():
    """
    Get a list of supported machines by reading .cfg files in the
    mache.machines directory.

    Returns
    -------
    list of str
        A sorted list of supported machine names.
    """
    machines = []
    for file in importlib_resources.files('mache.machines').iterdir():
        if file.suffix == '.cfg' and file.name != 'default.cfg':
            machines.append(file.stem)
    return sorted(machines)
