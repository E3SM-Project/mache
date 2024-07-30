setenv http_proxy http://proxyout.lanl.gov:8080/
setenv https_proxy http://proxyout.lanl.gov:8080/
setenv ftp_proxy http://proxyout.lanl.gov:8080
setenv HTTP_PROXY http://proxyout.lanl.gov:8080
setenv HTTPS_PROXY http://proxyout.lanl.gov:8080
setenv FTP_PROXY http://proxyout.lanl.gov:8080

source /usr/share/lmod/8.3.1/init/csh

module rm PrgEnv-gnu
module rm PrgEnv-nvidia
module rm PrgEnv-cray
module rm PrgEnv-aocc
module rm craype-accel-nvidia80
module rm craype-accel-host

module load PrgEnv-nvidia/8.4.0
module load nvidia/22.7
module load cudatoolkit/11.7
module load gcc-mixed/11.2.0
module load craype-x86-milan
module load libfabric/1.15.2.0
module load craype-accel-host
module load craype
module load cray-mpich/8.1.26
{% if e3sm_lapack %}
module load cray-libsci/23.05.1.4
{% endif %}
{% if e3sm_hdf5_netcdf %}
module rm cray-hdf5-parallel
module rm cray-netcdf-hdf5parallel
module rm cray-parallel-netcdf
module load cray-hdf5-parallel/1.12.2.3
module load cray-netcdf-hdf5parallel/4.9.0.3
module load cray-parallel-netcdf/1.12.3.3
{% endif %}

setenv MPICH_ENV_DISPLAY 1
setenv MPICH_VERSION_DISPLAY 1
## purposefully omitting OMP variables that cause trouble in ESMF
# setenv OMP_STACKSIZE 128M
# setenv OMP_PROC_BIND spread
# setenv OMP_PLACES threads
setenv HDF5_USE_FILE_LOCKING FALSE
setenv PERL5LIB /usr/projects/climate/SHARED_CLIMATE/software/chicoma-cpu/perl5-only-switch/lib/perl5
setenv PNETCDF_HINTS "romio_ds_write=disable;romio_ds_read=disable;romio_cb_write=enable;romio_cb_read=enable"
setenv MPICH_COLL_SYNC MPI_Bcast

setenv LD_LIBRARY_PATH $CRAY_LD_LIBRARY_PATH:$LD_LIBRARY_PATH
setenv BLA_VENDOR NVHPC
