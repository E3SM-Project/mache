#!/usr/bin/env python3

import argparse

from mache.cime_machine_config import (
    compare_machine_configs,
    extract_supported_machines,
)
from mache.io import download_file
from mache.machines import get_supported_machines


def main():
    """
    Main function to download the XML file, get supported machines, and extract
    them, then compare the machine configurations between the old and new XML.
    """
    parser = argparse.ArgumentParser(
        description='Get and display the updates made to '
        'config_supported_machines.xml',
    )

    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version='',
        help='Show version number and exit',
    )

    parser.parse_args()

    url = (
        'https://raw.githubusercontent.com/E3SM-Project/E3SM/refs/heads/'
        'master/cime_config/machines/config_machines.xml'
    )
    new_filename = 'new_config_machines.xml'
    download_file(url, new_filename)
    machines = get_supported_machines()
    extract_supported_machines(
        new_filename, 'new_config_supported_machines.xml', machines
    )

    old_filename = 'mache/cime_machine_config/config_machines.xml'
    extract_supported_machines(
        old_filename, 'old_config_supported_machines.xml', machines
    )

    for machine in machines:
        compare_machine_configs(
            'old_config_supported_machines.xml',
            'new_config_supported_machines.xml',
            machine,
        )


if __name__ == '__main__':
    main()
