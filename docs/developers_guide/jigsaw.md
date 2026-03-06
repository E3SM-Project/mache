# JIGSAW integration

This page describes developer-facing behavior for the JIGSAW/JIGSAW-Python
integration in `mache`.

Use this guide when developing `mache.jigsaw` itself.
For operational usage in downstream software (including `./deploy.py` flows,
pixi setup, and local-manifest workflows), see the user's guide JIGSAW page.

## CLI entry point

The command-line interface is:

```bash
mache jigsaw install
```

For user-facing examples and options, see the user's guide JIGSAW page.

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

## Internal notes

- Build/install orchestration entry point: `deploy_jigsawpy()`.
- Build metadata and cache behavior are represented by `JigsawBuildResult`.
- Platform-aware pixi package additions are implemented in `_install_into_pixi()`.
- CLI wiring lives in `mache/jigsaw/cli.py` and should stay thin.

When changing behavior, keep user-facing workflow details in one place in the
user guide to reduce maintenance duplication.
