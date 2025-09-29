#!/bin/bash

mkdir -p /data
export CALI_LOG_VERBOSITY="2"

# osu latency with mpi profile
# export CALI_CONFIG=spot,output=/data/out.cali,profile.mpi,mpi.message.count,mpi.message.size
# flux run -o cpu-affinity=per-task -N 2 -n 2 /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
# unset CALI_CONFIG

# echo
# echo "START"
# echo "cali-query -Gj /data/out.cali"
# cali-query -Gj /data/out.cali
# echo "END"
# echo
# echo "START"
# echo "cali-query -T /data/out.cali"
# cali-query -T /data/out.cali
# echo "END"
# rm /data/out.cali

# osu latency with trace
export CALI_CONFIG=trace.mpi,event-trace
flux run -o cpu-affinity=per-task -N 2 -n 2 /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
unset CALI_CONFIG
echo
echo "START"
echo "cali-query -Gj /data/out.cali"
cali-query -Gj /data/out.cali
echo "END"
echo
echo "START"
echo "cali-query -T /data/out.cali"
cali-query -T /data/out.cali
echo "END"
rm /data/out.cali

echo "OSU-ALLREDUCE"

# All reduce with mpi profile
export CALI_CONFIG=spot,output=/data/out.cali,profile.mpi,mpi.message.count,mpi.message.size
flux run -o cpu-affinity=per-task -N 4 -n 192 /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce
unset CALI_CONFIG

echo
echo "START"
echo "cali-query -Gj /data/out.cali"
sleep 3
cali-query -Gj /data/out.cali
echo "END"
echo
echo "START"
echo "cali-query -T /data/out.cali"
sleep 3
cali-query -T /data/out.cali
echo "END"
rm /data/out.cali

# All reduce with trace
export CALI_CONFIG=trace.mpi,event-trace
flux run -o cpu-affinity=per-task -N 4 -n 192 /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce
unset CALI_CONFIG
echo
echo "START"
echo "cali-query -Gj /data/out.cali"
sleep 3
cali-query -Gj /data/out.cali
echo "END"
echo
echo "START"
echo "cali-query -T /data/out.cali"
sleep 3
cali-query -T /data/out.cali
echo "END"

