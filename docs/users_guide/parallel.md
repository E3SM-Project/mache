(users-parallel)=

# Parallel execution with `mache.parallel`

`mache.parallel` provides a machine-aware interface for launching parallel
workloads based on each machine's config file.

## Typical downstream workflow

Downstream software (for example, Polaris software) can:

1. Load machine config with `MachineInfo`.
2. Build a parallel-system object with `get_parallel_system()`.
3. Query available resources (`cores`, `nodes`, `gpus`, and `mpi_allowed`).
4. Build a machine-correct launcher command with `get_parallel_command()`.
5. Use the command for either generated job scripts or direct subprocess calls.

## Example: build a launcher command

```python
from mache import MachineInfo
from mache.parallel import get_parallel_system

machine_info = MachineInfo()
parallel_system = get_parallel_system(machine_info.config)

args = ["python", "-m", "your_package.run_task", "--case", "smoke"]
command = parallel_system.get_parallel_command(
    args=args,
    ntasks=4,
    cpus_per_task=2,
    gpus_per_task=0,
)

print(" ".join(command))
```

On a batch allocation, this returns an `srun`/`mpiexec` command using the
machine's configured launcher and resource flags. On login nodes for `slurm`
or `pbs` systems, `get_parallel_system()` falls back to `login`, where MPI is
intentionally disabled.

## GPU-per-task flags

When `gpus_per_task > 0` is passed to `get_parallel_command()`:

- `slurm` systems add `--gpus-per-task <N>` by default. This can be overridden
    with `gpus_per_task_flag` in the machine's `[parallel]` config.
- `pbs` systems require a machine-specific `gpus_per_task_flag` to be set in
    config before a GPU-per-task argument is added.

## Hyperthreading

`mache.parallel` does not currently have a dedicated
`hyperthreading = true/false` switch. Instead, hyperthreading behavior is
controlled through the machine's `[parallel]` config and the resource values
passed to `get_parallel_command()`. The most important config knobs are
`cores_per_node`, `max_mpi_tasks_per_node`, `cpu_bind`, and any
launcher-specific arguments included in `parallel_executable`.

The default convention in mache's machine configs is to describe CPU resources
in terms of physical cores, not hardware threads. For E3SM itself, and for
most downstream software, this means:

- `cores_per_node` should usually be the number of physical CPU cores per node
- `max_mpi_tasks_per_node` should usually reflect the intended non-hyperthreaded
    MPI rank count per node
- `cpu_bind = cores` is often a good default when the launcher and machine
    topology support it, but some systems such as Frontier prefer
    `cpu_bind = threads`
- `cpus_per_task` should usually be sized assuming physical cores

This is why several shipped machine configs explicitly document
`cores_per_node` as the count "without hyperthreading".

If a downstream application wants to take advantage of hyperthreading, it
should opt in by overriding the relevant parallel config values for that use
case. In practice, that usually means switching from physical-core counts to
hardware-thread counts and adjusting binding accordingly. For example, on a
machine with 64 physical cores and 2 hardware threads per core:

```ini
[parallel]
cores_per_node = 128
max_mpi_tasks_per_node = 128
cpu_bind = threads
```

Then, calls to `get_parallel_command()` should use `cpus_per_task` and
`ntasks` values that match that threaded layout.

The important point is that hyperthreading is opt-in. Mache's default machine
configs should generally preserve the physical-core layout that is appropriate
for E3SM and most downstream tools, while still allowing downstream users to
provide a config override when they intentionally want thread-level placement.

## Using this in generated job scripts

A common pattern is to generate scheduler directives separately, then use
`mache.parallel` only for launch lines. For example:

- Use `MachineInfo.get_account_defaults()` to populate account/partition/QOS.
- Use `MachineInfo.get_queue_specs()`, `MachineInfo.get_partition_specs()` or
    `MachineInfo.get_qos_specs()` for optional scheduler-target policy
    metadata (`min_nodes`, `max_nodes`, `max_wallclock`,
    `max_wallclock_bins`) when available.
- Render scheduler headers (`#SBATCH` or `#PBS`) in your template logic.
- Use `get_parallel_command()` to build the executable line.

This keeps scheduler policy in your tool while reusing machine-specific launch
behavior from `mache`.

## Slurm distribution options

For `slurm` systems, mache supports two ways to control `srun -m`:

- `distribution = <value>` passes a raw Slurm distribution string directly as
    `-m <value>`, for example `block:cyclic` or `block:block`
- `placement = <value>` preserves mache's legacy behavior and expands to
    `-m <value>=<max_mpi_tasks_per_node>`, for example `plane=56`

