# Polaris Copilot Instructions

Follow the repository's automated style configuration in
`pyproject.toml` and `.pre-commit-config.yaml`.

- Keep changes consistent with existing Polaris patterns.
- For Python, follow the path-specific instructions in
  `.github/instructions/python.instructions.md`.
- pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer changes that pass the configured pre-commit hooks without
  adding ignores or suppressions.
