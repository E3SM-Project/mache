source /opt/cray/pe/lmod/lmod/init/sh

module reset

module switch Core Core/24.00
module switch PrgEnv-cray PrgEnv-amd/8.3.3
module switch amd amd/5.4.0
module load cray-libsci/22.12.1.1

module load \
    craype-accel-amd-gfx90a \
    rocm/5.4.0 \
    libunwind/1.5.0 \
    libfabric/1.20.1 \
    cray-mpich/8.1.26 \
    subversion/1.14.1 \
    git/2.36.1 \
    cmake/3.23.2

module rm \
    darshan-runtime &> /dev/null

{% if e3sm_hdf5_netcdf %}
module load \
    cray-hdf5-parallel/1.12.2.1 \
    cray-netcdf-hdf5parallel/4.9.0.1 \
    cray-parallel-netcdf/1.12.3.1
{% endif %}

export HDF5_ROOT=""
export MPICH_GPU_SUPPORT_ENABLED="0"
export MPICH_VERSION_DISPLAY="1"
export MPICH_OFI_CXI_COUNTER_REPORT="2"
export LD_LIBRARY_PATH="${CRAY_LD_LIBRARY_PATH}:${LD_LIBRARY_PATH}"
export SKIP_BLAS="True"
export GPUS_PER_NODE=" "
export NTASKS_PER_GPU=" "
export GPU_BIND_ARGS=" "
export MPICH_GPU_SUPPORT_ENABLED="1"
export GPUS_PER_NODE="--gpus-per-node=8"
export GPU_BIND_ARGS="--gpu-bind=closest"
export PKG_CONFIG_PATH="/lustre/orion/cli115/world-shared/frontier/3rdparty/protobuf/21.6/amdclang-15.0.0/lib/pkgconfig:${CRAY_LIBSCI_PREFIX_DIR}/lib/pkgconfig:${PKG_CONFIG_PATH}"

{% if e3sm_hdf5_netcdf %}
export NETCDF_PATH="${NETCDF_DIR}"
export NETCDF_C_PATH="${NETCDF_DIR}"
export NETCDF_FORTRAN_PATH="${NETCDF_DIR}"
export PNETCDF_PATH="${PNETCDF_DIR}"
{% endif %}
