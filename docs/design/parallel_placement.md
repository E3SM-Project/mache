# Design Document: parallel placement

## Summary

`mache.parallel` builds the command that launches parallel work on an HPC
system — `srun` on Slurm machines, `mpiexec` on PBS machines. Today that
command always asks for resources in the abstract: this many tasks, this many
CPUs each. It has no way to say *where* the work should run.

That is sufficient while the target software runs one piece of work at a time.
It is the blocking limitation as soon as it wants to run two, because two
launches that each describe their needs in the abstract will be given
overlapping resources, or — more often — the second will wait until the first
has finished.

This document proposes adding an optional **placement** to
`get_parallel_command()`: a description of which nodes, how many cores and
how many GPUs a particular launch should be confined to. Target software
describes the placement; `mache` renders it into whatever the machine's
launcher needs.

The immediate driver is Polaris, which is adding the ability to run
independent steps concurrently within one allocation. The capability is not
Polaris-specific; anything running several pieces of work inside one
allocation needs it.

---

## Background: what was measured

The requirements below are not derived from documentation. They come from
running concurrent placed launches on Chrysalis, Perlmutter (CPU and GPU),
Frontier and Aurora, and recording what each machine actually did. Four
results shaped this design.

**Launching is cheap.** Between 60 and 670 launches per minute depending on
the machine. A widely held belief that Perlmutter throttles `srun` to roughly
one launch a minute did not survive measurement; the symptom that produced
that belief was concurrent launches queueing, not launches being rate
limited.

**Slurm changed meaningfully at 20.11.** Before that release, job steps share
a node's resources by default, and the options that now control this do not
exist — passing them is an error, not a no-op. After it, a step reserves what
it asks for, and two steps that ask for everything will serialize. Both eras
are in production on machines Polaris supports: Chrysalis runs 20.02,
Perlmutter and Frontier run 25.11.

**An unstated GPU requirement is read as a claim on all of them.** This, and
not memory or CPU contention, is what prevented concurrency on the GPU
machines: a launch that said nothing about GPUs implicitly reserved every
one on the node, so the next waited. Constraining CPUs does not constrain
GPUs. The consequence for the API is that a placement must be able to say
"no GPUs" explicitly, and that saying nothing must not be treated as
equivalent — for most callers, whose work uses no GPUs at all, the explicit
"none" is the common case.

**GPUs must be requested as a per-launch total.** Requesting a number of GPUs
*per task* does not confine a launch — measured on both GPU machines. A
per-launch total does. This is a genuine asymmetry with how CPUs are
described, and the API has to reflect it rather than smooth it over.

---

## Requirements

*Date last modified: Aug 23, 2026*

*Contributors: Xylar Asay-Davis, Claude*

---

### Requirement: Express placement without machine-specific knowledge

Target software must be able to say where a launch should run in terms it
already understands — nodes, cores, GPUs — without knowing the flags any
particular machine uses.

The flags differ not only between Slurm and PBS but between Slurm versions on
similar machines. If target software has to know them, that knowledge spreads
into every caller and has to be updated whenever a site upgrades.

---

### Requirement: Isolation enforced by the batch system

Where the batch system can keep concurrent launches on separate resources, it
must be asked to do so.

`mache` should not implement placement by pinning processes itself when the
scheduler can do it. Scheduler-enforced placement is a stronger guarantee:
work that ignores an affinity mask is not prevented from doing so, whereas
work given a resource reservation cannot exceed it.

---

### Requirement: Support both eras of Slurm

Placement must work on Slurm both before and after the 20.11 change in job
step behavior.

On older Slurm the modern options do not exist and passing them fails
outright, so a different mechanism is required. Explicit CPU binding is
available there and was measured to give concurrent launches disjoint cores.
This is a weaker guarantee than a reservation, and `mache` must report which
mechanism it used so callers can decide whether that is acceptable.

---

### Requirement: Support PBS with PALS

Placement must work on PBS systems using the PALS launcher, where concurrent
launches within one job are already supported and are placed by naming hosts
and CPU lists explicitly.