If both are present, `distribution` takes precedence. Prefer `distribution`
for machines whose documented Slurm usage relies on explicit values like
`block:cyclic` rather than the older `plane=<tasks>` form.

```{note}
The `placement` config option here is the Slurm task distribution and is
unrelated to the `placement` argument to `get_parallel_command()` described in
{ref}`users-parallel-placement`. Passing that argument drops this config
option from the command.
```

## Selecting scheduler options by node count

`mache.parallel` also provides helpers for selecting queue/partition/QOS from
machine metadata:

- `ParallelSystem.get_scheduler_target(config, target_type, nodes)` selects
    one of `queue`, `partition`, or `qos`.
- `ParallelSystem.resolve_submission(config, nodes, target_type,
    min_nodes_allowed=None, requested=None, desired_wall_time=None)` returns a
    `SubmissionResolution` with fields `target`, `requested_nodes`,
    `effective_nodes`, `adjustment` (`exact`, `decrease`, or `increase`),
    `honored`, and `reason`.
- `SlurmSystem.resolve_slurm_options(config, nodes, min_nodes_allowed=None,
    partition=None, qos=None, constraint=None, desired_wall_time=None,
    scheduler_target=None)` returns a `SlurmOptions` object with fields
    `partition`, `qos`, `constraint`, `gpus_per_node`, `max_wallclock`,
    `effective_nodes`, `wall_time`, `honored`, and `reason`.
- `PbsSystem.resolve_pbs_options(config, nodes, min_nodes_allowed=None,
    queue=None, constraint=None, desired_wall_time=None,
    scheduler_target=None)` returns a `PbsOptions` object with fields `queue`,
    `constraint`, `gpus_per_node`, `max_wallclock`, `filesystems`,
    `effective_nodes`, `wall_time`, `honored`, and `reason`.

For invalid gaps between scheduler ranges, node count is adjusted to the
nearest valid value, preferring lower adjustments when feasible. If
`min_nodes_allowed` disallows lower adjustments, resolution moves to the next
valid higher range. If no feasible target exists, these functions raise
`ValueError`.

```{note}
`SlurmSystem.get_slurm_options()` and `PbsSystem.get_pbs_options()` return the
same values as tuples. They are deprecated as of v3.11.0 in favor of
`resolve_slurm_options()` and `resolve_pbs_options()`, which can be extended
with new fields without breaking positional unpacking.
```

## Requesting a specific queue, partition or QOS

Callers that want a particular scheduler target -- for example a test suite
that should run in the `debug` QOS -- can ask for one directly instead of
rewriting the machine's config:

```python
from mache import MachineInfo
from mache.parallel.slurm import SlurmSystem

config = MachineInfo(machine="pm-cpu").config
options = SlurmSystem.resolve_slurm_options(
    config=config,
    nodes=4,
    qos="debug",
    desired_wall_time="02:00:00",
)

if not options.honored:
    print(f"Falling back to the {options.qos} qos: {options.reason}")
```

A requested target is a preference, not an assertion. mache honors it when the
machine's metadata allows it and otherwise resolves the default target,
setting `honored = False` and putting a printable explanation in `reason`. A
request is not honored when:

- the target is not in the machine's `[parallel]` `queues` / `partitions` /
    `qos` list,
- clamping the node count to the target's `min_nodes`/`max_nodes` would fall
    below `min_nodes_allowed`, or
- `desired_wall_time` is longer than the target's `max_wallclock`.

A constraint can be requested the same way. Unlike a queue, partition or QOS,
it has no node-count or wall-clock metadata and no `[constraint.*]` section, so
it is validated only against the machine's `[parallel] constraints` list: a
constraint that is not on that list falls back to the machine's default with a
`reason`, exactly as the other targets do, and a machine that defines no
constraints ignores the request entirely.

Clamping the node count on its own does *not* prevent a target from being
honored. The clamp is reported through `effective_nodes` and `adjustment`, and
`min_nodes_allowed` is the guard for a clamp the caller cannot live with.

`requested` values of `None`, an empty string, and placeholders of the form
`<<<default>>>` all mean "no target was requested", so config-driven callers
can pass their raw config value through without guarding against unset
placeholders.

A request is also ignored, rather than denied, when the machine defines no
targets of that type at all. Machines hang a concept like "debug" off
different axes -- a partition on Chrysalis, a QOS on Frontier and Perlmutter,
a queue on Aurora -- so a caller that asks on more than one axis should not be
told its request was refused on the axes the machine does not use. There was
no choice to deny, so `honored` stays `True` and `reason` stays `None`. A
target missing from a list the machine *does* define is still a denied
request.

