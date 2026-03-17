# JIGSAW integration

This page covers the developer-facing layout of `mache.jigsaw` and the points
where it interacts with `mache.deploy`.

For downstream target-software usage, see the user's guide pages on
{doc}`deploy <../users_guide/deploy>` and
{doc}`JIGSAW <../users_guide/jigsaw>`.

## Responsibilities

`mache.jigsaw` has two distinct jobs:

1. Build a local conda package for `jigsawpy` and the bundled JIGSAW library.
2. Install that package into either a pixi environment or a conda
   environment.

The top-level orchestration entry point is `mache.jigsaw.deploy_jigsawpy()`.
That function resolves the backend, builds the local package channel if
needed, and installs `jigsawpy` into the target environment.

## Relationship to `mache.deploy`

`mache.deploy.run.run_deploy()` can invoke JIGSAW automatically when a target
repository enables it in `deploy/config.yaml.j2`:

```yaml
jigsaw:
  enabled: true
  jigsaw_python_path: jigsaw-python
```

At runtime, `mache deploy run`:

1. Creates the base pixi environment from `deploy/pixi.toml.j2`.
2. Calls `deploy_jigsawpy()` with `backend="pixi"`.
3. Targets the generated pixi manifest at `<prefix>/pixi.toml`.
4. Continues with any Spack and load-script work.

That means changes in `mache.jigsaw` can affect both direct
`mache jigsaw install` usage and downstream `./deploy.py` workflows.

## Module layout

`mache/jigsaw/cli.py`
: Thin CLI wiring for `mache jigsaw install`. Keep this file limited to
  argument parsing and dispatch.

`mache/jigsaw/__init__.py`
: Implementation module for build, cache, pixi install, and conda install
  logic.

The public API is documented in the {ref}`API reference <dev-api>`.

## Build and install pipeline

The normal call graph is:

1. `deploy_jigsawpy()`
2. `detect_install_backend()`
3. `build_jigsawpy_package()`
4. `install_jigsawpy_package()`

The build step:

- Ensures `jigsaw-python` source is available, cloning it when necessary.
- Computes a cache key from the source tree and selected Python/platform.
- Reuses cached output under `.mache_cache/jigsaw` when valid.
- Runs `rattler-build` through pixi or conda, depending on the selected
  backend.

The install step:

- Uses pixi when the backend resolves to `pixi`.
- Uses conda when the backend resolves to `conda`.
- Accepts explicit backend selection or `auto` detection.

## Backend-specific notes

### Pixi

The pixi install path can either mutate a chosen manifest directly or work
through a local copied manifest under `.mache_cache/jigsaw/pixi-local`.

The local-manifest path exists to avoid source-controlled manifest changes and
to isolate JIGSAW from unrelated pixi environments when a project defines
multiple features or Python variants.

### Conda

The conda install path resolves `conda` and `CONDA_PREFIX`, ensures a local
channel is available, and installs `jigsawpy` directly into the active or
requested prefix.

## Changing behavior safely

When changing `mache.jigsaw`, keep these contracts aligned:

1. The user's guide examples for `mache jigsaw install`.
2. The `jigsaw` section consumed by `mache.deploy.run`.
3. The generated runtime behavior of downstream `./deploy.py` flows.
4. The public API documented on {ref}`API reference <dev-api>`.

In practice, that usually means updating both the relevant code and the
downstream-facing docs whenever backend detection, cache semantics, or pixi
manifest mutation rules change.
