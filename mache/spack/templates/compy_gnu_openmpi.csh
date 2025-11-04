module load \
    gcc/10.2.0 \
    openmpi/4.0.1

{%- if e3sm_hdf5_netcdf %}
module load \
    hdf5/1.10.5 \
    netcdf/4.6.3 \
    pnetcdf/1.9.0
{%- endif %}
