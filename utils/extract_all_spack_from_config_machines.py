#!/usr/bin/env python3
import os

from mache.spack.config_machines import extract_spack_from_config_machines
from mache.spack.list import list_machine_compiler_mpilib


def main():
    """
    Main function to parse arguments and extract machine configuration.
    """

    directory = 'spack_scripts'
    os.makedirs(directory, exist_ok=True)

    for machine, compiler, mpilib in list_machine_compiler_mpilib():
        print(f'Extracting {machine}, {compiler}, {mpilib}')
        for shell in ['sh', 'csh']:
            filename = f'{directory}/{machine}_{compiler}_{mpilib}.{shell}'
            extract_spack_from_config_machines(
                machine, compiler, mpilib, shell, filename
            )


if __name__ == '__main__':
    main()
