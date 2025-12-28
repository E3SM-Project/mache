import platform

CONDA_PLATFORM_MAP = {
    ('linux', 'x86_64'): 'linux-64',
    ('linux', 'aarch64'): 'linux-aarch64',
    ('linux', 'ppc64le'): 'linux-ppc64le',
    ('osx', 'x86_64'): 'osx-64',
    ('osx', 'arm64'): 'osx-arm64',
}


def get_conda_platform_and_system() -> tuple[str, str]:
    """
    Get the conda system name ('linux' or 'osx') and platform (e.g.
    'linux-64').

    Returns
    -------
    platform : str
        The conda platform string (e.g. 'linux-64').
    system : str
        The conda system string (e.g. 'linux' or 'osx').

    """
    system = platform.system().lower()
    if system == 'darwin':
        system = 'osx'
    machine = platform.machine().lower()
    if (system, machine) in CONDA_PLATFORM_MAP:
        conda_platform = CONDA_PLATFORM_MAP[(system, machine)]
    else:
        raise ValueError(f'Unsupported platform for conda: {system} {machine}')
    return conda_platform, system
