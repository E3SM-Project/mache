setenv http_proxy http://proxyout.lanl.gov:8080/
setenv https_proxy http://proxyout.lanl.gov:8080/
setenv ftp_proxy http://proxyout.lanl.gov:8080
setenv HTTP_PROXY http://proxyout.lanl.gov:8080
setenv HTTPS_PROXY http://proxyout.lanl.gov:8080
setenv FTP_PROXY http://proxyout.lanl.gov:8080

source /usr/share/lmod/lmod/init/csh

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
{%- if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.9 \
            cray-netcdf-hdf5parallel/4.9.0.9 \
            cray-parallel-netcdf/1.12.3.9
{%- endif %}

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

# for standalone MPAS builds
setenv GNU_CRAY_LDFLAGS "-Wl,--enable-new-dtags"

setenv LD_LIBRARY_PATH="/usr/lib64/gcc/x86_64-suse-linux/12:${CRAY_LD_LIBRARY_PATH}:${LD_LIBRARY_PATH}"
