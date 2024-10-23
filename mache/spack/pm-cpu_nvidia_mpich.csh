module rm cray-hdf5-parallel \
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
            nvidia/22.7 \
            craype-x86-milan \
            libfabric/1.20.1 \
            craype-accel-host \
            craype/2.7.20 \
            cray-mpich/8.1.25 \
            cray-libsci/23.12.5
{% if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.3 \
            cray-netcdf-hdf5parallel/4.9.0.3 \
            cray-parallel-netcdf/1.12.3.3
{% endif %}

{% if e3sm_hdf5_netcdf %}
setenv NETCDF_PATH $CRAY_NETCDF_HDF5PARALLEL_PREFIX
setenv NETCDF_C_PATH $CRAY_NETCDF_HDF5PARALLEL_PREFIX
setenv NETCDF_FORTRAN_PATH $CRAY_NETCDF_HDF5PARALLEL_PREFIX
setenv PNETCDF_PATH $CRAY_PARALLEL_NETCDF_PREFIX
{% endif %}
setenv MPICH_ENV_DISPLAY 1
setenv MPICH_VERSION_DISPLAY 1
setenv MPICH_MPIIO_DVS_MAXNODES 1
## purposefully omitting OMP variables that cause trouble in ESMF
# setenv OMP_STACKSIZE 128M
# setenv OMP_PROC_BIND spread
# setenv OMP_PLACES threads
setenv HDF5_USE_FILE_LOCKING FALSE
## Not needed
# setenv PERL5LIB /global/cfs/cdirs/e3sm/perl/lib/perl5-only-switch
setenv MPICH_GPU_SUPPORT_ENABLED 1
setenv MPICH_COLL_SYNC MPI_Bcast
setenv GATOR_INITIAL_MB 4000MB
setenv BLA_VENDOR NVHPC
