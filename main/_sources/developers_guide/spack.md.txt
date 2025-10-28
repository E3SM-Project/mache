# Adding Spack Support for a New Machine

This guide describes how to add support for a new machine to the `mache.spack`
subpackage, focusing on the YAML configuration files for compilers and MPI
libraries. For instructions on adding a new machine to mache in general
(including non-spack configuration), see
[Adding a New Machine to Mache](adding_new_machine.md).

## Overview

To enable Spack-based environments for a new machine, you will need to:

1. Create one or more YAML template files in `mache/spack/templates/` for each
   supported compiler and MPI library combination.
2. Add system-provided (external) packages, saving time and preventing build
   failures if Spack attempts to build them from source.
3. Prefer automatic shell script generation. Shell snippets used to be
   maintained as templates in `mache.spack.templates`, but are now derived
   primarily from the E3SM CIME machine configuration
   (`mache/cime_machine_config/config_machines.xml`). Only add a minimal
   template override when strictly necessary (see below).

## YAML Template Files

Each YAML file describes a Spack environment for a particular combination of compiler and MPI library. The filename convention is:

```
<machine>_<compiler>_<mpilib>.yaml
```

For example: `chicoma-cpu_gnu_mpich.yaml`

These files are Jinja2 templates, allowing conditional inclusion of packages
(e.g., HDF5/NetCDF, LAPACK) based on user options.

### Typical External Packages

On most HPC systems, the following packages are provided by the system and
should be marked as `external` in the YAML:

- Compilers (e.g., `gcc`, `intel`, `nvhpc`, `rocmcc`, `oneapi`)
- MPI libraries (e.g., `cray-mpich`, `openmpi`, `mvapich2`, `intel-mpi`,
  `mpich`)
- BLAS/LAPACK libraries (e.g., `cray-libsci`, `intel-mkl`, `intel-oneapi-mkl`)
- HDF5, NetCDF, and PNetCDF libraries (often as modules or in system paths)
- Build tools: `cmake`, `gmake`, `autoconf`, `automake`, `libtool`, `m4`
- Compression and utility libraries: `bzip2`, `xz`, `zlib`, `curl`, `openssl`,
  `findutils`, `gettext`, `tar`, `perl`, `python`

**Note:** The exact set of external packages may vary by machine. Consult existing YAML files for examples.

### Finding Library Paths

To specify an external package, you need its installation prefix and (optionally) the module name. You can find these by:

- Using `which <executable>` or `echo $MODULEPATH` to find module paths
- Checking the output of `module show <modulename>` for environment variables like `PATH`, `LD_LIBRARY_PATH`, or `PREFIX`
- Consulting system documentation or sysadmins

Example external package entry:

```yaml
cmake:
  externals:
  - spec: cmake@3.27.9
    prefix: /sw/frontier/spack-envs/core-24.07/opt/gcc-7.5.0/cmake-3.27.9-pyxnvhiskwepbw5itqyipzyhhfw3yitk
    modules:
    - cmake/3.27.9
  buildable: false
```

### Marking Packages as Non-Buildable

For each external package, set `buildable: false` to prevent Spack from attempting to build it from source.

### Providers

Specify providers for `mpi` and `lapack` under the `all` section, e.g.:

```yaml
all:
  compiler: [gcc@13.2]
  providers:
    mpi: [cray-mpich@8.1.31%gcc@13.2]
    lapack: [cray-libsci@24.11.0]
```

## Automatic shell script generation (preferred)

When downstream packages call
{py:func}`mache.spack.get_spack_script`, the module loads and
environment-variable setup are constructed as follows:

1. Optional: activate Spack and the requested environment.
2. Auto-generate a shell snippet from the E3SM CIME machine configuration
   stored in `mache/cime_machine_config/config_machines.xml`, filtered for the
   requested `(machine, compiler, mpilib)` and rendered for the target shell
   (`sh` or `csh`).
3. Append any Jinja2 template override found in
   `mache/spack/templates/` named either `<machine>.<sh|csh>` or
   `<machine>_<compiler>_<mpilib>.<sh|csh>`.

This pipeline greatly reduces maintenance and prevents drift between Mache and
E3SM’s authoritative machine configuration. In most cases, you do not need to
author or maintain shell script templates in Mache.

### When to add a template override

Only provide a small override in `mache/spack/templates/` if you need to:

- Apply an adjustment that’s not appropriate for the shared E3SM CIME config
  (machine-local quirk, temporary workaround, etc.).
- Add conditional behavior toggled by
  `include_e3sm_lapack` or `include_e3sm_hdf5_netcdf` (both exposed as Jinja
  booleans in templates) that cannot be expressed in the CIME config.

Templates are Jinja2 files and can use the same conditional logic as YAML
templates.

## Testing

After adding or modifying YAML templates (or an exceptional shell override):

1. Use `make_spack_env` or `get_spack_script` in `mache.spack` to generate and
  test the environment and load scripts.
2. Confirm that the generated shell snippet includes the expected module loads
  from the CIME machine config and that Spack detects all external packages.
3. Build and run a simple test application to verify the environment.

## Further Reading

- For the non-spack aspects of adding a new machine, see [Adding a New Machine to Mache](adding_new_machine.md).
- For more details on Spack external packages, see the [Spack documentation on external packages](https://spack.readthedocs.io/en/latest/build_settings.html#external-packages).

