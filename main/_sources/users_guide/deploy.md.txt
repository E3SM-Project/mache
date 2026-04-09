# Deploying target software

This page is for developers of downstream software that want to use
`mache.deploy`.

From `mache`'s point of view, your downstream repository is the target
software. Polaris is a useful example, but the same workflow applies to any
package that wants `mache` to create pixi environments, optional Spack
environments, optional JIGSAW installs, and load scripts.

## What `mache deploy` gives you

`mache.deploy` separates deployment into three layers:

1. A generated repository entry point, `./deploy.py`.
2. A bootstrap step that creates a temporary pixi environment containing
   `mache`.
3. A runtime deploy step, `mache deploy run`, that renders templates,
   installs environments, and writes load scripts.

As a target-software developer, most of your work is in the generated
`deploy/` directory.

## Add deploy support to a downstream package

Run this from the root of the target repository:

```bash
mache deploy init --repo-root . --software polaris
```

This creates the initial starter kit for your repository.

If any of the generated files already exist and you really do want to replace
them, re-run with `--overwrite`.

### Files created by `mache deploy init`

`mache deploy init` currently creates:

```text
deploy.py
deploy/
  cli_spec.json
  config.yaml.j2
  custom_cli_spec.json
  hooks.py
  load.sh
  pins.cfg
  pixi.toml.j2
  spack.yaml.j2
```

The generated tree is intentionally small. It gives the target repository a
place to define pins, deployment policy, runtime templates, and optional hook
logic without importing the target package before the environment exists.

### Recommended first edits

After `init`, review and customize at least these files:

1. `deploy/pins.cfg`
2. `deploy/config.yaml.j2`
3. `deploy/pixi.toml.j2`

Typical Polaris-style changes include:

- setting target-specific conda channels,
- choosing a shared install prefix,
- deciding whether the target software should be installed in editable mode,
- enabling JIGSAW,
- enabling Spack support and defining specs.

## What belongs in `deploy/`

This section describes which files are required, which are optional, and which
ones are usually safe to edit.

### `deploy.py`

Required: yes

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: yes

Purpose:

- Acts as the user-facing deployment entry point for the target repository.
- Reads `deploy/pins.cfg` and `deploy/cli_spec.json`.
- Downloads the matching `bootstrap.py` from the pinned `mache` version or a
  requested fork/branch.
- Runs bootstrap and then `mache deploy run`.

Edit policy:

- Treat this file as generated.
- Do not hand-edit it unless you are deliberately forking the contract.
- Expect `mache deploy update` to replace it.

### `deploy/cli_spec.json`

Required: yes

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: yes

Purpose:

- Defines the command-line interface exposed by `./deploy.py`.
- Decides which arguments are routed to the bootstrap step and which are
  routed to `mache deploy run`.

Edit policy:

- This file is editable, but it is also generated.
- Keep edits deliberate and review them carefully after every
  `mache deploy update`.
- Any argument you add must remain compatible with the bootstrap parser and
  `mache deploy run` parser in the installed `mache` version.

### `deploy/custom_cli_spec.json`

Required: no

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Lets the target repository add its own command-line flags without editing
  the generated `deploy/cli_spec.json`.
- Is merged into the generated CLI by both `./deploy.py` and
  `mache deploy run`.
- Is the recommended place for downstream-only CLI additions such as optional
  feature toggles.

Edit policy:

- Fully target-repository owned.
- Safe to edit freely after `init`.
- Keep custom `flags` and `dest` names distinct from the generated
  `deploy/cli_spec.json`.
- Omit `meta`; only `arguments` is needed.

### `deploy/pins.cfg`

Required: yes

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Stores version pins used by deployment templates.
- Provides the pinned `mache` version used by `./deploy.py`.
- Provides the pinned Python version used by the deployed pixi environment.

Edit policy:

- This file is target-repository owned.
- You should expect to edit it frequently.
- When updating to a new `mache` release, update this file as well as running
  `mache deploy update`.

### `deploy/config.yaml.j2`

Required: yes

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Defines deployment policy in a repository-owned YAML file.
- Is rendered at deploy time with Jinja variables derived from pins and the
  current platform.
