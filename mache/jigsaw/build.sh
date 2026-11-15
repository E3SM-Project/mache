#!/usr/bin/env bash

set -x
set -e

# build and install JIGSAW
mkdir build
cd build
cmake ${CMAKE_ARGS} \
  -DCMAKE_INSTALL_PREFIX=${PREFIX} \
  -DCMAKE_BUILD_TYPE=Release \
  ../external/jigsaw
cmake --build . --config Release --target install
cd ..

# Since 1.1.1, jigsaw-python refuses to build a wheel unless the back end
# is bundled in the package, so copy it there too.  The copies on PATH stay
# for callers that run `jigsaw` directly.
mkdir -p jigsawpy/_bin jigsawpy/_lib
cp ${PREFIX}/bin/jigsaw ${PREFIX}/bin/tripod ${PREFIX}/bin/marche \
  jigsawpy/_bin/
cp ${PREFIX}/lib/libjigsaw${SHLIB_EXT} jigsawpy/_lib/

${PYTHON} -m pip install . -vv --no-deps --no-build-isolation
