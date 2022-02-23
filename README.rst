========================
mache: Machines for E3SM
========================

A package for providing configuration data relate to E3SM supported machines.

Example usage:

.. code-block:: python

    #!/usr/bin/env python
    from mache import MachineInfo

    machinfo = MachineInfo(machine='anvil')
    print(machinfo)

This loads machine info for Anvil and prints it:

.. code-block:: none

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

If you are on the login node of one of the following E3SM supported machines,
you don't need to provide the machine name.  It will be recognized from the
host name:

* acme1

* andes

* anvil

* badger

* chrysalis

* compy

* cooley

* cori-haswell (but you will get a warning)

* grizzly

If you are on a compute node or want info about a machine you're not currently
on, give the ``machine`` name in all lowercase.


Attributes
----------

The attributes currently available are:

machine : str
    The name of an E3SM supported machine

config : configparser.ConfigParser
    Config options for this machine

e3sm_supported : bool
    Whether this machine supports running E3SM itself, and therefore has
    a list of compilers, MPI libraries, and the modules needed to load them

compilers : list
    A list of compilers for this machine if ``e3sm_supported == True``

mpilibs : list
    A list of MPI libraries for this machine if ``e3sm_supported == True``

os : str
    The machine's operating system if ``e3sm_supported == True``

e3sm_unified_mpi : {'nompi', 'system', None}
    Which MPI type is included in the E3SM-Unified environment (if one is
    loaded)

e3sm_unified_base : str
    The base path where E3SM-Unified and its activation scripts are
    installed if ``e3sm_unified`` is not ``None``

e3sm_unified_activation : str
    The activation script used to activate E3SM-Unified if ``e3sm_unified``
    is not ``None``

diagnostics_base : str
    The base directory for diagnostics data

web_portal_base : str
    The base directory for the web portal

web_portal_url : str
    The base URL for the web portal

Syncing Diagnostics
-------------------

``mache`` can be used to synchronize diagnostics data (observational data sets,
testing data, mapping files, region masks, etc.) either directly on LCRC or
from LCRC to other supported machines.

E3SM maintains a set of public diagnostics data (those that we have permission
to share with any users of our software) on LCRC machines (Anvil and Chrysalis)
in the directory:

.. code-block:: none

    /lcrc/group/e3sm/public_html/diagnostics/

A set of private diagnostics data (which we do not have permission to share
outside the E3SM project) are stored at:

.. code-block:: none

    /lcrc/group/e3sm/diagnostics_private/

The ``mache sync diags`` command can be used to synchronize both sets of data
with a shared diagnostics directory on each supported machine.

Whenever possible, we log on to the E3SM machine and download the data from
LCRC because this allows the synchronization tool to also update permissions
once the data has been synchronized.  This is the approach for all machines
except for Los Alamos National Laboratory's Badger and Grizzly machines, which
are behind a firewall taht prevents this approach.

One-time Setup
~~~~~~~~~~~~~~

To synchronize data from LCRC to other machines, you must first provide your
SSH keys by going to the `Argonne Accounts <https://accounts.cels.anl.gov/>`_
page, logging in, and adding the public ssh key for each machine.  If you have
not yet generated an SSH key for the destination macine, you will need to run:

.. code-block:: bash

    ssh-keygen -t ed25519 -C "your_email@example.com"

This is the same procedure as for creating an SSH key for GitHub so if you have
already done that process, you will not need a new SSH key for LCRC.

Setup on Andes
~~~~~~~~~~~~~~
Andes at OLCF requires special treatment.  You need to create or edit the
file ``~/.ssh/config`` with the following:

.. code-block:: none

    Host blues.lcrc.anl.gov
        User <ac.user>
        PreferredAuthentications publickey
        IdentityFile ~/.ssh/id_ed25519

where, again ``<ac.user>`` is your username on LCRC.

Syncing from LCRC
~~~~~~~~~~~~~~~~~

To synchronize diagnostics data from LCRC, simply run:

.. code-block:: bash

    mache sync diags from anvil -u <ac.user>

where ``<ac.user>`` is your account name on LCRC.

Syncing on LCRC
~~~~~~~~~~~~~~~

To synchronize diagnostics on an LCRC machine, run:

.. code-block:: bash

    mache sync diags from anvil

Make sure the machine after ``from`` is the same as the machine you are on,
``anvil`` in this example.

Syncing to Machines with Firewalls
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To synchronize diagnostics data to a machine with a firewall by using a tunnel,
first log on to an LCRC machine, then run:

.. code-block:: bash

    mache sync diags to badger -u <username>

where ``<username>`` is your account name on the non-LCRC machine (``badger``
in this example).

License
-------

Copyright (c) 2021, Energy Exascale Earth System Model Project
All rights reserved

SPDX-License-Identifier: (BSD-3-Clause)

See `LICENSE <./LICENSE>`_ for details

Unlimited Open Source - BSD 3-clause Distribution ``LLNL-CODE-819717``
