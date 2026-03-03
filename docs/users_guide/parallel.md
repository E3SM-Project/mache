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

## Using this in generated job scripts

A common pattern is to generate scheduler directives separately, then use
`mache.parallel` only for launch lines. For example:

- Use `MachineInfo.get_account_defaults()` to populate account/partition/QOS.
- Render scheduler headers (`#SBATCH` or `#PBS`) in your template logic.
- Use `get_parallel_command()` to build the executable line.

This keeps scheduler policy in your tool while reusing machine-specific launch
behavior from `mache`.
