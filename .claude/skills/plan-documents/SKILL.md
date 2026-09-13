---
name: plan-documents
description: Write a plan for work not yet started, for a colleague or the user to approve before implementation begins.
---

# Plan documents

The reader is deciding whether to let you proceed.

- Open questions and anything needing a decision go at the top.
- The steps, in order, one line each.
- Do not justify each step. Do not list the files you will touch. Do not
  restate the codebase back.
- If a step needs a paragraph to explain, it belongs in a design document.

## Enough

Plans are approved in conversation rather than committed, so there is no
human example in this repository to copy. The following is constructed.

> **Open:** should the Frontier queue change go in here, or wait for #464?
>
> 1. Fall back to the login system when the Slurm job has ended.
> 2. Add `get_slurm_job_state()` and use it in the discovery.
> 3. Tests for both.
> 4. Rerun the Polaris `pr` suite on Chrysalis against a `main` baseline.
