from importlib import resources as importlib_resources
from pathlib import Path


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
        file_path = Path(str(file))
        if file_path.suffix == '.cfg' and file_path.name != 'default.cfg':
            machines.append(file_path.stem)
    return sorted(machines)
