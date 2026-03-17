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
`.mache_cache/jigsaw/pixi-local` and installs `jigsawpy` there. When the
source manifest already defines pixi environments, `mache` also creates or
reuses an isolated local `jigsaw` feature/environment to reduce solver
conflicts.

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
   `.mache_cache/jigsaw` or the deploy logs under `deploy_tmp/logs`.
4. For pixi, prefer `--pixi-local` if modifying the main manifest causes
   solver conflicts.
