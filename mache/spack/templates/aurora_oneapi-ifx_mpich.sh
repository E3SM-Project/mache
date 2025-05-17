source /usr/share/lmod/lmod/init/sh

module load \
    cmake/3.30.5 \
    oneapi/release/2025.0.5

export LD_LIBRARY_PATH="/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002/lib:/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002/lib:${LD_LIBRARY_PATH}"
export PATH="/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002/bin:/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002/bin:${PATH}"
export FI_CXI_DEFAULT_CQ_SIZE="131072"
export FI_CXI_CQ_FILL_PERCENT="20"
export LIBOMPTARGET_DEBUG="0"
export MPIR_CVAR_ENABLE_GPU="0"
export GPU_TILE_COMPACT=" "
export RANKS_BIND="core"
export KMP_AFFINITY="granularity=core,balanced"

{%- if e3sm_hdf5_netcdf %}
export NETCDF_PATH="/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
export NETCDF_C_PATH="/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
export NETCDF_FORTRAN_PATH="/lus/flare/projects/E3SM_Dec/soft/netcdf/4.9.2c-4.6.1f/oneapi.eng.2024.07.30.002"
export PNETCDF_PATH="/lus/flare/projects/E3SM_Dec/soft/pnetcdf/1.14.0/oneapi.eng.2024.07.30.002"
{%- endif %}
