# Design Document: mache.deploy

## Summary

`mache.deploy` is a subpackage of `mache` that provides a unified, documented, and extensible mechanism for deploying combined **conda** and **spack** environments for E3SM-supported software (e.g. Polaris, Compass, E3SM-Unified) on E3SM-supported HPC systems.

The primary motivation is to replace the redundant, subtly divergent, and poorly documented deployment logic currently embedded independently in these packages with a single, shared implementation. This improves maintainability, ensures feature parity across target software, and provides a scalable model for future E3SM software with mixed conda/spack dependencies.

In this document, software such as Polaris or E3SM-Unified that uses `mache.deploy` is referred to as the **target software**.

---

## Requirements

*Date last modified: Dec 26, 2025*
*Contributors: Xylar Asay-Davis, Althea Denlinger*

---

### Requirement: A mechanism to begin deployment

The target software must provide a user-facing entry point to begin deployment. This mechanism cannot depend on `mache` already being installed, because deployment is precisely how `mache` is introduced.

**Design resolution**

Each target software provides a small, stable `deploy.py` script at repository root. This script:

- Parses command-line arguments defined declaratively
- Downloads a standalone `bootstrap.py` script from the `mache` repository
- Executes `bootstrap.py` to install conda (if needed) and `mache`

---

### Requirement: A mechanism to install Miniforge

If conda is not already installed, the deployment process must be able to install it automatically.

**Design resolution**

The standalone `bootstrap.py` script (downloaded from `mache`) handles:

- Installing Miniforge into a user-specified or inferred location
- Initializing conda for non-interactive shells

This logic is intentionally duplicated only in `bootstrap.py`, which runs before `mache` is available.

---

### Requirement: A mechanism to install mache

The target software must support installing:

- A released version of `mache` from conda-forge, or
- A developer-specified fork and branch (for testing and development)

**Design resolution**

- `bootstrap.py` creates a minimal *bootstrap* conda environment
- `mache` is installed into that environment either:
  - via `conda install mache=<version>`, or
  - via cloning and installing from a fork/branch

---

### Requirement: A way for target software to specify conda packages

The target software must define:

- Which conda packages are installed
- Version constraints
- Variants across machines, compilers, MPI, etc.

**Design resolution**

The target software provides a Jinja2-templated YAML file located at:

`deploy/config.yaml.j2`

`mache.deploy` renders and interprets this file to construct conda environments. This file is the authoritative specification of the conda environment.

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
- Users select variants via command-line options to `deploy.py` / `mache deploy`
- Variant selection is propagated consistently to conda, spack, modules, and environment variables

---

### Requirement: Provide environment variables

Some target software requires environment variables to be set to function correctly.

**Design resolution**

- Environment variables are specified declaratively in `deploy/config.yaml.j2`
- `mache.deploy` generates shell *load* scripts that:
  - activate conda environments
  - load spack environments
  - load system modules
  - export required environment variables

---

### Requirement: Provide a mechanism to load environments

After deployment, users need a simple way to load the environment.

**Design resolution**

`mache.deploy` generates load scripts, for example:

`load_<env>_<machine>_<compiler>_<mpi>.sh`

These scripts encapsulate:

- Conda activation
- Spack environment activation
- Module loads
- Environment variables

Target software documentation points users to these scripts.

---

### Requirement: Conditional spack deployment

Allow day-to-day developers to avoid rebuilding spack, while allowing maintainers to do full shared-environment deployments when needed.

**Design resolution**

**Mechanisms**

- `deploy/config.yaml.j2` includes a default such as:
  - `spack.enabled: true | false`
- `deploy.py` exposes a CLI flag such as `--deploy-spack`

**Precedence**

1. If the user passes `--deploy-spack`, spack deployment is enabled regardless of the config default.
2. Otherwise, fall back to the `config.yaml.j2` default.

**Rationale**

- *E3SM-Unified maintainer workflow*: default `spack.enabled: true`
- *Polaris developer workflow*: default `spack.enabled: false`
- *Polaris maintainer workflow*: run `./deploy.py --deploy-spack ...` when producing or updating a shared spack environment

---

### Desired: Skip conda deployment (future)

Some deployments may want to reuse a shared conda environment.

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

*Date last modified: Dec 26, 2025*
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
   - Installs Miniforge if needed
   - Creates a bootstrap conda environment
   - Installs `mache`

3. **Deployment stage (`mache deploy`)**
   - Runs with full `mache` installed
   - Interprets `deploy/config.yaml.j2`
   - Creates conda and spack environments
   - Generates load scripts

This separation is intentional and strictly enforced.

---

## CLI Design and Sharing

### Problem

- `deploy.py`, `bootstrap.py`, and `mache deploy` all need overlapping CLI arguments
- Duplicating argparse definitions across repositories is fragile
- Users expect `./deploy.py --help` to be authoritative

### Design resolution: `cli_spec.json(.j2)`

Each target software includes `deploy/cli_spec.json` (or template), which declaratively defines:

- Command-line flags
- Help text
- Destinations
- Routing (`bootstrap`, `deploy`, or `both`)

**Usage**

- `deploy.py`
  - Builds its argparse interface from this file
  - Forwards appropriate arguments to `bootstrap.py`
- `mache deploy`
  - Uses the same spec to build its CLI

**Benefits**

- Single source of truth for user-facing CLI
- No duplication across repositories
- Consistent `--help` output

---

## Starter Templates and Initialization

### Templates

`mache.deploy` provides templates for:

- `deploy.py`
- `cli_spec.json.j2`
- `pins.cfg`
- `config.yaml.j2`

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

---

### Updating mache versions

When a target software updates its pinned `mache` version:

- `deploy.py` and `cli_spec.json` should be updated from the matching `mache` release
- `pins.cfg` and `config.yaml.j2` remain software-owned

The `mache deploy update` command automates updating only the shared files.

---

## Package Organization

All deployment-related assets live under:

```
mache/deploy/
├── bootstrap.py        # standalone script
├── cli.py              # mache deploy CLI
├── spec.py             # cli_spec parsing helpers
└── templates/
    ├── deploy.py.j2
    ├── cli_spec.json.j2
    ├── pins.cfg
    └── config.yaml.j2
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

Most importantly, it turns deployment from an ad hoc per-project liability into a shared, documented, and evolvable capability.

---

## Planned Testing

*Date last modified: Dec 26, 2025*
*Contributor: Xylar Asay-Davis*

### Test deployment of Polaris

- Full test deployment on Chrysalis
- Intel and GNU compilers
- MPAS-Ocean and Omega test suites

### Test deployment of E3SM-Unified

- Full test deployment on Chrysalis
- GNU compilers
- Test run of MPAS-Analysis

