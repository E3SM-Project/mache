# Quick Start

`mache` (Machines for E3SM) is a package for providing configuration data 
related to E3SM supported machines.

(dev-installing-mache)=

## Installing mache

You can install the latest release of `mache` from conda-forge:

```bash
conda config --add channels conda-forge
conda config --set channel_priority strict
conda install mache
```

If you need to install the latest development version, you can run the
following in the root of the `mache` branch you are developing:

```bash
conda config --add channels conda-forge
conda config --set channel_priority strict
conda create -y -n mache_dev --file spec-file.txt
conda activate mache_dev
python -m pip install -e .
```

To install the development version of `mache` in an existing
environment, you can run:

```bash
conda install --file spec-file.txt
python -m pip install -e .
```

(dev-code-styling)=

## Code styling and linting

`mache` uses `pre-commit` to lint incoming code when you make a commit (as 
long as you have your environment set up correctly), and on GitHub whenever you
make a pull request to the `mache` repository. Linting makes sure your code 
follows the formatting guidelines of PEP8, and cleans up additional things like
whitespace at the end of files.

The first time you set up the `mache_dev` environment, you will need to set up 
`pre-commit`. This is done by running:

```bash
pre-commit install
```

You only need to do this once when you create the `mache_dev` environment. If 
you create a new version of `mache_dev`, then you will need to run it again.

When you run `git commit <filename>`, `pre-commit` will automatically lint your
code before committing. Some formatting will be updated by `pre-commit` 
automatically, in which case it will terminate the commit and inform you of the
change. Then you can run `git commit <filename>` again to continue the linting
process until your commit is successful. Some changes need to be made manually,
such as inconsistent variable types. When this happens, you must update the 
file to `pre-commit`'s standards, and then attempt to re-commit the file.

