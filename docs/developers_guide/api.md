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

    JigsawBuildResult
    deploy_jigsawpy
    build_jigsawpy_package
    install_jigsawpy_package
    detect_install_backend
```

```{eval-rst}
.. currentmodule:: mache.jigsaw.cli

.. autosummary::
    :toctree: generated/

    add_jigsaw_subparser
```

## deploy

```{eval-rst}
.. currentmodule:: mache.deploy.bootstrap

.. autosummary::
    :toctree: generated/

    check_call
    build_pixi_shell_hook_prefix
    check_location
    install_dev_mache
    main
```

```{eval-rst}
.. currentmodule:: mache.deploy.cli

.. autosummary::
    :toctree: generated/

    add_deploy_subparser
```

```{eval-rst}
.. currentmodule:: mache.deploy.cli_spec

.. autosummary::
    :toctree: generated/

    CliArgSpec
    CliSpec
    parse_cli_spec
    routes_include
    filter_args_by_route
    load_cli_spec_file
    add_args_to_parser
```

```{eval-rst}
.. currentmodule:: mache.deploy.conda

.. autosummary::
    :toctree: generated/

    get_conda_platform_and_system
```

```{eval-rst}
.. currentmodule:: mache.deploy.hooks

.. autosummary::
    :toctree: generated/

    DeployContext
    HookRegistry
    HookRegistry.run_hook
    load_hooks
    configparser_to_nested_dict
```

```{eval-rst}
.. currentmodule:: mache.deploy.init_update

.. autosummary::
    :toctree: generated/

    init_or_update_repo
```

```{eval-rst}
.. currentmodule:: mache.deploy.jinja

.. autosummary::
    :toctree: generated/

    define_square_bracket_environment
```

```{eval-rst}
.. currentmodule:: mache.deploy.machine

.. autosummary::
    :toctree: generated/

    get_known_mache_machines
    get_known_target_machines
    get_known_machines
    get_machine
    get_machine_config
```

```{eval-rst}
.. currentmodule:: mache.deploy.run

.. autosummary::
    :toctree: generated/

    run_deploy
```

```{eval-rst}
.. currentmodule:: mache.deploy.spack

.. autosummary::
    :toctree: generated/

    SpackDeployResult
    SpackSoftwareEnvResult
    deploy_spack_envs
    deploy_spack_software_env
    load_existing_spack_envs
    load_existing_spack_software_env
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