- Controls pixi, Spack, JIGSAW, machine discovery, hooks, and runtime version
  checks.

Edit policy:

- This is one of the main files target-software developers are expected to
  maintain.
- Keep repository-specific policy here rather than in `deploy.py`.

Important settings:

- `project.software`: required and normally fixed.
- `project.version`: required unless a `pre_pixi` hook writes
  `runtime["project"]["version"]`.
- `project.runtime_version_cmd`: optional version probe used by the generated
  load scripts.
- `project.machine`: optional fixed machine name, otherwise use `dynamic`.
- `machines.path`: optional path to target-owned machine config files.
- `pixi.prefix`: required in practice.
- `pixi.channels`: required and must be non-empty.
- `pixi.login_mpi`: optional alternate MPI setting for login nodes. When set,
  `mache deploy run` may create a second pixi environment for login-node use
  and the generated load script will auto-select between the login and compute
  environments.
- `pixi.login_prefix`: optional install path for that login-node pixi
  environment. If omitted, mache reuses `pixi.prefix` when the login and
  compute MPI settings match, or defaults to `<pixi.prefix>_login` when they
  differ.
- `permissions.group`: optional shared-filesystem group to apply after a
  successful deploy. If unset, `mache deploy run` falls back to merged machine
  config `[deploy] group`.
- `permissions.world_readable`: optional boolean controlling whether deployed
  files are readable outside the shared group. Hooks may override both values
  through `ctx.runtime["permissions"]`.
- `spack.spack_path`: required when Spack support is enabled and no hook or
  CLI override provides it, unless the user disables Spack for that run with
  `--no-spack`.
- `spack.exclude_packages`: optional list of machine-provided Spack packages
  that the target software wants Spack to build instead.
- `jigsaw.enabled`: optional.
- `hooks`: optional and disabled unless explicitly configured.

Example:

If a downstream package such as Compass wants to use the machine-provided
libraries in general but build its own newer `cmake`, it can set
`spack.exclude_packages` in `deploy/config.yaml.j2`:

```yaml
spack:
  supported: true
  deploy: true
  spack_path: /path/to/shared/spack
  exclude_packages:
    - cmake
```

With this setting, `mache deploy run` will:

- remove the machine-provided `cmake` external from the rendered Spack
  environment YAML,
- remove matching machine-provided `cmake` module loads and related
  environment-variable setup from generated shell snippets, and
- let Spack build the `cmake` version requested by `deploy/spack.yaml.j2`.

The package list in `deploy/spack.yaml.j2` does not need any special syntax
for this.  You simply request the Spack package you want, for example:

```yaml
software:
  - "cmake@{{ spack.cmake }}"
library:
  - "trilinos@{{ spack.trilinos }}"
```

The same mechanism can be used for the machine-provided HDF5/NetCDF bundle:

```yaml
spack:
  exclude_packages:
    - hdf5_netcdf
```

This is the preferred replacement for the older `e3sm_hdf5_netcdf` flag.

Another common pattern is to keep a machine-specific boolean such as
`[deploy] use_e3sm_hdf5_netcdf` in the target repository's machine config and
translate that into `exclude_packages` in a `pre_spack` hook.

For example, if a downstream project like Compass has a machine config with:

```ini
[deploy]
use_e3sm_hdf5_netcdf = false
```

then `deploy/hooks.py` can map that to the new mechanism:

```python
from __future__ import annotations

from typing import Any

from mache.deploy.hooks import DeployContext


def pre_spack(ctx: DeployContext) -> dict[str, Any] | None:
    updates: dict[str, Any] = {}

    exclude_packages = list(ctx.config.get("spack", {}).get("exclude_packages", []))

    use_bundle = False
    if ctx.machine_config.has_section("deploy") and ctx.machine_config.has_option(
        "deploy", "use_e3sm_hdf5_netcdf"
    ):
        use_bundle = ctx.machine_config.getboolean("deploy", "use_e3sm_hdf5_netcdf")

    if not use_bundle:
        exclude_packages.append("hdf5_netcdf")

    updates.setdefault("spack", {})["exclude_packages"] = exclude_packages
    return updates
```

