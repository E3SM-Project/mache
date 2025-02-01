#!/usr/bin/env python3

import difflib
import os

import requests
from lxml import etree
from termcolor import colored


def download_file(url, local_filename):
    """
    Download a file from a URL.

    Parameters
    ----------
    url : str
        The URL of the file to download.
    local_filename : str
        The local path where the file will be saved.
    """
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def get_supported_machines(directory):
    """
    Get a list of supported machines by reading .cfg files in a directory.

    Parameters
    ----------
    directory : str
        The directory to search for .cfg files.

    Returns
    -------
    list of str
        A sorted list of supported machine names.
    """
    machines = []
    for filename in os.listdir(directory):
        if filename.endswith('.cfg') and filename != 'default.cfg':
            machines.append(os.path.splitext(filename)[0])
    return sorted(machines)


def extract_supported_machines(input_xml, output_xml, supported_machines):
    """
    Extract supported machines from an XML file and write to a new XML file.

    Parameters
    ----------
    input_xml : str
        The path to the input XML file.
    output_xml : str
        The path to the output XML file.
    supported_machines : list of str
        A list of supported machine names.
    """
    tree = etree.parse(input_xml)
    root = tree.getroot()

    for machine in root.findall('machine'):
        mach_name = machine.get('MACH')
        if mach_name not in supported_machines:
            root.remove(machine)

    tree.write(output_xml, pretty_print=True)


def compare_machine_configs(old_xml, new_xml, machine_name):
    """
    Compare the XML within the `machine` tag for a given machine between the
    old and new XML files and print the differences.

    Parameters
    ----------
    old_xml : str
        The path to the old XML file.
    new_xml : str
        The path to the new XML file.
    machine_name : str
        The name of the machine to compare.
    """
    old_tree = etree.parse(old_xml)
    new_tree = etree.parse(new_xml)

    old_machine = old_tree.find(f".//machine[@MACH='{machine_name}']")
    new_machine = new_tree.find(f".//machine[@MACH='{machine_name}']")

    if old_machine is None:
        print(f"Machine {machine_name} not found in {old_xml}.")
        return

    if new_machine is None:
        print(f"Machine {machine_name} not found in {new_xml}.")
        return

    old_machine_str = etree.tostring(old_machine, pretty_print=True).decode()
    new_machine_str = etree.tostring(new_machine, pretty_print=True).decode()

    diff = difflib.unified_diff(
        old_machine_str.splitlines(),
        new_machine_str.splitlines(),
        fromfile='old',
        tofile='new',
        lineterm=''
    )

    print()
    print(colored(f"Comparing machine: {machine_name}", 'blue'))
    for line in diff:
        if line.startswith('-'):
            print(colored(line, 'red'))
        elif line.startswith('+'):
            print(colored(line, 'green'))
        else:
            print(line)
    print()


def main():
    """
    Main function to download the XML file, get supported machines, and extract
    them, then compare the machine configurations between the old and new XML.
    """
    url = ('https://raw.githubusercontent.com/E3SM-Project/E3SM/refs/heads/'
           'master/cime_config/machines/config_machines.xml')
    new_filename = 'new_config_machines.xml'
    download_file(url, new_filename)
    machines = get_supported_machines('mache/machines')
    extract_supported_machines(new_filename,
                               'new_config_supported_machines.xml',
                               machines)

    old_filename = 'mache/cime_machine_config/config_machines.xml'
    extract_supported_machines(old_filename,
                               'old_config_supported_machines.xml',
                               machines)

    for machine in machines:
        compare_machine_configs('old_config_supported_machines.xml',
                                'new_config_supported_machines.xml',
                                machine)


if __name__ == "__main__":
    main()
