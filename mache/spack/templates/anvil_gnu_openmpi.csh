source /home/software/spack-0.10.1/opt/spack/linux-centos7-x86_64/gcc-4.8.5/lmod-7.4.9-ic63herzfgw5u3na5mdtvp3nwxy6oj2z/lmod/lmod/init/csh
setenv MODULEPATH $MODULEPATH:/software/centos7/spack-latest/share/spack/lmod/linux-centos7-x86_64/Core

module purge

module use \
    /lcrc/group/e3sm/soft/modulefiles/anvil

module load \
    cmake/3.26.3-nszudya \
    gcc/8.2.0-xhxgy33 \
    intel-mkl/2020.4.304-d6zw4xa \
    openmpi/4.1.1-x5n4m36

{% if e3sm_hdf5_netcdf %}
module load \
    netcdf-c/4.4.1-mtfptpl \
    netcdf-cxx/4.2-osp27dq \
    netcdf-fortran/4.4.4-5yd6dos \
    parallel-netcdf/1.11.0-a7ohxsg
{% endif %}

setenv UCX_TLS "self,sm,ud"
setenv UCX_UD_MLX5_RX_QUEUE_LEN "16384"
