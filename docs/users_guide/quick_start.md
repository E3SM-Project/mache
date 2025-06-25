# Quick Start

`mache` (Machines for E3SM) is a package for providing configuration data related to E3SM supported machines.

## Installing mache

You can install the latest release of `mache` from conda-forge:

```bash
conda config --add channels conda-forge
conda config --set channel_priority strict
conda install mache
```

## Example usage

```python
#!/usr/bin/env python
from mache import MachineInfo, discover_machine

machine_info = MachineInfo()
print(machine_info)
diags_base = machine_info.config.get('diagnostics', 'base_path')
machine = discover_machine()
```

This loads machine info for the current machine, prints it, and retrieves a
config option specific to that machine. The {py:func}`mache.discover_machine()`
function can also be used to detect which machine you are on.

As an example, the result of `print(machine_info)` is:

```
Machine: anvil
  E3SM Supported Machine: True
  Compilers: intel, gnu
  MPI libraries: impi, openmpi, mvapich
  OS: LINUX

E3SM-Unified:
  E3SM-Unified is not currently loaded
  Base path: /lcrc/soft/climate/e3sm-unified

Diagnostics:
  Base path: /lcrc/group/e3sm/diagnostics

Config options:
  [e3sm_unified]
    group = cels
    compiler = intel
    mpi = impi
    base_path = /lcrc/soft/climate/e3sm-unified

  [diagnostics]
    base_path = /lcrc/group/e3sm/diagnostics

  [web_portal]
    base_path = /lcrc/group/e3sm/public_html
    base_url = https://web.lcrc.anl.gov/public/e3sm/

  [parallel]
    system = slurm
    parallel_executable = srun
    cores_per_node = 36
    account = condo
    partitions = acme-small, acme-medium, acme-large
    qos = regular, acme_high
```

If you are on the login node of one of the following E3SM supported machines,
you don't need to provide the machine name. It can be discovered automatically:

- andes
- aurora
- anvil
- chicoma-cpu
- chrysalis
- compy
- dane
- frontier
- pm-cpu
- polaris
- ruby

If you are on a compute node or want info about a machine you're not currently on, give the `machine` name in all lowercase.

## Public Functions

The following public functions are available in the top-level `mache` package:

- {py:class}`mache.MachineInfo`: Class for querying machine-specific
  configuration and capabilities.
- {py:func}`mache.discover_machine`: Function to detect the current machine
  name.

### MachineInfo attributes

- `machine`: Name of the E3SM supported machine.
- `config`: ConfigParser object with machine-specific options.
- `e3sm_supported`: Whether this machine supports running E3SM.
- `compilers`: List of compilers for this machine.
- `mpilibs`: List of MPI libraries for this machine.
- `os`: The machine's operating system.
- `e3sm_unified_mpi`: Which MPI type is included in the E3SM-Unified
  environment.
- `e3sm_unified_base`: Base path for E3SM-Unified and activation scripts.
- `e3sm_unified_activation`: Activation script for E3SM-Unified.
- `diagnostics_base`: Base directory for diagnostics data.
- `web_portal_base`: Base directory for the web portal.
- `web_portal_url`: Base URL for the web portal.
- `username`: The current user's name.

### Additional utilities

- {py:func}`mache.machines.get_supported_machines()`: Returns a sorted list of
  supported machine names.
- {py:func}`mache.io.download_file()`: Download a file from a URL to a local
  path.

For more details on these and other features, see the full user's guide.
