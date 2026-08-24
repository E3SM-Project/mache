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

It also proposes that `mache` describe how much memory a machine's nodes
have, in the same way it already describes their cores and GPUs. Memory is
the one resource a placement deliberately does *not* carry, for reasons
given below, and the two proposals together draw the line: `mache` says what
a machine has and where a launch goes; the caller decides what fits.

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

**Asking for memory changed nothing observable.** Giving a launch a share of
the node's memory neither fixed the serialization — the unstated GPU claim
did that — nor appeared to reserve anything. This is a negative result and
it is the reason memory is absent from the placement type: a memory figure
rendered into a launch command would reserve nothing and prevent nothing,
while implying to every reader that it did.

The limit of that evidence is worth stating, since it decides a boundary.
It shows memory was not the cause of the serialization. It does not show
that a memory request is inert on every machine, and in particular nobody
has yet checked whether a launch given a small allowance is killed for
exceeding it. Polaris's Phase A validation includes that check, and if some
machine turns out to enforce, a memory field becomes worth adding — as an
additive change, on evidence, rather than now on expectation.

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

### Requirement: Describe how much memory a node has

`mache` must report the memory available on a machine's nodes, as a
per-node figure and as an allocation-wide total, beside the core and GPU
counts it already reports.

A caller running several pieces of work inside one allocation has to decide
how many of them fit, and memory is one of the quantities that decides it.
That number is a property of the machine, which is what `mache` is for; a
caller that had to discover it for itself would either hard-code it per
machine — duplicating exactly what `mache` exists to centralize — or read it
from a node it has not been given yet.

The figure must be the memory a job may actually use, not the hardware
total, since the two differ by enough to matter and it is the smaller one a
caller must not exceed.

---

### Requirement: A placement says where, not how much memory

The placement type must not carry memory.

Every field in a placement is rendered into a launch command. On the
machines measured, a memory field would render into nothing, or into an
option that demonstrably does nothing — and a caller reading the type would
reasonably conclude that `mache` was keeping memory apart for it, which is
the one thing nothing here can do.

This keeps a clean division. `mache` describes what a machine has and
renders where a launch goes. Deciding how much of the machine each piece of
work may take is the caller's, because only the caller knows what else it is
running.

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

There is no scheduler on PALS to hand out GPUs, so a total is not enough
there: something has to name the devices. Deriving them from the placement's
core set would work only while every concurrent launch has the same shape,
and would collide the first time launches of different sizes ran beside each
other. Only the caller sees every launch running at that moment, so the
placement carries the device indices the caller assigned, and `mache` renders
them rather than guessing. The total remains the machine-independent
statement and is what Slurm is given; a PALS placement that asks for GPUs
without naming them is an error, not an invitation to choose.

The variable is set on the command line rather than exported, so a value
cannot leak from the parent into a later launch that meant to set its own.
This follows what E3SM's own `config_machines.xml` already does on these
machines.

Setting it is all that is done. Removing it first as well, so that nothing
inherited could survive, is what the first implementation did — and Aurora's
PALS `mpiexec` has no `--env-remove`, rejects the whole command when given
one, and so failed every placed launch on the machine before any of them
started. The removal was belt and braces to begin with, since `--env` sets
the variable explicitly and that already overrides whatever was inherited.
It would only have mattered if setting an *empty* value differed from not
setting one, which is the open question below rather than something the
removal answered.

The variable is given as two arguments, `--env VAR=VAL`, which is the form
PALS's usage text describes. Whether `--env=VAR=VAL` would also be accepted
is not known: the Aurora command was rejected at `--env-remove` before its
parser reached the `--env` after it. The two-argument form is the one with
evidence behind it, because every other option `mache` renders for PALS —
`--depth`, `--hosts`, `--cpu-bind list:` — is rendered that way and did get
past that parser.

### A machine's memory

