# "Bare Metal" on Compute Engine Size 2

## Experiment

Bring up:

```bash
make
```

Shell in:

```bash
gcloud compute ssh flux-0 --zone us-central1-a --tunnel-through-iap
```

If you need to see startup logs:

```bash
sudo journalctl -u google-startup-scripts.service
```

### 1. Applications

```bash
cd /opt/containers
mkdir -p ./results
```

For each experiment, we need to be instance owner. This also cleans up `flux jobs -a` so you get a clean slate.

```bash
sudo -i
```

Oras needs an update

```bash
sudo rm $(which oras) 
VERSION="1.2.0" && \
    curl -LO "https://github.com/oras-project/oras/releases/download/v${VERSION}/oras_${VERSION}_linux_amd64.tar.gz" && \
    mkdir -p oras-install/ && \
    tar -zxf oras_${VERSION}_*.tar.gz -C oras-install/ && \
    sudo mv oras-install/oras /usr/local/bin/ && \
    rm -rf oras_${VERSION}_*.tar.gz oras-install/
```

You'll need to login to oras just once:

```bash
oras login ghcr.io --username vsoch
```

Save this script

```
#!/bin/bash
output=$1

# When they are done:
for jobid in $(flux jobs -a --json | jq -r .jobs[].id)
  do
    # Get the job study id
    study_id=$(flux job info $jobid jobspec | jq -r ".attributes.user.study_id")    
    if [[ -f "$output/${study_id}-${jobid}.out" ]] || [[ "$study_id" == "null" ]]; then
        continue
    fi
    echo "Parsing jobid ${jobid} and study id ${study_id}"
    flux job attach $jobid &> $output/${study_id}-${jobid}.out 
    echo "START OF JOBSPEC" >> $output/${study_id}-${jobid}.out 
    flux job info $jobid jobspec >> $output/${study_id}-${jobid}.out 
    echo "START OF EVENTLOG" >> $output/${study_id}-${jobid}.out 
    flux job info $jobid guest.exec.eventlog >> $output/${study_id}-${jobid}.out
done
```

#### Kripke

```console
mkdir -p ./results/kripke/no-caliper
app=kripke
size=2

# Without caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 2 -n 16 singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_kripke-test.sif kripke --niter 500 --procs 1,4,4 --zones 32,32,32 |& tee ./results/kripke/no-caliper/log-$i.out
done

# Testing vs. bare metal (seems the same)
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  # 3m 6s 3.68e-098 grind time
  time flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i-N 2 -n 16 kripke --niter 500 --procs 1,4,4 --zones 32,32,32
done

# Testing procs (topology)
# 4,4,1: 3m,6s, 3.682430e-09 [(seconds/iteration)/unknowns]
# 4,1,4: 2m57s, 3.508270e-09 [(seconds/iteration)/unknowns]
# 1,4,4: 3m10s, 3.778019e-09 [(seconds/iteration)/unknowns]

bash ./save.sh ./results/kripke/no-caliper
job purge --force --age-limit=0
```

# With caliper

```bash
mkdir -p ./results/kripke/caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,timeseries,timeseries.iteration_interval=1,timeseries.maxrows=500,mpi.message.count,mpi.message.size
  flux run --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 2 -n 16 singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_kripke-caliper-test.sif kripke --niter 500 --procs 1,4,4 --zones 32,32,32 |& tee ./results/kripke/caliper/log-$i.out
  unset CALI_CONFIG

  sleep 3
  echo "/opt/caliper-build/src/tools/cali-query/cali-query -Gj /data/out.cali"
  singularity exec /opt/containers/google-performance-study_kripke-caliper-test.sif /opt/caliper-build/src/tools/cali-query/cali-query -Gj /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-Gj.out
  singularity exec /opt/containers/google-performance-study_kripke-caliper-test.sif /opt/caliper-build/src/tools/cali-query/cali-query -T /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-T.out
  mv /tmp/out.cali ./results/kripke/caliper/$i.cali
done

bash ./save.sh ./results/kripke/caliper
job purge --force --age-limit=0
```

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-$size-$app ./results/kripke
```

#### OSU

Write this script to the filesystem `flux-run-combinations.sh`

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n $nodes | tr '\n' ' ')
list=${hosts}

dequeue_from_list() {
  shift;
  list=$@
}

iter=0
for i in $hosts; do
  dequeue_from_list $list
  for j in $list; do
    echo "${i} ${j}"
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task \
      singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-test.sif /opt/osu-benchmark/build.openmpi/mpi/pt2pt/osu_latency 
  done
done
```

Test on host?

```bash
time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$size-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task /opt/osu-benchmark/build.openmpi/mpi/pt2pt/osu_latency
```

```bash
mkdir -p ./results/osu-latency/no-caliper
bash flux-run-combinations.sh 2 osu-latency
bash ./save.sh ./results/osu-latency/no-caliper
flux job purge --force --age-limit=0

mkdir -p ./results/osu-allreduce/no-caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  time flux run --setattr=user.study_id=$app-$size-iter-$i -N2 -n 16 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-test.sif /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
done

bash ./save.sh ./results/osu-allreduce/no-caliper
flux job purge --force --age-limit=0
```

##### With caliper

