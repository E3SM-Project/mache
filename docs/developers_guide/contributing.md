# Contributing to mache

Thank you for your interest in contributing to `mache`! We welcome
contributions of all kinds, including bug reports, feature requests, code, and
documentation improvements.

## How to Contribute

- **Bug Reports & Feature Requests:**
  Please use [GitHub Issues](https://github.com/E3SM-Project/mache/issues) to
  report bugs or request features.

- **Pull Requests:**
  Fork the repository, create a new branch for your changes, and submit a pull
  request (PR) to the `main` branch. Please provide a clear description of
  your changes.

## Development Environment

1. **Set up an isolated environment:**
    ```bash
    pixi install
    pixi run python -m pip install --no-deps --no-build-isolation -e .
    ```

2. **Install pre-commit hooks:**
    ```bash
    pre-commit install
    ```
    This ensures code style and quality checks run automatically on each
    commit.

## Code Style and Linting

- Follow [PEP8](https://peps.python.org/pep-0008/) and project code style.
- The following tools are used (via [pre-commit](https://pre-commit.com/)):
  - [ruff](https://docs.astral.sh/ruff/) for linting and formatting
  - [flynt](https://github.com/ikamensh/flynt) for f-string conversion
  - [mypy](https://mypy-lang.org/) for type checking

If a pre-commit hook fails, fix the reported issues and recommit.

## Testing

- Add or update tests for new features or bug fixes.
- Run the test suite before submitting a PR:
    ```bash
    pytest
    ```

## Documentation

- Document all public functions and classes using docstrings.
- Update the [API documentation](api.md) if you add or modify public APIs.
- Build and preview the documentation locally:
    ```bash
    cd docs
    DOCS_VERSION=test make clean versioned-html
    ```

## Pull Request Checklist

- [ ] User's Guide has been updated if needed
- [ ] Developer's Guide has been updated if needed
- [ ] API documentation lists any new or modified class, method, or function
- [ ] Documentation builds cleanly and changes look as expected
- [ ] Tests pass and new features are covered by tests
- [ ] PR description includes a summary and any relevant issue references
- [ ] `Testing` comment, if appropriate, in the PR documents testing used to verify the changes

Thank you for helping improve `mache`!
