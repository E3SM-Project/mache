(users-machine-config)=

# Machine Config Options

Each supported machine has a config file,
[`mache/machines/<machine>.cfg`](https://github.com/E3SM-Project/mache/tree/main/mache/machines),
that records where shared E3SM resources live on that machine and how to run
jobs there. This page lists the sections and options those files contain, what
each one means, and which machines define it. To add a machine or fill in a
missing option, see {ref}`dev-config-sources`.

## Reading the options

{py:class}`mache.MachineInfo` reads `default.cfg` and then the machine's own
file into a `configparser.ConfigParser`:

```python
from mache import MachineInfo

machine_info = MachineInfo(machine='chrysalis')
config = machine_info.config

inputdata = config.get('inputdata', 'base_path')
www = config.get('web_portal', 'base_path', fallback=None)
```

Not every machine defines every section, so use `fallback=` or
`config.has_option()` for anything not marked "all machines" below. The parser
uses `configparser.ExtendedInterpolation`, so `${section:option}` references
work if you add your own options on top of these.

Software that deploys with `mache deploy` can layer its own machine configs
over these ones; see `machines.path` in {doc}`deploy`.

## Paths and shared resources

### `[e3sm_unified]`

Options for deploying and locating
[E3SM-Unified](https://github.com/E3SM-Project/e3sm-unified). Defined on all
machines; `compiler`, `mpi` and `use_e3sm_hdf5_netcdf` only on aurora,
chrysalis, compy, dane, frontier, pm-cpu and pm-gpu.

| Option | Meaning |
| --- | --- |
| `base_path` | Directory holding E3SM-Unified's activation scripts and environments. Also available as `MachineInfo.e3sm_unified_base`. |
| `group` | Unix group that owns the E3SM-Unified deployment. Downstream tools also use it as the shared group for files they write. |
| `compiler`, `mpi` | Toolchain for the Spack-built system libraries in E3SM-Unified. |
| `use_e3sm_hdf5_netcdf` | Whether to use the machine's E3SM modules for HDF5, NetCDF and PnetCDF instead of building them with Spack. |
| `use_system_git`, `use_legacy_glibc_pins` | Compy-only workarounds read by E3SM-Unified's deploy hooks. |

### `[diagnostics]`

The shared directory of observations, mapping files and other reference data
used by e3sm_diags, MPAS-Analysis, zppy and related tools. Defined on all
machines.

| Option | Meaning |
| --- | --- |
| `base_path` | Root of the diagnostics data. Also available as `MachineInfo.diagnostics_base`. |
| `group` | Unix group given to files synced into `base_path` by {doc}`sync/diags`. |

### `[inputdata]`

Defined on all machines except chicoma-cpu, where E3SM's inputdata is
per-user.

| Option | Meaning |
| --- | --- |
| `base_path` | Root of the shared E3SM inputdata tree (CIME's `DIN_LOC_ROOT`). Also available as `MachineInfo.inputdata_base`. |

### `[web_portal]`

The project's public web space, where tools like zppy and e3sm_diags publish
output. Defined on bebop, chrysalis, compy, dane, improv, pm-cpu and pm-gpu.

| Option | Meaning |
| --- | --- |
| `base_path` | Directory served by the web portal. Also available as `MachineInfo.web_portal_base`. |
| `base_url` | URL that corresponds to `base_path`. Also available as `MachineInfo.web_portal_url`. |
| `username` | Not in the files. `MachineInfo` adds the current user's name here on every machine, for building per-user portal paths. |

## Running jobs

### `[parallel]` and scheduler sections

`[parallel]` describes the scheduler, launcher and node resources, with
optional per-compiler overrides in `[parallel.<compiler>]` and policy limits in
`[queue.<name>]`, `[partition.<name>]` and `[qos.<name>]`. It is defined on
every machine except bebop; `default.cfg` supplies `login_cores` and
`login_gpus` everywhere. {doc}`parallel` explains how these options are used
and {ref}`dev-new-config-file` lists each one.

### `[spack]`

Defined on frontier, pm-cpu and pm-gpu.

| Option | Meaning |
| --- | --- |
| `cray_compilers` | Whether Spack builds use the Cray `cc`, `CC` and `ftn` wrappers instead of the MPI library's own wrappers. Defaults to `False`. |

## Machine identity

### `[sync]`

Used by {doc}`sync/diags`. Defined on all machines.

| Option | Meaning |
| --- | --- |
| `hostname` | Fully qualified login hostname that rsync connects to. |
| `tunnel_hostname` | Optional front-end host to tunnel through when `hostname` can't be reached directly (chicoma-cpu only). |
| `public_diags`, `private_diags` | Source directories that `mache sync diags` copies from. LCRC machines (bebop, chrysalis, improv) only. |

### `[discovery]`

Used by {py:func}`mache.discover_machine()`. Defined on every machine except
pm-cpu and pm-gpu, which are recognized from `$NERSC_HOST` instead.

| Option | Meaning |
| --- | --- |
| `hostname_re` | One or more regular expressions, separated by commas, matched against the start of the hostname. |

### `[deploy]`

No shipped config defines `[deploy]`. Downstream software sets it in its own
machine configs to give `mache deploy run` defaults such as `compiler`, `mpi`
and `group`; see {doc}`deploy`.
