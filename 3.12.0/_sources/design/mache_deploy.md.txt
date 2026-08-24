# Design Document: mache.deploy

## Summary

`mache.deploy` is a subpackage of `mache` that provides a unified, documented,
and extensible mechanism for deploying combined **pixi** (conda packages) and
**spack** environments for E3SM-supported software (e.g. Polaris, Compass,
E3SM-Unified) on E3SM-supported HPC systems.

The primary motivation is to replace the redundant, subtly divergent, and
poorly documented deployment logic currently embedded independently in these
packages with a single, shared implementation. This improves maintainability,
ensures feature parity across target software, and provides a scalable model
for future E3SM software with mixed pixi/spack dependencies.

In this document, software such as Polaris or E3SM-Unified that uses
`mache.deploy` is referred to as the **target software**.

---

## Requirements

*Date last modified: Dec 29, 2025*
*Contributors: Xylar Asay-Davis, Althea Denlinger*

---

### Requirement: A mechanism to begin deployment

The target software must provide a user-facing entry point to begin deployment.
 This mechanism cannot depend on `mache` already being installed, because
  deployment is precisely how `mache` is introduced.

**Design resolution**

Each target software provides a small, stable `deploy.py` script at repository
root. This script:

- Parses command-line arguments defined declaratively
- Downloads a standalone `bootstrap.py` script from the `mache` repository
- Executes `bootstrap.py` to install pixi (if needed) and `mache`

---

### Requirement: A mechanism to install pixi

If pixi is not already installed, the deployment process must be able to
install it automatically.

**Design resolution**

The standalone `bootstrap.py` script (downloaded from `mache`) handles:

- Installing pixi into a user-specified or inferred location
- Using pixi in a non-interactive, non-login context (no reliance on shell
  init)

This logic is intentionally duplicated only in `bootstrap.py`, which runs
before `mache` is available.

---

### Requirement: A mechanism to install mache

The target software must support installing:

- A released version of `mache` from conda-forge (via pixi), or
- A developer-specified fork and branch (for testing and development)

**Design resolution**

- `bootstrap.py` creates a minimal *bootstrap* pixi environment
- `mache` is installed into that environment either:
  - via a pixi manifest that depends on `mache==<version>` (from conda-forge),
    or
  - via cloning and installing from a fork/branch (installed into the pixi
    environment)

---

### Requirement: A way for target software to specify pixi packages

The target software must define:

- Which conda packages are installed (via pixi)
- Version constraints
- Variants across machines, compilers, MPI, etc.

**Design resolution**

The target software provides two inputs:

- `deploy/pixi.toml.j2`: a Jinja2-templated pixi manifest that declaratively
  defines the pixi environment dependencies
- `deploy/config.yaml.j2`: a Jinja2-templated YAML configuration file that
  defines deployment options and variants (channels, prefix, MPI selection,
  feature toggles, etc.)

`mache.deploy` renders and interprets these files to construct a pixi
environment. The pixi manifest (`deploy/pixi.toml.j2`) is the authoritative
specification of the pixi environment dependencies.

---

### Requirement: A way for target software to specify spack packages

The target software must define:

- Spack packages
- Versions, variants, and compiler/MPI combinations

**Design resolution**

- Spack specifications are included in `deploy/config.yaml.j2`
- `mache.deploy` interprets and realizes these specs using spack
- Spack logic lives entirely inside `mache`, not in the target software

---

### Requirement: Support for environment variants

The target software must support multiple deployment variants, including:

- Different machines
- Different compilers and MPI stacks
- Optional components (e.g., Trilinos, Albany, PETSc)

**Design resolution**

- Variants are declared declaratively in `deploy/config.yaml.j2`
- Users select variants via command-line options to `deploy.py` /
  `mache deploy`
- Variant selection is propagated consistently to pixi, spack, modules, and
  environment variables

---

### Requirement: Provide environment variables

Some target software requires environment variables to be set to function
correctly.

**Design resolution**

- Environment variables are specified declaratively in `deploy/config.yaml.j2`
- `mache.deploy` generates shell *load* scripts that:
  - activate pixi environments
  - load spack environments
  - load system modules
  - export required environment variables

---

### Requirement: Provide a mechanism to load environments

After deployment, users need a simple way to load the environment.

**Design resolution**

`mache.deploy` generates load scripts, for example:

- `load_<software>.sh` (no toolchain-specific Spack environment)
- `load_<software>_<machine>_<compiler>_<mpi>.sh` (toolchain-specific)

