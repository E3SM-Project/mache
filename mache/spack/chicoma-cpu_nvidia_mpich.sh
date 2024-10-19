export http_proxy=http://proxyout.lanl.gov:8080/
export https_proxy=http://proxyout.lanl.gov:8080/
export ftp_proxy=http://proxyout.lanl.gov:8080
export HTTP_PROXY=http://proxyout.lanl.gov:8080
export HTTPS_PROXY=http://proxyout.lanl.gov:8080
export FTP_PROXY=http://proxyout.lanl.gov:8080

source /usr/share/lmod/lmod/init/sh

module rm cray-hdf5-parallel
module rm cray-netcdf-hdf5parallel
module rm cray-parallel-netcdf
module rm cray-netcdf
module rm cray-hdf5
module rm intel
module rm intel-oneapi
module rm nvidia
module rm aocc
module rm cudatoolkit
module rm climate-utils
module rm cray-libsci
module rm craype-accel-nvidia80
module rm craype-accel-host
module rm perftools-base
module rm perftools
module rm darshan
module rm PrgEnv-gnu
module rm PrgEnv-intel
module rm PrgEnv-nvidia
module rm PrgEnv-cray
module rm PrgEnv-aocc

module load PrgEnv-nvidia/8.4.0
module load nvidia/22.7
module load craype-x86-milan
module load craype-accel-host
module load craype
module load cray-mpich/8.1.26
{% if e3sm_lapack %}
module load cray-libsci/23.05.1.4
{% endif %}
{% if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.3
module load cray-netcdf-hdf5parallel/4.9.0.3
module load cray-parallel-netcdf/1.12.3.3
{% endif %}
module load cmake/3.27.7

export MPICH_ENV_DISPLAY=1
export MPICH_VERSION_DISPLAY=1
## purposefully omitting OMP variables that cause trouble in ESMF
# export OMP_STACKSIZE=128M
# export OMP_PROC_BIND=spread
# export OMP_PLACES=threads
export HDF5_USE_FILE_LOCKING=FALSE
export PERL5LIB=/usr/projects/climate/SHARED_CLIMATE/software/chicoma-cpu/perl5-only-switch/lib/perl5
export PNETCDF_HINTS="romio_ds_write=disable;romio_ds_read=disable;romio_cb_write=enable;romio_cb_read=enable"
export MPICH_COLL_SYNC=MPI_Bcast

export LD_LIBRARY_PATH=$CRAY_LD_LIBRARY_PATH:$LD_LIBRARY_PATH
export BLA_VENDOR=NVHPC
