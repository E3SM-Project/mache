# Quick Start for Developers

This guide is for contributors to `mache`. For general installation and usage,
see the [User's Guide](../users_guide/quick_start.md).

(dev-installing-mache)=

## Setting up for Development

To work on `mache`, you should install the development version in an isolated environment:

```bash
pixi install
pixi run python -m pip install --no-deps --no-build-isolation -e .
```

This creates a Pixi environment based on the root `pixi.toml` and then installs
`mache` in editable mode.

(dev-code-styling)=

## Code Styling and Linting

`mache` uses [`pre-commit`](https://pre-commit.com/) to enforce code style and
quality. After setting up your environment, run:

```bash
pre-commit install
```

This only needs to be done once per environment. `pre-commit` will
automatically check and format your code on each commit. If it makes changes,
review and re-commit as needed. Some issues (like inconsistent variable types)
may require manual fixes.

Internally, `pre-commit` uses:

- [ruff](https://docs.astral.sh/ruff/) for PEP8 compliance and import formatting,
- [flynt](https://github.com/ikamensh/flynt) to convert format strings to
  f-strings,
- [mypy](https://mypy-lang.org/) for type checking.

Example error:

```bash
example.py:77:1: E302 expected 2 blank lines, found 1
```

In this case, add a blank line after line 77 and try again.

You may also use an IDE with a PEP8 style checker, such as [PyCharm](https://www.jetbrains.com/pycharm/). See
[this tutorial](https://www.jetbrains.com/help/pycharm/tutorial-code-quality-assistance-tips-and-tricks.html)
for tips.
```bash
example.py:77:1: E302 expected 2 blank lines, found 1
```

For this example, we would just add an additional blank line after line 77 and
try the commit again to make sure we've resolved the issue.

You may also find it useful to use an IDE with a PEP8 style checker built in,
such as [VS Code](https://code.visualstudio.com/). See
[Formatting Python in VS Code](https://code.visualstudio.com/docs/python/formatting)
for some tips on checking code style in VS Code.

## Running Tests

To run the test suite:

```bash
pytest
```

Make sure all tests pass before submitting a pull request.

## Contributing

- Follow PEP8 and project code style.
- Use descriptive commit messages.
- Add or update tests for new features or bug fixes.
- Document public functions and classes.

For more details, see the [contributing guide](contributing.md).

