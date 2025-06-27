import os as os
import subprocess as subprocess

import yaml as yaml
from jinja2 import Template as Template

from mache.machine_info import (
    MachineInfo as MachineInfo,
)
from mache.machine_info import (
    discover_machine as discover_machine,
)
from mache.spack.config_machines import (
    config_to_shell_script as config_to_shell_script,
)
from mache.spack.config_machines import (
    extract_machine_config as extract_machine_config,
)
from mache.spack.config_machines import (
    extract_spack_from_config_machines as extract_spack_from_config_machines,
)
from mache.spack.list import (
    list_machine_compiler_mpilib as list_machine_compiler_mpilib,
)
from mache.version import __version__ as __version__
