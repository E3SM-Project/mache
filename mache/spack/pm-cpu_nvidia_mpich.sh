module rm cpe \
          cray-hdf5-parallel \
          cray-netcdf-hdf5parallel \
          cray-parallel-netcdf \
          PrgEnv-gnu \
          PrgEnv-intel \
          PrgEnv-nvidia \
          PrgEnv-cray \
          PrgEnv-aocc \
          gcc-native \
          intel \
          intel-oneapi \
          cudatoolkit \
          climate-utils \
          cray-libsci \
          matlab \
          craype-accel-nvidia80 \
          craype-accel-host \
          perftools-base \
          perftools \
          darshan \
          cray-mpich &> /dev/null

module load PrgEnv-nvidia \
            nvidia/24.5 \
            cray-libsci/23.12.5 \
            craype-accel-host \
            craype/2.7.30 \
            libfabric/1.20.1 \
            cray-mpich/8.1.28
{% if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.9 \
            cray-netcdf-hdf5parallel/4.9.0.9 \
            cray-parallel-netcdf/1.12.3.9
{% endif %}

{% if e3sm_hdf5_netcdf %}
export NETCDF_PATH=$CRAY_NETCDF_HDF5PARALLEL_PREFIX
export NETCDF_C_PATH=$CRAY_NETCDF_HDF5PARALLEL_PREFIX
export NETCDF_FORTRAN_PATH=$CRAY_NETCDF_HDF5PARALLEL_PREFIX
export PNETCDF_PATH=$CRAY_PARALLEL_NETCDF_PREFIX
{% endif %}
export MPICH_ENV_DISPLAY=1
export MPICH_VERSION_DISPLAY=1
export MPICH_MPIIO_DVS_MAXNODES=1
## purposefully omitting OMP variables that cause trouble in ESMF
# export OMP_STACKSIZE=128M
# export OMP_PROC_BIND=spread
# export OMP_PLACES=threads
export HDF5_USE_FILE_LOCKING=FALSE
## Not needed
# export PERL5LIB=/global/cfs/cdirs/e3sm/perl/lib/perl5-only-switch
export MPICH_GPU_SUPPORT_ENABLED=1

if [ -z "${NERSC_HOST:-}" ]; then
  # happens when building spack environment
  export NERSC_HOST="perlmutter"
fi
export FI_CXI_RX_MATCH_MODE=software
export FI_MR_CACHE_MONITOR=kdreg2
export MPICH_COLL_SYNC=MPI_Bcast
export GATOR_INITIAL_MB=4000MB
export BLA_VENDOR=NVHPC
