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
    E3SM Supported Machine? True
      Compilers: intel, gnu
      MPI libraries: mvapich, impi
      OS: LINUX
    E3SM-Unified:
      Base path: /lcrc/soft/climate/e3sm-unified
      E3SM-Unified is not currently loaded
    Diagnostics:
      Base path: /lcrc/group/e3sm/diagnostics

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

License
-------

Copyright (c) 2021, Energy Exascale Earth System Model Project
All rights reserved

SPDX-License-Identifier: (BSD-3-Clause)

See `LICENSE <./LICENSE>`_ for details

Unlimited Open Source - BSD 3-clause Distribution ``LLNL-CODE-819717``
