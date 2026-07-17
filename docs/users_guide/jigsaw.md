# JIGSAW

`mache` can install JIGSAW and `jigsawpy` in two ways:

1. Automatically as part of a downstream `./deploy.py` workflow.
2. Directly with `mache jigsaw install` for an existing pixi or conda
   environment.

## When `./deploy.py` installs JIGSAW automatically

Downstream target software can enable JIGSAW in `deploy/config.yaml.j2`:

```yaml
jigsaw:
  enabled: true
  jigsaw_python_path: jigsaw-python
```

When this is enabled, `mache deploy run` will:

1. Create the base pixi environment from `deploy/pixi.toml.j2`.
2. Build a local conda package for `jigsawpy` if needed.
3. Install `jigsawpy` into the deployed pixi environment.

This is the usual path for downstream packages such as Polaris.

## Installing JIGSAW into an existing environment

The direct command is:

```bash
mache jigsaw install
```

This command builds a local conda package for `jigsawpy` and installs it into
the current pixi or conda environment.

Backend selection is automatic by default:

- If pixi environment variables are present, pixi is used.
- Otherwise, if `CONDA_PREFIX` is set, conda is used.

If neither backend can be inferred, the command fails and you should run it
from an active pixi or conda environment.

## Pixi workflow

For pixi development workflows, the recommended form is:

```bash
mache jigsaw install --pixi-local
```

This keeps your source-controlled manifest unchanged.

`--pixi-local` creates or refreshes a local manifest copy under
`<repo-root>/.mache_cache/jigsaw/pixi-local` and installs `jigsawpy` there.
When the source manifest already defines pixi environments, `mache` also
creates or reuses an isolated local `jigsaw` feature/environment to reduce
solver conflicts.

Useful pixi options are:

- `--pixi-local`
- `--pixi-manifest`
- `--pixi-feature`
- `--jigsaw-python-path`
- `--repo-root`
- `--quiet`

Use `--pixi-manifest` and `--pixi-feature` when you intentionally want to
target a specific existing manifest instead of the auto-managed local copy.

## Conda workflow

From an active conda environment, run:

```bash
mache jigsaw install
```

The conda backend installs `jigsawpy` into `CONDA_PREFIX` unless you provide a
different prefix programmatically.

For most users, no additional options are required beyond:

- `--jigsaw-python-path`
- `--repo-root`
- `--quiet`

## The build cache

Building JIGSAW takes a couple of minutes, so `mache` caches the result and
rebuilds only when something that affects the build changes: the
`jigsaw-python` commit, its version, the Python version, or the platform.

The cache belongs to the *clone*, not to the checkout you happen to be
standing in. If you use a separate git worktree per branch — the workflow
recommended by Polaris and Compass — every worktree of a clone shares one
build, so only the first `./deploy.py` pays for it:

```
<clone>/.mache_cache/jigsaw/
├── tools/         # environments used to run the build
└── <cache_key>/   # one directory per distinct build
```

Builds that differ, for example because two branches pin different
`jigsaw-python` commits, get their own directory and do not displace each
other. `mache` never deletes these, so a build stays valid for as long as any
environment you deployed from it. Each one is small (a few MB); the bulk of
the cache is `tools/`, which is shared by every build.

If two `./deploy.py` runs in different worktrees need the same build at the
same time, they serialize on `<clone>/.mache_cache/jigsaw/.lock`. The second
one waits, then finds the finished build and reuses it.

To force a rebuild, delete the relevant `<cache_key>` directory. To reclaim
everything, delete `<clone>/.mache_cache`, but note that this invalidates the
local channel recorded in environments you have already deployed, which will
need to be redeployed.

### Reclaiming space after upgrading

Before `mache` 3.8.0 the cache lived in each worktree, so a worktree-per-branch
checkout accumulated a full copy — roughly 100 MB each — per branch. Those old
caches are left in place rather than migrated, because environments deployed by
older versions of `mache` still refer to them.

Once you have redeployed a worktree, its old cache is safe to remove:

```bash
rm -rf <worktree>/.mache_cache/jigsaw/build
```

The first `./deploy.py` after upgrading rebuilds JIGSAW once per clone. Every
worktree after that reuses it.

## Source requirements

By default, `mache` looks for `jigsaw-python` under `./jigsaw-python` relative
to `--repo-root`.

If the source tree is missing:

- In downstream deploy workflows, `mache deploy run` can clone or initialize
  the source automatically when JIGSAW is enabled.
- In direct `mache jigsaw install` workflows, `mache` will also try to make
  the source available before building.

## Troubleshooting

If installation fails:

1. Confirm you are in an active pixi or conda environment.
2. Check that `jigsaw-python` is present at the expected path.
3. Re-run with terminal output enabled and inspect the build logs under
   `<clone>/.mache_cache/jigsaw/<cache_key>` or the deploy logs under
   `deploy_tmp/logs`.
4. For pixi, prefer `--pixi-local` if modifying the main manifest causes
   solver conflicts.
5. If a deploy reports that it is waiting for the JIGSAW build lock and no
   other build is running, remove `<clone>/.mache_cache/jigsaw/.lock`.
