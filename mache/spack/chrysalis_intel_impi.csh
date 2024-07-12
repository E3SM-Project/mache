setenv UCX_TLS "^xpmem"
setenv OMPI_MCA_sharedfp "^lockedfile,individual"
setenv OMP_STACKSIZE 128M
setenv KMP_AFFINITY "granularity=core,balanced"
setenv KMP_AFFINITY "granularity=thread,balanced"
