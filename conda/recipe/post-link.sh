#!/usr/bin/env bash

machine=$("${PREFIX}/bin/python" -c "from mache import discover_machine; print(discover_machine(quiet=True))")
if [[ "${machine}" != "None" ]]; then
  mkdir -p "${PREFIX}/share/mache"
  echo "${machine}" > "${PREFIX}/share/mache/machine.txt"
fi
