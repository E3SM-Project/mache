module rm craype
module rm craype-mic-knl
module rm craype-haswell
module rm PrgEnv-intel
module rm PrgEnv-cray
module rm PrgEnv-gnu
module rm intel
module rm cce
module rm gcc
module rm cray-parallel-netcdf
module rm cray-hdf5-parallel
module rm pmi
module rm cray-mpich2
module rm cray-mpich
module rm cray-netcdf
module rm cray-hdf5
module rm cray-netcdf-hdf5parallel
module rm cray-libsci
module rm papi
module rm cmake
module rm cray-petsc
module rm esmf
module rm zlib
module rm craype-hugepages2M
module rm darshan

module load craype
module load PrgEnv-intel
module load cray-mpich
module rm craype-haswell
module load craype-mic-knl

module swap cray-mpich impi/2020.up4

module load PrgEnv-intel/6.0.10
module rm intel
module load intel/19.0.3.199

module swap craype craype/2.6.2
module rm pmi
module load pmi/5.0.14
module rm craype-haswell
module load craype-mic-knl

module rm cray-netcdf-hdf5parallel
module load cray-netcdf-hdf5parallel/4.6.3.2
module load cray-hdf5-parallel/1.10.5.2
module load cray-parallel-netcdf/1.11.1.1

module rm cmake
module load cmake
module load perl5-extras
