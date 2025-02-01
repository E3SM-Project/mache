import importlib.resources
import re
from pathlib import Path


def list_machine_compiler_mpilib():
    """
    List tuples of machine, compiler, and MPI library parsed from the name of
    YAML files in the `mache.spack` directory.

    Returns
    -------
    list of tuples
        Each tuple contains (machine, compiler, mpilib).
    """
    machine_compiler_mpi_list = []
    pattern = re.compile(r'([\w-]+)_([\w-]+)_([\w-]+)')

    files = sorted(importlib.resources.files('mache.spack').iterdir(), key=str)
    for file in files:
        file_path = Path(str(file))
        if file_path.suffix == '.yaml':
            match = pattern.match(file_path.stem)
            if match:
                machine, compiler, mpilib = match.groups()
                machine_compiler_mpi_list.append((machine, compiler, mpilib))

    return machine_compiler_mpi_list
