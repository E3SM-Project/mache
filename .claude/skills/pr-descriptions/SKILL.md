---
name: pr-descriptions
description: Write or update a pull request description, including drafting pr_description.md before opening a PR. Use when opening a pull request or editing its body.
---

# Pull request descriptions

The reader is deciding whether to review.

- What changed and why, in a few sentences. Not how.
- Anything needing a reviewer decision goes in its own short list near the
  top, never mid-paragraph.
- A list of changed behaviours is fine. A trace of the mechanism is not.
- No commit list. No testing; that goes in a separate `Testing` comment.
- Link the issue or upstream pull request that gives context.
- Several fixes usually means several pull requests.

## Calibration

Measured over pull requests from 2023 and 2024, before any agent wrote here
(dependabot excluded). Descriptions run 19 words at the median, 36 at the
seventy-fifth percentile, 52 at the ninetieth, and 124 at the longest.
Recent agent-written ones ran 633 and 728 words, five times the longest a
colleague has written.

## Enough

A bug fix, stated and done:

> These filepaths changed, causing errors when building an intel
> environment on pm-cpu. This PR fixes them.

A machine update, with the changes as a list:

> This merge adds:
> * spack support for `gnugpu` and `crayclang(gpu)` on Frontier
> * It updates the number of cores per node to 64 to match the
>   documentation and what slurm sees.

A new capability, with the context a reviewer needs and nothing else:

> We want to be able to build spack environments for external machines
> that aren't supported by `mache` or E3SM. This merge allows a config
> file to be passed to `make_spack_env()` and `get_spack_script()` for an
> external machine. There is already support for passing a template yaml
> file for defining the spack environment.

## Too much

A real agent-written description ran 728 words and traced the mechanism
of a check it was making cheaper:

> A process running on one of the allocation's own nodes settles the
> question without asking anyone. Slurm kills a job's processes before it
> releases its nodes, so a process still running on an allocated node is
> itself proof that the allocation survives. That covers exactly the case
> the rate is a problem for -- a batch job and everything it launches --
> and it costs a string comparison against `SLURMD_NODENAME`, falling back
> to expanding `SLURM_JOB_NODELIST` with `scontrol show hostnames`, which
> is local work rather than a controller query.

Someone deciding whether to review does not need the proof. "Skip the
controller query when running on one of the job's own nodes" would do; the
rest belongs in the commit message.
