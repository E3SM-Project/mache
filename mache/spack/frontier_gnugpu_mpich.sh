module reset >& /dev/null
module switch Core Core/24.00 >& /dev/null
module switch PrgEnv-cray PrgEnv-gnu/8.3.3 >& /dev/null
module switch gcc gcc/11.2.0 >& /dev/null
module load craype-accel-amd-gfx90a
module load rocm/5.4.0

{% if e3sm_lapack %}
module load cray-libsci/22.12.1.1
{% endif %}
{% if e3sm_hdf5_netcdf %}
module load cray-hdf5-parallel/1.12.2.1
module load cray-netcdf-hdf5parallel/4.9.0.1
module load cray-parallel-netcdf/1.12.3.1
{% endif %}

{% if e3sm_hdf5_netcdf %}
export NETCDF_C_PATH=$CRAY_NETCDF_HDF5PARALLEL_PREFIX
export NETCDF_FORTRAN_PATH=$CRAY_NETCDF_HDF5PARALLEL_PREFIX
export PNETCDF_PATH=$CRAY_PARALLEL_NETCDF_PREFIX
{% endif %}
export HDF5_USE_FILE_LOCKING=FALSE
export MPICH_GPU_SUPPORT_ENABLED=1
