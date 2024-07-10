export UCX_TLS="^xpmem"
export OMPI_MCA_sharedfp="^lockedfile,individual"
export OMP_STACKSIZE=128M
export KMP_AFFINITY="granularity=core,balanced"
export KMP_AFFINITY="granularity=thread,balanced"
