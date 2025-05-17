source /usr/share/lmod/lmod/init/csh

module load \
    cmake/3.30.5 \
    oneapi/release/2025.0.5

setenv LD_LIBRARY_PATH "/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002/lib:/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002/lib:${LD_LIBRARY_PATH}"
setenv PATH "/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002/bin:/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002/bin:${PATH}"
setenv FI_CXI_DEFAULT_CQ_SIZE "131072"
setenv FI_CXI_CQ_FILL_PERCENT "20"
setenv LIBOMPTARGET_DEBUG "0"
setenv MPIR_CVAR_ENABLE_GPU "0"
setenv GPU_TILE_COMPACT " "
setenv RANKS_BIND "core"
setenv KMP_AFFINITY "granularity=core,balanced"

{%- if e3sm_hdf5_netcdf %}
setenv NETCDF_PATH "/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
setenv NETCDF_C_PATH "/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
setenv NETCDF_FORTRAN_PATH "/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
setenv PNETCDF_PATH "/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002"
{%- endif %}
