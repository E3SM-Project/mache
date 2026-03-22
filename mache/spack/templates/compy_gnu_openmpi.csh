module load \
    gcc/10.2.0 \
    openmpi/4.0.1

{%- if use_system_package('hdf5') %}
module load hdf5/1.10.5
{%- endif %}
{%- if use_system_packages('netcdf-c', 'netcdf-fortran') %}
module load netcdf/4.6.3
{%- endif %}
{%- if use_system_package('parallel-netcdf') %}
module load pnetcdf/1.9.0
{%- endif %}
