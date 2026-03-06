# JIGSAW (Advanced)

This page describes advanced/manual `jigsawpy` installation behavior.

## CLI entry point

`mache` includes a JIGSAW helper command:

```bash
mache jigsaw install
```

This command builds a local conda package for `jigsawpy` and installs it into
the target pixi or conda environment.

## Downstream deployment context

Most downstream users trigger JIGSAW installation indirectly from the
downstream repository's `./deploy.py` workflow.
That workflow may invoke `mache` deployment logic that installs `jigsawpy`
when the downstream software enables JIGSAW in its deploy configuration.

You only need `mache jigsaw install` directly for advanced/manual workflows.

## Common options

- `--jigsaw-python-path`: Path to the `jigsaw-python` source directory
  relative to `--repo-root` (default: `jigsaw-python`)
- `--repo-root`: Repository root containing the `jigsaw-python` source
  (default: `.`)
- `--pixi-feature`: Optional pixi feature to target explicitly when
  installing with pixi
- `--pixi-manifest`: Optional pixi manifest path to update when
  installing with pixi. This can be a `pixi.toml`/`pyproject.toml` file
  or a workspace directory containing one of those files.
- `--quiet`: Suppress command output to stdout

## Backend behavior

- If running inside a pixi environment, the pixi backend is selected.
- If running inside a conda environment, the conda backend is selected.

## Pixi behavior

In pixi development environments, this command mutates a pixi manifest.
Use it intentionally, and prefer a local untracked manifest for experiments.

When used from the command line in a pixi environment, `mache jigsaw install`
updates the selected pixi project manifest.

Installation does not infer or require any specific pixi feature or
environment name pattern (for example, `py314`).

The `jigsawpy` dependency added to pixi is pinned to the built version
series (for example, `jigsawpy=1.1.0.*`) and scoped to the current platform.

If `PIXI_ENVIRONMENT_NAME` is set and a feature with the same name exists in
the manifest, installation is scoped to that feature.

## Pixi setup guidance

If your downstream project has multiple environments (for example CI matrices),
you may need an explicit JIGSAW feature/environment for clean solves.

Recommended shared `pixi.toml` pattern:

```toml
[feature.jigsaw.dependencies]
# optional: leave empty; `mache jigsaw install` adds jigsawpy as needed

[environments]
jigsaw = ["jigsaw"]
```

If your project already has CI environments such as `py310`, `py311`, etc.,
avoid adding JIGSAW directly to a shared `default` feature used by all of
those environments.

### Local/untracked manifest workflow

To avoid mutating a shared repo manifest while experimenting:

1. Create a local copy with a supported manifest filename:
`mkdir -p .pixi-local && cp pixi.toml .pixi-local/pixi.toml`
2. Activate a local environment from that copy:
`pixi shell -m .pixi-local -e jigsaw`
3. Run JIGSAW install against the local manifest copy:
`mache jigsaw install --pixi-manifest .pixi-local --pixi-feature jigsaw`

Because pixi only recognizes `pixi.toml` or `pyproject.toml` manifest
filenames, prefer a local directory containing one of those names (for
example `.pixi-local/pixi.toml`) rather than a custom filename like
`pixi.local.toml`.