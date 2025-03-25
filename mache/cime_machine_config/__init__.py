import difflib

from lxml import etree
from termcolor import colored


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
        print(f'Machine {machine_name} not found in {old_xml}.')
        return

    if new_machine is None:
        print(f'Machine {machine_name} not found in {new_xml}.')
        return

    old_machine_str = etree.tostring(old_machine, pretty_print=True).decode()
    new_machine_str = etree.tostring(new_machine, pretty_print=True).decode()

    diff = difflib.unified_diff(
        old_machine_str.splitlines(),
        new_machine_str.splitlines(),
        fromfile='old',
        tofile='new',
        lineterm='',
    )

    print()
    print(colored(f'Comparing machine: {machine_name}', 'blue'))
    for line in diff:
        if line.startswith('-'):
            print(colored(line, 'red'))
        elif line.startswith('+'):
            print(colored(line, 'green'))
        else:
            print(line)
    print()
