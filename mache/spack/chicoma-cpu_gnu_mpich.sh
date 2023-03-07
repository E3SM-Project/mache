export http_proxy=http://proxyout.lanl.gov:8080/
export https_proxy=http://proxyout.lanl.gov:8080/
export ftp_proxy=http://proxyout.lanl.gov:8080
export HTTP_PROXY=http://proxyout.lanl.gov:8080
export HTTPS_PROXY=http://proxyout.lanl.gov:8080
export FTP_PROXY=http://proxyout.lanl.gov:8080

source /usr/share/lmod/8.3.1/init/sh

module rm PrgEnv-gnu
module rm PrgEnv-nvidia
module rm PrgEnv-cray
module rm PrgEnv-aocc
module rm craype-accel-nvidia80
module rm craype-accel-host

module load PrgEnv-gnu/8.3.3
module load gcc/12.1.0
module load craype-accel-host
{% if e3sm_lapack %}
module load cray-libsci
{% endif %}
module load craype
module load libfabric/1.15.0.0
module load cray-mpich/8.1.21
{% if e3sm_hdf5_netcdf %}
module rm cray-hdf5-parallel
module rm cray-netcdf-hdf5parallel
module rm cray-parallel-netcdf
module load cray-hdf5-parallel/1.12.2.1
module load cray-netcdf-hdf5parallel/4.9.0.1
module load cray-parallel-netcdf/1.12.3.1
{% endif %}

export MPICH_ENV_DISPLAY=1
export MPICH_VERSION_DISPLAY=1
export OMP_STACKSIZE=128M
export OMP_PROC_BIND=spread
export OMP_PLACES=threads
export HDF5_USE_FILE_LOCKING=FALSE
export PERL5LIB=/usr/projects/climate/SHARED_CLIMATE/software/chicoma-cpu/perl5-only-switch/lib/perl5
export PNETCDF_HINTS="romio_ds_write=disable;romio_ds_read=disable;romio_cb_write=enable;romio_cb_read=enable"
export FI_CXI_RX_MATCH_MODE=software
export MPICH_COLL_SYNC=MPI_Bcast
