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
    mvapich2/2.3.6-verbs-x4iz7lq

{%- if e3sm_hdf5_netcdf %}
module load \
    netcdf-c/4.4.1-gei7x7w \
    netcdf-cxx/4.2-db2f5or \
    netcdf-fortran/4.4.4-b4ldb3a \
    parallel-netcdf/1.11.0-kj4jsvt
{%- endif %}

setenv UCX_TLS "self,sm,ud"
setenv UCX_UD_MLX5_RX_QUEUE_LEN "16384"
setenv MV2_ENABLE_AFFINITY "0"
setenv MV2_SHOW_CPU_BINDING "1"
setenv MV2_HOMOGENEOUS_CLUSTER "1"
setenv KMP_AFFINITY "granularity=core,balanced"
setenv KMP_HOT_TEAMS_MODE "1"
