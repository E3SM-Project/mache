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
2. Add system-provided (external) packages, saving time and prefenting build
   failures if Spack attempts to build them from source.
3. Optionally, provide shell script templates for module/environment setup if
   needed.

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

## Shell Script Templates

If the machine requires special module loads or environment variables not handled by Spack, add corresponding shell script templates:

- `<machine>.sh` and/or `<machine>_<compiler>_<mpilib>.sh` for bash
- `<machine>.csh` and/or `<machine>_<compiler>_<mpilib>.csh` for csh/tcsh

These scripts are also Jinja2 templates and can use the same conditional logic as the YAML files.

## Testing

After adding or modifying YAML and shell script templates:

1. Use the `make_spack_env` or `get_spack_script` functions in `mache.spack` to generate and test the environment.
2. Confirm that all modules load and all external packages are correctly detected by Spack.
3. Build and run a simple test application to verify the environment.

## Further Reading

- For the non-spack aspects of adding a new machine, see [Adding a New Machine to Mache](adding_new_machine.md).
- For more details on Spack external packages, see the [Spack documentation on external packages](https://spack.readthedocs.io/en/latest/build_settings.html#external-packages).

