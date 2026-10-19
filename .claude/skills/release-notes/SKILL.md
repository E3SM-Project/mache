---
name: release-notes
description: Write or revise the notes for a mache GitHub release. Use when preparing a release or rewriting an existing release's description.
---

# Release notes

The reader maintains a package or deployment that uses mache (Polaris,
Compass, E3SM-Unified, MPAS-Analysis) and wants to know what is new and
what they must change when they upgrade. The notes replace GitHub's
generated list of pull requests, but every pull request still appears
somewhere.

## Structure

```
<1 to 3 sentences: what this release is about>

## Major features
### <Theme>
<2 to 4 sentences.> (#N, #M, @author)

## Minor features
### Deployment
### Spack
### Parallel
### Other
- <What changed> (#N, @author)

## Machines
- <Machine>: <what changed> (#N, @author)
- `config_machines.xml` synced with E3SM (#N, #M)

## Breaking changes
## Bug fixes
## Documentation
## Developer tools and CI
## Dependencies
## New contributors
**Full changelog**: https://github.com/E3SM-Project/mache/compare/<prev>...<tag>
```

Drop an empty section or subsection. Many mache releases have only a few
pull requests: then skip Major features and the subsections, and a summary
sentence plus a few bullets under the remaining headings is enough.

## Gathering

- Take the list of pull requests from GitHub, not from merge commits, which
  miss squash merges:
  `gh api repos/E3SM-Project/mache/releases/generate-notes -f tag_name=<tag> -f previous_tag_name=<prev> -q .body`.
  Keep its New contributors list.
- Read each pull request's title, labels and description with
  `gh pr view`.
- Take dependency versions from `pyproject.toml`,
  `conda/recipe/recipe.yaml` and `mache/spack/pins.yaml` at the two tags,
  not from titles.
- Find machine changes with
  `git diff <prev> <tag> -- mache/machines mache/spack/templates`,
  including renamed or removed compilers.

## Sorting

- A major feature is a theme that spans several pull requests or a
  capability a downstream package would adopt. The line is blurry; do not
  agonize over it.
- Machines gets one bullet per machine, naming what changed: modules,
  compiler versions, Spack templates, new or removed machines.
- Breaking changes are what a downstream package must change: the deploy
  files it copies (`deploy.py`, `deploy/cli_spec.json`), its
  `deploy/config.yaml.j2` or hooks, its Spack templates or pins, compiler
  names, supported Python versions, or a public API. A pull request can
  appear both here and in another section.
- Bug fixes say what was wrong, not how it was fixed.
- Collapse the `config_machines.xml` syncs into one line under Machines,
  and the bot updates of GitHub Actions and pre-commit hooks into one line
  under Dependencies.
- Leave out release-candidate version bumps unless they changed a pin, in
  which case they go under Dependencies with that pin.

## Writing

- One line per bullet and per paragraph; GitHub release notes are not
  hard-wrapped.
- Rewrite titles as what changed for the reader, not what the pull request
  did.
- Credit the human: a pull request opened by Copilot or Claude for @xylar
  is `@xylar`.
- End with the signature from `AGENTS.md`.

## Checking

Every number from the generated notes must appear in the draft, apart from
the version bumps you dropped on purpose:

```
gh api repos/E3SM-Project/mache/releases/generate-notes \
    -f tag_name=<tag> -f previous_tag_name=<prev> -q .body \
  | grep -o 'pull/[0-9]*' | cut -d/ -f2 | sort -nu \
  | while read n; do grep -q "#$n\b" notes.md || echo "missing #$n"; done
```

Show the draft to the user before posting it with
`gh release edit <tag> --notes-file notes.md`.

## Example

The 5.0.0 release, in this format:

> mache 5.0.0 moves Spack builds to Spack 1.x, which breaks existing Spack
> instances and templates, and publishes mache to PyPI as `e3sm-mache`.

> ## Breaking changes
> - Spack environments are built with Spack 1.x rather than the
>   `E3SM-Project/spack` fork; downstream packages need a new `spack_path`
>   and Spack templates migrated to the Spack 1.x compiler model (#492)
> - Python 3.10 is no longer supported (#499)

> ## Machines
> - Aurora: oneapi 2026.1.0 (#515, @xylar)
> - Frontier: craygnu templates match cpe/25.09 (#513, @xylar)
> - `config_machines.xml` synced with E3SM (#491, #506, #508, #510, #520)

The Polaris 1.0.0 and 1.1.0 notes show the full format on a large release.
