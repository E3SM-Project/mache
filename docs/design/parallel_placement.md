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

A caller that has decided can then say so: an optional memory **cap**, given
separately from the placement and absent unless asked for, holds a launch to
a figure the caller deliberately stated. It is a cap and not a reservation,
and it is rendered only on machines that will act on it.

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

**Asking for memory changed nothing observable — but memory is enforced.**
Giving a launch a share of the node's memory neither fixed the serialization
— the unstated GPU claim did that — nor appeared to reserve anything. That
negative result is about serialization and does not generalize, which a
later measurement on the same machines settled: a step given `--mem=1024M`
and told to allocate 4 GB is killed at 960 MB on Perlmutter GPU and on
Frontier, and reaches 4 GB and exits 0 on Chrysalis, whose Slurm predates
20.11.

Both halves point the same way, and together they decide where memory
belongs. Where a memory figure is inert it reserves nothing and prevents
nothing while implying to every reader that it did. Where it is enforced it
is a cap, and work that under-declared would be killed rather than merely
mis-scheduled. Neither is a thing to render on a caller's behalf out of a
field that was filled in loosely — which is why memory stays out of the
placement type, and why a cap is stated separately and only when a caller
means it.

**A placement does not cap memory by itself.** Asking Slurm for exactly the
cores a launch needs does not hand it a slice of the node's memory to go
with them. A placed single-core launch and an unplaced control, neither
mentioning memory, both allocated twice what a single core's proportional
share of the node would be, and neither was touched — measured on Perlmutter
CPU and Frontier. That bounds rather than settles: it shows no ceiling below
the amount tried, and Perlmutter GPU was not tested on the point.

The one worry this raises does not materialize: silence about memory does
not repeat the trap that silence about GPUs sets. An unstated memory
requirement is not read as a claim on the node's memory. On both Perlmutter
GPU and Frontier, four concurrent launches that said nothing about it all
started within 40 ms of each other and ran for their full duration. Aurora
is unmeasured on this point.

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

Every field in a placement is rendered into a launch command, and a memory
field would render into an option whose effect differs by machine: inert on
the older Slurm, and on the newer one a cap that kills a step for exceeding
it. A caller reading the type would reasonably conclude that `mache` was
keeping memory apart for it — which on one machine is a promise nothing here
can keep, and on the other is a limit the caller did not ask to be held to.

This keeps a clean division. `mache` describes what a machine has and
renders where a launch goes. Deciding how much of the machine each piece of
work may take is the caller's, because only the caller knows what else it is
running.

---

### Requirement: A memory cap is stated separately, and only on purpose

A caller must be able to say how much memory a launch may use, as an
argument of its own rather than as part of a placement, absent unless it is
given.

The requirement above rests on a memory figure being rendered "out of a
field that was filled in loosely" — a caller filling in a placement to say
where its work goes, and finding it had also declared a limit it would be
held to. A separate argument removes exactly that. Setting it is a distinct
act, and the caller that performs it has said a number knowing it is a
ceiling.

The two requirements are therefore the same rule seen twice, not a reversal
of one by the other: the placement still says *where*, and how much memory
is a different statement, made in a different place in the signature.

What is being asked for is a **cap, not a reservation**. Nothing measured
suggests such a figure sets memory aside, so it must not be documented in
terms that read as scheduling. And because it means nothing at all on
machines whose launcher has no memory option or ignores the one it has, it
must be rendered only where it will be acted on. A cap on the command line
that nothing keeps is worse than no cap: it reads to everyone who sees the
command as a safety net.

---

### Requirement: Report what the machine supports

`mache` must be able to tell a caller which placement mechanism applies on
the current machine: scheduler-enforced, CPU-binding fallback, or none, and
whether a memory cap will be enforced here.

A caller that cannot place work needs to know that before it tries to run
things concurrently, rather than discovering it as a hang or as silent
oversubscription.

The two reports differ in what they justify. A placement that cannot be
honored is an error, because concurrent launches will then collide. A cap
that cannot be enforced is not: the work runs correctly and is merely
unprotected, so the caller is told rather than stopped, and can record in a
run log that caps do not bite on this machine instead of believing it has a
safety net.

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