## Requesting a target without naming its axis

Asking on every axis is still awkward for a caller whose intent is simply
"use this machine's debug target". `scheduler_target` says it once and lets
mache work out which axis this machine uses:

```python
options = SlurmSystem.resolve_slurm_options(
    config=config,
    nodes=2,
    scheduler_target="debug",
    desired_wall_time="00:20:00",
)
```

This selects the `debug` partition on Chrysalis, the `debug` QOS on Frontier
and Perlmutter (leaving the default `batch` partition in place on Frontier),
and the `debug` queue on Aurora, with no spurious `reason` on any of them.
Slurm machines are searched partitions-first and then QOS; PBS machines
schedule by queue, so only queues are searched. `partition`, `qos` and `queue`
take precedence on the axis they name, so a caller can set a broad
`scheduler_target` and still pin one axis explicitly.

Once an axis is chosen the target is resolved exactly as if it had been
requested there, so it is still subject to that target's node and wall-clock
metadata: `scheduler_target="debug"` with a three-hour wall time on Frontier
falls back to the `normal` QOS and says why. A name that appears on no axis at
all is a genuine failed request, and the `reason` lists what each axis does
offer.

When `desired_wall_time` is given, the returned `wall_time` is that value
capped at the selected target's `max_wallclock`. The same capping is available
on its own:

```python
from mache.parallel.system import cap_wall_time

cap_wall_time("04:00:00", "00:30:00")  # "00:30:00"
```

Note that mache resolves the partition and the QOS independently and has no
concept of one being valid only with the other. A caller that requests both is
responsible for asking for a combination its machine accepts.

## Wall-clock limits that depend on job size

On some machines, the maximum wall time depends on how many nodes a job asks
for. Frontier's `batch` partition allows 2 hours for 1-91 nodes, 6 hours for
92-183 nodes, and 12 hours above that. These machines describe their policy
with `max_wallclock_bins` rather than a single `max_wallclock` (see
{ref}`dev-new-config-file`), and mache selects the bin that matches the
resolved node count:

```python
options = SlurmSystem.resolve_slurm_options(config=config, nodes=8)
options.max_wallclock  # "02:00:00" on Frontier

options = SlurmSystem.resolve_slurm_options(config=config, nodes=200)
options.max_wallclock  # "12:00:00" on Frontier
```

When both a partition and a QOS set a limit, the more restrictive of the two
is reported, and that is also the limit `wall_time` is capped at.

(users-parallel-placement)=

## Placing concurrent launches within one allocation

`get_parallel_command()` normally asks for resources in the abstract -- this
many tasks, this many CPUs each -- and lets the machine decide where the work
runs. That is enough while a tool runs one piece of work at a time. As soon as
it wants to run two inside the same allocation, the two launches are given
overlapping resources or, more often, the second waits until the first has
finished.

An optional `placement` says where a launch should run:

```python
from mache import MachineInfo
from mache.parallel import ResourcePlacement, get_parallel_system

parallel_system = get_parallel_system(MachineInfo().config)

placement = ResourcePlacement(
    nodes=["nid001373"],
    cores=list(range(8, 16)),
)
command = parallel_system.get_parallel_command(
    args=["./run_step.py"],
    ntasks=1,
    cpus_per_task=8,
    placement=placement,
)
```

A placement carries three things: the nodes the launch may use, the cores it
may use on each of them, and how many GPUs it needs in total. mache renders
them into whatever the machine's launcher needs, so callers do not have to
know which flags a given site takes.

A call without a placement produces exactly the command it produced before
this feature existed.

### Checking what a machine supports

Not every machine can confine a launch. Check before running things
concurrently, rather than discovering the answer as a hang or as silent
oversubscription:

```python
from mache.parallel import PlacementSupport

support = parallel_system.placement_support
if support is PlacementSupport.NONE:
    print("this machine cannot place launches; run steps one at a time")
elif support is PlacementSupport.CPU_BINDING:
    print("placement is by CPU binding, which the work itself could ignore")
```

The three values are:

- `PlacementSupport.SCHEDULER` -- the batch system reserves what each launch
    asks for, so a launch cannot exceed what it was given. This is Slurm 20.11
    and newer.
- `PlacementSupport.CPU_BINDING` -- the launcher binds each task to specific
    cores, which keeps concurrent launches apart but reserves nothing. Work
    that rebinds itself is not prevented from doing so. This is Slurm before
    20.11, PBS with PALS, and `single_node`.