Write this script to the filesystem `flux-run-caliper.sh`

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n $nodes | tr '\n' ' ')
list=${hosts}

dequeue_from_list() {
  shift;
  list=$@
}

iter=0
for i in $hosts; do
  dequeue_from_list $list
  for j in $list; do
    export CALI_LOG_VERBOSITY="2"
    export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task \
      singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
    unset CALI_CONFIG
    sleep 2
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-Gj-$i-$j.out
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -T /tmp/out.cali  |& tee ./results/osu-latency/caliper/cali-query-T-$i-$j.out
    mv /tmp/out.cali ./results/osu-latency/caliper/cali-$i-$j.out
    export CALI_CONFIG=trace.mpi,event-trace
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task \
      singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
    unset CALI_CONFIG
    sleep 2
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-trace-Gj-$i-$j.out
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -T /tmp/out.cali  |& tee ./results/osu-latency/caliper/cali-query-trace-T-$i-$j.out
    mv /tmp/out.cali ./results/osu-latency/caliper/cali-trace-$i-$j.out
  done
done
```

Without trace

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n $nodes | tr '\n' ' ')
list=${hosts}

dequeue_from_list() {
  shift;
  list=$@
}

iter=0
for i in $hosts; do
  dequeue_from_list $list
  for j in $list; do
    export CALI_LOG_VERBOSITY="2"
    export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task \
      singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
    unset CALI_CONFIG
    sleep 2
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-Gj-$i-$j.out
    singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -T /tmp/out.cali  |& tee ./results/osu-latency/caliper/cali-query-T-$i-$j.out
    mv /tmp/out.cali ./results/osu-latency/caliper/cali-$i-$j.out
    export CALI_CONFIG=output=/tmp/out.cali,trace.mpi,event-trace
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task \
      singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
    unset CALI_CONFIG
    sleep 2
    # Move files for now - the extraction part might freeze.
    mkdir -p ./results/osu-latency/caliper/trace/$i-$j/
    mv *.cali ./results/osu-latency/caliper/trace/$i-$j/
    # singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-trace-Gj-$i-$j.out
    # singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-trace-Gj-$i-$j.out
  # mv /tmp/*.cali ./results/osu-latency/caliper/cali-trace-$i-$j.out
  done
done
```

Run:

```bash
mkdir -p ./results/osu-latency/caliper
bash ./caliper.sh 2 osu-latency

# Save results
bash ./save.sh ./results/osu-latency/caliper
flux job purge --force --age-limit=0
```

Now osu all reduce.

```bash
mkdir -p ./results/osu-allreduce/caliper
for i in $(seq 1 5); do 

  echo "Running iteration $i"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
  flux run --setattr=user.study_id=$app-$size-iter-$i -N2 -n 16 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /build/osu/build.openmpi/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj /tmp/out.cali |& tee ./results/osu-allreduce/caliper/cali-query-Gj-$i-$j.out
  singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -T /tmp/out.cali  |& tee ./results/osu-allreduce/caliper/cali-query-T-$i-$j.out
  mv /tmp/out.cali ./results/osu-allreduce/caliper/cali-$i.out

  # With trace
  export CALI_CONFIG=trace.mpi,event-trace
  flux run --setattr=user.study_id=$app-$size-iter-$i -N2 -n 16 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task singularity exec --pwd /tmp --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-caliper-test.sif /build/osu/build.openmpi/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  mkdir -p ./results/osu-allreduce/caliper/trace-$i/
  for filename in $(ls /tmp/*.cali)
    do
       identifier=$(basename $filename).result
       mkdir -p ./results/osu-allreduce/caliper/trace-$i/$identifier/
       singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -Gj $filename |& tee ./results/osu-allreduce/caliper/trace-$i/$identifier/cali-query-trace-Gj.out
       # Note that this freezes
       # singularity exec /opt/containers/google-performance-study_osu-caliper-test.sif cali-query -T $filename |& tee ./results/osu-allreduce/caliper/trace-$i/$identifier/cali-query-trace-T.out
  done       
  mv /tmp/*.cali ./results/osu-allreduce/caliper/trace-$i/
done

bash ./save.sh ./results/osu-allreduce/caliper
flux job purge --force --age-limit=0
```

Test on host?

```bash
time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$size-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task /opt/osu-benchmark/build.openmpi/mpi/pt2pt/osu_latency
```
With multiple tests, there isn't much difference.

```bash
mkdir -p ./results/osu-latency/no-caliper
bash flux-run-combinations.sh 2 osu-latency
bash ./save.sh ./results/osu-latency/no-caliper
flux job purge --force --age-limit=0

mkdir -p ./results/osu-allreduce/no-caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  time flux run --setattr=user.study_id=$app-$size-iter-$i -N2 -n 16 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task singularity exec --bind /run/flux:/run/flux /opt/containers/google-performance-study_osu-test.sif /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
done

bash ./save.sh ./results/osu-allreduce/no-caliper
flux job purge --force --age-limit=0
```

When they are done:

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-$size-osu-latency ./results/osu-latency
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-$size-osu-allreduce ./results/osu-allreduce
```

Testing:

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-$size-test ./results/
```

### Clean up

When you are done, exit and:

```bash
export GOOGLE_PROJECT=myproject
make destroy
```