Including `<machine>` avoids filename collisions on shared filesystems where
multiple machines (or machine partitions exposed as distinct machine names)
share compiler and MPI naming.

These scripts encapsulate:

- Pixi activation
- Spack environment activation
- Module loads
- Environment variables

Target software documentation points users to these scripts.

---

### Requirement: Conditional spack deployment

Allow day-to-day developers to avoid rebuilding spack, while allowing
maintainers to do full shared-environment deployments when needed.

**Design resolution**

**Mechanisms**

- `deploy/config.yaml.j2` includes a default such as:
  - `spack.deploy: true | false` (deploy all supported spack envs, or none)
  - `spack.spack_path: <path>` (default checkout path for spack)
  - `spack.supported: true | false` (whether the target supports a “library”
    spack env)
  - `spack.software.supported: true | false` (whether the target supports a
    “software” spack env)
- `deploy.py` exposes CLI flags such as:
  - `--deploy-spack` (force-enable spack deployment)
  - `--no-spack` (disable all spack use for a single run)
  - `--spack-path <path>` (temporary override for `spack.spack_path`)

**Precedence**

1. If the user passes `--no-spack`, all spack use is disabled for that run.
2. Otherwise, if the user passes `--deploy-spack`, spack deployment is enabled
   regardless of the config default.
3. Otherwise, fall back to the `config.yaml.j2` default for deployment and
   reuse any supported pre-existing spack environments in load scripts.

For spack checkout path resolution:

1. If the user passes `--spack-path`, it takes highest priority.
2. Otherwise, a deployment hook may set `ctx.runtime['spack']['spack_path']`.
3. Otherwise, fall back to `spack.spack_path` in `config.yaml.j2`.

**Rationale**

- *E3SM-Unified maintainer workflow*: default `spack.deploy: true`
- *Polaris developer workflow*: default `spack.deploy: false`
- *Polaris maintainer workflow*: run `./deploy.py --deploy-spack ...` when
  producing or updating a shared spack environment
- *Temporary testing workflow*: run
  `./deploy.py --spack-path /tmp/<my-spack> ...` to avoid editing and
  accidentally committing `deploy/config.yaml.j2`

---

### Desired: Skip pixi deployment (future)

Some deployments may want to reuse a shared pixi environment.

**Design resolution (future)**

- Supported declaratively
- `mache.deploy` would still provide load scripts and environment management

---

### Desired: Testing target software (future)

It should be possible to validate that deployment succeeded.

**Design resolution (future)**

- Target software may optionally provide post-deployment tests
- `mache.deploy` can expose hooks for running these tests

---

## Conceptual Design

*Date last modified: Dec 29, 2025*
*Contributors: Xylar Asay-Davis, Althea Denlinger*

---

### Three-stage deployment model

Deployment proceeds in three clearly separated stages:

1. **Target software entrypoint (`deploy.py`)**
   - Runs with system Python (minimal assumptions)
   - Parses CLI from a declarative spec
   - Downloads `bootstrap.py`
   - Invokes `bootstrap.py`

2. **Bootstrap stage (`bootstrap.py`)**
   - Standalone script, not part of the `mache` package
   - Installs pixi if needed
   - Creates a bootstrap pixi environment
   - Installs `mache`

3. **Deployment stage (`mache deploy`)**
   - Runs with full `mache` installed
   - Interprets `deploy/config.yaml.j2`
   - Creates pixi and spack environments
   - Generates load scripts

This separation is intentional and strictly enforced.

---

## CLI Design and Sharing

*Date last modified: Jan 26, 2026*
*Contributor: Xylar Asay-Davis*

### Problem

- `deploy.py`, `bootstrap.py`, and `mache deploy` all need overlapping CLI
  arguments
- Duplicating argparse definitions across repositories is fragile
- Users expect `./deploy.py --help` to be authoritative

### Design resolution: `cli_spec.json(.j2)`

Each target software includes `deploy/cli_spec.json` rendered from the
packaged template, plus an optional downstream-owned
`deploy/custom_cli_spec.json`, which declaratively define:

- Command-line flags
- Help text
- Destinations
- Routing (`deploy`, `bootstrap`, `run`)

**Usage**

- `deploy.py`
  - Builds its argparse interface from `deploy/cli_spec.json` plus optional
    `deploy/custom_cli_spec.json`
  - Forwards appropriate arguments to `bootstrap.py` and `mache deploy run`
