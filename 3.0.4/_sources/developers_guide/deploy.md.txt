# `mache.deploy` developer guide

This page is for maintainers of `mache` itself.

For downstream target-software developers, see the user's guide page on
{doc}`deploy <../users_guide/deploy>`.

## Goals and boundaries

`mache.deploy` exists to let a downstream repository keep a small,
repository-owned deployment description while delegating the orchestration to
`mache`.

The implementation is intentionally split between:

1. Files rendered once into the target repository by `mache deploy init` or
   `mache deploy update`.
2. Files rendered or consumed later at deployment time by `./deploy.py` and
   `mache deploy run`.

That separation is the main thing to preserve when changing the design.

## Module layout

`mache/deploy/cli.py`
: Top-level `mache deploy` subcommand wiring for `init`, `update`, and `run`.

`mache/deploy/init_update.py`
: Starter-kit generation. Renders repository files into the target repo and
  defines which files are refreshed during `init` versus `update`.

`mache/deploy/bootstrap.py`
: Bootstrap script executed by generated target-side `deploy.py`. Creates the
  temporary pixi environment used to run `mache deploy run`.

`mache/deploy/run.py`
: Runtime deployment orchestration. Reads target-repo config, installs pixi,
  optionally installs JIGSAW and Spack environments, and writes load scripts.

`mache/deploy/cli_spec.py`
: Shared parser utilities for the structured CLI spec format.

`mache/deploy/hooks.py`
: Hook discovery, hook execution, and the `DeployContext` data model.

`mache/deploy/machine.py`
: Machine selection and merged machine-config loading from both
  `mache.machines` and target-owned config files.

`mache/deploy/spack.py`
: Spack deployment helpers and result models.

`mache/deploy/conda.py`
: Conda platform detection helpers.

`mache/deploy/jinja.py`
: Alternate square-bracket Jinja environment used for double-rendered target
  templates.

The auto-generated API for these modules is on
{ref}`API reference <dev-api>`.

## Template lifecycle

The package template directory is `mache/deploy/templates/`.

Each template has an intended render phase.

### Rendered during `mache deploy init` and `mache deploy update`

`deploy.py.j2`
: Rendered into the target repository root as `deploy.py`.

`cli_spec.json.j2`
: Rendered into `deploy/cli_spec.json`.

These are the only files currently refreshed by `mache deploy update`.

### Rendered only during `mache deploy init`

`pins.cfg.j2`
: Rendered into `deploy/pins.cfg`.

`config.yaml.j2.j2`
: Rendered once with square-bracket delimiters into `deploy/config.yaml.j2`.
  The remaining curly-brace Jinja expressions are preserved for deploy time.

`pixi.toml.j2.j2`
: Rendered once with square-bracket delimiters into `deploy/pixi.toml.j2`.

`spack.yaml.j2`
: Copied into the target repo as a deploy-time template owned by the target
  project.

`hooks.py.j2`
: Copied into the target repo as an example hook module.

Additionally, `init_update.py` creates a plain `deploy/load.sh` placeholder.
That file is target-owned and is not generated from a package template.

### Used at deployment time by `mache deploy run`

`deploy/config.yaml.j2`
: Rendered from the target repository into an in-memory config mapping.

`deploy/pixi.toml.j2`
: Rendered from the target repository into `<prefix>/pixi.toml`.

`deploy/spack.yaml.j2`
: Rendered from the target repository into the list of Spack specs to install.

`load.sh.j2`
: Package-owned template used by `run.py` to create final
  `load_<software>*.sh` scripts in the target repo
  (toolchain-specific form:
  `load_<software>_<machine>_<compiler>_<mpi>.sh`).

`spack_install.bash.j2`
: Package-owned template used by `spack.py` to create a temporary Spack build
  script under `deploy_tmp/spack/`.

## Why the double-template files exist

`config.yaml.j2.j2` and `pixi.toml.j2.j2` are rendered twice on purpose.

The first render happens during `mache deploy init` using square-bracket Jinja
delimiters such as `[[ software ]]`.

The second render happens later during `mache deploy run` using ordinary
curly-brace Jinja variables such as `{{ python }}` and `{{ platform }}`.

