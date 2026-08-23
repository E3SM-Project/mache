"""
Check that every machine config mache ships describes its memory.

A caller deciding how many pieces of work fit inside one allocation needs
``memory_per_node``. A machine that omits it works for everything else, so
the omission would surface as a caller unable to schedule on that machine
rather than as anything failing here. That is worth catching when a machine
is added or edited rather than on the machine.
"""

from configparser import ConfigParser
from pathlib import Path
from typing import List

import pytest

from mache import MachineInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
MACHINES_DIR = REPO_ROOT / 'mache' / 'machines'


def _get_machine_config_names() -> List[str]:
    return sorted(
        path.stem
        for path in MACHINES_DIR.glob('*.cfg')
        if path.stem != 'default'
    )


def _describes_a_parallel_system(config: ConfigParser) -> bool:
    """
    Whether a machine describes a system that runs work in parallel.

    Andes and Bebop ship no ``[parallel]`` section at all, so mache only ever
    treats them as login nodes and there is no compute node to describe.
    """
    return config.get('parallel', 'system', fallback=None) is not None


@pytest.mark.parametrize('machine', _get_machine_config_names())
def test_machine_configs_describe_memory(machine):
    config = MachineInfo(machine=machine).config
    if not _describes_a_parallel_system(config):
        return

    memory_per_node = config.get('parallel', 'memory_per_node', fallback=None)
    assert memory_per_node is not None, (
        f'{machine} does not set memory_per_node in [parallel]. It is the '
        f'usable memory of one compute node in MB, which is what the site '
        f'reports as available rather than the hardware capacity.'
    )

    # MB as an integer, since that is the unit Slurm's memory options default
    # to and the unit callers already use
    assert memory_per_node == memory_per_node.strip()
    assert int(memory_per_node) > 0
