source /opt/cray/pe/lmod/lmod/init/sh

module reset

module load \
    Core/25.03 \
    PrgEnv-gnu \
    cpe/24.11 \
    libunwind/1.8.1 \
    subversion \
    git \
    cmake \
    craype-accel-amd-gfx90a \
    rocm/6.2.4

module rm \
    darshan-runtime &> /dev/null

{%- if e3sm_hdf5_netcdf %}
module load \
    cray-hdf5-parallel/1.14.3.3 \
    cray-netcdf-hdf5parallel/4.9.0.15 \
    cray-parallel-netcdf/1.12.3.15
{%- endif %}

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
export PKG_CONFIG_PATH="/lustre/orion/cli115/world-shared/frontier/3rdparty/protobuf/21.6/gcc-native-13.2/lib/pkgconfig:${PKG_CONFIG_PATH}"

{%- if e3sm_hdf5_netcdf %}
export NETCDF_PATH="${NETCDF_DIR}"
export NETCDF_C_PATH="${NETCDF_DIR}"
export NETCDF_FORTRAN_PATH="${NETCDF_DIR}"
export PNETCDF_PATH="${PNETCDF_DIR}"
{%- endif %}
