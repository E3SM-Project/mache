# Polaris Agent Instructions

These instructions apply to the whole repository unless a deeper
`AGENTS.md` overrides them.

## Source of truth

- Follow the repo's automated style and lint configuration in
  `pyproject.toml` and `.pre-commit-config.yaml`.
- If an instruction here conflicts with automated tooling, follow the
  automated tooling.

## Python environment

- This repository uses Pixi as the primary development environment manager.
- Check the root `.pixi/` and `pixi.toml` before creating or selecting any
  other Python environment.
- Prefer `pixi run -e py314 <command>` for Python tools such as `python`,
  `pytest`, `pre-commit`, `ruff`, and `mypy`.
- If you need an interactive shell, use `pixi shell -e py314` from the repo
  root instead of creating a new virtual environment.
- Do not treat `pytest: command not found` in a plain shell as a missing
  dependency until you have tried the command through Pixi.

## Python style

- Keep Python lines at 79 characters or fewer whenever possible.
- Use `ruff format` style. Do not preserve manual formatting that Ruff
  would rewrite.
- Keep imports at module scope whenever possible. Avoid local imports
  unless they are needed to prevent circular imports, defer expensive
  dependencies, or avoid optional dependency failures.
- Avoid nested functions whenever possible. Prefer private module-level
  helpers instead.
- Put public functions before private helper functions whenever
  practical.
- Name private helper functions with a leading underscore when that fits
  existing repo conventions.


## Validation

- Run tests and linting through Pixi unless the task explicitly requires a
  different environment.
- Prefer `pixi run -e py314 pytest` for tests.
- pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer `pixi run -e py314 pre-commit run --files ...` for required
  validation.
- Prefer fixing lint and formatting issues rather than suppressing them.
