# Design Document: Spack 1.x in mache

## Summary

`mache` builds Spack environments from `E3SM-Project/spack`, a fork of Spack
0.23.1 carrying about a hundred E3SM commits, checked out from a
`spack_for_mache_<version>` branch. Spack 1.0 (July 2025) moved every package
into a separate repository, `spack/spack-packages`, turned compilers into
ordinary packages, and fixed a versioned package API. The fork cannot follow:
its changes sit in the old in-tree package layout, and Spack 0.23 needs a
workaround to run on Python 3.12 or newer.

This design replaces the fork with three pinned pieces: an unmodified Spack
release, a `spack-packages` release, and a small E3SM package repository,
`E3SM-Project/e3sm-spack-packages` (namespace `e3sm`), searched ahead of
`builtin`. `mache` pins all three per release, keeps the on-disk instance
layout, and migrates its machine templates to the Spack 1.x compiler model.
Load scripts stop running `spack env activate` and instead source an
activation snippet captured at build time. Support for the legacy Intel
classic compilers ends. The change ships as `mache` 5.0.0.

Andrew Nolan's `spack-v1.0.0` branch
([PR #281](https://github.com/E3SM-Project/mache/pull/281)) is the starting
point. What was kept and what was changed is listed in [Prior work](#prior-work).

---

## Open Questions

*Date last modified: Sep 22, 2026*

None remain; resolved questions are recorded in [Decisions](#decisions). The
two items this document left for verification on the pinned Spack, that a
toolchain name is accepted inside `packages:all:require` and the set of
variables `spack env activate --sh` emits for a view, both held, so neither
fallback was needed.

---

## Requirements

*Date last modified: Sep 19, 2026*
*Contributors: Xylar Asay-Davis, with Claude Code*

---

### Requirement: Build with unmodified upstream Spack

`mache` must build environments with a released Spack 1.x, checked out from
`spack/spack` at a tag. `mache` must not depend on any fork of the Spack tool.

**Design resolution**

The build script clones `https://github.com/spack/spack.git` at the tag in
[`pins.yaml`](#version-pins) into `spack_path`. The pinned Spack must be 1.2
or newer, for `spack isolate`.

---

### Requirement: Upstream packages come from a released `spack-packages`

Package recipes must come from a released `spack/spack-packages` version.
`mache` must not carry a copy of any package that the pinned release already
provides in the form E3SM needs.

**Design resolution**

The `builtin` repository is a clone of `spack/spack-packages` at a release tag,
registered second in the instance's `repos.yaml`. See
[Package repositories](#package-repositories).

---

### Requirement: E3SM-specific packages and early updates

E3SM must be able to build packages that upstream does not have (`albany`,
`trilinos-for-albany`), and versions or fixes that the pinned upstream release
does not yet have. These must take precedence over the upstream package of the
same name.

**Design resolution**

`E3SM-Project/e3sm-spack-packages`, namespace `e3sm`, is registered first in
`repos.yaml`. Spack resolves a package name to the first repository that
provides it, so `e3sm` shadows `builtin`. Packages that extend an upstream
package subclass it instead of copying it. See
[The e3sm package repository](#the-e3sm-package-repository) and
[Decisions](#decisions) 1 and 7.

---

### Requirement: Reproducible pins per mache release

A `mache` release must fully determine the Spack version, the `builtin`
release and the `e3sm` release used to build environments. Two deployments
from the same `mache` release must concretize the same package sources.

**Design resolution**

`mache/spack/pins.yaml` pins each repository to exactly one of a tag, a commit
or a branch. Releases pin tags or commits. See [Version pins](#version-pins).

---

### Requirement: Pins can be overridden for development

A developer must be able to build against a branch or commit of any of the
three repositories without editing packaged files, to test a recipe before it
is tagged.

**Design resolution**

Overrides are accepted as a file (`--spack-pins <file>` in `mache deploy`, or
`pins=` in `make_spack_env`), from a deployment hook, or from
`spack.pins` in `deploy/config.yaml.j2`. See [Precedence](#precedence).

---

### Requirement: Isolation from user configuration and between releases

Building and activating environments must not read or write the invoking
user's `~/.spack`. Environments built by different `mache` releases must not
share a Spack instance, package repositories or install tree.

**Design resolution**

The build script runs `spack isolate --self` on the instance, which moves the
user scope, caches, stages and bootstrap store under `$SPACK_ROOT`. Package
repositories are cloned under `$SPACK_ROOT/var/spack/package_repos`. Loading
an environment sources a static file and runs no Spack at all. One instance
per `mache` release is what downstream already does by putting the `mache`
version in `spack_path`. See [Spack instance layout](#spack-instance-layout).

---

### Requirement: Machine templates valid for Spack 1.x

Every `<machine>_<compiler>_<mpi>.yaml` template must render to a `spack.yaml`
that Spack 1.x accepts with no deprecated sections, and must select the E3SM
compiler and MPI for every package that needs one.

**Design resolution**

Templates drop the `compilers:` section and `packages:all:compiler`, declare
the compiler as an external with `extra_attributes.compilers`, and select it
through a `toolchains:` entry required for all packages. The three templates
for Intel classic compilers are retired. See
[Environment templates](#environment-templates-for-spack-1x).

---

### Requirement: Loading an environment is fast and needs no Spack

A load script must set up a Spack environment without running Spack, so that
loading costs milliseconds rather than seconds and does not depend on the
user's Spack configuration.

**Design resolution**

At build time `mache` captures `spack env activate --sh <env>` in a clean
shell, rewrites path-like variables as prepends relative to the shell that
sources the file, and writes `activate.sh` and `activate.csh` into the
environment directory. Load scripts source that file. See
[Captured activation](#captured-activation).

---

### Requirement: Existing entry points keep working

`make_spack_env`, `get_spack_script`, `get_modules_env_vars_and_mpi_compilers`
and the `spack:` section of `deploy/config.yaml.j2` must keep their signatures
and meanings, with additions only. Load scripts generated by earlier `mache`
releases must keep working for the environments they were generated for.

**Design resolution**

`spack_path` remains `$SPACK_ROOT` and environments remain managed
environments under `var/spack/environments`, so `view_path` and every path a
downstream hook computes are unchanged. `get_spack_script(load_spack_env=True)`
now emits a `source` of the captured file instead of `spack env activate`.
Old instances are untouched because new releases use new instance paths. See
[Integration](#integration-with-machespack-and-machedeploy).

---

### Requirement: Legacy instances are refused

`mache` must refuse to reuse a `spack_path` that holds a Spack 0.x checkout,
and tell the user to choose a new path.

**Design resolution**

Before touching an existing checkout, the build script reads
`lib/spack/spack/__init__.py` and exits with a message if `__version__` is
below 1.0. Resetting such a checkout to a 1.x tag would leave a 0.x database
and environments underneath it.

---

### Desired: Provenance for each build

Each environment build records the resolved commit of the three repositories
and the resulting `spack.lock`.

**Design resolution**

After `spack install`, the build script copies `spack.lock` and writes
`provenance.yaml` next to the rendered environment YAML in the work directory.

---

## Package repositories

*Date last modified: Sep 20, 2026*

### Repository roles

Three git repositories, listed in Spack's search order:

| Role | Repository | Namespace | Pinned by |
|------|------------|-----------|-----------|
| E3SM overlay | `E3SM-Project/e3sm-spack-packages` | `e3sm` | tag or commit |
| upstream packages | `spack/spack-packages` | `builtin` | release tag, e.g. `v2026.06.0` |
| tool | `spack/spack` | – | release tag, e.g. `v1.2.2` |

`spack-packages` releases are tied to Spack minor releases (`v2026.06.0` with
Spack 1.2) and state which Spack versions they support; the `v2026.06.0` notes
allow any Spack 1.0 or newer. The `e3sm` tag records which `builtin` release
it was tested against.

### The `e3sm` package repository

`E3SM-Project/e3sm-spack-packages` exists as an empty repository (created
Sep 20, 2026, no initial commit) and is seeded from Andrew Nolan's
`open_PR_rebase` branch of `andrewdnolan/spack-packages`; see
[Repository setup](#repository-setup). Its maintainers are Xylar Asay-Davis
and Andrew Nolan, with others added as needed. Layout, following the Spack v2
repository layout and the monorepo index:

```
e3sm-spack-packages/
├── README.md                    # one line per package: why it is here, upstream PR
├── LICENSE
├── spack-repo-index.yaml        # repo_index: paths: [repos/spack_repo/e3sm]
├── ci/
│   ├── versions.yaml            # (spack tag, builtin tag) pairs CI tests against
│   └── specs.txt                # the specs downstream software actually requests
├── .github/workflows/ci.yaml
└── repos/spack_repo/e3sm/
    ├── repo.yaml                # repo: {namespace: e3sm, api: v2.2}
    └── packages/
        ├── albany/package.py
        ├── trilinos_for_albany/package.py
        ├── e3sm_scorpio/package.py
        └── ...
```

Rules for packages in this repository:

- Directory names use the v2 convention (`trilinos_for_albany`, not
  `trilinos-for-albany`).
- Build systems are imported from `spack_repo.builtin.build_systems`; nothing
  is imported from `spack.pkg` or from `spack.*` other than `spack.package`.
- Every package lists `maintainers("xylar", "andrewdnolan")` plus the
  package's upstream owner where one exists (Albany's developers for `albany`
  and `trilinos-for-albany`).
- A package that exists upstream is extended by subclassing, not by copying:

  ```python
  from spack_repo.builtin.packages.parallel_netcdf.package import (
      ParallelNetcdf as BuiltinParallelNetcdf,
  )

  from spack.package import *


  class ParallelNetcdf(BuiltinParallelNetcdf):
      version('1.15.0', sha256='...')
  ```

  A change inside a builder (for example `esmf`'s
  `setup_build_environment`) is made by defining a builder subclass with the
  build system's class name in the same module, which Spack looks up before
  the upstream builder. Verified on Spack 1.2.2 (Sep 21, 2026).

  Directives are inherited and re-executed by a subclass, so one cannot
  remove an upstream `depends_on`. `esmf` needs that (upstream declares
  run-time `python` and `py-pyyaml` dependencies for ESMX, which would put a
  Spack python in the view), so its module deletes the two entries from the
  class's `dependencies` table after the class is created, with a comment;
  the overlay's CI catches a change to that table's shape.
- A package or version that is not E3SM-specific is submitted upstream when it
  is added here. It is deleted from `e3sm` when the pinned `builtin` release
  contains it.

**Rationale**

Subclassing keeps the upstream recipe evolving underneath and leaves only the
delta to maintain. The fork's copy of `esmf` had removed 400 lines of upstream
code and re-added machine-specific `NERSC_HOST` checks; the rebase problem
that closed PR #281 came from exactly this kind of drift.

### Repository setup

The first commit is `mache`'s `LICENSE` (BSD 3-Clause, copyright Energy
Exascale Earth System Model Project) together with the layout above, the CI
workflow and the tag rules, so that every later commit is checked.

- Files derived from `spack-packages`, whether a copied full package or a
  subclass module that reuses upstream code, keep their upstream header,
  `SPDX-License-Identifier: (Apache-2.0 OR MIT)`. E3SM-authored files carry
  a BSD 3-Clause header. The `README` states both. Apache-2.0 and MIT allow
  redistribution inside a BSD-licensed repository, so no relicensing is
  needed.
- No tag is cut until `mache` 5.0.0 is ready to pin one; the first tag is
  `v2026.06.0`. Until then `mache`'s development branch pins the overlay by
  `commit`, and developers testing an overlay branch use `--spack-pins` with
  a `branch` entry rather than editing the packaged file.
- A `mache` unit test guards the release: when `__version__` is not a
  pre-release (`packaging.version.Version.is_prerelease`), every `git` URL in
  `pins.yaml` must be under `github.com/spack/` or `github.com/E3SM-Project/`
  and every ref must be a `tag`. The `spack-v1` development branch carries a
  release-candidate version, as `mache` did for `3.3.0rc1`, so commit pins
  pass until the release is cut.
- Personal forks such as `xylar/e3sm-spack-packages` are ordinary forks for
  pull requests, not development homes ([Decisions](#decisions) 16).

### Continuous integration for `e3sm-spack-packages`

Recommended: concretize every package against the pinned `builtin` on GitHub
runners for every pull request. It is cheap, because nothing is built.

`.github/workflows/ci.yaml` has three jobs:

1. `style`: `spack style` (Ruff-based in Spack 1.2) and
   `spack audit packages` over `repos/spack_repo/e3sm`.
2. `concretize`: a matrix over the `(spack, builtin)` pairs in
   `ci/versions.yaml`. Each job clones Spack at the tag, registers `builtin`
   at its tag and `e3sm` from the checkout, runs `spack compiler find` for
   the runner's GCC, and runs `spack spec -N` on every package directory and
   on every line of `ci/specs.txt`. The bootstrap store is cached with
   `actions/cache` so clingo is downloaded once.
3. `install`: on manual dispatch or weekly, `spack install` of the cheap
   packages (`parallel-netcdf`, `tempestremap`, `tempestextremes`,
   `e3sm-scorpio`) to catch bad checksums and patches. `albany` and
   `trilinos-for-albany` are too slow for a runner and are covered by
   deployments.

`ci/specs.txt` mirrors the specs in the three downstream `spack.yaml.j2`
files, so a recipe change that breaks the variants E3SM asks for fails here
rather than on a machine. The `README` "tested against" statement is derived
from `ci/versions.yaml`, and `mache`'s `pins.yaml` must name a pair listed
there.

### Tags for `e3sm-spack-packages`

Tags are `vYYYY.MM.N`, in the form upstream uses, where `YYYY.MM` is the
oldest `builtin` release in `ci/versions.yaml` at the time of tagging and `N`
counts tags for that era from zero. The tag therefore names the `builtin`
line it is built for, not the month it was cut: a fix for the 2026.06 line
made in October is `v2026.06.3`, and the first tag after `ci/versions.yaml`
drops 2026.06 in favour of 2026.09 is `v2026.09.0`. Tags are independent of
`mache` releases; which tag a `mache` release uses is recorded in that
release's `pins.yaml` and nowhere else ([Decisions](#decisions) 15).

**Rationale**

Concretization of the Albany stack takes a minute or two; the whole matrix
finishes in well under ten minutes and needs no HPC access. Building on
runners would take hours and is what the deployments in [Testing](#testing)
are for.

### Package inventory

What the fork carries on top of Spack 0.23.1, against `spack-packages`
`v2026.06.0`, and where each piece goes:

| Package | In the fork | Upstream `v2026.06.0` | Disposition |
|---------|-------------|------------------------|-------------|
| `albany` | compass tags, `+cuda`, `+mpas`, `+py`, `+omegah`, `+slfad` | `develop` only | `e3sm`, full package |
| `trilinos-for-albany` | full package, 3 patches | absent | `e3sm`, full package |
| `e3sm-scorpio` | 1.9.0–2.0.3, three variants, cce fix | up to 1.8.1 | upstream PR; `e3sm` subclass until released |
| `esmf` | no Python dependency; NetCDF handling on Perlmutter, Chicoma, Frontier; oneAPI `libstdc++` fix | 8.9.1 | `e3sm` subclass for the build-environment changes; upstream the general fixes |
| `tempestextremes` | 2.2.2–2.4.2 as `CMakePackage`, two patches | 2.3, 2.3.1 (package added by Andrew, #853) | upstream PR for 2.4.x; `e3sm` subclass until released |
| `tempestremap` | version for MOAB master, grid-tolerance patch | 2.2.0 (Andrew, #858), but missing `depends_on("c")` although configure runs `AC_PROG_CC` | `e3sm` subclass (patch + `c` dependency); upstream PR for the dependency |
| `parallel-netcdf` | 1.15.0 | 1.14.1 (Andrew, #936) | upstream PR; `e3sm` subclass until released |
| `netcdf-c` | 4.10.1 | 4.10.0 | upstream PR; `e3sm` subclass until released |
| `moab` | 5.6.0, tempest variant | 5.6.0, tempest (Andrew, #872) | drop |
| `nco` | up to 5.3.9 | 5.3.9 | drop |
| `netcdf-fortran` | 4.6.2 | 4.6.2 (Andrew, #835); polaris pins 4.6.3, which neither has | upstream PR for 4.6.3; `e3sm` subclass until released |
| `hdf5` | 1.14.6 preferred | present | drop |
| `visit` | 3.4.0, 3.4.1 | 3.4.1 | drop |
| `superlu` | `BUILD_SHARED_LIBS=ON` | – | `e3sm` subclass if Albany still needs it |
| `trilinos` | `cmake@3.23:` | – | drop |
| `boost`, `rhash` | Intel classic build patches | – | drop; Intel classic is retired ([Decisions](#decisions) 9) |

---

## Version pins

*Date last modified: Sep 20, 2026*

`mache/spack/pins.yaml` is packaged with `mache` (added to `MANIFEST.in`):

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

- Each entry has exactly one of `tag`, `commit` or `branch`; `mache` raises an
  error otherwise.
- The order of `repos` is Spack's search order and is written as such into
  the instance's `repos.yaml`.
- The `repos` entries use the keys of Spack's own `repos.yaml` schema, so an
  entry can be pasted into a Spack configuration unchanged.
- A release of `mache` pins tags only, from `github.com/spack/` or
  `github.com/E3SM-Project/`; a unit test enforces this for non-pre-release
  versions ([Repository setup](#repository-setup)). Development branches may
  pin commits.
- Bumping a pin is an ordinary pull request. The release checklist adds: bump
  pins, run a test deployment on at least one machine.

### Precedence

Highest first:

1. `--spack-pins <file>` on the `mache deploy` command line, or `pins=` (a
   mapping or a path) passed to `make_spack_env`.
2. `ctx.runtime['spack']['pins']` set by a `pre_spack` hook.
3. `spack.pins` in `deploy/config.yaml.j2`.
4. The packaged `pins.yaml`.

Overrides merge per repository. Naming a `branch` for a repository replaces
that repository's `tag` or `commit`. Overrides cannot add or remove
repositories.

---

## Spack instance layout

*Date last modified: Sep 19, 2026*

`spack_path` stays the Spack checkout, `$SPACK_ROOT` ([Decisions](#decisions)
3 and 8). Everything `mache` manages lives under it:

```
<spack_path>/                              # spack/spack at the pinned tag
├── etc/spack/repos.yaml                   # written by mache on every build
├── var/spack/package_repos/
│   ├── e3sm/                              # e3sm-spack-packages at the pinned ref
│   └── builtin/                           # spack-packages at the pinned ref
├── var/spack/environments/<env_name>/     # managed environments
│   ├── spack.yaml
│   ├── spack.lock
│   ├── activate.sh                        # captured activation, sourced by load scripts
│   ├── activate.csh
│   └── .spack-env/view/                   # view path, unchanged
└── opt/spack/                             # install tree, unchanged
```

`etc/spack/repos.yaml` names the two repositories by path, `e3sm` first
([Decisions](#decisions) 2):

```yaml
repos:
  e3sm: <spack_path>/var/spack/package_repos/e3sm/repos/spack_repo/e3sm
  builtin: <spack_path>/var/spack/package_repos/builtin/repos/spack_repo/builtin
```

In Spack 1.x the `spack` scope (`$SPACK_ROOT/etc/spack/`) outranks the user
scope, so a user's own `repos.yaml` cannot replace either entry. `spack
isolate --self` then moves the user scope, misc cache, source cache, build
stages and bootstrap store under `$SPACK_ROOT/etc/spack/isolate/` for
everyone who sources the instance.

`spack isolate --self` (Spack 1.2.2) is not idempotent: it exits 3 when
`etc/spack/isolate` exists, `--overwrite` deletes that directory including
the bootstrap store, and it rewrites the tracked `etc/spack/include.yaml`,
which the `git reset --hard` in step 3 reverts. The build script therefore
always resets the checkout, then moves `etc/spack/isolate` aside, runs
`spack isolate --self`, copies the freshly written `*.yaml` into the old
directory and moves it back, so the bootstrap store survives rebuilds.

### Build flow

One Jinja template, `mache/spack/templates/spack_install.bash.j2`, replaces
both `build_spack_env.template` and `mache/deploy/templates/spack_install.bash.j2`.
Rendered, it does the following in order:

1. Module loads and environment variables from
   `get_spack_script(load_spack_env=False)`, and `TMPDIR`, as today. This
   prologue is also written to `<env_name>.prologue.sh` in the work
   directory for the capture step (one per environment, because a deploy
   run builds every toolchain pair before capturing any of them).
2. Refuse an existing `spack_path` whose Spack is older than 1.0.
3. For each of Spack, `e3sm` and `builtin`: clone if absent, otherwise
   `git fetch`; then check out the pinned tag or commit detached, or
   `reset --hard origin/<branch>` for a branch.
4. Write `etc/spack/repos.yaml`.
5. `source share/spack/setup-env.sh`, `spack isolate --self`, then
   `spack repo list`, which must show both repositories as available.
6. Add the source mirror if `spack_mirror` is set, as today.
7. Remove and recreate the environment from the rendered YAML, activate it,
   `spack install`, as today.
8. Copy `spack.lock` to `<env_name>.spack.lock` and write
   `<env_name>.provenance.yaml` with the three resolved commits into the
   work directory.
9. Run `custom_spack`.

Activation is captured afterwards, in a separate step; see
[Captured activation](#captured-activation).

Removed from the build script: the `SPACK_PYTHON` search for a Python older
than 3.12, and the SSH clone URL in the legacy template.

Spack 1.2's installer schedules package builds concurrently and draws a
terminal UI. The UI is off when output goes to a pipe or log file (verified
on 1.2.2), and `spack.build_jobs` from deploy config (or `build_jobs=` in
`make_spack_env`) is passed as `spack install -j`.

---

## Environment templates for Spack 1.x

*Date last modified: Sep 19, 2026*

All 25 packaged templates carry a `compilers:` section and
`packages:all:compiler`, both of which Spack 1.x deprecates or ignores. Three
are retired rather than migrated ([Decisions](#decisions) 9):
`compy_intel_impi.yaml`, `chrysalis_intel-classic_openmpi.yaml` and
`chrysalis_intel-classic_impi.yaml`. Their compiler, Intel 20.x, has no
package in any `spack-packages` release. Retiring them removes the templates
only; `MPI_COMPILERS` and the `config_machines.xml`-derived shell snippets for
`intel-classic` are unchanged.

The migrated `chrysalis_gnu_openmpi.yaml`, abridged:

```yaml
{%- set compiler = "gcc@11.2.0" %}
{%- set mpi = "openmpi@4.1.6" %}
spack:
  specs:
  - {{ mpi }}
{%- if e3sm_lapack %}
  - intel-oneapi-mkl
{%- endif %}
  - hdf5
  - netcdf-c
  - netcdf-fortran
  - parallel-netcdf
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
{%- if e3sm_lapack %}
        lapack: [intel-oneapi-mkl@2022.1.0]
{%- endif %}
    gcc:
      externals:
      - spec: {{ compiler }}
        prefix: /gpfs/fs1/soft/chrysalis/spack/opt/spack/linux-centos8-x86_64/gcc-9.3.0/gcc-11.2.0-bgddrif
        modules:
        - gcc/11.2.0-bgddrif
        extra_attributes:
          compilers:
            c: /gpfs/fs1/soft/chrysalis/spack/opt/spack/linux-centos8-x86_64/gcc-9.3.0/gcc-11.2.0-bgddrif/bin/gcc
            cxx: /gpfs/fs1/soft/chrysalis/spack/opt/spack/linux-centos8-x86_64/gcc-9.3.0/gcc-11.2.0-bgddrif/bin/g++
            fortran: /gpfs/fs1/soft/chrysalis/spack/opt/spack/linux-centos8-x86_64/gcc-9.3.0/gcc-11.2.0-bgddrif/bin/gfortran
      buildable: false
    openmpi:
      externals:
      - spec: {{ mpi }}
        prefix: /gpfs/fs1/soft/chrysalis/spack/opt/spack/linux-centos8-x86_64/gcc-11.2.0/openmpi-4.1.6-ggebj5o
        modules:
        - openmpi/4.1.6-ggebj5o
      buildable: false
    # remaining externals unchanged
```

The changes, applied to every remaining template:

1. The `compilers:` section is deleted. Its `environment`, `flags` and
   `extra_rpaths` move under the compiler external's `extra_attributes`, for
   example the `PKG_CONFIG_PATH` prepend on Perlmutter.
2. `packages:all:compiler` is deleted. A toolchain named `mache` selects the
   compiler for `c`, `cxx` and `fortran` only where a package depends on that
   language, and `packages:all:require` applies it to everything. The name
   `mache` cannot collide with a package name; compiler names such as `intel`
   or `gnu` could.
3. `%{{ compiler }}` is removed from every spec: root specs, externals and
   providers ([Decisions](#decisions) 4). The compiler is no longer a root
   spec, so it no longer appears in the view; MPI stays a root so its
   wrappers do.
4. Compiler package names follow `spack-packages`: `gcc`, `nvhpc`, `cce`, and
   `intel-oneapi-compilers` for both today's `intel@2025.x` and `oneapi@x`.
5. `extra_attributes.compilers` keeps the keys `c`, `cxx` and `fortran` that
   the templates on `main` already use.
6. The `e3sm_hdf5_netcdf` and `exclude_packages` handling is unchanged;
   `_filter_yaml_data` already removes root specs, externals and providers by
   package name.

Implementation may use the explicit conditional form
`require: ["%[when=%c]c={{ compiler }} %[when=%cxx]cxx={{ compiler }} %[when=%fortran]fortran={{ compiler }}"]`
if a toolchain name inside `require` is not accepted by the pinned Spack.

### Spec semantics for downstream

`mache` no longer appends `%{{ compiler }}` to specs from
`deploy/spack.yaml.j2` or `spack_specs` ([Decisions](#decisions) 4). Specs
pass through unchanged. In Spack 1.x `%` means "direct dependency", and
anything after it binds to that dependency: `trilinos %gcc +mpi` asks for
`gcc+mpi`. Downstream specs must therefore put variants before any `%`, and
normally need no `%` at all. `spack style --spec-strings` reports the old
ordering.

### Validation of rendered YAML

After rendering, `mache` fails fast if the YAML still contains a top-level
`compilers` key or `packages.all.compiler`, naming the template. This catches
un-migrated `deploy/spack/<machine>_<compiler>_<mpi>.yaml` overrides and
`yaml_template` files before Spack produces a less direct error.

---

## Captured activation

*Date last modified: Sep 19, 2026*

`spack env activate` runs Python, loads the package repositories and calls
every package's `setup_run_environment` on each shell start. Polaris users
pay that on every `source load_polaris_*.sh`. Instead, `mache` captures the
result once at build time ([Decisions](#decisions) 10 and 11).

### What Spack emits

`spack env activate --sh <env>` prints `export NAME=<value>;` for every
variable that activation changes, with the *full* new value computed from
the calling process's environment, plus `export SPACK_ENV=...;` and an alias.
For `PATH` that value is the view's `bin` followed by the whole `PATH` of the
capturing shell. Run-time activation does not load external modules; the
variables come from prefix inspections of the view (`PATH`, `MANPATH`,
`PKG_CONFIG_PATH`, `CMAKE_PREFIX_PATH`, `ACLOCAL_PATH`, plus anything added
by `modules:prefix_inspections`), from packages' `setup_run_environment`, and
from `env_vars:` in `spack.yaml`.

### Capture step

After `post_spack` hooks have run, so that a hook such as compass's
`_set_ld_library_path_for_spack_env` is reflected, `mache` runs one fresh
login shell per environment:

```
env -i bash -l -c '
  source <work_dir>/spack/<env>.prologue.sh    # same modules as the build
  source <spack_path>/share/spack/setup-env.sh
  env -0 > <work_dir>/spack/<env>.env_before
  spack env activate --sh <env> > <work_dir>/spack/<env>.raw_activate.sh
'
```

`mache` then parses the raw output with `shlex` and rewrites it:

- `alias` lines are dropped.
- For a variable in `PATH_LIKE_ENV_VARS` (already defined in
  `mache/spack/shared.py`), the new value is split on `:` and every element
  not present in the `env_before` value is kept, in order, as `X`. The
  snippet prepends `X`:

  ```sh
  export PATH="/path/to/view/bin${PATH:+:$PATH}"
  ```

  ```csh
  if ($?PATH) then
    setenv PATH "/path/to/view/bin:$PATH"
  else
    setenv PATH "/path/to/view/bin"
  endif
  ```

  Elements that were present before and are absent afterwards are ignored
  with a warning in the build log. An empty `X` emits nothing. Spack gives
  `MANPATH` a trailing colon so `man` keeps its default search path; the
  rendered prepend keeps that when the variable was unset
  (`export MANPATH="X:${MANPATH:-}"`). Prefix inspections of externals with
  `prefix: /usr` add entries such as `/usr/share/pkgconfig`; these are new
  elements too and are kept in Spack's order.
- Every other variable is set to its literal value, `SPACK_ENV` included.
- The snippet starts by setting `SPACK_ROOT` and prepending `$SPACK_ROOT/bin`
  to `PATH`, which `setup-env.sh` used to do. `spack` is then a plain
  executable, not the shell function, and with `SPACK_ENV` set commands such
  as `spack find` and `spack config get modules` act on the loaded
  environment; `spack env activate` and `spack load` are not available. No
  downstream package runs `spack` after loading, so this is for maintainers
  only ([Decisions](#decisions) 13).

Both `activate.sh` and `activate.csh` are rendered from the same parsed list
and written into `var/spack/environments/<env>/`. Recreating the environment
removes them; a build that fails before the capture step leaves none, and
`load_existing_spack_envs` errors if they are missing.

### Loading

`get_spack_script(load_spack_env=True)` emits

```
source <spack_path>/var/spack/environments/<env_name>/activate.<shell>
```

in place of the `setup-env` and `spack env activate` lines, followed by the
`config_machines.xml`-derived modules and variables in the same order as
today. Because the snippet prepends rather than assigns, the final `PATH`
order is the same as with dynamic activation.

The "software" environment keeps its `PATH`-only handling in
`mache/deploy/spack.py`; it never activated.

### What hooks see

`post_spack` hooks run before the capture step and may need an activated
environment: E3SM-Unified's hook appends `spack_result['activation']` to a
build script and then compiles `mpi4py` against the view's `mpicc`. The
`activation` string in `ctx.runtime['spack']['results']` is therefore the
dynamic form (`source setup-env.sh` + `spack env activate`) during a deploy
run, regardless of `spack.activation`. Only the generated load scripts use
the captured `source` line ([Decisions](#decisions) 14).

`spack.activation: captured | dynamic` in deploy config, and
`activation=` in `make_spack_env`, select the old behaviour for debugging.
`captured` is the default.

---

## Integration with `mache.spack` and `mache.deploy`

*Date last modified: Sep 19, 2026*

New module `mache/spack/pins.py`:

- `load_pins(overrides=None)` reads the packaged `pins.yaml`, merges overrides
  (a mapping, a path, or a sequence of these in [precedence](#precedence)
  order, lowest first), and validates one ref per repository.
- `merge_pins`, `validate_pins`, `checkout_command`, `release_pins_are_valid`.
- `render_repos_yaml(spack_path, pins)` returns the instance `repos.yaml`.

New module `mache/spack/install.py`:

- `render_install_script(...)` renders the shared build template for both
  callers; `write_prologue` / `prologue_path` handle `<env_name>.prologue.sh`.

New module `mache/spack/activation.py`:

- `capture_activation(spack_path, env_name, prologue_path, work_dir)` runs
  the capture shell and returns the rewritten modifications.
- `parse_raw_activation`, `parse_env_before`, `rewrite_modifications` are the
  testable pieces of that; `render_activation(modifications, shell,
  spack_path)` returns the snippet text.
- `write_activation_files(spack_path, env_name, modifications)` writes both
  files; `activation_source_line` gives the `source` line for a shell.

`mache.spack.env.make_spack_env` gains keywords `pins=None` (mapping or path),
`activation='captured'` and `build_jobs=None`, and calls the capture step
after `custom_spack`. `get_spack_script` gains `activation='captured'`. Its
docstring no longer describes the `spack_for_mache_<version>` branch.

`mache.deploy`:

- `spack.pins` and `spack.activation` are accepted in `deploy/config.yaml.j2`
  and merged into the effective Spack config with the existing runtime
  override mechanism.
- `--spack-pins <file>` is added to `cli_spec.json.j2`, routed to `deploy`.
- `_install_spack_env` stops computing a branch from `mache.version` and
  renders the shared template.
- `run.py` calls the capture step for every library environment between the
  `post_spack` and `pre_publish` hooks. `SpackDeployResult.activation` keeps
  the dynamic form, so hooks that source it keep working; a new
  `SpackDeployResult.load_activation` holds the captured `source` line (the
  path is known before capture) and replaces `result.activation` in
  `_write_load_script`. Under `spack.activation: dynamic` both fields are
  the same. `load_existing_spack_envs` errors if `activate.sh` is missing
  under `captured`.

Removed: `mache/spack/templates/build_spack_env.template` and
`mache/deploy/templates/spack_install.bash.j2`, replaced by the one template.
Removed: `compy_intel_impi.yaml`, `chrysalis_intel-classic_openmpi.yaml`,
`chrysalis_intel-classic_impi.yaml`.

Unchanged: `list_machine_compiler_mpilib`, `MPI_COMPILERS`, `cray_compilers`,
`extract_spack_from_config_machines` and the shell-template overrides.

---

## Downstream migration

*Date last modified: Sep 19, 2026*

E3SM-Unified, compass and polaris all deploy through `mache deploy` today.
None passes a `yaml_template`. Their `deploy/spack.yaml.j2` specs contain no
`%`, so they need no spec changes. Compass and polaris ship one identical
override, `deploy/spack/katara_gnu_openmpi.yaml`, in the 0.x form (a
`compilers:` block, `packages:all:compiler`, `%{{ compiler }}` on every
spec); E3SM-Unified ships none.

For all three:

- Use a new `spack_path`. Downstream already keys it on the `mache` version;
  a 0.x checkout at the old path is refused, not converted.
- Bump `mache` in `deploy/pins.cfg` to 5.0.0 and run `mache deploy update`.
- Load-script consumption does not change; `MACHE_DEPLOY_SPACK_LIBRARY_VIEW`
  and the view-relative paths in `deploy/load.sh` are the same. None of the
  three `deploy/load.sh` snippets runs `spack`; they locate tools with
  `command -v` on the view's `bin`.
- `post_spack` hooks that source `spack_result['activation']` (E3SM-Unified)
  or `setup-env.sh` directly (compass) keep working; see
  [What hooks see](#what-hooks-see).
- Maintainer docs that say to run `spack find` or `spack config get ...`
  after loading keep working, because `$SPACK_ROOT/bin` is on `PATH` and
  `SPACK_ENV` is set. Docs that want the shell function (for
  `spack env activate` or `spack load`) should say
  `source $SPACK_ROOT/share/spack/setup-env.sh` first. References to the
  `spack_for_mache_<version>` branch in those docs need updating.

For compass and polaris additionally:

- Migrate `deploy/spack/katara_gnu_openmpi.yaml` as in
  [Environment templates](#environment-templates-for-spack-1x). It uses
  `prefix: /usr` for both `gcc` and `openmpi`, so it also needs
  `extra_attributes.compilers` paths.

For compass additionally:

- The `post_spack` hook that adds `LD_LIBRARY_PATH` to
  `modules:prefix_inspections` keeps working because capture runs after
  `post_spack`. Moving that setting into the katara override or into
  `spack.yaml.j2` is optional.

The `E3SM-Project/spack` fork is archived once the last `mache` 4.x release
that uses it is no longer deployed. Its `spack_for_mache_*` branches stay for
existing instances.

---

## Testing

*Date last modified: Sep 22, 2026*

Unit tests in `mache`:

- pins: merge precedence, one-ref validation, branch replacing tag.
- `repos.yaml` rendering and search order.
- Every packaged template renders for its `(machine, compiler, mpi)` and
  contains a `mache` toolchain, `packages.all.require`, no `compilers` key and
  no `packages.all.compiler`.
- Build-script rendering for tag, commit and branch pins; legacy refusal.
- Activation rewrite: prepend of new elements, unset baseline, `MANPATH`
  trailing colon, literal non-path variables, alias dropped, csh rendering,
  from a recorded `raw_activate.sh` and `env_before` pair.

Deployments, each compared against `spack env activate --sh` run
interactively and followed by a rerun on the existing instance:

1. Chrysalis with polaris: the default path, Cray-free.
2. Chrysalis with E3SM-Unified: the `e3sm` subclass packages (`e3sm-scorpio`,
   `esmf`, `tempestremap`).
3. Chrysalis with compass and Albany: the E3SM-only packages and the
   `LD_LIBRARY_PATH` hook.
4. Perlmutter `pm-cpu` `gnu`: Cray wrappers `cc`/`CC`/`ftn` as compiler
   paths, `gcc-runtime` detection through them, and the moved
   `PKG_CONFIG_PATH` prepend.
5. Aurora `intel` and `intelgpu`: the oneAPI compiler model, and an Omega
   build through the load script.

The results are in the `Testing` comment of
[PR #492](https://github.com/E3SM-Project/mache/pull/492).

---

## Prior work

*Date last modified: Sep 19, 2026*

Andrew Nolan's `spack-v1.0.0` branch (PR #281, opened Aug 2025, closed Apr
2026 as a reference rather than a base) and his branches of
`andrewdnolan/spack-packages`.

Kept:

- A separate E3SM package repository in the v2 layout with namespace `e3sm`
  and a `spack-repo-index.yaml`. His `open_PR_rebase` branch is the seed of
  `e3sm-spack-packages`: `albany`, `trilinos_for_albany`, `esmf`, `moab`,
  `parallel_netcdf`, `tempestextremes`, `tempestremap`, already converted to
  v2 imports and directory names.
- A pin file with exactly one of tag, branch or commit per repository, and the
  matching validation.
- Removing `compilers:` and `packages:all:compiler` from templates, and moving
  compiler `environment` settings into `extra_attributes`.
- Renaming Intel compiler externals to the `intel-oneapi-compilers*` packages.
- Six upstream PRs (#833, #835, #853, #858, #872, #936) that make `nco`,
  `netcdf-fortran`, `tempestextremes`, `tempestremap`, `moab` and
  `parallel-netcdf` unnecessary in the overlay at the versions they added.

Changed:

- One Spack instance per `mache` release, not one clone per
  `(compiler, mpi)` (`spack/spack_for_{compiler}_{mpi}` in his branch;
  [Decisions](#decisions) 5).
- `mache` clones the package repositories itself and writes a path-based
  `repos.yaml`, instead of `spack repo add` and `spack repo update --scope
  site` at build time.
- Pins in YAML using Spack's `repos.yaml` keys, instead of `config.cfg`.
- No `%{{ compiler }}` on externals; the toolchain selects compilers.
- `extra_attributes.compilers` keys `c`/`cxx`/`fortran`, not `cc`/`f77`/`fc`.
- `https://` clone URLs, not `git@github.com:`.

---

## Decisions

*Date last modified: Sep 19, 2026*

Rejected alternatives and resolved questions, cited from the sections they
affect.

1. **Packages inside `mache`** (`mache/spack/repo/spack_repo/e3sm/...`),
   versioned with `mache` like the fork branches were. Rejected: a recipe fix
   would need a `mache` release on conda-forge; the overlay is useful to Spack
   users who do not use `mache`; `package.py` files need
   `from spack.package import *`, which the repo's lint forbids. See
   [Package repositories](#package-repositories).
2. **Git-based `repos.yaml` entries** (`git:` plus `tag:` and `destination:`)
   with Spack doing the cloning. Rejected: `mache` and Spack would both own
   the clone, and Spack's behaviour when the pinned ref changes under an
   existing clone, or when only a mirror is reachable, is undocumented.
   Path-based entries make `spack repo list` show the same thing either way.
   See [Spack instance layout](#spack-instance-layout).
3. **An instance root above the Spack checkout** (`<spack_path>/spack`,
   `<spack_path>/spack-packages`, `<spack_path>/envs`). Rejected: it changes
   `view_path`, environment paths and every downstream hook that derives
   them, for no gain; `spack isolate --self` already targets `$SPACK_ROOT`.
   See [Spack instance layout](#spack-instance-layout).
4. **Appending `%{{ compiler }}` to every spec**, as today. Rejected: in 1.x
   variants after `%` bind to the compiler, externals do not take a compiler,
   and downstream specs would break silently. See
   [Environment templates](#environment-templates-for-spack-1x).
5. **One Spack instance per toolchain** (Andrew's branch). Rejected: disk and
   bootstrap cost per toolchain; Spack supports many environments per
   instance and reuses common builds across them. See [Prior work](#prior-work).
6. **Keeping a Spack 0.23 code path** behind a pin. Rejected: it keeps the
   fork alive, keeps the Python 3.12 workaround, and doubles the templates.
   `mache` 4.0.0 was released in Sep 2026 before this design landed, so
   this design ships as 5.0.0.
7. **Copying upstream packages into `e3sm`** rather than subclassing.
   Rejected: this is how the fork drifted. See
   [The e3sm package repository](#the-e3sm-package-repository).
8. **Independent environments** (`spack env create -d <dir>`) outside
   `$SPACK_ROOT`. Rejected for now: managed environments keep every existing
   path; independent environments add nothing until instances are shared
   across `mache` releases, which this design forbids. See
   [Spack instance layout](#spack-instance-layout).
9. **Porting the legacy `intel` compiler package** into `e3sm` to keep
   `compy_intel_impi` and `chrysalis_intel-classic_*`. Rejected: `mache`
   drops Intel classic support with this transition; the three templates and
   the `boost` and `rhash` patches go. See
   [Environment templates](#environment-templates-for-spack-1x).
10. **Dynamic activation** (`spack env activate` in load scripts), as today.
    Rejected as the default: seconds per shell, and a dependency on Spack and
    the package repositories at load time. Kept behind
    `spack.activation: dynamic` for debugging. See
    [Captured activation](#captured-activation).
11. **Capturing `spack env activate --sh` verbatim**, and **having `mache`
    compute the activation itself** from the view layout. Rejected: verbatim
    output assigns the capturing shell's full `PATH` and would clobber the
    user's; a `mache`-computed snippet would lose packages'
    `setup_run_environment` (for example `ESMFMKFILE` from `esmf`) and
    `env_vars:`. The rewrite keeps both. See
    [Captured activation](#captured-activation).
12. **A fork of `spack/spack-packages`** as the overlay's home. Rejected: the
    overlay shares no history with upstream, so a fork only confuses GitHub's
    fork tooling. `E3SM-Project/e3sm-spack-packages` is a standalone
    repository; upstream contributions go from personal forks as Andrew's did.
13. **`spack` on `PATH` after loading.** Resolved on Sep 19, 2026: keep
    `$SPACK_ROOT/bin` on `PATH` and export `SPACK_ENV`. A survey of
    E3SM-Unified, compass, polaris, MPAS-Analysis, MPAS-Tools, zppy,
    e3sm_diags and Omega found no code that runs `spack` after a load script
    is sourced; the only uses are build-time hooks, which source
    `setup-env.sh` themselves or use the hook-time activation string, and
    maintainer troubleshooting docs, which the plain executable satisfies.
    Dropping `spack` from `PATH` entirely was the alternative; it saves
    nothing and breaks those docs. See
    [Captured activation](#captured-activation).
14. **Giving `post_spack` hooks the captured `source` line.** Rejected:
    capture must run after `post_spack` so that compass's
    `prefix_inspections` change is reflected, but E3SM-Unified's hook
    sources the activation string before that, when `activate.sh` does not
    yet exist. Hooks get dynamic activation; load scripts get the captured
    form. Capturing twice (before and after hooks) was the other option and
    doubles the slowest step for no benefit. See
    [What hooks see](#what-hooks-see).
15. **Tagging `e3sm-spack-packages` with the `mache` version that pins it.**
    Rejected on Sep 19, 2026: `mache` releases far more often than recipes
    change, so most tags would be either no-op tags or fixes with no honest
    `mache` number; the tag would have to be chosen before `mache` is
    released and would lie if the release slipped; and the number means
    nothing to Spack users outside `mache`. Independent SemVer was also
    considered and rejected: "breaking" is ill-defined for a recipe overlay
    and collapses into "the `builtin` era changed", which CalVer already
    says. Tags follow upstream's `vYYYY.MM.N`, with `YYYY.MM` the oldest
    supported `builtin` era. See
    [Tags for e3sm-spack-packages](#tags-for-e3sm-spack-packages).
16. **Starting the overlay in a personal repository**
    (`xylar/e3sm-spack-packages`) and pushing its history to the
    organization later. Considered on Sep 20, 2026 while the organization
    repository did not exist; superseded on Sep 21, 2026 when
    `E3SM-Project/e3sm-spack-packages` was created empty. Development starts
    there directly. What was kept from the plan is the license handling for
    upstream-derived files and the release guard on `pins.yaml`. See
    [Repository setup](#repository-setup).
