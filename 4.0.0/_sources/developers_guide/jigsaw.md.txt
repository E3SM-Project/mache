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
- Reuses cached output under the shared cache when valid.
- Runs `rattler-build` through pixi or conda, depending on the selected
  backend.

### Cache layout and invariants

The cache is anchored at the clone that `repo_root` belongs to, found via
`git rev-parse --git-common-dir`, so every git worktree of that clone shares
one build. Outside a git checkout it falls back to `<repo_root>`, which is
also where it lands for an original clone — so upgrading needs no migration.

```
<clone>/.mache_cache/jigsaw/     # shared: _get_jigsaw_shared_cache_dir()
├── .lock                        # _jigsaw_cache_lock()
├── tools/                       # _jigsaw_tools_dir()
└── <cache_key>/                 # _jigsaw_slot_dir(), rattler-build output

<repo_root>/.mache_cache/jigsaw/ # per-worktree: _get_jigsaw_workspace_dir()
└── pixi-local/
```

Four invariants hold this together. Breaking any of them is a behavior
change, not a refactor:

1. **The cache key is worktree-agnostic.** It hashes the `jigsaw-python`
   commit, its version, the Python version and the platform — nothing about
   the containing checkout. Adding anything worktree-specific to it silently
   un-shares the cache.
2. **Slots are never deleted.** `channel_uri` names a slot, and that URI is
   baked into the `pixi.toml` and `pixi.lock` of every environment deployed
   from it, which outlive the deploy. Pruning slots would break those
   environments long afterward, at their next solve. Slots are small; the
   growth this permits is not worth that failure mode.
3. **`tools/` is key-independent, and shared on purpose.** These environments
   are the great majority of the cache's size and depend only on the platform.
   Moving them inside a slot would restore most of the per-worktree
   duplication that sharing the cache exists to remove.
4. **`pixi-local` is per-`repo_root`, not per-clone.** It is a copy of the
   source manifest, so it derives from the worktree rather than from the cache
   key; sharing it would let one worktree clobber another's.

Writes to the shared cache happen under an exclusive `flock`, since worktrees
can deploy concurrently. The sentinel `<cache_key>/.jigsaw_cache_key` is
written *after* the build finishes, so a slot mid-build never reads as a cache
hit — that ordering is what lets the cache-hit path skip the lock entirely.

### Repodata the driving pixi can read

`_get_local_channel_uri()` strips `info.repodata_revisions` from every
`repodata.json` in a slot before the channel is handed to pixi or conda.
rattler-build 0.75.0 began writing that key as a map, and the rattler
bundled in older pixi (0.70.2, for one) expects a sequence there, so it
fails to parse the file at all and the deploy dies with `invalid type: map,
expected a sequence`.

mache chooses the rattler-build that fills a slot but not the pixi that
reads it — `pixi_exe` is whatever it was handed — so the file mache writes
is the only place it can fix this. The key is purely informational for a
channel holding one locally built package.

That it happens in `_get_local_channel_uri()` rather than at the end of the
build is the point: a slot filled by an older mache is poisoned in exactly
the same way and still validates as a cache hit, because
`_is_cached_jigsaw_build_valid()` only asks whether the repodata exists.
Sanitizing on the path that both a fresh build and a cache hit take is what
reaches those slots.

The install step:

- Uses pixi when the backend resolves to `pixi`.
- Uses conda when the backend resolves to `conda`.
- Accepts explicit backend selection or `auto` detection.

## Backend-specific notes

### Pixi

The pixi install path can either mutate a chosen manifest directly or work
through a local copied manifest under
`<repo_root>/.mache_cache/jigsaw/pixi-local`.

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
