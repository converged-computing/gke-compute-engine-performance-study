#!/bin/bash

mkdir -p /data
export CALI_LOG_VERBOSITY="2"
export CALI_CONFIG=spot,output=/data/out.cali,profile.mpi,timeseries,timeseries.iteration_interval=1,timeseries.maxrows=500,mpi.message.count,mpi.message.size
flux run -o cpu-affinity=per-task -N 4 -n 192 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 8,6,4      
unset CALI_CONFIG

echo
echo "START"
echo "/opt/caliper-build/src/tools/cali-query/cali-query -Gj /data/out.cali"
/opt/caliper-build/src/tools/cali-query/cali-query -Gj /data/out.cali
echo "END"
echo
echo "START"
echo "/opt/caliper-build/src/tools/cali-query/cali-query -T /data/out.cali"
/opt/caliper-build/src/tools/cali-query/cali-query -T /data/out.cali
echo "END"
