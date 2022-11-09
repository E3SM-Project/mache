module rm PrgEnv-gnu
module rm PrgEnv-nvidia
module rm cudatoolkit
module rm craype-accel-nvidia80
module rm craype-accel-host
module rm perftools-base
module rm perftools
module rm darshan

module load PrgEnv-gnu/8.3.3
module load gcc/11.2.0
module load craype-accel-host
{% if e3sm_lapack %}
module load cray-libsci
{% endif %}
module load craype
module rm cray-mpich
module load libfabric/1.15.0.0
module load cray-mpich/8.1.15
{% if e3sm_hdf5_netcdf %}
module rm cray-hdf5-parallel
module rm cray-netcdf-hdf5parallel
module rm cray-parallel-netcdf
module load cray-hdf5-parallel/1.12.1.1
module load cray-netcdf-hdf5parallel/4.8.1.1
module load cray-parallel-netcdf/1.12.2.1
{% endif %}
module load cmake/3.22.0

{% if e3sm_hdf5_netcdf %}
setenv NETCDF_C_PATH $(dirname $(dirname $(which nc-config)))
setenv NETCDF_FORTRAN_PATH $(dirname $(dirname $(which nf-config)))
setenv PNETCDF_PATH $(dirname $(dirname $(which pnetcdf_version)))
{% endif %}
setenv MPICH_ENV_DISPLAY 1
setenv MPICH_VERSION_DISPLAY 1
setenv OMP_STACKSIZE 128M
setenv OMP_PROC_BIND spread
setenv OMP_PLACES threads
setenv HDF5_USE_FILE_LOCKING FALSE
setenv PERL5LIB /global/cfs/cdirs/e3sm/perl/lib/perl5-only-switch
setenv FI_CXI_RX_MATCH_MODE software
