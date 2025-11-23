# Synchronize diagnostics between machines (`mache sync diags`)

This command copies precomputed E3SM diagnostics (both public and private)
between supported HPC systems using rsync. A common use is to pull diagnostics
stored on the LCRC filesystem (Chrysalis) down to another site so local
post-processing and plotting tools can find them.

The command supports two directions:

- `from <other>`: Pull diagnostics from an LCRC machine (e.g., `chrysalis`) to
  your current machine
- `to <other>`: Push diagnostics from your current LCRC machine to another
  machine

Important constraints:

- LCRC machines are `anvil` and `chrysalis`
- You may only:
  - run `to` when you are currently on an LCRC machine; and
  - run `from` when the other machine is an LCRC machine.
- If you try to sync between two different LCRC machines, you'll be told to
  sync with the same machine instead, since the files are local/shared.
- It is *highly* recommended that you sync `from` an LCRC machine to another
  HPC system because this allows permissions to be updated after the sync.

---

## Prerequisites

- A valid LCRC/CELS account and username (used below as `<cels_username>`)
- SSH key-based access configured for each machine from which you will run the
  sync
- `mache` installed and configured on the machine where you run the command

### 1) Generate an SSH key (if you don’t already have one)

On each HPC machine where you plan to run the sync:

```bash
ssh-keygen -t ed25519
```

Accept the default path (`~/.ssh/id_ed25519`) unless you have a reason to use a
different one. Don’t share your private key.

### 2) Add your public key to your CELS account

- Copy the content of your public key (typically `~/.ssh/id_ed25519.pub`).
- Visit https://accounts.cels.anl.gov/ and add it under your account’s SSH
  keys.
- Give it a descriptive name (e.g., `andes`, `frontier`, `compy`).
- Allow a few minutes for the new key to propagate.

### 3) Configure your `~/.ssh/config`

We recommend a control connection and a short host alias for Chrysalis:

```ini
Host *
    ControlMaster auto
    ControlPath ~/.ssh/connections/%r@%h:%p
    ServerAliveInterval 300
    ServerAliveCountMax 3

Host chrys
    Hostname chrysalis.lcrc.anl.gov
    User <cels_username>
    ProxyJump <cels_username>@logins.lcrc.anl.gov
```

Also create the connections directory if it doesn’t exist:

```bash
mkdir -p ~/.ssh/connections
chmod 700 ~/.ssh ~/.ssh/connections
```

#### OLCF (Andes, Frontier) extra settings

Some OLCF systems require explicit auth options. Add these lines to the
`chrys` host in your SSH config if you’re on Andes/Frontier:

```ini
Host chrys
    Hostname chrysalis.lcrc.anl.gov
    User <cels_username>
    ProxyJump <cels_username>@logins.lcrc.anl.gov
    IdentityFile ~/.ssh/id_ed25519
    PreferredAuthentications publickey,keyboard-interactive
    PasswordAuthentication no
```

---

## Recommended workflow

1) Start a background control connection to Chrysalis (you’ll be prompted for
   Duo):

```bash
ssh -MNf chrys
```

You should be returned to your original login shell after MFA.

2) Run the sync. For example, to pull diagnostics from Chrysalis to your
   current machine:

```bash
mache sync diags from chrysalis -u <cels_username>
```

If the control connection is active, you shouldn’t be prompted for Duo again.
You’ll see `rsync` output similar to:

```
running: rsync --verbose --recursive --times --links --compress --progress --update --no-perms --omit-dir-times <cels_username>@chrysalis.lcrc.anl.gov:/lcrc/group/e3sm/public_html/diagnostics/ /path/to/local/diagnostics
receiving incremental file list
grids/ocean.RRSwISC6to18E3r5.mask.scrip.20240327.nc
    633,767,353 100%   16.58MB/s    0:00:36 (xfr#1, ir-chk=1293/1488)
grids/ocean.RRSwISC6to18E3r5.nomask.scrip.20240327.nc
    633,767,353 100%   26.88MB/s    0:00:22 (xfr#2, ir-chk=1292/1488)
...
```

3) When you’re done, close the control connection:

```bash
ssh -O exit chrys
```

Notes:
- When pulling data (`from`), `mache` will automatically fix permissions on
  the local destination according to machine settings.
- Destination paths are derived from your machine configuration (diagnostics
  base path), and source paths from the LCRC machine configuration.

---

## Command reference

Basic usage:

```text
mache sync diags to <other>   [-u <username>] [-m <this_machine>] [-f <config_file>]
mache sync diags from <other> [-u <username>] [-m <this_machine>] [-f <config_file>]
```

- `to | from` — direction of sync
- `<other>` — the other machine name (e.g., `chrysalis`)
- `-u, --username` — the username to use on the other machine (required in
  practice)
- `-m, --machine` — explicitly set the name of the current machine
  (auto-detected if omitted)
- `-f, --config_file` — path to a config file that overrides defaults for the
  current machine

Constraints enforced by the command:

- Only `anvil`/`chrysalis` are considered LCRC machines
- `to` is only allowed when you are on an LCRC machine
- `from` is only allowed when the other machine is an LCRC machine
- Do not attempt to sync between two different LCRC machines (there is no need
  and this wastes bandwidth)

---

## Troubleshooting

- You get Duo prompts during rsync:
  - Ensure the control connection is active (`ssh -MNf chrys`) and your
    `Host chrys` alias matches the command you used to connect.
- Permission errors on the destination:
  - Verify your local diagnostics base path exists and that you have write
    access; `mache` adjusts group/world permissions on pull, but can’t create
    parent paths that don’t exist.
- Connection fails through the login proxy:
  - Double-check `ProxyJump <cels_username>@logins.lcrc.anl.gov` and that your
    public key is present at https://accounts.cels.anl.gov/.