A machine's own binding options are kept alongside a placement only where
they do not contradict it, and one value has to be singled out. A `gpu_bind`
of `none` asks Slurm not to bind tasks to GPUs, which is what it does anyway
without the option — so dropping it takes nothing away, and keeping it
appears to take something away. Four concurrent placed launches on Perlmutter
GPU, whose configured `gpu_bind` is `none`, each asked for one GPU: one was
given a GPU and the other three got none, ran anyway and exited 0. Frontier,
whose `gpu_bind` is `closest`, gave all four disjoint GPUs from a nearly
identical command. That `none` suppressed the assignment rather than merely
the binding is a hypothesis, not yet confirmed, and confirming it takes one
rerun on Perlmutter GPU with the option gone. The change is made now because
the asymmetry of the two outcomes is the whole point: a launch that silently
runs on no GPU and exits 0 is the same class of failure as a placement that
silently does nothing.

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

One thing to know before it becomes urgent: PALS's usage output marks both
`--cpu-bind` and `--mem-bind` as deprecated. They are still accepted, and
Aurora's unplaced launches use them and run, so nothing is broken today. But
the PALS placement path is built on `--cpu-bind list:`, so it is that path
that will have to change when they go, and there is no second mechanism on
PALS to fall back to.

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

### A memory cap on a launch

`get_parallel_command()` takes an optional `memory_cap`, in MB, alongside
the placement and independent of it. Absent, nothing about memory is
rendered and every existing caller's command is unchanged.

**Per node, in MB**, which is both what Slurm's `--mem` means and what
`memory_per_node` is denominated in — the figure a caller divides up between
the launches it runs at once. A different denomination would put a
conversion between two numbers the caller has to reason about together.

**Rendered only where it will be acted on.** On Slurm 20.11 and newer that
is `--mem=<N>M`. Chrysalis's Slurm accepts the same option and does not act
on it, and PALS has no equivalent at all; on both, `mache` renders nothing.
Rendering an option known to be inert would put a figure on the command line
that nothing keeps, which is the failure this design objects to everywhere
else: something that reads as though it is working.

The version is a proxy, and worth naming as one. Memory enforcement comes
from the cgroup constraints a site configures, not from the step options
20.11 added; the boundary is the same only because that is where it was
measured. A site running a new Slurm with memory constraints disabled would
be reported as enforcing when it is not. That is why the constant deciding
it is separate from the one deciding step isolation, though the two
currently hold the same number.

**Two values, not three.** Whether a launcher lacks a memory option or
accepts one and ignores it, the consequence for the caller is the same:
nothing here will hold the launch to its cap. `memory_cap_support` says
`ENFORCED` or `NONE` and does not distinguish two ways of being useless.

**Not validated against `memory_per_node`.** The obvious check — refusing a
cap larger than the node is said to have — would reject caps the node can
honor. The shipped figures are conservative by design, and on Perlmutter and
Frontier they measured below what a node actually reported, so `mache` would
be enforcing its own estimate.

**What has not been measured** is whether a stated cap is also a claim. If
Slurm treats `--mem` on a step as a reservation and not only as a limit,
then two concurrent launches whose caps together exceed the node would
serialize, the way an unstated GPU requirement serializes them today.
Nothing measured suggests it does, and nothing measured rules it out: every
concurrency measurement so far was made without caps.

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
enough that being wrong is merely wasteful. This is a rule about
*estimates*. Once a figure has been read off the machine, padding it further
only wastes the node; what is left to worry about is whether the figure is
the partition's smallest, and that is answered by surveying rather than by
rounding down again.

**A single node cannot establish the number.** What a node reports is
evidence about that node. The figure a config needs is the smallest any of
them reports, and getting it costs no allocation — `sinfo -o "%m" -p
<partition>` on Slurm, and take the minimum. This was learned the awkward
way in the first round of measurement, when a figure read off whichever node
a job happened to land on was briefly taken for evidence that one machine
had two node types; the sample had come from a different machine's node. No
machine `mache` ships a config for is currently known to differ in memory
between its nodes.

**The correction was someone's job, and that opportunity has now come
round.** Polaris's Phase A validation ran on Chrysalis, Perlmutter CPU and
GPU, Frontier and Aurora — the same five machines these configs describe.
What came back is that **no shipped value was wrong**: every one sat at or
below what the nodes reported, which is the direction estimates are asked to
err in. Three have now been raised to the measured figure.

| machine | shipped | measured | nodes | standing |
| --- | --- | --- | --- | --- |
| Chrysalis | 253000 | 253000 | partition-wide | surveyed, and agrees; unchanged |
| Perlmutter CPU | 515100 | 515100 | `nid004394`, `nid006473` | raised from 480000; sampled |
| Perlmutter GPU | 257200 | 257200 | `nid002328`, `nid002993` | raised from 240000; sampled |
| Frontier | 512000 | 512000 | `frontier01793`, `03091`, `08884` | raised from 480000; sampled |
| Aurora | 960000 | — | none | never measured |

