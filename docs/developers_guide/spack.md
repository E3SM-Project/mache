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
(e.g., LAPACK) based on user options.

### Template skeleton

Templates use the Spack 1.x compiler model: the compiler is an external
package with `extra_attributes.compilers`, and a toolchain named `mache`,
required for every package, selects it for `c`, `cxx` and `fortran`. The
compiler is not a root spec, and no spec carries `%{{ compiler }}`. A minimal
template:

```yaml
{%- set compiler = "gcc@11.2.0" %}
{%- set mpi = "openmpi@4.1.6" %}
spack:
  specs:
  - {{ mpi }}
  - "hdf5"
  - "netcdf-c"
  - "netcdf-fortran"
  - "parallel-netcdf"
{%- for spec in specs %}
  - "{{ spec }}"
{%- endfor %}
  concretizer:
    unify: true
  toolchains:
    mache:
    - spec: "%c={{ compiler }}"
      when: "%c"
    - spec: "%cxx={{ compiler }}"
      when: "%cxx"
    - spec: "%fortran={{ compiler }}"
      when: "%fortran"
  packages:
    all:
      require: ["%mache"]
      providers:
        mpi: [{{ mpi }}]
    gcc:
      externals:
      - spec: {{ compiler }}
        prefix: /path/to/gcc-11.2.0
        modules:
        - gcc/11.2.0
        extra_attributes:
          compilers:
            c: /path/to/gcc-11.2.0/bin/gcc
            cxx: /path/to/gcc-11.2.0/bin/g++
            fortran: /path/to/gcc-11.2.0/bin/gfortran
          # optional, as in the old compilers: section
          environment:
            prepend_path:
              PKG_CONFIG_PATH: /path/to/pkgconfig
      buildable: false
    openmpi:
      externals:
      - spec: {{ mpi }}
        prefix: /path/to/openmpi-4.1.6
        modules:
        - openmpi/4.1.6
      buildable: false
    # further externals: hdf5, netcdf-c, cmake, ...
```

Compiler package names follow `spack-packages`: `gcc`, `nvhpc`, `cce` and
`intel-oneapi-compilers` (for `icx`/`icpx`/`ifx`). On Cray systems the
compiler paths can be the wrappers `cc`, `CC` and `ftn`. Every oneAPI
external (`intel-oneapi-compilers`, `intel-oneapi-mkl`, ...) needs an
explicit `prefix:` that is the root of the oneAPI installation (the
directory holding `compiler/<version>/` or `mkl/<version>/`); a prefix
inferred from `modules:` points inside that component directory and the
oneAPI build system then fails to find `env/vars.sh`. The Intel classic
compilers (`icc`/`ifort`) have no package in any `spack-packages` release and
are not supported.

Do not list `gcc-runtime` as an external: Spack 1.x always builds it (from
the `gcc` external) whenever anything else in the environment is built, so
a `buildable: false` entry makes concretization fail. A template whose
compiler is `intel-oneapi-compilers` still needs a `gcc` external, because
`intel-oneapi-runtime` links against `gcc-runtime`.

`mache` rejects a rendered template that still has a top-level `compilers:`
section or `packages:all:compiler`, so an old-style template or
`deploy/spack/<machine>_<compiler>_<mpi>.yaml` override fails with a clear
message before Spack sees it.

Machine-provided HDF5/NetCDF packages should now be listed unconditionally in
the YAML templates.  Downstream packages can opt out of them, or any other
machine-provided external such as `cmake`, with `exclude_packages`.  Mache
filters the rendered YAML after Jinja expansion and removes matching:

- `spack.specs` entries
- `spack.packages.<name>` external-package sections
- matching provider specs under `spack.packages.all.providers`

### Typical External Packages

On most HPC systems, the following packages are provided by the system and
should be marked as `external` in the YAML:

- Compilers (e.g., `gcc`, `intel-oneapi-compilers`, `nvhpc`, `cce`)
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
  require: ["%mache"]
  providers:
    mpi: [cray-mpich@8.1.31]
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

