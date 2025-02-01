# Utilities for Mache Package

This directory contains utilities that are helpful for making updates to the
mache package.

## update CIME machine config

The `update_cime_machine_config.py` script can be used to download the latest
version of the `config_machines.xml` file from E3SM's `master` branch, then
compare it from the previous version stored in `mache` and show changes related
to supported machines.

A developer can then copy `new_config_machines.xml` into
`mache/cime_machine_config/config_machines.xml` as part of a PR that makes
relevant updates. They should also make the changes associated with the
differences that this utility displays in the appropriate `mache/spack` files.