- `PlacementSupport.NONE` -- there is no mechanism here. Passing a placement
    raises `ValueError` rather than producing a command that would be accepted
    and then silently do nothing.

This is determined at run time from the launcher actually present, not from
the machine's config, because a site can be upgraded without its mache config
changing.

### GPUs are a total, not a count per task

`ResourcePlacement.gpus` is the number of GPUs for the whole launch. This is
deliberately unlike `cpus_per_task`: asking for a number of GPUs *per task*
was measured not to confine a launch on either of the GPU machines mache
supports, while a per-launch total does.

`gpus` defaults to 0, and 0 is rendered as an explicit request for *no* GPUs.
On Slurm this matters more than it sounds: a launch that says nothing about
GPUs is read as claiming every one on the node, so the next launch waits.
Callers whose work uses no GPUs -- most of them -- get correct behavior
without having to know GPUs were ever a consideration.

On PALS the same request is belt and braces rather than the mechanism that
makes concurrency work, since nothing there reserves a GPU in the first
place. See {ref}`users-parallel-pals-gpus`.

### Which cores are honored

`cores` is an explicit set rather than a count, because the usable cores on a
node may not be contiguous and may not start at zero -- Aurora reserves core 0
and cores 49-52 -- and because a count cannot say *which* cores.

How much of that set is honored depends on the mechanism:

- where the scheduler reserves resources, only the size of the set is used;
    Slurm is asked for that many cores and picks which ones itself, and an
    explicit core list is rejected outright alongside `-c`
- where placement is by CPU binding, the set is used exactly as given, in
    order, split into one contiguous chunk of `cpus_per_task` cores per task

Either way, mache raises `ValueError` if the set is too small for
`ntasks x cpus_per_task`.

(users-parallel-pals-gpus)=

### Assigning GPUs on PBS with PALS

PALS has no scheduler to hand out GPUs, so isolation there is by the vendor's
visible-device variable -- `ZE_AFFINITY_MASK` on Aurora,
`CUDA_VISIBLE_DEVICES` on Polaris. mache renders it into the `mpiexec` command
and needs to be told *which* devices to name:

```python
placement = ResourcePlacement(
    nodes=["x4401c1s0b0n0"],
    cores=list(range(1, 9)),
    gpus=1,
    gpu_ids=[2],
)
```

`gpu_ids` are indices from 0 to `gpus_per_node - 1`; mache maps them to
whatever form the machine's variable takes, including Aurora's `device.tile`
addressing. Only the caller knows about every launch running at that moment,
so only the caller can assign disjoint GPUs -- mache renders what it is given
and never guesses. A placement with `gpus > 0` and no `gpu_ids` raises on
PALS, and `len(gpu_ids)` must equal `gpus`.

`gpu_ids` is ignored where the scheduler assigns GPUs itself, which is every
Slurm machine.

A placement with no GPUs sets the variable to an empty value. Note that this
is weaker than the equivalent on Slurm: PALS reserves nothing, so a launch
that stays quiet about GPUs does not block the next one, and how much an
empty value actually hides has not been measured. An empty
`CUDA_VISIBLE_DEVICES` means "no devices", but an empty `ZE_AFFINITY_MASK`
may instead mean "no mask", which is every tile. Do not rely on it to keep a
GPU launch and a CPU launch off the same device -- give the GPU launch
explicit `gpu_ids` instead.

Two config options support this, both already set on the machines that need
them: `gpu_visible_devices_var` names the variable, and the ordered
`gpu_bind = list:...` binding list, where a machine has one, says how its
devices are named.

### What a placement overrides

A placement is the authority on which resources a launch gets, so it
supersedes the machine's config options that describe spreading a launch over
a whole node:

- `distribution` and the legacy `placement` config option are dropped, since
    the placement has already said which nodes and how many cores the launch
    gets
- `cpu_bind`, `gpu_bind` and `mem_bind` are dropped when they name specific
    cores or devices, as Aurora's do
- `cpu_bind` is also dropped wherever the placement renders its own binding
- `gpu_bind` is dropped when the placement asks for no GPUs

A binding *policy* such as `cpu_bind = cores` or `gpu_bind = closest` is kept
where it does not conflict, since it still applies within whatever the launch
was given.

```{note}
Verifying GPU placement from inside a launch needs the scheduler's global GPU
identifiers, such as `SLURM_STEP_GPUS`. `CUDA_VISIBLE_DEVICES` is renumbered
per launch, so four launches on four different GPUs all report device `0`.
```