This lets existing machine-config policy continue to drive behavior while
moving the actual Spack selection onto `exclude_packages`.

### `deploy/pixi.toml.j2`

Required: yes

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Template for the deployed pixi project written to `<prefix>/pixi.toml`.
- Receives deploy-time replacements such as Python version, selected channels,
  MPI flavor, whether `mache` or `jigsawpy` should be included, and optional
  hook-provided dependency lists such as `extra_dependencies` and
  `omit_dependencies`.

Edit policy:

- Target-repository owned.
- Safe to customize for package dependencies and features.
- If you remove or rename the Jinja placeholders that `mache deploy run`
  expects, you must also update the runtime code.

One useful pattern is to keep the dependency list mostly static in
`deploy/pixi.toml.j2`, then let hooks add or remove a few machine-specific
tools. For example:

```toml
[dependencies]
python = "{{ python }}.*"
pip = "*"
setuptools = ">=60"
{%- set omitted_dependencies = omit_dependencies | default([]) %}
{%- if 'git' not in omitted_dependencies %}
git = "*"
{%- endif %}
{%- for dependency in extra_dependencies | default([]) %}
{{ dependency }}
{%- endfor %}
```

This lets a downstream repository keep using the system `git` command on one
machine while still installing conda `git` everywhere else, without teaching
`mache` about a new package-specific toggle.

### `deploy/spack.yaml.j2`

Required: only when you support Spack

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Repository-owned template that renders to a YAML mapping containing `library`
  specs, `software` specs, or both.
- Supplies the target-specific package list used when `mache` constructs Spack
  environments.
- Receives `exclude_packages` as a deploy-time Jinja variable, reflecting any
  configured opt-outs of machine-provided Spack packages.

Edit policy:

- Safe and expected to edit.
- Leave it empty if you do not support Spack yet.

In most target repositories, package opt-outs belong in `deploy/config.yaml.j2`
under `spack.exclude_packages`, not in `deploy/spack.yaml.j2`.  The Spack spec
template is where you request the package versions and variants you want to
build; `exclude_packages` controls which machine-provided externals are
suppressed before concretization.

### `deploy/hooks.py`

Required: no

Created by `mache deploy init`: yes, as an example module

Overwritten by `mache deploy update`: no

Purpose:

- Contains optional Python hook functions executed during `mache deploy run`.
- Lets the target repository compute runtime values without modifying `mache`
  itself.

Edit policy:

- Fully target-repository owned.
- Hooks are not active unless `deploy/config.yaml.j2` opts in.

Known hook stages are:

- `pre_pixi`
- `post_pixi`
- `pre_spack`
- `post_spack`
- `post_deploy`

Hooks can also drive generic pixi dependency overrides. For example, a
downstream repository can omit `git` on a machine whose host OS is too old for
the current conda-forge `git` builds:

```python
def pre_pixi(ctx: DeployContext) -> dict[str, Any] | None:
    omit_dependencies: list[str] = []
    if (
        ctx.machine_config.has_section("my_software")
        and ctx.machine_config.has_option("my_software", "use_system_git")
        and ctx.machine_config.getboolean("my_software", "use_system_git")
    ):
        omit_dependencies.append("git")

    return {
        "pixi": {
            "omit_dependencies": omit_dependencies,
            "extra_dependencies": ['my-extra-tool = ">=1.0"'],
        }
    }
```

Combined with a matching `deploy/pixi.toml.j2`, this gives downstream projects
an escape hatch for optional tools without needing a new hard-coded helper in
`mache.deploy.run`.

### `deploy/load.sh`

Required: no

Created by `mache deploy init`: yes

Overwritten by `mache deploy update`: no

Purpose:

- Optional shell snippet sourced by the generated `load_<software>*.sh`
  scripts.
- Good place for target-specific environment variables.

Edit policy:

- Safe to edit.
- Keep it limited to environment setup; it should not recreate the deployment.

### Optional target-owned additions

`mache deploy init` does not create these, but `mache deploy run` can use
them:

`deploy/machines/*.cfg`
: Optional target-specific machine configuration files merged with
  `mache.machines`.

