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
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-kripke-no-caliper ./results
```

# With caliper

```bash
kubectl apply -f crd/kripke-caliper-4.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash

mkdir -p ./results/kripke/caliper
for i in $(seq 2 5); do     
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
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-kripke-caliper ./results
```

### OSU

```bash
outdir=results/size-4/osu-latency
mkdir -p $outdir
for iter in $(seq 1 10)
  do
  kubectl apply -f crd/osu-latency.yaml
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
  sleep 5
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f  |& tee $outdir/$iter.out
  sleep 5
  kubectl delete -f crd/osu-latency.yaml  
done

outdir=results/size-4/osu-allreduce-4
mkdir -p $outdir
for iter in $(seq 1 10)
  do
  kubectl apply -f crd/osu-allreduce-4.yaml
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
  sleep 5
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f  |& tee $outdir/$iter.out
  sleep 5
  kubectl delete -f crd/osu-allreduce-4.yaml  
done

kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash

outdir=results/osu-latency
mkdir -p $outdir
mkdir -p /data
export CALI_LOG_VERBOSITY="2"

for iter in $(seq 1 10)
  do
  export CALI_CONFIG=spot,output=/data/out.cali,profile.mpi,mpi.message.count,mpi.message.size
  flux run -o cpu-affinity=per-task -N 2 -n 2 /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency > $outdir/log-$iter.out
  unset CALI_CONFIG
  sleep 3

  cali-query -Gj /data/out.cali > $outdir/cali-query-Gj-$iter.out
  cali-query -T /data/out.cali > $outdir/cali-query-T-$iter.out
  mv /data/out.cali $outdir/cali-$iter.out

#  export CALI_CONFIG=trace.mpi,event-trace,output=/data/out.cali
#  flux run -o cpu-affinity=per-task -N 2 -n 2 /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency > $outdir/log-trace-$iter.out
#  unset CALI_CONFIG
#  sleep 3
#  cali-query -Gj /data/out.cali > $outdir/cali-query-trace-Gj-$iter.out
#  cali-query -T /data/out.cali > $outdir/cali-query-trace-T-$iter.out
#  mv /data/out.cali $outdir/cali-trace-$iter.out
done

echo "OSU-ALLREDUCE"

outdir=results/osu-allreduce
mkdir -p $outdir

for iter in $(seq 1 10)
  do
  export CALI_CONFIG=spot,output=/data/out.cali,profile.mpi,mpi.message.count,mpi.message.size
  flux run -o cpu-affinity=per-task -N 4 -n 192 /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce  |& tee $outdir/log-$iter.out
  unset CALI_CONFIG
  sleep 3

  cali-query -Gj /data/out.cali > $outdir/cali-query-Gj-$iter.out
  cali-query -T /data/out.cali > $outdir/cali-query-T-$iter.out
  mv /data/out.cali $outdir/cali-$iter.out

  export CALI_CONFIG=trace.mpi,event-trace
  flux run -o cpu-affinity=per-task -N 4 -n 192 /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee $outdir/log-$iter-trace.out
  unset CALI_CONFIG
  sleep 3
  mkdir -p $outdir/$iter/
  mv *.cali $outdir/$iter/
done
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
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-4-osu-2 ./results
```

Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
