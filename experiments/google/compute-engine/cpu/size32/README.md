# "Bare Metal" on Compute Engine Size 32

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
mkdir -p ./results
```

For each experiment, we need to be instance owner. This also cleans up `flux jobs -a` so you get a clean slate.

```bash
sudo -i
```

You'll need to login to oras just once:

```bash
oras login ghcr.io --username vsoch
```

Save this script

```bash
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
size=32

# Without caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 32 -n 1536 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,12,8 |& tee ./results/kripke/no-caliper/log-$i.out
done

bash ./save.sh ./results/kripke/no-caliper
flux job purge --force --age-limit=0
```

# With caliper

```bash
mkdir -p ./results/kripke/caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,timeseries,timeseries.iteration_interval=1,timeseries.maxrows=500,mpi.message.count,mpi.message.size
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 32 -n 1536 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,12,8 |& tee ./results/kripke/caliper/log-$i.out
  unset CALI_CONFIG

  sleep 3
  cali-query -Gj /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-Gj.out
  cali-query -T /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-T.out
  mv /tmp/out.cali ./results/kripke/caliper/$i.cali
done

bash ./save.sh ./results/kripke/caliper
flux job purge --force --age-limit=0
```

#### OSU

Write this script to the filesystem `flux-run-combinations.sh`

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n 8 | tr '\n' ' ')
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
      -o cpu-affinity=per-task osu_latency 
  done
done
```

```bash
mkdir -p ./results/osu-latency/no-caliper
bash run.sh 32 osu-latency

bash ./save.sh ./results/osu-latency/no-caliper
flux job purge --force --age-limit=0

app=osu-allreduce
mkdir -p ./results/osu-allreduce/no-caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  time flux run --setattr=user.study_id=$app-$size-iter-$i -N 32 -n 1536 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
done

bash ./save.sh ./results/osu-allreduce/no-caliper
flux job purge --force --age-limit=0
```

Now with caliper

Write this script to the filesystem `flux-run-caliper.sh`

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n 8 | tr '\n' ' ')
list=${hosts}

dequeue_from_list() {
  shift;
  list=$@
}

iter=0
# We can only see index / rank 0 filesystem
i=flux-0
for j in $hosts; do
    if [[ "${i}" == "${j}" ]]; then
        continue
    fi
    export CALI_LOG_VERBOSITY="2"
    export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task osu_latency
    unset CALI_CONFIG
    sleep 3
    cali-query -Gj /tmp/out.cali |& tee ./results/osu-latency/caliper/cali-query-Gj-$i-$j.out
    cali-query -T /tmp/out.cali  |& tee ./results/osu-latency/caliper/cali-query-T-$i-$j.out
    mv /tmp/out.cali ./results/osu-latency/caliper/cali-$i-$j.out
    export CALI_CONFIG=trace.mpi,event-trace
    time flux run -N 2 -n 2 \
      --env OMPI_MCA_btl_vader_single_copy_mechanism=none \
      --setattr=user.study_id=$app-$nodes-iter-$iter \
      --requires="hosts:${i},${j}" \
      -o cpu-affinity=per-task osu_latency
    unset CALI_CONFIG
    sleep 3
    mkdir -p ./results/osu-latency/caliper/$i-$j
    mv *.cali ./results/osu-latency/caliper/$i-$j/
  done
```

pass definition of derivative of graph to convex optimizer (for neural networks)
come up with ways to sample that space that maybe wouldn't be deterministic but might come to solution.

Run:

```bash
mkdir -p ./results/osu-latency/caliper
bash ./caliper.sh 32 osu-latency

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
  flux run --setattr=user.study_id=$app-$size-iter-$i -N 32 -n 1536 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  cali-query -Gj /tmp/out.cali |& tee ./results/osu-allreduce/caliper/cali-query-Gj-$i.out
  cali-query -T /tmp/out.cali  |& tee ./results/osu-allreduce/caliper/cali-query-T-$i.out
  mv /tmp/out.cali ./results/osu-allreduce/caliper/cali-$i.out

  # With trace
  export CALI_CONFIG=trace.mpi,event-trace
  flux run --setattr=user.study_id=$app-$size-iter-$i -N 32 -n 1536 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  mkdir -p ./results/osu-allreduce/caliper/trace-$i/
  # Note that the query T freezes, so I'm just saving output
  mv *.cali ./results/osu-allreduce/caliper/trace-$i/
done

bash ./save.sh ./results/osu-allreduce/caliper
flux job purge --force --age-limit=0
```

When they are done:

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-32 ./results/
```

### Clean up

When you are done, exit and:

```bash
export GOOGLE_PROJECT=myproject
make destroy
```