`deploy/spack/<machine>_<compiler>_<mpi>.yaml`
: Optional per-toolchain Spack environment template overrides used when a
  target repository needs a custom environment skeleton for one machine or
  toolchain combination.

## Adding a custom CLI flag

Use `deploy/custom_cli_spec.json` when the target repository wants an extra
flag that should survive `mache deploy update`.

For example, Compass could add both `--with-albany` and
`--moab-version 5.6.0` like this:

```json
{
  "arguments": [
    {
      "flags": ["--with-albany"],
      "dest": "with_albany",
      "action": "store_true",
      "help": "Install optional Albany and Trilinos support.",
      "route": ["deploy", "run"]
    },
    {
      "flags": ["--moab-version"],
      "dest": "moab_version",
      "help": "Version of MOAB to install for this deployment.",
      "route": ["deploy", "run"]
    }
  ]
}
```

This route means:

- `deploy`: `./deploy.py` accepts the flag.
- `run`: the flag is forwarded to `mache deploy run`, so hooks can inspect it.

Then enable hooks in `deploy/config.yaml.j2`:

```yaml
hooks:
  file: "deploy/hooks.py"
  entrypoints:
    pre_spack: "pre_spack"
```

And use the flags inside `deploy/hooks.py`:

```python
from pathlib import Path


def pre_spack(ctx):
    if getattr(ctx.args, "with_albany", False):
        marker = Path(ctx.work_dir) / "with_albany.txt"
        marker.write_text("Albany requested\n", encoding="utf-8")

    moab_version = getattr(ctx.args, "moab_version", None)
    if moab_version:
        marker = Path(ctx.work_dir) / "moab_version.txt"
        marker.write_text(f"{moab_version}\n", encoding="utf-8")
```

Running

```bash
./deploy.py --with-albany --moab-version 5.6.0
```

would therefore make both of these values available in hooks:

- `ctx.args.with_albany == True`
- `ctx.args.moab_version == "5.6.0"`

From there, the hook can:

- add derived runtime settings,
- render target-specific files,
- or trigger downstream install steps for optional dependencies.

Use `deploy/custom_cli_spec.json` for downstream extensions. Keep
`deploy/cli_spec.json` aligned with upstream `mache`.

## The three deployment phases

From a user's point of view, deployment starts with `./deploy.py`. Internally,
that process has three phases.

### Phase 1: `./deploy.py`

The generated `deploy.py` file:

1. Verifies it is being run from the target repository root.
2. Reads the pinned `mache` and Python versions from `deploy/pins.cfg`.
3. Reads `deploy/cli_spec.json` plus optional `deploy/custom_cli_spec.json`
   and builds the command-line parser.
4. Validates that `deploy/cli_spec.json` and `deploy/pins.cfg` agree on the
   pinned `mache` version unless a fork/branch override is being used.
5. Downloads `mache/deploy/bootstrap.py` from the requested `mache` source.
6. Runs bootstrap with the arguments routed to the bootstrap phase.
7. Unless `--bootstrap-only` was requested, runs `mache deploy run` inside the
   bootstrap pixi environment.

The important design point is that `deploy.py` stays small and generated. Most
repository-specific behavior lives in the files under `deploy/`.

### Phase 2: bootstrap

Bootstrap is implemented by `mache/deploy/bootstrap.py` from the selected
`mache` version.

Its job is to create a temporary pixi environment under
`deploy_tmp/bootstrap_pixi` that contains the `mache` code that will perform
the real deployment.

Bootstrap currently:

1. Resolves the pixi executable, installing pixi if necessary.
2. Creates or refreshes `deploy_tmp/bootstrap_pixi`.
3. Installs `mache` either from a tagged release or from a requested
   fork/branch clone.
4. Leaves logs under `deploy_tmp/logs/bootstrap.log`.

If you pass `--bootstrap-only`, the process stops here and leaves you with an
interactive environment that can run `mache deploy update` or `mache deploy
run` manually.

This mode is especially useful when a downstream repository wants to adopt a
new `mache` release. In that case, bootstrap the new release explicitly so the
temporary environment contains the new `mache` code:

