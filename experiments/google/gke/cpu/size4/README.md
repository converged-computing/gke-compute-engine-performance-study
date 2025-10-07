# Google Performance Study

```console
# Instance choice is c4d-standard-96
# Go up to size 32 at least
# Let's start up to size 32, analyze, then go up.
```

This is technically round 3, to supplement the original [oerformance study](https://github.com/converged-computing/performance-study) and the follow up [ebpf study](https://github.com/converged-computing/google-performance-study).

## 4 Node Runs

Let's test our larger instance type of 4 nodes and compare between caliper vs. not.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 4 \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-96 \
  --project=llnl-flux

kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
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

### Kripke

```bash
kubectl apply -f crd/kripke-4.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash
```

You'll need to login to oras just once:

```bash
oras login ghcr.io --username vsoch
```

```console
mkdir -p ./results/kripke/no-caliper
app=kripke
size=4

# Without caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 4 -n 192 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 8,6,4 |& tee ./results/kripke/no-caliper/log-$i.out
done

bash ./save.sh ./results/kripke/no-caliper
flux job purge --force --age-limit=0
```
```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-kripke-no-caliper-1 ./results
```

# With caliper

```bash
kubectl apply -f crd/kripke-caliper-4.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash

mkdir -p ./results/kripke/caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,timeseries,timeseries.iteration_interval=1,timeseries.maxrows=500,mpi.message.count,mpi.message.size
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 4 -n 192 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 8,6,4 |& tee ./results/kripke/caliper/log-$i.out
  unset CALI_CONFIG

  sleep 3
  cali-query -Gj /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-Gj.out
  cali-query -T /tmp/out.cali  |& tee ./results/kripke/caliper/cali-query-$i-T.out
  mv /tmp/out.cali ./results/kripke/caliper/$i.cali
done

bash ./save.sh ./results/kripke/caliper
flux job purge --force --age-limit=0
```

```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-kripke-caliper-1 ./results
```

### OSU

```bash
# use this for both benchmarks
kubectl apply -f crd/osu-allreduce-4.yaml
kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash
```

Write this script to file:

```
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n 28 | tr '\n' ' ')
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
      -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
  done
done
```

And run:

```bash
mkdir -p ./results/osu-latency/no-caliper
bash run.sh 4 osu-latency
bash ./save.sh ./results/osu-latency/no-caliper
flux job purge --force --age-limit=0

mkdir -p ./results/osu-allreduce/no-caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  time flux run --setattr=user.study_id=$app-$size-iter-$i -N4 -n 192 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
done

bash ./save.sh ./results/osu-allreduce/no-caliper
flux job purge --force --age-limit=0
```

```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-osu-1 ./results
```

Now with caliper.

```bash
kubectl apply -f crd/osu-caliper.yaml
kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash

outdir=results/osu-latency
mkdir -p $outdir
mkdir -p /data
export CALI_LOG_VERBOSITY="2"
```

Write this to file.

```bash
#/bin/bash

nodes=$1
app=$2

# At most 28 combinations, N nodes 2 at a time
hosts=$(flux run -N $1 hostname | shuf -n 28 | tr '\n' ' ')
list=${hosts}

dequeue_from_list() {
  shift;
  list=$@
}

iter=0
# We can only see index / rank 0 filesystem
i=osu-0
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
      -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
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
      -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
    unset CALI_CONFIG
    sleep 3
    mkdir -p ./results/osu-latency/caliper/$i-$j
    mv *.cali ./results/osu-latency/caliper/$i-$j/
  done
```

Run:

```
mkdir -p ./results/osu-latency/caliper
bash ./caliper.sh 4 osu-latency

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
  flux run --setattr=user.study_id=$app-$size-iter-$i -N4 -n 192 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  cali-query -Gj /tmp/out.cali |& tee ./results/osu-allreduce/caliper/cali-query-Gj-$i.out
  cali-query -T /tmp/out.cali  |& tee ./results/osu-allreduce/caliper/cali-query-T-$i.out
  mv /tmp/out.cali ./results/osu-allreduce/caliper/cali-$i.out

  # With trace
  export CALI_CONFIG=trace.mpi,event-trace
  flux run --setattr=user.study_id=$app-$size-iter-$i -N4 -n 192 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  mkdir -p ./results/osu-allreduce/caliper/trace-$i/
  # Note that the query T freezes, so I'm just saving output
  mv *.cali ./results/osu-allreduce/caliper/trace-$i/
done

bash ./save.sh ./results/osu-allreduce/caliper
flux job purge --force --age-limit=0
```

Push oras

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

```bash
oras login ghcr.io
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-4-osu-3 ./results
```

Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
