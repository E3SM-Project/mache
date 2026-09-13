---
name: testing-comments
description: Write a Testing comment on a pull request, recording what was run and what the results were. Use after running suites, tests or linting for a PR.
---

# Testing comments

What you ran, where, and whether it passed.

- Name the suite, the machine and the compiler. One sentence.
- Give the work directory or the baseline you compared against.
- Say the result. Bit-for-bit, passed, or the numbers if they matter.
- Use a table only when there are several runs to compare.
- Do not restate in prose what a table or a pasted result already shows.
- Failures unrelated to the branch go under their own heading at the end.

## Calibration

Measured over Testing comments from 2023 and 2024, before any agent wrote
here. They run 40 words at the median, 68 at the ninetieth percentile, and
161 at the longest, in one or two paragraphs. A recent agent-written one
ran 1339 words in 35 paragraphs.

## Enough

> ## Testing
>
> I built a spack environment on Chrysalis with `polaris` using this
> branch. Without the Chrysalis OS fix, spack was unable to build the
> environment.

> ## Testing
>
> Deployed test spack builds with nvidia and nvidiagpu on Perlmutter using
> these fixes. Without them, spack fails to build `findutils` and (for
> nvidia) `cray-libsci`.

When the results are worth pasting, paste them and stop:

> ## Testing
>
> I was able to build an intel environment on pm-cpu using this change.
> However, there is a warning present at the end:
> ```shell
> Loading Spack environment...
> ==> Warning: could not load runtime environment due to RuntimeError: Trying to source non-existing file: /opt/cray/libfabric/1.20.1/compilers_and_libraries/linux/bin/compilervars.sh
> Done.
> ```

## Too much

A real agent-written comment opened with "The short version", then gave
the rest of its 1339 words to "How it was tested", a list of every unit
test by name, and a section per machine:

> The rest of this comment is the evidence behind those claims. It is
> written for provenance rather than for reading start to finish.

A Testing comment is read start to finish or not at all. "Ran in batch
jobs and `salloc` shells on Chrysalis and Perlmutter; the fast path never
answered wrongly and the #476 case is unchanged" is the whole of it, and
the evidence belongs on a branch that the comment links.
