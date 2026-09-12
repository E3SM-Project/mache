---
name: review-comments
description: Write a review comment, review findings, or a reply to review feedback on a GitHub pull request. Use when reviewing code, reporting what testing someone else's branch turned up, or answering a reviewer's question.
---

# Review comments

The reader is deciding what to change.

- Put each finding as an inline comment on the line it concerns, one point
  each. That is where colleagues put them, and it is why their review
  bodies are short.
- The review body summarizes: what you ran, and the verdict. Two or three
  sentences.
- Use a list in the body only for requests that span files.
- No section on what already works. One line for all of it, if any.
- Say what you could not check.

## Calibration

Measured over review comments from 2023 and 2024, before any agent wrote
here. Review bodies run 14 words at the median, 34 at the ninetieth
percentile, and 97 at the longest. Inline comments run 21 words at the
median, 72 at the ninetieth percentile, and 165 at the longest. No agent
has posted a review here yet; one on Polaris, a sibling repository with
the same conventions, ran 1117 words with the findings starting 444 words
in.

## Enough

Inline, one point and a suggestion:

> Here and elsewhere, everything after `autosummary` needs to be indented
> 3 spaces, not 4. I don't know why sphinx is so picky about that but it
> is...
>
> ```suggestion
>    :toctree: generated/
> ```

> Currently, PBS isn't supported by any of the downstream tools (notably
> the Compass and Polaris software) and we don't have a computing
> allocation on the Polaris machine anyway.

In the body, what was run and the verdict:

> This worked for me on Chrysalis even outside of a git repository,
> whereas I am seeing failures without the `MANIFEST.in`.

> @altheaden, this looks great! There are just some descriptions of the
> now-removed parameters in the docstrings that also need to be removed.

## Too much

The Polaris review spent its first 444 words on "How this was reviewed",
"What the previous review asked for" and four paragraphs of "What works",
then traced each finding's mechanism:

> It is static: computed once in the `MOC` constructor from `NumBins`,
> `MinLat` and `MaxLat`, and never updated. But it is attached to the
> output streams with `addField()` like any other field, so every reduction
> in every file carries a copy of the same 61 numbers.
