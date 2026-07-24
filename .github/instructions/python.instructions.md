---
applyTo: "**/*.py"
---

# Python Instructions

- Keep lines at 79 characters or fewer whenever possible.
- Adhere to `ruff format` formatting.
- Keep imports at module scope whenever possible. Avoid local imports
  unless they are needed for circular-import avoidance, lazy loading, or
  optional dependencies.
- Avoid nested functions whenever possible.
- Prefer public functions before private helper functions whenever
  practical.
- Prefer private module-level helper functions over nested helpers.

## Shell/CLI environment

- `rg` (ripgrep) is not available in this environment. Use `grep`, `find`,
  `git grep`, or the built-in `grep`/`glob` tools instead.
