(dev-adding-new-machine)=

# Adding a New Machine to Mache

Adding an E3SM-known machine to mache requires adding a new config file, as
well as updating the list of machines in `discover.py`.

:::{note}
Only machines that are included in mache's
[machine config list](https://github.com/E3SM-Project/mache/blob/main/mache/cime_machine_config/config_machines.xml)
can be added to mache. This list is a *copy* of the
[E3SM cime machine config list](https://github.com/E3SM-Project/E3SM/blob/master/cime_config/machines/config_machines.xml)
which we try to keep up-to-date. If you wish to add a machine that is not
included in this list, you must contact the E3SM-Project developers to add your
machine.
:::

(dev-new-config-file)=

## Adding a new config file

Adding a new config file is usually straightforward if you follow the format of
an existing config file.

For machines with a known E3SM inputdata location, also add an `[inputdata]`
section with:

- `base_path`: base directory for the shared E3SM inputdata tree

When the machine also appears in
`mache/cime_machine_config/config_machines.xml`, this value should match that
machine's `DIN_LOC_ROOT` entry.

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
- `max_mpi_tasks_per_node`
- `cpus_per_task_flag` (primarily for PBS launchers)
- `cpu_bind`, `gpu_bind`, `mem_bind`, `placement` (optional launcher tuning)
- `login_cores`, `login_gpus` (for the `login` system)

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

Downstream software can query these values with
`MachineInfo.get_queue_specs()`, `MachineInfo.get_partition_specs()`,
`MachineInfo.get_qos_specs()` or
`MachineInfo.get_scheduler_specs()`.

These options are used to:

- detect available resources on the current allocation,
- construct launcher commands via `mache.parallel`, and
- enforce machine-specific limits like max MPI tasks per node.

(dev-discover-new-machine)=

## Adding the new machine to `discover.py`

You will need to amend the list of machine names in `discover.py` so that mache
can identify the new machine via its hostname. This process is typically done
using a regular expression, which is often possible whenever the machine's
hostname follows a standardized format. For example, we can identify known
machines from hostnames with the following regular expressions:

```python
'^chr-\d{4}'  # Chrysalis compute nodes with hostnames chr-0000 to chr-9999
'^compy'      # Compy nodes with hostname compy
'^dane\d{1,4}' # Dane nodes with hostnames dane0 to dane9999
```

In some cases, the hostname assigned to a machine is too generic to
differentiate it from other machines. In these cases, we must identify the
machine by its environment variables. However, this is *not* the recommended
procedure and should only be done as a last resort. For example, we identify
`frontier` by its `LMOD_SYSTEM_NAME` environment variable:

```python
if machine is None and 'LMOD_SYSTEM_NAME' in os.environ:
    hostname = os.environ['LMOD_SYSTEM_NAME']
    if hostname == 'frontier':
        # frontier's hostname is too generic to detect, so relying on
        # LMOD_SYSTEM_NAME
        machine = 'frontier'
```

:::{note}
Identifying the machine by environment variables is **not recommended** unless
absolutely necessary.
:::