```bash
./deploy.py --bootstrap-only --mache-version 2.2.0
pixi shell -m deploy_tmp/bootstrap_pixi/pixi.toml
mache deploy update --software polaris --mache-version 2.2.0
```

After that, update `deploy/pins.cfg` manually so `[pixi] mache = 2.2.0`
matches the regenerated `deploy/cli_spec.json`, then exit the bootstrap shell.

### Phase 3: `mache deploy run`

The runtime deploy phase is where the actual target-software environment is
created.

`mache deploy run` currently:

1. Reads `deploy/pins.cfg`.
2. Renders `deploy/config.yaml.j2`.
3. Resolves the machine and merged machine config.
4. Loads hooks if configured.
5. Resolves toolchain pairs for Spack.
6. Renders `deploy/pixi.toml.j2` into the install prefix and runs
   `pixi install`.
7. Optionally creates a second login-node pixi environment when
   `pixi.login_mpi` is configured or a hook sets `ctx.runtime["pixi"]`
   accordingly.
8. Optionally installs a development copy of `mache` when a fork/branch was
   requested.
9. Optionally builds and installs JIGSAW.
10. Optionally deploys or loads Spack environments.
11. Optionally installs the target software in editable mode.
12. Writes one or more `load_<software>*.sh` scripts.

When a toolchain pair is selected, script names include machine, compiler,
and MPI tags, for example:

`load_<software>_<machine>_<compiler>_<mpi>.sh`

Those load scripts are the main artifact a downstream user consumes after the
deployment completes.

When a login pixi environment is configured, the generated load script chooses
the login environment on login nodes and the compute environment inside common
batch jobs such as Slurm, PBS, or Cobalt. Spack activation remains compute-only
in that split-environment case.

## The command-line contract

There are really two CLIs involved:

1. The author-time CLI, `mache deploy init` and `mache deploy update`.
2. The runtime CLI exposed to downstream users as `./deploy.py`.

### `mache deploy init` and `mache deploy update`

These commands operate on the target repository itself.

`mache deploy init`
: Generates the starter kit.

`mache deploy update`
: Regenerates only the files that are intended to track `mache` closely,
  currently `deploy.py` and `deploy/cli_spec.json`.

`deploy/custom_cli_spec.json`
: Is intentionally not regenerated. Use it for target-owned CLI additions.

### How `deploy/cli_spec.json` works

Each argument entry contains:

- `flags`
- `dest`
- `route`
- a safe subset of `argparse` keyword arguments

The key field is `route`.

`route: ["deploy"]`
: The option is accepted only by `./deploy.py`.

`route: ["deploy", "bootstrap"]`
: The option is accepted by `./deploy.py` and forwarded to bootstrap.

`route: ["deploy", "run"]`
: The option is accepted by `./deploy.py` and forwarded to `mache deploy run`.

`route: ["deploy", "bootstrap", "run"]`
: The option is accepted by `./deploy.py` and forwarded to both later phases.

Examples from the current contract:

- `--bootstrap-only` is deploy-only.
- `--machine` is deploy-plus-run.
- `--mache-version` is bootstrap-plus-run.
- `--pixi`, `--pixi-path`, `--recreate`, `--quiet`, `--mache-fork`, and
  `--mache-branch` are routed across all relevant phases.
- `--prefix` is still accepted as a deprecated compatibility alias for
  `--pixi-path`.

### How `deploy/custom_cli_spec.json` works

`deploy/custom_cli_spec.json` uses the same argument-entry format as
`deploy/cli_spec.json`, but it is downstream-owned and optional.

At runtime:

1. `./deploy.py` loads `deploy/cli_spec.json`.
2. If `deploy/custom_cli_spec.json` exists, it appends those argument entries.
3. Duplicate `flags` or `dest` values are rejected to avoid ambiguous parsers.

In practice, this means:

- use `deploy/cli_spec.json` for the generated upstream contract,
- use `deploy/custom_cli_spec.json` for downstream feature flags,
- route custom flags to `run` when hooks need to inspect them.

### Contract rules for target-software developers

When you customize `deploy/cli_spec.json` or `deploy/custom_cli_spec.json`,
keep these rules in mind:

