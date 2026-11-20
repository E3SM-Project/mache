(dev-adding-new-machine)=

# Adding a New Machine to Mache

Adding an E3SM-known machine to mache requires adding a new config file,
`mache/machines/<machine>.cfg`, that includes the regular expressions mache
uses to recognize the machine from its hostname.

:::{note}
Only machines that are included in mache's
[machine config list](https://github.com/E3SM-Project/mache/blob/main/mache/cime_machine_config/config_machines.xml)
can be added to mache. This list is a *copy* of the
[E3SM cime machine config list](https://github.com/E3SM-Project/E3SM/blob/master/cime_config/machines/config_machines.xml)
which we try to keep up-to-date. If you wish to add a machine that is not
included in this list, you must contact the E3SM-Project developers to add your
machine.

For details on the automated workflow that detects upstream drift in this file
and hands the follow-up work to Claude Code, see
{doc}`config_machines_updates`.
:::

(dev-new-config-file)=

## Adding a new config file

Adding a new config file is usually straightforward if you follow the format of
an existing config file. {ref}`users-machine-config` describes every section
and option; the rest of this page covers where to find the values.

(dev-config-sources)=

### Where the paths and other values come from

Most values are not mache's to choose. Each one comes from E3SM's CIME
machine config, the site, or the team that maintains the resource:

| Option | Where to find it |
| --- | --- |
| `[inputdata] base_path` | The machine's `DIN_LOC_ROOT` in `config_machines.xml`. A test fails if they differ. Leave it out if `DIN_LOC_ROOT` is per-user. |
| `[diagnostics] base_path` | The E3SM project's shared diagnostics directory, usually in the same project space as inputdata. If none exists yet, create one and populate it with `mache sync diags from chrysalis` (see {doc}`../users_guide/sync/diags`). |
| `[e3sm_unified] base_path` | Wherever the E3SM-Unified maintainers deploy it, normally the project's shared software space. |
| `[e3sm_unified] compiler`, `mpi` | A pair with a Spack template in `mache/spack/templates/<machine>_<compiler>_<mpi>.yaml`. |
| `[e3sm_unified] group`, `[diagnostics] group` | The Unix group that owns the E3SM project space. `stat -c %G <base_path>` on an existing shared directory shows it. |
| `[web_portal] base_path`, `base_url` | The site's documentation for project web space. At NERSC, `/global/cfs/cdirs/<project>/www` is served at `https://portal.nersc.gov/cfs/<project>`. Leave the section out if the site has none. |
| `[sync] hostname` | The login hostname users `ssh` to, as given in the site's documentation. |
| `[parallel] memory_per_node` and other node resources | The machine itself; see {ref}`dev-parallel-settings` below. |

Paths that aren't in `config_machines.xml` should be checked on the machine
before they are committed, since no test can catch a path that doesn't exist.

(dev-parallel-settings)=

### Parallel execution settings

Machine config files now include parallel-resource settings that are consumed
by `mache.parallel`. At minimum, each machine should define a `[parallel]`
section with:

- `system`: one of `slurm`, `pbs`, `single_node`, or `login`
- `parallel_executable`: launcher command (for example, `srun --label` or
    `mpiexec --label`)

Depending on the parallel system, the following options are typically required:

- `cores_per_node`
- `gpus_per_node` (if GPUs are available)
- `memory_per_node`
- `max_mpi_tasks_per_node`
- `cpus_per_task_flag` (primarily for PBS launchers)
- `cpu_bind`, `gpu_bind`, `mem_bind`, `placement` (optional launcher tuning)
- `login_cores`, `login_gpus` (for the `login` system)

For machines with hyperthreading, mache's convention is that `cores_per_node`
should normally be the physical-core count, not the hardware-thread count.
Likewise, `max_mpi_tasks_per_node` should normally reflect the default
non-hyperthreaded layout used by E3SM and most downstream software, and
`cpu_bind = cores` is the preferred default when supported by the launcher.
Downstream projects that intentionally want hyperthreading can override these
settings in their own config to use hardware-thread counts and thread binding.
In other words, these config fields are the hyperthreading controls rather
than a dedicated boolean option.

`memory_per_node` is the usable memory of one compute node in **MB** -- what
the site reports as available to a job, not the hardware capacity. On a Slurm
machine, read it off the machine itself:

```bash
sinfo --noheader --format="%m" --partition=<the machine's default partition>
```

That prints one figure per node group, so **take the smallest**. The value
has to be one no node falls below, and a figure read off whichever node you
happen to be on is evidence about that node rather than about the partition.
Where the config offers more than one partition, the figure has to hold for
all of them, so pass them all: `--partition=batch,extended`.

Not every machine separates its node types by partition. Perlmutter selects
between CPU and GPU nodes with a *constraint*, so a partition-wide query there
mixes the two and the smallest figure comes back from whichever type has less.
Select on the feature column instead:

```bash
sinfo --noheader --format="%m %f" | awk '$2 ~ /(^|,)cpu(,|$)/ {print $1}' \
    | sort -n | head -1
```

Check which axis a machine uses before trusting the answer -- if its config
sets `constraints` rather than `partitions`, this is the query it needs.

On a PBS machine the same figure is `resources_available.mem`:

```bash
pbsnodes -a | grep resources_available.mem
```

Take the smallest of those too. If the field is missing, do **not** fall back
to the kernel's `MemTotal` from `/proc/meminfo`. That reports what the
hardware holds, which is larger than what the site hands a job, and the
distance between the two is the whole reason this option exists -- copying it
in makes the value too high in exactly the direction that gets a job killed.
Leave the estimate in place and say in the comment that the measurement was
attempted and produced nothing, as Aurora's config does.

A test fails if any shipped config omits it, since a machine without it works
for everything else and the omission would only surface as a downstream tool
unable to decide how much work fits on a node. Nothing in CI can check that
the value is right, so say in a comment above the option where the figure
came from -- a survey of the partition, a sample of one or two nodes, or the
site's documentation -- as the shipped configs do. If you had to estimate it,
round it down: too low wastes some of a node, while too high gets a job
killed for exhausting one.

Compiler-specific overrides can be provided in optional
`[parallel.<compiler>]` sections, e.g. `[parallel.gnu]`.

For machines with scheduler-target policy limits, you can also define optional
sections for queue- or partition-based schedulers:

- `[queue.<name>]` sections corresponding to entries in `parallel.queues`
- `[partition.<name>]` sections corresponding to entries in
    `parallel.partitions`
- `[qos.<name>]` sections corresponding to entries in `parallel.qos`

Supported keys are:

- `min_nodes`: minimum node count for this scheduler target
- `max_nodes`: maximum node count for this scheduler target (leave unset for
    no upper bound)
- `max_wallclock`: maximum allowed wall-clock time (for example,
    `01:00:00`)
- `max_wallclock_bins`: maximum allowed wall-clock time as a function of job
    size, for machines whose policy varies with node count

Some machines allow longer jobs the more nodes they use. Frontier's `batch`
partition, for example, allows 2 hours for 1-91 nodes, 6 hours for 92-183
nodes and 12 hours above that. Describe this with `max_wallclock_bins`
instead of `max_wallclock`:

```ini
[partition.batch]
min_nodes = 1
max_nodes = 9472
max_wallclock_bins = 91: 02:00:00,
                     183: 06:00:00,
                     9472: 12:00:00
```

Each entry is `<max nodes>: <max wallclock>` and the bin that applies is the
first one, in increasing order of node count, whose node bound is at least the
job's node count. Continuation lines must be indented. A section may set
`max_wallclock` or `max_wallclock_bins` but not both.

Downstream software can query these values with
`MachineInfo.get_queue_specs()`, `MachineInfo.get_partition_specs()`,
`MachineInfo.get_qos_specs()` or
`MachineInfo.get_scheduler_specs()`.

A scheduler target can only be requested by name (see
{ref}`users-parallel`) if it is listed in `parallel.queues`,
`parallel.partitions` or `parallel.qos`. The matching `[queue.<name>]`,
`[partition.<name>]` or `[qos.<name>]` section is what supplies the limits
mache uses to decide whether such a request can be honored, so a target with
no section can always be requested but never rejected. The first entry in each
list is the machine's default.

`parallel.constraints` is an availability list in the same sense -- the first
entry is the default and a constraint can only be requested if it appears
there -- but it takes no `[constraint.<name>]` section, since a constraint has
no node-count or wall-clock limits to record.

These options are used to:

- detect available resources on the current allocation,
- construct launcher commands via `mache.parallel`, and
- enforce machine-specific limits like max MPI tasks per node.

(dev-discover-new-machine)=

## Letting mache discover the machine

{py:func}`mache.discover_machine()` matches the hostname against the
`hostname_re` patterns in each config's `[discovery]` section, so a new
machine needs one:

```ini
# Options related to machine discovery
[discovery]

# regular expression(s) used to identify this machine from its hostname
hostname_re = ^chrlogin, ^chr-\d{4}
```

Include patterns for both login and compute nodes. Each pattern is matched
against the start of the hostname, and patterns are separated by a comma and a
space so that ones like `\d{1,4}` are safe. Check that the new patterns don't
also match another machine's hostnames; mache warns and picks the first match
if they do.

In some cases, the hostname is too generic to tell the machine apart from
others. Only then, add a check of an environment variable to `discover.py`, as
is done for Frontier (`$LMOD_SYSTEM_NAME`) and Perlmutter (`$NERSC_HOST`), and
leave `[discovery]` out of the config.