This split lets `mache` stamp repository identity into the generated starter
kit once, while still letting the target repository own the deploy-time
template logic.

## Which files are target-owned versus generated

This distinction matters when changing `mache deploy update`.

Generated and expected to track `mache` closely:

- `deploy.py`
- `deploy/cli_spec.json`

Target-owned after `init`:

- `deploy/pins.cfg`
- `deploy/config.yaml.j2`
- `deploy/pixi.toml.j2`
- `deploy/spack.yaml.j2`
- `deploy/hooks.py`
- `deploy/load.sh`
- optional `deploy/machines/*.cfg`
- optional `deploy/spack/*.yaml`

If you expand the set of files refreshed by `mache deploy update`, do so very
carefully. Overwriting target-owned files is likely to destroy downstream
customization.

This also means version-bump documentation must be explicit: downstream users
should bootstrap the new release with
`./deploy.py --bootstrap-only --mache-version <new_version>`, run
`mache deploy update --mache-version <new_version>` inside that bootstrap
environment, and then update `deploy/pins.cfg` manually. Today, preserving
target ownership of `deploy/pins.cfg` is more important than auto-rewriting it.

## The command-line contract from the maintainer side

The runtime CLI surface is defined by `mache/deploy/templates/cli_spec.json.j2`
and consumed in three places:

1. Target-side `deploy.py` reads the rendered JSON and exposes the user-facing
   arguments.
2. `mache.deploy.bootstrap` accepts the subset routed to `bootstrap`.
3. `mache.deploy.cli` plus `mache.deploy.run` accept the subset routed to
   `run`.

When changing the CLI contract:

1. Update `cli_spec.json.j2`.
2. Update `bootstrap.py` if any bootstrap-routed arguments change.
3. Update `run.py` and `cli.py` if any run-routed arguments change.
4. Update the target-side documentation in the user's guide.
5. Update or add tests.

One important subtlety is that `mache deploy run` builds its parser from the
package template, while target repositories use their rendered
`deploy/cli_spec.json`. A downstream repo therefore remains safe only when its
rendered JSON stays compatible with the pinned `mache` version.

## Changing starter-kit generation

Use `mache/deploy/init_update.py` for any change to the generated starter kit.

Typical changes include:

- adding a new starter file,
- changing overwrite rules,
- changing which files `update` refreshes,
- adding new repository identity placeholders.

If the change affects repository-owned files, document whether it is `init`
only or whether existing repos must make a manual migration.

## Changing runtime deployment behavior

Use `mache/deploy/run.py` when the change affects deployment-time behavior,
including:

- config rendering,
- machine resolution,
- toolchain pairing,
- pixi installation,
- load-script generation,
- JIGSAW wiring.

Use the companion modules for narrower changes:

- `hooks.py` for hook semantics and runtime overrides,
- `machine.py` for machine discovery and config merge behavior,
- `spack.py` for Spack environment logic,
- `bootstrap.py` for bootstrap environment creation.

## Public API surface to keep documented

The deploy API is not just internal glue. Several pieces are already intended
for reuse or external understanding:

- `mache.deploy.init_update.init_or_update_repo()`
- `mache.deploy.run.run_deploy()`
- `mache.deploy.hooks.DeployContext`
- `mache.deploy.hooks.HookRegistry`
- `mache.deploy.hooks.load_hooks()`
- `mache.deploy.machine.get_machine()`
- `mache.deploy.machine.get_machine_config()`
- `mache.deploy.spack.SpackDeployResult`
- `mache.deploy.spack.SpackSoftwareEnvResult`

Whenever you add or remove a public class or function in `mache.deploy`, add
it to the auto-generated API page and update this guide if its role affects
template ownership or downstream behavior.

## Recommended checklist for `mache.deploy` changes

1. Identify whether the change is init/update time, runtime, or both.
2. Confirm which files are generated versus target-owned.
3. Update code, templates, and parser contracts together.
4. Update the user's guide for downstream developers.
5. Update this page and the {ref}`API reference <dev-api>`.
6. Add or update tests for the changed behavior.