Every sampled figure came from `sinfo -h -o "%m" -n <node>` on the node the
job actually ran on, which is what the site says a job may use rather than
what the hardware holds.

**Raising them spends the margin the estimates carried, deliberately.** A
value 7% low is not harmless here: Polaris derives every step's default
memory from it, so the shortfall propagates into every step on that machine,
and the figure is read at setup when there is nothing else to go on. Against
that, an optimistic value can no longer over-admit at run time, because
Polaris reads what its assigned nodes report once it is inside the
allocation and accounts against those. So the cost of being slightly high is
now bounded in a way the cost of being persistently low is not.

What it buys is worth stating plainly all the same: three of these four now
*equal* a sample rather than sit below one. If any node in those partitions
is smaller, the value is above the partition minimum, which is the side that
kills a job rather than the side that wastes a node. Nothing suggests those
partitions are mixed, and no machine `mache` ships a config for is known to
differ in memory between its nodes — but nothing has ruled it out either.
The `sinfo -h -o "%m" -p <partition>` that would settle all three costs no
allocation and has not been run.

**Aurora is the real gap**, and the way its measurement failed is a trap for
whoever tries next. The `pbsnodes` output parsed to no
`resources_available.mem`, and the harness fell back to the kernel's
`MemTotal`, reading 1161578 MB. That number is not the answer: it is what
the hardware holds, and the distance between it and what the site hands a
job is the entire reason this option exists.

Each config option carries a comment saying where its figure came from — a
partition-wide survey, a sample of one or two nodes, or nothing but the
site's documentation — and that comment is what changes as each machine is
surveyed. A reader can then see at a glance which machines are on firm
ground, and a sampled machine cannot quietly pass for a surveyed one.

**The stakes are lower than they were.** Polaris now treats the configured
figure as a planning estimate rather than a promise: it sizes job scripts
with it at setup, when no node has been assigned yet, and inside the
allocation reads what the nodes it actually received report, accounting
against those and reporting any disagreement. A stale or optimistic value
can no longer over-admit at run time. That is a reason not to hold a release
for perfect numbers, not a reason to stop wanting them.

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
  config, with `memory` and `memory_per_node` on `ParallelSystem`;
- an optional `memory_cap` argument to
  `ParallelSystem.get_parallel_command()`, rendered as `--mem` by
  `SlurmSystem` where the version says it will be enforced and rendered
  nowhere else, with a `memory_cap_support` report beside
  `placement_support`.

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

### What validation found, machine by machine

Validation ran on all five machines, and the rendering works on every one of
them. This is recorded here in prose because the harness that produced it is
being removed from Polaris's history at the end of its Phase A, taking the
raw evidence with it.

Two defects were found, both in the first round, both fixed above and both
confirmed by a rerun.

- **Chrysalis** (Slurm 20.02, CPU only) — clean. Placement is by explicit
  CPU binding, and the cores a launch got were exactly the cores it was
  given. A memory figure is not enforced: a step allowed 1024 MB and told to
  take 4 GB reached 4 GB and exited 0.
- **Perlmutter CPU** (Slurm 25.11) — clean first time.
- **Perlmutter GPU** (Slurm 25.11) — clean once `gpu_bind = none` was
  dropped. Before that, four concurrent placed launches each asking for one
  GPU produced one launch with a GPU and three with none, which ran anyway
  and exited 0. Memory is enforced: the same 4 GB step was killed at 960 MB.
- **Frontier** (Slurm 25.11) — clean throughout, including four concurrent
  launches with disjoint cores and disjoint GPUs. Memory is enforced, at the
  same 960 MB.
- **Aurora** (PBS with PALS) — every placed launch failed to start until
  `--env-remove` was dropped; clean afterwards.

### What is still open

**The empty-`ZE_AFFINITY_MASK` question, which a green Aurora run does not
close.** On Slurm, the GPUs a launch can see are reported by the scheduler's
own variables, so a check reads back something `mache` did not write. On
PALS nothing assigns GPUs: `mache` renders the indices the caller chose into
the variable, and the check reads that same variable back. A clean run
therefore confirms the plumbing and says nothing about what Level Zero makes
of an empty value — whether it means "no devices" or "no mask", which is
every tile. Settling it takes a placed CPU-only launch on Aurora reporting
what Level Zero actually sees.

**Whether a stated memory cap is also a claim**, described above. Every
concurrency measurement so far was made without caps.

**The memory cap rendering itself.** The enforcement facts behind it were
measured directly, but no launch has yet been run through
`get_parallel_command()` with `memory_cap` set.

**A survey of `memory_per_node` on every machine but Chrysalis**, and any
measurement at all on Aurora.