### Package opt-outs and deprecated HDF5/NetCDF flag

The preferred downstream-facing interface is `exclude_packages`, available in
the public `mache.spack` APIs and in `mache.deploy` runtime config.

Examples:

- `exclude_packages=["cmake"]`: build CMake with Spack instead of using the
  machine-provided external package and module setup.
- `exclude_packages=["hdf5_netcdf"]`: opt out of the machine-provided
  HDF5/NetCDF bundle.
- `exclude_packages=["hdf5", "netcdf-c", "netcdf-fortran",
  "parallel-netcdf"]`: the same bundle, expressed explicitly.

`e3sm_hdf5_netcdf` and `include_e3sm_hdf5_netcdf` remain supported as
deprecated compatibility flags in public `mache.spack` APIs.  New code should
prefer `exclude_packages`.

### When to add a template override

Only provide a small override in `mache/spack/templates/` if you need to:

- Apply an adjustment that’s not appropriate for the shared E3SM CIME config
  (machine-local quirk, temporary workaround, etc.).
- Add conditional behavior toggled by `include_e3sm_lapack` or by package
  helper functions such as `use_system_package('cmake')` and
  `use_system_packages('netcdf-c', 'netcdf-fortran')` that cannot be
  expressed in the CIME config.

  Note: `include_e3sm_hdf5_netcdf` remains supported as a deprecated alias for
  `e3sm_hdf5_netcdf` in public `mache.spack` APIs, but new shell overrides
  should prefer the package helpers over `e3sm_hdf5_netcdf`.

Templates are Jinja2 files and can use the same conditional logic as YAML
templates.  For shell overrides, the most useful helpers are:

- `use_system_package('<spack-package-name>')`
- `use_system_packages('<pkg1>', '<pkg2>', ...)`
- `render_env_var(name, value, shell_type)`

These helpers let shell overrides stay package-oriented even when the machine
module names do not match Spack package names exactly.

## Testing

After adding or modifying YAML templates (or an exceptional shell override):

1. Run `pixi run pytest tests/test_spack_templates.py`, which renders every
   template and checks it against the Spack 1.x model.
2. Use `make_spack_env` or `get_spack_script` in `mache.spack` to generate and
  test the environment and load scripts.
3. Confirm that the generated shell snippet includes the expected module loads
  from the CIME machine config and that Spack detects all external packages.
4. Build and run a simple test application to verify the environment, and
   compare the captured `activate.sh` in the environment directory with the
   output of `spack env activate --sh <env>` run by hand.

## Package recipes

Recipes that E3SM needs beyond the pinned `spack-packages` release live in
[E3SM-Project/e3sm-spack-packages](https://github.com/E3SM-Project/e3sm-spack-packages),
which `mache` registers ahead of `builtin`. Its README explains how packages
subclass upstream recipes and how it is tagged. Bumping the Spack,
`spack-packages` or `e3sm-spack-packages` pin is an ordinary pull request
that edits `mache/spack/pins.yaml`; a release must pin tags only, which
`tests/test_spack_pins.py` enforces for non-pre-release versions.

## Patches to Spack

`mache/spack/patches/*.patch` are `git apply` patches that the build script
applies to the pinned Spack checkout right after resetting it, so they are
applied exactly once per build and recorded under `spack: patches:` in the
provenance file. Each patch starts with a description of what it fixes,
the upstream pull request, and when it can be dropped. A patch is a last
resort for a Spack bug that blocks E3SM builds before the fix is released;
open the upstream pull request first, and remove the patch when the pin
moves to a release that contains the fix (the build fails at `git apply`
if a patch no longer applies). `tests/test_spack_install_script.py` checks
that every patch still applies to the pinned tag.

## Further Reading

- For the non-spack aspects of adding a new machine, see [Adding a New Machine to Mache](adding_new_machine.md).
- For more details on Spack external packages, see the [Spack documentation on external packages](https://spack.readthedocs.io/en/latest/build_settings.html#external-packages).
