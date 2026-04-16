# Automated `config_machines.xml` updates

This page describes the automation that watches for upstream changes to
E3SM's `config_machines.xml`, opens or refreshes a Copilot task when drift is
detected, and explains how maintainers are expected to review the resulting
pull request.

## Goal

`mache` keeps a repository-local copy of the upstream E3SM machine list in
`mache/cime_machine_config/config_machines.xml`.

The automation added here does **not** edit that file directly. Instead, it:

1. Compares the copy in `mache` against the current upstream E3SM source.
2. Produces a structured report describing any drift for supported machines.
3. Creates or updates one GitHub issue that assigns the work to Copilot.
4. Lets Copilot open a PR that updates `config_machines.xml` and any related
   Spack configuration.

This keeps the source-of-truth update in a reviewed pull request rather than a
silent CI-side commit.

## Pieces of the automation

### Daily workflow

`.github/workflows/cime_machine_config_update.yml`
: Runs once a day at `0 8 * * *` and can also be started manually with
  `workflow_dispatch`.

The job:

1. Checks out `main`.
2. Sets up the `py314` Pixi environment.
3. Installs `mache` from the checked-out repository.
4. Runs `utils/update_cime_machine_config.py`.
5. Uploads the generated JSON and Markdown report artifacts.
6. Runs `utils/manage_cime_machine_config_issue.py` when `GH_CLI_TOKEN` is
   configured.

### Copilot environment workflow

`.github/workflows/copilot-setup-steps.yml`
: Defines the setup steps the Copilot cloud agent can use on the default
  branch so it starts from a working Pixi environment with `mache` installed.

### Drift report builder

`utils/update_cime_machine_config.py`
: Downloads the current upstream E3SM `config_machines.xml`, compares it with
  `mache/cime_machine_config/config_machines.xml`, prints a short console
  summary, and optionally writes:

  - a JSON report for machine-readable automation,
  - a Markdown issue body for Copilot and human reviewers.

`mache/cime_machine_config/report.py`
: Contains the structured comparison logic. It determines which supported
  machines changed, identifies module and environment-variable drift, infers
  related package groups, and lists candidate Spack template files to review.

### Issue synchronization

`utils/manage_cime_machine_config_issue.py`
: Owns the GitHub-side lifecycle for the automation issue.

If drift exists, it creates or updates the issue.

If no drift exists, it closes the existing issue.

If Copilot assignment fails, it falls back to creating or updating the same
issue without Copilot assignment so the report is still visible.

### Tests

`tests/test_cime_machine_config_report.py`
: Verifies that the report builder detects relevant drift and that the rendered
  issue body contains the required maintainer instructions.

## How `config_machines.xml` gets updated

The important point is that the scheduled workflow never edits
`mache/cime_machine_config/config_machines.xml` itself.

The update path is:

1. The workflow detects drift between the `mache` copy and upstream E3SM.
2. The workflow creates or refreshes a GitHub issue.
3. Copilot is assigned to that issue.
4. Copilot opens a pull request against `main`.
5. That PR replaces `mache/cime_machine_config/config_machines.xml` with the
  latest version from `E3SM-Project/E3SM`, then updates any related Spack
  templates or version strings that the report indicates should be reviewed.
6. A maintainer reviews and merges the PR.
7. The next daily run compares the merged repository state against upstream
   again.

If the PR fully resolved the drift, the issue is closed automatically on the
next run.

If only part of the drift was resolved, the issue stays open and its body is
updated to reflect the remaining work.

## What Copilot is told to do

Copilot receives instructions from two places.

### Fixed API-level instructions

`utils/manage_cime_machine_config_issue.py` adds the following guidance in the
`agent_assignment` payload:

- Use the issue body as the task definition.
- Run `pixi run -e py314 python utils/update_cime_machine_config.py
  --work-dir .`.
- Replace `mache/cime_machine_config/config_machines.xml` with the generated
  `upstream_config_machines.xml`, then remove that temporary file before
  committing.
- State the upstream E3SM commit hash in the PR summary.
- Then update related Spack templates and version strings under
  `mache/spack/templates/<machine>*.yaml`,
  `mache/spack/templates/<machine>*.sh`, and
  `mache/spack/templates/<machine>*.csh`.
- Add TODO comments in the PR when prefix or path changes need reviewer
  confirmation.

### Generated issue-body instructions

