export OMPI_MCA_sharedfp="^lockedfile,individual"
export UCX_TLS="^xpmem"
## purposefully omitting OMP variables that slow down MPAS-Ocean runs
#export OMP_STACKSIZE=128M
#export OMP_PLACES=cores
