setenv OMPI_MCA_sharedfp "^lockedfile,individual"
setenv UCX_TLS "^xpmem"
## purposefully omitting OMP variables that slow down MPAS-Ocean runs
#setenv OMP_STACKSIZE 128M
#setenv OMP_PLACES cores