`memory_per_node` joins `cores_per_node` and `gpus_per_node` as a
`[parallel]` config option in each shipped machine config, and
`ParallelSystem` exposes it alongside an allocation-wide `memory`, computed
from it and the node count exactly as `cores` is computed from
`cores_per_node`. Nothing in `get_parallel_command()` reads it. It is
machine description, and it travels the same path as the rest of the
machine description.

Two details are worth fixing rather than leaving to whoever fills in the
configs.

**Megabytes, as an integer.** It matches the unit Slurm's memory options
default to, and the unit callers already use — Polaris's step attribute is
in megabytes — so no conversion sits between the number written down and the
number acted on. Gigabytes would read better in a config file and would
force every usable-memory figure to be rounded to something wrong.

**The number is what the site reports as available, rounded down**, not the
hardware capacity. On a Slurm machine that is what `sinfo` reports for the
node, which is already net of what the operating system and the site's own
services hold back. The two differ by several percent, and the whole value
of the figure is that a caller can pack up to it.

Machine configs give one value per machine, as they already do for cores and
GPUs. On a machine with more than one node type this describes the type the
config's constraint selects, which is the existing convention and its
existing limitation; memory does not make it worse and should not be the
occasion for fixing it.

### The first values will be estimates, and must be corrected

Whoever adds these options to the machine configs cannot measure them. The
figure that matters is what a job on that machine may actually allocate, and
that is knowable only from the machine — not from vendor specifications, not
from site documentation, and not from what a login node's `/proc/meminfo`
happens to say. The initial values will therefore be estimates, and they
must be labeled as estimates in the configs rather than shipped looking like
facts.

Two things follow.

**Estimates must err low.** Too high is a job killed for exhausting a node;
too low is a job that packs less work than it could. The failure directions
are not comparable, so an unverified figure should be rounded down hard
enough that being wrong is merely wasteful.

**The correction has to be someone's job, and the only opportunity is
already scheduled.** Polaris's Phase A validation runs on Chrysalis,
Perlmutter CPU and GPU, Frontier and Aurora — the same five machines these
configs describe — and it is the point at which anyone is on all of them
with a reason to look. Measuring the per-node memory there and returning
corrections is part of that work, described in Polaris's Phase A design
document. This is easy to lose between two repositories, which is why it is
written down in both.

Each config option should carry a comment saying whether its value has been
measured or is still an estimate, and that comment should be removed as each
machine is verified. A reader can then see at a glance which machines are on
firm ground, and an unverified machine cannot quietly pass for a verified
one.

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

- a small placement type in `mache.parallel`, holding nodes, cores, a GPU
  total and — only where the batch system does not assign GPUs itself — the
  device indices the caller chose;
- an optional argument to `ParallelSystem.get_parallel_command()`, and a
  rendering of it in `SlurmSystem`, `PbsSystem` and `SingleNodeSystem`;
- capability detection, computed once and reported;
- `SlurmSystem` gains version detection, since its rendering depends on it;
- `memory_per_node` as a `[parallel]` config option in every shipped machine
  config, with `memory` and `memory_per_node` on `ParallelSystem`.

The memory work is independent of the placement work and shares none of its
code. It is here because it is the other half of what a caller needs in
order to schedule concurrent launches, and because splitting a machine's
description across two repositories would be worse than the small amount of
unrelatedness in one document. It can land separately and in either order.

`SingleNodeSystem` can honor a core set and should, since it makes the
capability testable without a batch system at all. It confines a launch with
`taskset`, which the whole process tree inherits, and reports the
CPU-binding mechanism.

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

Because a missing `memory_per_node` would leave a caller unable to schedule
on a machine that otherwise works, every shipped machine config must be
checked for it, in the same way the placement rendering is checked against
every shipped config. An omission should fail in CI, when a machine is added
or edited, rather than on the machine.

CI cannot check that the value is *right* — no test has a node to compare
against. The only check on correctness is the measurement on real machines
described above, and the honest statement of the situation is that a value
CI accepts is a value nobody has verified.

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

These findings were established with throwaway scripts that are not being
preserved. The per-machine results they produced are recorded in Polaris's
task-parallelism design documents, which is where to look for the detail
behind the requirements above.