1. `deploy.py` exposes only the arguments listed in the JSON file.
2. Bootstrap must accept every argument routed to `bootstrap`.
3. `mache deploy run` must accept every argument routed to `run`.
4. The pinned `mache` version in `deploy/pins.cfg` must match
   `deploy/cli_spec.json` unless you are intentionally testing a fork/branch.
5. `deploy/custom_cli_spec.json` must not reuse a generated flag or `dest`.

If you break this contract, deployment usually fails with an argument-parsing
error or a version-mismatch error.

## Updating a target repository to a new `mache` version

Use `mache deploy update` when a downstream repository wants to adopt a newer
version of `mache`.

The usual sequence is:

1. Bootstrap the new release explicitly:

   ```bash
   ./deploy.py --bootstrap-only --mache-version 2.2.0
   ```

2. Enter the bootstrap environment and regenerate the generated files with the
   same version:

   ```bash
   pixi shell -m deploy_tmp/bootstrap_pixi/pixi.toml
   mache deploy update --repo-root . --software polaris --mache-version 2.2.0
   ```

3. Update `deploy/pins.cfg`, especially `[pixi] mache = 2.2.0`.
4. Exit the bootstrap shell.
5. Review the diffs in `deploy.py` and `deploy/cli_spec.json`.
6. Confirm that target-owned files such as `deploy/custom_cli_spec.json` still
   reflect the downstream CLI you want.
7. Adjust repository-owned files such as `deploy/config.yaml.j2` only if the
   new `mache` release expects new settings or supports new behavior.

Important limitation:

- `mache deploy update` does not rewrite `deploy/pins.cfg`,
  `deploy/config.yaml.j2`, `deploy/custom_cli_spec.json`,
  `deploy/pixi.toml.j2`, `deploy/spack.yaml.j2`, or `deploy/hooks.py`.
- `./deploy.py --bootstrap-only --mache-version <new_version>` is the safest
  way to make sure the bootstrap environment and downloaded `bootstrap.py`
  come from the new release instead of the old pin.

That is intentional. Those files are treated as target-repository owned and
should not be replaced automatically.

## Troubleshooting

This section is intentionally short for now and will grow over time.

### `deploy.py` says it must be run from the repository root

Cause:

- You ran `./deploy.py` from the wrong directory.

Fix:

- Run it from the repository root where `deploy.py` and `deploy/` live.

### `deploy/cli_spec.json` and `deploy/pins.cfg` disagree on the `mache` version

Cause:

- `mache deploy update` was run without also updating `deploy/pins.cfg`, or a
  file was copied manually from another release.

Fix:

- Update `[pixi] mache` in `deploy/pins.cfg` and regenerate with
  `mache deploy update` if needed.

### Pixi cannot be found

Cause:

- Pixi is not installed and was not found on `PATH`.

Fix:

- Re-run with `--pixi /path/to/pixi` or allow bootstrap to install pixi.

### The machine is unknown

Cause:

- `--machine` named a machine that is not present in `mache.machines` or in
  the target repository's `deploy/machines` directory.

Fix:

- Add the machine config under `deploy/machines` or choose a known machine.

### Spack is enabled but deployment fails because `spack_path` is missing

Cause:

- Spack support was enabled for this run, but no path was provided in config,
  hooks, or the CLI.

Fix:

- Set `spack.spack_path`, write it in a hook through
  `ctx.runtime["spack"]["spack_path"]`, or pass `--spack-path`.
- If this should be a Pixi-only run, pass `--no-spack`.
- A `pre_spack` hook may also disable Spack for one run by returning
  `{"spack": {"supported": false, "software": {"supported": false}}}`.

### `project.version` is still `dynamic`

Cause:

- `deploy/config.yaml.j2` left `project.version: dynamic`, but no `pre_pixi`
  hook provided the runtime value.

Fix:

- Either set a fixed `project.version` or return
  `{"project": {"version": ...}}` from `pre_pixi`.

### The generated load script fails when executed

Cause:

- The generated `load_<software>*.sh` script is meant to be sourced, not run as
  a standalone executable.

Fix:

- Use `source load_<software>*.sh` from `bash`.
