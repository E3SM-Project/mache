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
- Prefer the `default` environment for Python tools such as `python`,
  `pytest`, `pre-commit`, `ruff`, and `mypy`: run `pixi run <command>` (or
  `pixi shell` for an interactive shell) from the repo root. This is the
  environment `pixi shell` creates, so it is usually the one already
  installed under `.pixi/envs/`.
- If the `default` environment is not available, fall back to an explicit
  Python environment such as `pixi run -e py314 <command>` (`py310`
  through `py314` are defined in `pixi.toml`). Note that selecting an
  environment that is not yet installed will make Pixi solve and install
  it, which can be slow.
- If no Pixi environment is installed at all, ask the user to create one
  (e.g. `pixi shell`) rather than building a separate virtual environment.
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
- Prefer `pixi run pytest` for tests (the `default` environment; see the
  "Python environment" section for fallbacks).
- Do not run `workflow_tests/test_deploy_workflow.py` during routine
  validation unless the user explicitly requests that workflow test.
- pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer `pixi run pre-commit run --files ...` for required validation.
- Prefer fixing lint and formatting issues rather than suppressing them.


## GitHub pull requests and issues

- Do not hard-wrap. Write each paragraph and each bullet as a single
  line, however long. GitHub wraps them for display, and hard breaks
  make later edits show up as reflowed paragraphs in the diff.
- Start with a paragraph summarizing what the pull request or issue is
  about, then use sections for the detail.
- Keep the description in a file at the root of the worktree for the
  branch it describes, and never commit it. It is a draft to paste into
  GitHub, not part of the branch's content.
- Follow `.github/pull_request_template.md`: the description goes at
  the top, keep only the checklist lines that apply, and use closing
  keywords for any issue the pull request fixes.
- Do not list individual commits in a pull request description. The
  commits are already on the pull request; describe what the change
  accomplishes as a whole instead.
- Do not describe testing in a pull request description. Testing goes
  in its own `Testing` comment on the pull request, which is what the
  template's checklist asks for.
- An issue should say what happens, what was expected instead, and
  enough about the configuration and commands used to reproduce it.
