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

## Backend selection

- In a pixi shell, `mache jigsaw install` uses the pixi backend.
- In a conda shell, `mache jigsaw install` uses the conda backend.

## Pixi users (recommended)

For pixi development workflows, strongly prefer:

`mache jigsaw install --pixi-local`

This keeps your source-controlled `pixi.toml` unchanged.

What `--pixi-local` does:

- Creates or refreshes a local manifest copy at
  `.mache_cache/jigsaw/pixi-local/pixi.toml` (or `pyproject.toml` when that is
  the source manifest name).
- Adds the local JIGSAW build channel and installs `jigsawpy` there.
- For `pixi.toml` manifests that already define `[environments]`, ensures an
  isolated local `jigsaw` feature/environment and installs with
  `--feature jigsaw`.

This avoids cross-environment solve conflicts (for example, `py310`, `py311`,
etc. getting constrained by a single `python_abi`).

Pixi options you may still use with this workflow:

- `--pixi-local`
- `--jigsaw-python-path`
- `--repo-root`
- `--quiet`

## Pixi users (manual alternatives)

Use this section only if you intentionally want to edit a chosen pixi
manifest.

Relevant options:

- `--pixi-manifest`: Path to a pixi manifest file or workspace directory to
  update (`pixi.toml` or `pyproject.toml`).
- `--pixi-feature`: Explicit feature to target for install.

Example manual local-copy workflow:

1. Create a local copy:
`mkdir -p .pixi-local && cp pixi.toml .pixi-local/pixi.toml`
2. Activate that local copy:
`pixi shell -m .pixi-local -e jigsaw`
3. Install with explicit targeting:
`mache jigsaw install --pixi-manifest .pixi-local --pixi-feature jigsaw`

Because pixi only recognizes `pixi.toml` or `pyproject.toml` manifest
filenames, prefer a local directory containing one of those names (for
example `.pixi-local/pixi.toml`) rather than a custom filename like
`pixi.local.toml`.

## Conda users

Conda users do not need any pixi options.

Run from an active conda environment:

`mache jigsaw install`

Conda-relevant options:

- `--jigsaw-python-path`
- `--repo-root`
- `--quiet`
