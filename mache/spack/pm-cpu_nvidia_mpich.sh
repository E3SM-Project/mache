module rm cray-hdf5-parallel &> /dev/null
module rm cray-netcdf-hdf5parallel &> /dev/null
module rm cray-parallel-netcdf &> /dev/null
module rm PrgEnv-gnu &> /dev/null
module rm PrgEnv-intel &> /dev/null
module rm PrgEnv-nvidia &> /dev/null
module rm PrgEnv-cray &> /dev/null
module rm PrgEnv-aocc &> /dev/null
module rm gcc-native &> /dev/null
module rm intel &> /dev/null
module rm intel-oneapi &> /dev/null
module rm cudatoolkit &> /dev/null
module rm climate-utils &> /dev/null
module rm cray-libsci &> /dev/null
module rm matlab &> /dev/null
module rm craype-accel-nvidia80 &> /dev/null
module rm craype-accel-host &> /dev/null
module rm perftools-base &> /dev/null
module rm perftools &> /dev/null
module rm darshan &> /dev/null

module load PrgEnv-nvidia
module load nvidia/22.7
module load craype-x86-milan
module load libfabric/1.15.2.0
module load craype-accel-host
module load craype/2.7.20
module rm cray-mpich &> /dev/null
module load cray-mpich/8.1.25
{% if e3sm_lapack %}
module load cray-libsci/23.02.1.1
{% endif %}
{% if e3sm_hdf5_netcdf %}
module rm cray-hdf5-parallel &> /dev/null
module rm cray-netcdf-hdf5parallel &> /dev/null
module rm cray-parallel-netcdf &> /dev/null
module load cray-hdf5-parallel/1.12.2.3
module load cray-netcdf-hdf5parallel/4.9.0.3
module load cray-parallel-netcdf/1.12.3.3
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
export MPICH_COLL_SYNC=MPI_Bcast
export GATOR_INITIAL_MB=4000MB
export BLA_VENDOR=NVHPC
