# Polaris Copilot Instructions

Follow the repository's automated style configuration in
`pyproject.toml` and `.pre-commit-config.yaml`.

- Keep changes consistent with existing Polaris patterns.
- For Python, follow the path-specific instructions in
  `.github/instructions/python.instructions.md`.
- Use the repository's Pixi environment before considering any other Python
  environment. Prefer `pixi run -e py314 <command>` for `python`, `pytest`,
  `pre-commit`, `ruff`, and `mypy`, and check `.pixi/` plus `pixi.toml`
  before concluding a tool is missing.
- Do not run `workflow_tests/test_deploy_workflow.py` as part of normal
  validation. It is a long-running workflow test and should only be run if
  the user explicitly asks for it.
- pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer changes that pass the configured pre-commit hooks without
  adding ignores or suppressions.