- `mache deploy run`
  - Builds its CLI from the packaged `mache/deploy/templates/cli_spec.json.j2`
    plus optional `deploy/custom_cli_spec.json`
  - Uses the same source template as `mache deploy init/update` for the
    generated portion

**Benefits**

- Single source of truth for user-facing CLI
- No duplication across repositories
- Consistent `--help` output
- Safe downstream extension point for repo-specific flags

---

## Starter Templates and Initialization
*Date last modified: Jan 26, 2026*
*Contributor: Xylar Asay-Davis*

### Templates

`mache.deploy` provides templates for:

- `deploy.py`
- `cli_spec.json.j2`
- `custom_cli_spec.json`
- `pins.cfg`
- `config.yaml.j2.j2` (renders to `deploy/config.yaml.j2`)
- `pixi.toml.j2.j2` (renders to `deploy/pixi.toml.j2`)
- `spack.yaml.j2`
- `hooks.py.j2`
- `load.sh.j2`
- `spack_install.bash.j2`

These templates include placeholders for:

- Software name
- Pinned `mache` version
- Minimal configuration scaffolding

---

### `mache deploy init`

A command that:

- Copies templates into a target software repository
- Fills in required placeholders
- Creates a minimal, working deployment setup
- Writes: `deploy.py`, `deploy/cli_spec.json`, `deploy/pins.cfg`,
  `deploy/custom_cli_spec.json`, `deploy/config.yaml.j2`,
  `deploy/pixi.toml.j2`, `deploy/spack.yaml.j2`, `deploy/hooks.py`, and a
  placeholder `deploy/load.sh`

---

### Updating mache versions

When a target software updates its pinned `mache` version:

- `deploy.py` and `deploy/cli_spec.json` should be updated from the matching
  `mache` release
- `deploy/custom_cli_spec.json`, `deploy/pins.cfg`, `deploy/config.yaml.j2`,
  and `deploy/pixi.toml.j2` remain software-owned

The `mache deploy update` command updates only `deploy.py` and
`deploy/cli_spec.json`.

The intended upgrade workflow is therefore:

1. `./deploy.py --bootstrap-only --mache-version <new_version>`
2. `mache deploy update --software <software> --mache-version <new_version>`
   inside the bootstrap environment
3. manual edit of `deploy/pins.cfg` so the pinned `mache` version matches

---

## Package Organization

*Date last modified: Jan 26, 2026*
*Contributor: Xylar Asay-Davis*

All deployment-related assets live under:

```
mache/deploy/
├── bootstrap.py        # standalone script
├── cli.py              # mache deploy CLI
├── cli_spec.py         # cli_spec parsing helpers
├── conda.py            # conda/pixi helpers
├── hooks.py            # deployment hook framework
├── init_update.py      # init/update logic for target repos
├── jinja.py            # Jinja helpers
├── machine.py          # machine/deploy config helpers
├── run.py              # deployment runner (called by `mache deploy run`)
├── spack.py            # spack helpers
└── templates/
  ├── deploy.py.j2
  ├── cli_spec.json.j2
  ├── pins.cfg.j2
  ├── config.yaml.j2.j2
  ├── pixi.toml.j2.j2
  ├── spack.yaml.j2
  ├── hooks.py.j2
  ├── load.sh.j2
  └── spack_install.bash.j2
```

Reusable JIGSAW build/install logic now lives outside `mache.deploy` in:

```
mache/jigsaw/
├── __init__.py         # backend selection + build/install orchestration
├── recipe.yaml.j2      # rattler-build recipe template
├── linux-64.yaml.j2    # linux variant template
├── osx-64.yaml.j2      # macOS variant template
└── build.sh            # build script used by the recipe
```

This keeps deployment concerns clearly separated from the rest of `mache`.

---

## Closing Notes

The current design:

- Satisfies all original requirements
- Clarifies responsibilities across stages
- Minimizes redundancy
- Supports both stable users and developers
- Provides a clear path for future growth (init, update, testing)

Most importantly, it turns deployment from an ad hoc per-project liability
into a shared, documented, and evolvable capability.

---

## Testing

*Date last modified: Jan 26, 2026*
*Contributor: Xylar Asay-Davis*

### Polaris

- Full deployment on Chrysalis
- Intel and GNU compilers
- MPAS-Ocean `pr` suite (both compilers)
- Omega `omega_pr` suite (both compilers)

### Planned test deployment of E3SM-Unified

- Not yet started
- Full test deployment on Chrysalis
- GNU compilers
- Test run of MPAS-Analysis