`mache/cime_machine_config/report.py` renders the issue body for the current
drift and includes:

- the timestamp and upstream source URL,
- the upstream revision when it could be resolved from GitHub,
- the workflow run URL,
- the list of affected supported machines,
- the required work list,
- per-machine details such as package groups, prefix or path variables, and
  candidate Spack templates to inspect.

The required work section tells Copilot to:

- run `pixi run -e py314 python utils/update_cime_machine_config.py
  --work-dir .`,
- replace `mache/cime_machine_config/config_machines.xml` with the generated
  `upstream_config_machines.xml`,
- remove `upstream_config_machines.xml` before committing,
- state the upstream E3SM commit hash in the PR summary,
- update Spack templates and version strings in
  `mache/spack/templates/<machine>*.yaml`,
  `mache/spack/templates/<machine>*.sh`, and
  `mache/spack/templates/<machine>*.csh` when module or environment drift
  implies different package versions,
- keep the PR focused when the change is only version or module drift,
- add a TODO in the PR instead of guessing when a new prefix or path is not
  obvious.

## Why this does not create a new issue every day

The workflow is designed to reuse one open issue rather than create a new one
for every scheduled run.

`utils/manage_cime_machine_config_issue.py` looks for an existing open issue
with the fixed title stored in the workflow environment:

- `ISSUE_TITLE: Daily config_machines drift detected`

The lifecycle is:

1. If no matching open issue exists and drift is detected, create one.
2. If a matching open issue already exists and drift is still present, update
   that same issue.
3. If no drift remains and the issue exists, close it.

That means an unresolved drift while you are away does **not** produce a fresh
issue every day. The same issue remains open and is refreshed in place.

A new issue would only be created if one of these is true:

- the existing automation issue was manually closed while drift still exists,
- the issue title configured in the workflow was changed,
- the existing issue was deleted or otherwise no longer appears as an open
  issue in the repository.

## Reviewer workflow

When Copilot opens a PR from this issue, the reviewer should check the changes
in this order.

### 1. `config_machines.xml` changes

Verify that the PR replaces
`mache/cime_machine_config/config_machines.xml` with the current upstream file
from `E3SM-Project/E3SM`, rather than hand-editing only selected machine
blocks.

The supported-machine report from the workflow tells you which machine entries
caused the drift and which sections deserve the closest review.

In practice, the easiest cross-check is to compare the PR against the report
artifact and the upstream XML source from the workflow run that opened or
refreshed the issue.

### 2. Related Spack updates

If the report lists package groups or candidate Spack templates, check that the
PR updated the relevant `mache/spack/*.yaml` inputs and any version strings
that should track the new module or environment values.

If the report does not indicate Spack-relevant drift, the PR should usually be
limited to `config_machines.xml`.

### 3. Ambiguous path or prefix changes

When upstream changes a path-like variable such as `NETCDF_PATH`, the correct
replacement in `mache` may not be obvious from the XML alone.

In that case, the expected behavior is **not** to guess. The PR should leave a
TODO note for the reviewer and explain what needs confirmation.

### 4. Validation

At minimum, reviewers or PR authors should run the same local checks used by
development in this repository.

Generate the current report locally:

```bash
pixi run -e py314 python utils/update_cime_machine_config.py \
  --json-output /tmp/cime_machine_config_report.json \
  --markdown-output /tmp/cime_machine_config_report.md
```

Run the focused tests:

```bash
pixi run -e py314 pytest tests/test_cime_machine_config_report.py
```

Run pre-commit on changed files before merging:

```bash
pixi run -e py314 pre-commit run --files <changed files>
```

## Manual dry run for maintainers

To exercise the detection path without waiting for the cron schedule:

1. Trigger the workflow manually with `workflow_dispatch`, or
2. Run `utils/update_cime_machine_config.py` locally in the Pixi environment.

If `GH_CLI_TOKEN` is not configured, the workflow still generates and uploads
the report artifacts but skips issue synchronization.

That is a safe way to validate the comparison and report rendering logic
without asking Copilot to act on the result.

## Operational notes

- `GH_CLI_TOKEN` should be a user token with access to create and update
  issues in the repository. A classic PAT with `repo` scope is sufficient.
- Copilot assignment additionally depends on Copilot cloud agent being enabled
  for the repository.
- The workflow uses the repository's current `main` branch as the comparison
  baseline and as the branch Copilot is asked to target.