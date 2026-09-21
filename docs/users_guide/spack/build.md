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

## Spack sources and version pins

`mache` builds environments with an unmodified Spack 1.x release and two
package repositories, searched in this order:

| Role | Repository | Namespace |
|------|------------|-----------|
| E3SM packages and early updates | [E3SM-Project/e3sm-spack-packages](https://github.com/E3SM-Project/e3sm-spack-packages) | `e3sm` |
| upstream packages | [spack/spack-packages](https://github.com/spack/spack-packages) | `builtin` |

A package in `e3sm` shadows the upstream package of the same name. Each
`mache` release pins the three sources in `mache/spack/pins.yaml`:

```yaml
spack:
  git: https://github.com/spack/spack.git
  tag: v1.2.2
repos:
  e3sm:
    git: https://github.com/E3SM-Project/e3sm-spack-packages.git
    tag: v2026.06.0
  builtin:
    git: https://github.com/spack/spack-packages.git
    tag: v2026.06.0
```

Each entry names exactly one of `tag`, `commit` or `branch`. To build against
an unreleased recipe, pass overrides in the same schema (a mapping or the path
to a YAML file) as `pins=` to `make_spack_env`, or `--spack-pins <file>` to
`mache deploy run`. Overrides merge per repository and replace that
repository's ref:

```yaml
repos:
  e3sm:
    branch: my-fix
```

The Spack checkout at `spack_path` holds everything: the two package
repositories under `var/spack/package_repos/`, the user configuration scope,
caches and bootstrap store (through `spack isolate --self`), the managed
environments under `var/spack/environments/` and the install tree. Use a new
`spack_path` for each major `mache` release; a checkout of Spack 0.x is
refused rather than converted.

### Spec syntax

Specs from `spack_specs` (or `deploy/spack.yaml.j2`) are passed to Spack
unchanged; `mache` no longer appends `%<compiler>`. The compiler is selected
by a toolchain in the machine template, so specs normally need no `%`. If a
spec does use `%`, remember that in Spack 1.x everything after it applies to
that dependency: `trilinos %gcc +mpi` asks for `gcc+mpi`, so put variants
before `%`.

---

## `make_spack_env`

```python
from mache.spack import make_spack_env
```

**Purpose:**
Checks out the pinned Spack sources (see
[Spack sources and version pins](#spack-sources-and-version-pins)) and builds
a Spack environment for a specified machine, compiler, and MPI library, using
a set of package specs and optional configuration.

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
    e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    exclude_packages=exclude_packages,
    yaml_template=yaml_template,
    tmpdir=tmpdir,
    spack_mirror=spack_mirror,
    custom_spack=custom_spack,
    pins=pins,
    activation='captured',
    build_jobs=build_jobs,
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
- `include_e3sm_lapack`: Whether to include E3SM-specific LAPACK packages.
- `exclude_packages`: A package name or list of package names whose
  machine-provided externals, modules, and related environment variables
  should be removed so Spack can build them instead.  For example, setting
  `exclude_packages=["cmake"]` lets a downstream package build a newer CMake
  than the system provides.  The template's own root spec for an excluded
  package is removed too, but a spec for it in `spack_specs` is kept.
- `e3sm_hdf5_netcdf`: Deprecated compatibility flag for opting into the
  machine-provided HDF5/NetCDF bundle.  New code should prefer
  `exclude_packages=["hdf5_netcdf"]` (or the individual package names
  `hdf5`, `netcdf-c`, `netcdf-fortran`, and `parallel-netcdf`) instead.
- `yaml_template`: Path to a custom Jinja2 YAML template (optional).
- `tmpdir`: Temporary directory for builds (optional).
- `spack_mirror`: Path to a local Spack mirror (optional).
- `custom_spack`: Additional Spack commands to run after environment creation
  (optional).
- `pins`: Overrides for the pinned Spack sources, a mapping or the path to a
  YAML file (optional).
- `activation`: `captured` (default) writes `activate.sh` and `activate.csh`
  into the environment directory after the build; `dynamic` does not (see
  [`get_spack_script`](#get_spack_script)).
- `build_jobs`: Number of parallel build jobs for `spack install -j`
  (optional).

**Behavior:**

- Writes `<env_name>.yaml`, `build_<env_name>.bash` and
  `<env_name>.prologue.sh` (the module loads and environment variables the
  build runs with) to the current directory.
- Runs the build script in a fresh login shell: it clones or updates Spack
  and the package repositories at their pinned refs, writes the instance's
  `etc/spack/repos.yaml`, isolates the instance from `~/.spack`, recreates
  the environment and installs it.
- Copies `<env_name>.spack.lock` and writes `<env_name>.provenance.yaml`
  (the resolved commit of each source) to the current directory.
- With `activation='captured'`, captures the environment's activation into
  `activate.sh` and `activate.csh` in the environment directory.

**Recommended pattern for downstream packages:**

```python
exclude_packages = []
if needs_newer_cmake:
    exclude_packages.append("cmake")

make_spack_env(
    ...,
    exclude_packages=exclude_packages,
)
```

To opt out of the machine-provided HDF5/NetCDF bundle, use either:

```python
exclude_packages=["hdf5_netcdf"]
```

or the individual package names:

```python
exclude_packages=[
    "hdf5",
    "netcdf-c",
    "netcdf-fortran",
    "parallel-netcdf",
]
```

---

## `get_spack_script`

```python
from mache.spack import get_spack_script
```

**Purpose:**
Generates a shell script snippet to activate a Spack environment and load the
required modules or environment variables.

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
    include_e3sm_lapack=include_e3sm_lapack,
    e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    exclude_packages=exclude_packages,
    activation='captured',  # or 'dynamic'
)
```

**How the script is composed:**

The returned snippet is assembled in three steps:

1. Optionally activate the requested environment. By default this is a
   single line:

   ```bash
   source <spack_path>/var/spack/environments/<env_name>/activate.sh
   ```

   `activate.sh` (and `activate.csh`) is captured when the environment is
   built: `mache` runs `spack env activate` once in a clean shell and
   rewrites the result so that path-like variables are prepended to, rather
   than replaced. Sourcing it costs milliseconds and runs no Spack. It also
   sets `SPACK_ROOT` and `SPACK_ENV` and puts the plain `spack` executable on
   `PATH`, so `spack find` and `spack config get` work on the loaded
   environment; for `spack load` or `spack env activate`, source
   `$SPACK_ROOT/share/spack/setup-env.sh` first. With `activation='dynamic'`
   the snippet sources `setup-env.sh` and runs `spack env activate` instead.
2. Auto-generate module loads and environment exports from the E3SM CIME
  machine configuration (`mache/cime_machine_config/config_machines.xml`) for
  the given `(machine, compiler, mpi)` and target shell (`sh` or `csh`).
3. Append any Mache template override present in `mache/spack/templates/` named
  `<machine>.<sh|csh>` or `<machine>_<compiler>_<mpi>.<sh|csh>`.

This design keeps Mache aligned with E3SM’s authoritative machine
configuration and minimizes maintenance.

`exclude_packages` applies here too, so `get_spack_script()` removes matching
machine-provided module loads and environment variables from both:

- shell snippets derived from `config_machines.xml`, and
- any package-local shell overrides in `mache/spack/templates/*.sh` or
  `*.csh`.

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
Returns the MPI compiler wrappers and a shell snippet to load modules and set
environment variables for a given machine, compiler, and MPI library.

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
    e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
    exclude_packages=exclude_packages,
)
```

**Returns:**

- `mpicc`: Name of the MPI C compiler wrapper (e.g., `mpicc` or `cc`).
- `mpicxx`: Name of the MPI C++ compiler wrapper (e.g., `mpicxx` or `CC`).
- `mpifc`: Name of the MPI Fortran compiler wrapper (e.g., `mpif90` or `ftn`).
- `mod_env_commands`: Shell commands to load modules and set environment variables.

As with `get_spack_script()`, `exclude_packages` can be used to remove
machine-provided package setup from the generated shell snippet.

**Notes and usage in build scripts:**

```bash
{{ mod_env_commands }}
# Now safe to use $mpicc, $mpicxx, $mpifc for building MPI-dependent software
```

- This helper uses the same shell-generation logic as `get_spack_script()`
  but does not activate a Spack environment. It therefore includes the
  machine-derived setup from `config_machines.xml` plus any matching Mache
  shell overrides.

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
- `e3sm_hdf5_netcdf` and `include_e3sm_hdf5_netcdf` remain supported for
  backward compatibility, but new downstream code should use
  `exclude_packages` instead.
- The downstream package is responsible for determining the correct arguments
  (machine, compiler, MPI, etc.) and for integrating the generated scripts
  into their activation workflow.
- For more details, see the source code and examples in the downstream
  packages listed above.