Internally, `pre-commit`  uses [flake8](https://flake8.pycqa.org/en/latest/) to
check PEP8 compliance, [isort](https://pycqa.github.io/isort/) to sort, check 
and format imports, [flynt](https://github.com/ikamensh/flynt) to change any 
format strings to f-strings, and [mypy](https://mypy-lang.org/) to check for
consistent variable types. An example error might be:

```bash
example.py:77:1: E302 expected 2 blank lines, found 1
```

For this example, we would just add an additional blank line after line 77 and
try the commit again to make sure we've resolved the issue.

You may also find it useful to use an IDE with a PEP8 style checker built in,
such as [PyCharm](https://www.jetbrains.com/pycharm/). See
[this tutorial](https://www.jetbrains.com/help/pycharm/tutorial-code-quality-assistance-tips-and-tricks.html)
for some tips on checking code style in PyCharm.

(dev-example-usage)=

## Example usage

```python
#!/usr/bin/env python
from mache import MachineInfo, discover_machine

machine_info = MachineInfo()
print(machine_info)
diags_base = machine_info.config.get('diagnostics', 'base_path')
machine = discover_machine()
```

This loads machine info the current machine, prints it (see below) and
retrieves a config option specific to that machine. The
`discover_machine()` function can also be used to detect which machine
you are on, as shown.

As an example, the result of `print(machine_info)` is:

```
Machine: anvil
  E3SM Supported Machine: True
  Compilers: intel, gnu
  MPI libraries: impi, openmpi, mvapich
  OS: LINUX

E3SM-Unified:
  E3SM-Unified is not currently loaded
  Base path: /lcrc/soft/climate/e3sm-unified

Diagnostics:
  Base path: /lcrc/group/e3sm/diagnostics

Config options:
  [e3sm_unified]
    group = cels
    compiler = intel
    mpi = impi
    base_path = /lcrc/soft/climate/e3sm-unified

  [diagnostics]
    base_path = /lcrc/group/e3sm/diagnostics

  [web_portal]
    base_path = /lcrc/group/e3sm/public_html
    base_url = https://web.lcrc.anl.gov/public/e3sm/

  [parallel]
    system = slurm
    parallel_executable = srun
    cores_per_node = 36
    account = condo
    partitions = acme-small, acme-medium, acme-large
    qos = regular, acme_high
```

If you are on the login node of one of the following E3SM supported
machines, you don't need to provide the machine name. It can be
discovered automatically when you create a `MachineInfo()` object or
call `discover_machine()`. It will be recognized from the host name:

-   acme1
-   andes
-   anvil
-   chicoma-cpu
-   chrysalis
-   compy
-   cooley
-   frontier
-   pm-cpu

If you are on a compute node or want info about a machine you're not
currently on, give the `machine` name in all lowercase.

(dev-attributes)=

## Attributes

The attributes currently available are:

machine : str

: The name of an E3SM supported machine

config : configparser.ConfigParser

: Config options for this machine

e3sm_supported : bool

: Whether this machine supports running E3SM itself, and therefore has a list 
of compilers, MPI libraries, and the modules needed to load them

compilers : list

: A list of compilers for this machine if `e3sm_supported == True`

mpilibs : list

: A list of MPI libraries for this machine if `e3sm_supported == True`

os : str

: The machine's operating system if `e3sm_supported == True`

e3sm_unified_mpi : {'nompi', 'system', None}

: Which MPI type is included in the E3SM-Unified environment (if one is loaded)

e3sm_unified_base : str

: The base path where E3SM-Unified and its activation scripts are installed if 
`e3sm_unified` is not `None`

e3sm_unified_activation : str

: The activation script used to activate E3SM-Unified if `e3sm_unified` is not 
`None`

diagnostics_base : str

: The base directory for diagnostics data

web_portal_base : str

: The base directory for the web portal

web_portal_url : str

: The base URL for the web portal

username : str

: The name of the current user, for use in web-portal directories. This value 
is also added to the `web_portal` and `username` option of the `config` 
attribute.

## Syncing diagnostics

`mache` can be used to synchronize diagnostics data (observational data
sets, testing data, mapping files, region masks, etc.) either directly
on LCRC or from LCRC to other supported machines.

E3SM maintains a set of public diagnostics data (those that we have
permission to share with any users of our software) on LCRC machines
(Anvil and Chrysalis) in the directory:

```
/lcrc/group/e3sm/public_html/diagnostics/
```

A set of private diagnostics data (which we do not have permission to
share outside the E3SM project) are stored at:

```
/lcrc/group/e3sm/diagnostics_private/
```

The `mache sync diags` command can be used to synchronize both sets of
data with a shared diagnostics directory on each supported machine.

Whenever possible, we log on to the E3SM machine and download the data
from LCRC because this allows the synchronization tool to also update
permissions once the data has been synchronized. This is the approach
for all machines except for Los Alamos National Laboratory's Badger,
which is behind a firewall that prevents this approach.

### One-time setup

To synchronize data from LCRC to other machines, you must first provide
your SSH keys by going to the [Argonne
Accounts](https://accounts.cels.anl.gov/) page, logging in, and adding
the public ssh key for each machine. If you have not yet generated an
SSH key for the destination machine, you will need to run:

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

This is the same procedure as for creating an SSH key for GitHub so if
you have already done that process, you will not need a new SSH key for
LCRC.

### Setup on Andes

Andes at OLCF requires special treatment. You need to create or edit the
file `~/.ssh/config` with the following:

```
Host blues.lcrc.anl.gov
    User <ac.user>
    PreferredAuthentications publickey
    IdentityFile ~/.ssh/id_ed25519
```

where, again `<ac.user>` is your username on LCRC.

### Syncing from LCRC

To synchronize diagnostics data from LCRC, simply run:

```bash
mache sync diags from anvil -u <ac.user>
```

where `<ac.user>` is your account name on LCRC.

## Syncing on LCRC

To synchronize diagnostics on an LCRC machine, run:

```bash
mache sync diags from anvil
```

Make sure the machine after `from` is the same as the machine you are
on, `anvil` in this example.

### Syncing to machines with firewalls

To synchronize diagnostics data to a machine with a firewall by using a
tunnel, first log on to an LCRC machine, then run:

```bash
mache sync diags to chicoma-cpu -u <username>
```

where `<username>` is your account name on the non-LCRC machine
(`chicoma-cpu` in this example).

