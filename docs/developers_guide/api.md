(dev-api)=

# API reference

This page provides an auto-generated summary of the mache API. For more
details and examples, refer to the relevant sections in the main part of the
documentation.

## discover

```{eval-rst}
.. currentmodule:: mache.discover

.. autosummary::
    :toctree: generated/

    discover_machine
```

## permissions

```{eval-rst}
.. currentmodule:: mache.permissions

.. autosummary::
    :toctree: generated/

    update_permissions
```

## parallel

```{eval-rst}
.. currentmodule:: mache.parallel

.. autosummary::
    :toctree: generated/

    get_parallel_system
```

```{eval-rst}
.. currentmodule:: mache.parallel.system

.. autosummary::
    :toctree: generated/

    SubmissionResolution
    ParallelSystem
    ParallelSystem.get_parallel_command
    ParallelSystem.get_scheduler_target
    ParallelSystem.resolve_submission
```

```{eval-rst}
.. currentmodule:: mache.parallel.login

.. autosummary::
    :toctree: generated/

    LoginSystem
```

```{eval-rst}
.. currentmodule:: mache.parallel.single_node

.. autosummary::
    :toctree: generated/

    SingleNodeSystem
```

```{eval-rst}
.. currentmodule:: mache.parallel.slurm

.. autosummary::
    :toctree: generated/

    SlurmSystem
    SlurmSystem.get_slurm_options
```

```{eval-rst}
.. currentmodule:: mache.parallel.pbs

.. autosummary::
    :toctree: generated/

    PbsSystem
    PbsSystem.get_pbs_options
```

## spack

```{eval-rst}
.. currentmodule:: mache.spack

.. autosummary::
    :toctree: generated/

    make_spack_env
    get_spack_script
    get_modules_env_vars_and_mpi_compilers
    extract_machine_config
    config_to_shell_script
    extract_spack_from_config_machines
    list_machine_compiler_mpilib
```

## sync

```{eval-rst}
.. currentmodule:: mache.sync.diags

.. autosummary::
    :toctree: generated/

    sync_diags
```

## jigsaw

```{eval-rst}
.. currentmodule:: mache.jigsaw

.. autosummary::
    :toctree: generated/

    deploy_jigsawpy
    build_jigsawpy_package
    install_jigsawpy_package
    detect_install_backend
```

## MachineInfo

```{eval-rst}
.. currentmodule:: mache

.. autosummary::
    :toctree: generated/

    MachineInfo
    MachineInfo.get_account_defaults
    MachineInfo.get_queue_specs
    MachineInfo.get_partition_specs
    MachineInfo.get_qos_specs
```
