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
'^n\d{4}'     # Anvil nodes with hostnames n0000 to n9999
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


