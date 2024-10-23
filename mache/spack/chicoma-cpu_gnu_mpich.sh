export http_proxy=http://proxyout.lanl.gov:8080/
export https_proxy=http://proxyout.lanl.gov:8080/
export ftp_proxy=http://proxyout.lanl.gov:8080
export HTTP_PROXY=http://proxyout.lanl.gov:8080
export HTTPS_PROXY=http://proxyout.lanl.gov:8080
export FTP_PROXY=http://proxyout.lanl.gov:8080

source /usr/share/lmod/lmod/init/sh

module rm cray-hdf5-parallel \
          cray-netcdf-hdf5parallel \
          cray-parallel-netcdf \
          cray-netcdf \
          cray-hdf5 \
          gcc \
          gcc-native \
          intel \
          intel-oneapi \
          nvidia \
          aocc \
          cudatoolkit \
          climate-utils \
          cray-libsci \
          craype \
          craype-accel-nvidia80 \
          craype-accel-host \
          perftools-base \
          perftools \
          darshan \
          PrgEnv-gnu \
          PrgEnv-intel \
          PrgEnv-nvidia \
          PrgEnv-cray \
          PrgEnv-aocc

# we must load cray-libsci for gcc to work
module load PrgEnv-gnu/8.5.0 \
            gcc-native/12.3 \
            cray-libsci/23.12.5 \
            craype-accel-host \
            craype/2.7.30 \
            cray-mpich/8.1.28 \
            cmake/3.27.7
{% if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.9 \
            cray-netcdf-hdf5parallel/4.9.0.9 \
            cray-parallel-netcdf/1.12.3.9
{% endif %}

export MPICH_ENV_DISPLAY=1
export MPICH_VERSION_DISPLAY=1
## purposefully omitting OMP variables that cause trouble in ESMF
# export OMP_STACKSIZE=128M
# export OMP_PROC_BIND=spread
# export OMP_PLACES=threads
export HDF5_USE_FILE_LOCKING=FALSE
export PERL5LIB=/usr/projects/climate/SHARED_CLIMATE/software/chicoma-cpu/perl5-only-switch/lib/perl5
export PNETCDF_HINTS="romio_ds_write=disable;romio_ds_read=disable;romio_cb_write=enable;romio_cb_read=enable"
export FI_CXI_RX_MATCH_MODE=software
export MPICH_COLL_SYNC=MPI_Bcast

export LD_LIBRARY_PATH="/usr/lib64/gcc/x86_64-suse-linux/12:${CRAY_LD_LIBRARY_PATH}:${LD_LIBRARY_PATH}"

# for standalone MPAS builds
export GNU_CRAY_LDFLAGS="-Wl,--enable-new-dtags"
