# Building and Using Spack Environments with `mache.spack`

This page documents the main public functions in `mache.spack` for building
and using Spack environments, as leveraged by downstream packages such as
[compass](https://github.com/MPAS-Dev/compass),
[polaris](https://github.com/E3SM-Project/polaris), and
[e3sm-unified](https://github.com/E3SM-Project/e3sm-unified).

## Overview

The `mache.spack` module provides three primary functions for Spack
environment management:

- [`make_spack_env`](#make_spack_env): Build a Spack environment for a given
  machine, compiler, and MPI library.
- [`get_spack_script`](#get_spack_script): Generate a shell script snippet to
  activate a Spack environment.
- [`get_modules_env_vars_and_mpi_compilers`](#get_modules_env_vars_and_mpi_compilers):
  Query modules, environment variables, and MPI compiler wrappers for a given
  configuration.

These functions are typically called from bootstrap or deployment scripts in
downstream packages.

---

## `make_spack_env`

```python
from mache.spack import make_spack_env
```

**Purpose:**
Builds a Spack environment for a specified machine, compiler, and MPI library, using a set of package specs and optional configuration.

**Typical usage in downstream packages:**

- Called during environment setup (e.g., in
  [compass](https://github.com/MPAS-Dev/compass/blob/main/conda/bootstrap.py)
  [polaris](https://github.com/E3SM-Project/polaris/blob/main/deploy/bootstrap.py)
  or [e3sm-unified](https://github.com/E3SM-Project/e3sm-unified/blob/main/e3sm_supported_machines/deploy_e3sm_unified.py)).
- Used to automate the creation of a Spack environment with the correct
  packages and configuration for the target HPC system.

**Example usage:**

```python
make_spack_env(
    spack_path=spack_base,
    env_name=spack_env,
    spack_specs=specs,
    compiler=compiler,
    mpi=mpi,
    machine=machine,
    config_file=machine_config,
    include_e3sm_lapack=include_e3sm_lapack,
    include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    yaml_template=yaml_template,
    tmpdir=tmpdir,
    spack_mirror=spack_mirror,
    custom_spack=custom_spack
)
```

**Key arguments:**

- `spack_path`: Path to the Spack clone to use.
- `env_name`: Name for the Spack environment.
- `spack_specs`: List of package specs (e.g.,
  `["hdf5@1.12.2+mpi", "netcdf-c@4.8.1"]`).
- `compiler`, `mpi`: Compiler and MPI library names.
- `machine`: Machine name (optional, auto-detected if not provided).
- `config_file`: Path to a machine config file (optional).
- `include_e3sm_lapack`, `include_e3sm_hdf5_netcdf`: Whether to include
  E3SM-specific LAPACK or HDF5/NetCDF packages.
- `yaml_template`: Path to a custom Jinja2 YAML template (optional).
- `tmpdir`: Temporary directory for builds (optional).
- `spack_mirror`: Path to a local Spack mirror (optional).
- `custom_spack`: Additional Spack commands to run after environment creation
  (optional).

**Behavior:**

- Writes a YAML file describing the environment.
- Generates and runs a shell script to create the Spack environment.
- Loads any required modules and sets up environment variables as needed.

---

## `get_spack_script`

```python
from mache.spack import get_spack_script
```

**Purpose:**
Generates a shell script snippet to activate a Spack environment and load any required modules or environment variables.

**Typical usage in downstream packages:**

- Used to generate activation scripts for users (e.g., `load_compass.sh`,
  `load_polaris.sh`, `load_e3sm_unified.sh`).
- Ensures that the correct modules are loaded and the Spack environment is
  activated in the user's shell.

**Example usage:**

```python
spack_script = get_spack_script(
    spack_path=spack_base,
    env_name=spack_env,
    compiler=compiler,
    mpi=mpi,
    shell='sh',  # or 'csh'
    machine=machine,
    config_file=machine_config,
    include_e3sm_lapack=include_e3sm_lapack,
    include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
)
```

**Returns:**
A string containing shell commands to:

- Load required modules (if any).
- Source the Spack setup script.
- Activate the specified Spack environment.
- Set any additional environment variables.

**Usage in activation scripts:**

```bash
# Example in a load script
{{ spack_script }}
```

---

## `get_modules_env_vars_and_mpi_compilers`

```python
from mache.spack import get_modules_env_vars_and_mpi_compilers
```

**Purpose:**
Returns the MPI compiler wrappers and a shell snippet to load modules and set environment variables for a given machine, compiler, and MPI library.

**Typical usage in downstream packages:**

- Used when building or installing packages that require knowledge of the correct MPI compiler wrappers (e.g., `mpicc`, `mpicxx`, `mpifc`).
- Used to generate build scripts for additional software (e.g., building `mpi4py`, `ilamb`, or `esmpy` in `e3sm-unified`).

**Example usage:**

```python
mpicc, mpicxx, mpifc, mod_env_commands = get_modules_env_vars_and_mpi_compilers(
    machine=machine,
    compiler=compiler,
    mpi=mpi,
    shell='sh',  # or 'csh'
    include_e3sm_lapack=include_e3sm_lapack,
    include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
)
```

**Returns:**

- `mpicc`: Name of the MPI C compiler wrapper (e.g., `mpicc` or `cc`).
- `mpicxx`: Name of the MPI C++ compiler wrapper (e.g., `mpicxx` or `CC`).
- `mpifc`: Name of the MPI Fortran compiler wrapper (e.g., `mpif90` or `ftn`).
- `mod_env_commands`: Shell commands to load modules and set environment variables.

**Usage in build scripts:**

```bash
{{ mod_env_commands }}
# Now safe to use $mpicc, $mpicxx, $mpifc for building MPI-dependent software
```

---

## Example: How Downstream Packages Use These Functions

- **compass**:
  Uses `make_spack_env` to build the Spack environment, then calls `get_spack_script` to generate activation scripts for users.
  See: [`compass' conda/bootstrap.py`](https://github.com/MPAS-Dev/compass/blob/main/conda/bootstrap.py)

- **polaris**:
  Similar usage to `compass`, with additional logic for "soft" and "libs" Spack environments.
  See: [`polaris' deploy/bootstrap.py`](https://github.com/E3SM-Project/polaris/blob/main/deploy/bootstrap.py)

- **e3sm-unified**:
  Uses all three functions to build Spack environments, generate activation scripts, and build additional packages (e.g., `mpi4py`, `ilamb`, `esmpy`) using the correct compilers and environment.
  See: [`e3sm-unified's e3sm_supported_machines/bootstrap.py`](https://github.com/E3SM-Project/e3sm-unified/blob/main/e3sm_supported_machines/bootstrap.py)

---

## Notes

- These functions are intended for use in deployment scripts, not for
  interactive use.
- The downstream package is responsible for determining the correct arguments
  (machine, compiler, MPI, etc.) and for integrating the generated scripts
  into their activation workflow.
- For more details, see the source code and examples in the downstream
  packages listed above.