The usable set of cores on such a machine may not be contiguous and may not
start at zero. Placement must be expressible as an explicit set rather than
as a count.

---

### Requirement: GPUs as a per-launch total

A placement must express GPUs as a total for the launch, not as a count per
task, for the reason measured above.

The total must default to none, and "none" must be rendered as an explicit
request for no GPUs rather than as an omission. Callers whose work uses no
GPUs — the majority — should get correct behavior without having to know
that GPUs were ever a consideration.

---

### Requirement: Report what the machine supports

`mache` must be able to tell a caller which placement mechanism applies on
the current machine: scheduler-enforced, CPU-binding fallback, or none.

A caller that cannot place work needs to know that before it tries to run
things concurrently, rather than discovering it as a hang or as silent
oversubscription.

---

### Requirement: Existing behavior unchanged

A call to `get_parallel_command()` without a placement must produce exactly
the command it produces today.

---

## Design

*Date last modified: Aug 23, 2026*

*Contributors: Xylar Asay-Davis, Claude*

---

### The placement description

A placement carries three things: the nodes a launch may use, the cores it may
use, and the number of GPUs it needs in total. Cores are given as an explicit
set rather than a count, because that is what the non-contiguous case
requires and because a count cannot express which cores.

`get_parallel_command()` takes it as an optional argument. When it is absent,
nothing changes.

### Rendering per system

Each `ParallelSystem` subclass renders the placement in its own terms. The
three cases established by measurement are:

- **Slurm 20.11 and newer** — ask for exactly the resources the launch needs
  rather than inheriting the job's, name the nodes, and give the GPU total.
  This yields concurrent launches with disjoint cores and disjoint GPUs,
  enforced by Slurm.
- **Slurm before 20.11** — the above options do not exist. Concurrent
  launches already share the node, and placement comes from an explicit CPU
  binding. Report that the weaker mechanism was used.
- **PBS with PALS** — name the hosts and give an explicit core list. GPU
  isolation is by the vendor's visible-device mechanism, which is the
  documented approach on those machines.

### Capability detection

The mechanism must be determined at run time, from the launcher actually
present, not from configuration. The same machine can be upgraded across the
20.11 boundary without its `mache` configuration changing, and a stale
assumption there fails in the worst way: the command is accepted and the
placement silently does nothing.

---

## Implementation

*Date last modified: Aug 23, 2026*

*Contributors: Xylar Asay-Davis, Claude*

---

- a small placement type in `mache.parallel`, holding nodes, cores and GPU
  total;
- an optional argument to `ParallelSystem.get_parallel_command()`, and a
  rendering of it in `SlurmSystem`, `PbsSystem` and `SingleNodeSystem`;
- capability detection, computed once and reported;
- `SlurmSystem` gains version detection, since its rendering depends on it.

`SingleNodeSystem` can honor a core set and should, since it makes the
capability testable without a batch system at all.

This is an additive change. No existing caller passes a placement, so no
existing behavior moves.

---

## Testing

*Date last modified: Aug 23, 2026*

*Contributors: Xylar Asay-Davis, Claude*

---

### Command construction

Unit tests must check the rendered command for each system and each placement
shape: one node, several nodes, a non-contiguous core set, a GPU total, an
explicit request for no GPUs, and no placement at all — which must render
exactly as today.

Slurm must be tested at both sides of the 20.11 boundary, with the version
faked, since both are in production and CI will only ever have one.

### Behavior on real machines

Command construction can be tested without an allocation; whether a machine
honors the command cannot. Validation must include launching several placed
pieces of work concurrently inside one allocation and confirming from inside
each that it sees only the cores and GPUs it was given.

Note that on CUDA machines the visible-device variable is renumbered per
launch, so four launches on four different GPUs all report device `0`.
Verification must use the scheduler's global GPU identifiers instead. This
cost us a round of testing and is worth stating in any test that checks GPU
placement.

The scripts used to establish these findings live in Polaris under
`utils/launcher_spike/` and can be adapted rather than rewritten.
