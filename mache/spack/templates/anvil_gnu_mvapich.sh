source /home/software/spack-0.10.1/opt/spack/linux-centos7-x86_64/gcc-4.8.5/lmod-7.4.9-ic63herzfgw5u3na5mdtvp3nwxy6oj2z/lmod/lmod/init/sh
export MODULEPATH=$MODULEPATH:/software/centos7/spack-latest/share/spack/lmod/linux-centos7-x86_64/Core

module purge

module use \
    /lcrc/group/e3sm/soft/modulefiles/anvil

module load \
    cmake/3.26.3-nszudya \
    gcc/8.2.0-xhxgy33 \
    intel-mkl/2020.4.304-d6zw4xa \
    mvapich2/2.2-verbs-ppznoge

{%- if e3sm_hdf5_netcdf %}
module load \
    netcdf/4.4.1-ve2zfkw \
    netcdf-cxx/4.2-2rkopdl \
    netcdf-fortran/4.4.4-thtylny \
    parallel-netcdf/1.11.0-c22b2bn
{%- endif %}

export UCX_TLS="self,sm,ud"
export UCX_UD_MLX5_RX_QUEUE_LEN="16384"
export MV2_ENABLE_AFFINITY="0"
export MV2_SHOW_CPU_BINDING="1"
export MV2_HOMOGENEOUS_CLUSTER="1"
