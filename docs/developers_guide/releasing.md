# Releasing a New Version

This document describes the steps for maintainers to tag and release a new
version of `mache`, and to update the conda-forge feedstock. Releases are
also published to PyPI automatically when a tag is pushed.

## Building the Conda Package Locally with Rattler Build

Before publishing or updating the feedstock, you can build the local conda
package from this repository with `rattler-build`:

```bash
rattler-build build -m conda/variants/linux_64_.yaml -r conda/recipe/ --output-dir output
```

This uses:

- `conda/variants/linux_64_.yaml` for build variants
- `conda/recipe/` for the package recipe
- `output` as the local output directory for generated artifacts

If you are already using the repository's pixi environment, you can also run:

```bash
pixi run rattler-build build -m conda/variants/linux_64_.yaml -r conda/recipe/ --output-dir output
```

The resulting package is typically written under `output/noarch/` because the
recipe is currently `noarch: python`.

This local build is useful when:

- testing release changes before tagging,
- validating recipe edits while working on `mache.deploy` or `mache.jigsaw`,
- debugging downstream deployment issues against an unpublished package.

## Version Bump and Dependency Updates

1. **Update the Version Number**

   - Manually update the version number in the following files:
     - `mache/version.py`
     - `conda/recipe/recipe.yaml`

   - Make sure the version follows [semantic versioning](https://semver.org/).
     For release candidates, use versions like `1.31.0rc1`.

2. **Check and Update Dependencies**

   - Ensure that dependencies and their constraints are up-to-date and
     consistent in:
     - `conda/recipe/recipe.yaml` (for the local recipe used by `rattler-build`)
     - `pyproject.toml` (for PyPI; used for sanity checks)
     - `dev-spec.txt` (development dependencies; should be a superset)

   - Use the GitHub "Compare" feature to check for dependency changes between
     releases:
     https://github.com/E3SM-Project/mache/compare

3. **Make a PR and merge it**

   - Open a PR for the version bump and dependency changes and merge once
     approved.

## Tagging and Publishing a Release Candidate

4. **Tagging a Release Candidate**

   - For release candidates, **do not create a GitHub release page**. Just
     create a tag from the command line:

     - Make sure your changes are merged into `main` or your own update branch
       (e.g. `update-to-1.31.0`) and your local repo is up to date.

     - Tag the release candidate (e.g., `1.31.0rc1`):

       ```bash
       git checkout main
       git fetch --all -p
       git reset --hard origin/main
       git tag 1.31.0rc1
       git push origin 1.31.0rc1
       ```

       (Replace `1.31.0rc1` with your actual version, and `main` with your
       branch if needed.)

     **Note:** This will only create a tag. No release page will be created on
     GitHub.

## Publishing to PyPI

   - Pushing any tag runs the
     [publish workflow](https://github.com/E3SM-Project/mache/actions/workflows/publish_workflow.yml),
     which builds the sdist and wheel, checks that the tag matches
     `mache/version.py`, and publishes them to PyPI as
     [`e3sm-mache`](https://pypi.org/project/e3sm-mache/). The name `mache`
     on PyPI belongs to an unrelated project.

   - Release candidates are published as well. `pip` and `uv` do not install
     pre-releases unless asked to, so this serves as an end-to-end test of
     the release before the stable tag.

   - Publishing uses PyPI
     [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no
     API token is needed. The trusted publisher registered on PyPI must
     match this repository, the workflow file name `publish_workflow.yml`,
     and the `pypi` GitHub environment. Only PyPI owners of `e3sm-mache`
     can change this.

   - PyPI never allows a file to be uploaded twice, so if a published
     release is broken, fix it and tag a new version (e.g. `1.31.0rc2`)
     rather than moving the tag.

   - Check the workflow run in GitHub Actions, then test the release in a
     clean environment:

     ```bash
     uvx --from e3sm-mache==<version> mache --help
     ```

## Updating the conda-forge Feedstock for a Release Candidate

5. **Manual Feedstock Update (Required for Release Candidates)**

   - The conda-forge feedstock does **not** update automatically for release
     candidates.
   - You must always create a PR manually, and it must target the `dev`
     branch of the feedstock.

   Steps:

   - Download the release tarball:

     ```bash
     wget https://github.com/E3SM-Project/mache/archive/refs/tags/<version>.tar.gz
     ```

   - Compute the SHA256 checksum:

     ```bash
     shasum -a 256 <version>.tar.gz
     ```

   - In the `recipe.yaml` of the feedstock recipe:
     - Set `context.version: <version>`
     - Set the new `sha256` value
     - Update dependencies if needed

   - Commit, push to a new branch, and open a PR **against the `dev` branch**
     of the feedstock:
     https://github.com/conda-forge/mache-feedstock

   - Follow any instructions in the PR template and merge once approved

## Releasing a Stable Version

6. **Publishing a Stable Release**

   - For stable releases, create a GitHub release page as follows:

     - Go to https://github.com/E3SM-Project/mache/releases
     - Click "Draft a new release"
     - Enter a tag (e.g., `1.31.0`)
     - Set the release title to the version prefixed with `v` (e.g., `v1.31.0`)
     - Generate or manually write release notes
     - Click "Publish release"

## Updating the conda-forge Feedstock for a Stable Release

7. **Automatic Feedstock Update (Preferred Method)**

   - Wait for the `regro-cf-autotick-bot` to open a PR at:
     https://github.com/conda-forge/mache-feedstock

   - This may take several hours to a day.

   - Review the PR:
     - Confirm the version bump and dependency changes
     - Merge once CI checks pass

   **Note:** If you are impatient, you can accelerate this process by creating
   a bot issue at: https://github.com/conda-forge/mache-feedstock/issues with
   the subject `@conda-forge-admin, please update version`. This will open a
   new PR with the version within a few minutes.

   - If the bot PR does not appear or is too slow, you may update manually (see
     the manual steps for release candidates above, but target the `main`
     branch of the feedstock).

## Post Release Actions

8. **Verify and Announce**

   - Install the package in a clean environment to test:

     ```bash
     conda create -n test-mache -c conda-forge mache=<version>
     ```

     and check that the PyPI release is present at
     https://pypi.org/project/e3sm-mache/

   - Optionally announce the release on relevant communication channels

   - Update any documentation or release notes as needed
