---
name: design-documents
description: Write or revise a design document under docs/design/. Use when proposing a new capability, not when fixing a bug.
---

# Design documents

Long is fine. A design document is scanned and returned to, not read
straight through. What must be scannable is the specification.

- Normative statements come first in a section and stand alone. Rationale
  goes in a marked block below, which a reader can skip.
- Rejected alternatives and superseded drafts go in one `Decisions`
  section, cited from the places they affect. Never re-argued in place.
- A principle is stated once. Later sections cite it by name.
- Do not pre-empt objections. Drop "worth noting", "not an accident",
  "deliberately", "this is not a stylistic preference". State the decision
  and let it stand.
- Open questions go at the top or in their own section, never
  mid-paragraph.

## Calibration

The two design documents in `docs/design/` run 1,481 and 5,644 words, at
34 and 24 words per sentence, with one and four instances of the hedging
phrases above. Aim for twenty words per sentence and none of them.

There is no template. Follow the structure of the existing documents: a
`Summary`, a `Requirements` section with one `### Requirement:` heading per
requirement, then the design. Requirements say what the capability must
do, not how the software will do it, which is the rule most often broken.

## Enough

From `docs/design/mache_deploy.md`. The heading states the requirement and
the body is one or two normative sentences; the design resolution follows
in its own marked block.

> ### Requirement: A mechanism to begin deployment
>
> The target software must provide a user-facing entry point to begin
> deployment. This mechanism cannot depend on `mache` already being
> installed, because deployment is precisely how `mache` is introduced.
>
> ### Requirement: A mechanism to install pixi
>
> If pixi is not already installed, the deployment process must be able to
> install it automatically.

Some requirements need no body at all.
