source /home/software/spack-0.10.1/opt/spack/linux-centos7-x86_64/gcc-4.8.5/lmod-7.4.9-ic63herzfgw5u3na5mdtvp3nwxy6oj2z/lmod/lmod/init/csh
setenv MODULEPATH $MODULEPATH:/software/centos7/spack-latest/share/spack/lmod/linux-centos7-x86_64/Core

module purge

module use \
    /lcrc/group/e3sm/soft/modulefiles/anvil

module load \
    cmake/3.26.3-nszudya \
    gcc/8.2.0 \
    intel/20.0.4-lednsve \
    intel-mkl/2020.4.304-voqlapk \
    openmpi/4.1.1-v3b3npd

{%- if e3sm_hdf5_netcdf %}
module load \
    netcdf-c/4.4.1-smyuxme \
    netcdf-cxx/4.2-kfb2aag \
    netcdf-fortran/4.4.4-mablvyc \
    parallel-netcdf/1.11.0-x4n5s7k
{%- endif %}

setenv UCX_TLS "self,sm,ud"
setenv UCX_UD_MLX5_RX_QUEUE_LEN "16384"
setenv KMP_AFFINITY "granularity=core,balanced"
setenv KMP_HOT_TEAMS_MODE "1"
