export http_proxy=http://proxyout.lanl.gov:8080/
export https_proxy=http://proxyout.lanl.gov:8080/
export ftp_proxy=http://proxyout.lanl.gov:8080
export HTTP_PROXY=http://proxyout.lanl.gov:8080
export HTTPS_PROXY=http://proxyout.lanl.gov:8080
export FTP_PROXY=http://proxyout.lanl.gov:8080

module purge
module load cmake/3.16.2
module load intel/19.0.4
module load intel-mpi/2019.4
module load friendly-testing
module load hdf5-parallel/1.8.16
module load pnetcdf/1.11.2
module load netcdf-h5parallel/4.7.3
module load mkl/2019.0.4
