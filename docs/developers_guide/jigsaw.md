# JIGSAW integration

This page describes developer-facing behavior for the JIGSAW/JIGSAW-Python
integration in `mache`.

## CLI entry point

The command-line interface is:

```bash
mache jigsaw install
```

For user-facing examples and options, see the user's guide quick-start section
on building and installing jigsawpy.

## Module overview

The `mache.jigsaw` module provides programmatic build and install helpers:

- `deploy_jigsawpy()`: convenience wrapper to build and install in one call
- `build_jigsawpy_package()`: build a local conda package channel for jigsawpy
- `install_jigsawpy_package()`: install jigsawpy from a local channel
- `detect_install_backend()`: resolve pixi vs conda backend selection

## Backend behavior

- Backend selection supports `pixi`, `conda`, or `auto` detection.
- In pixi contexts, install behavior uses pixi commands.
- In conda contexts, install behavior uses conda commands.

## Pixi isolation behavior

When using the CLI in pixi mode without an explicit manifest path,
`mache.jigsaw` uses an isolated pixi manifest in
`.mache_cache/jigsaw/pixi_install/...` so the active workspace manifest is not
modified.

When a matching pixi feature exists for the selected Python version (for
example, `py314`), jigsaw installation is scoped to that feature to avoid
conflicts with other environments in the same manifest.
