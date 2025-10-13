# Redo of Caliper

We need to run with trace, and get data across pods.

Let's test our larger instance type of 4 nodes and compare between caliper vs. not.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 4 \
  --disk-size "500GB" \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-96 \
  --project=llnl-flux

kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
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

### Kripke

# Kripke with caliper

```bash
kubectl apply -f crd/kripke-caliper-4.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash

mkdir -p ./results/kripke/caliper
for i in $(seq 2 5); do     
  echo "Running iteration $i"
  flux exec -r all mkdir -p /opt/results/kripke/caliper/trace-${i}
  cd /opt/results/kripke/caliper/trace-$i/
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=trace.mpi,event-trace
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 4 -n 192 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 8,6,4 |& tee ../log-$i.out
  unset CALI_CONFIG
  cd -
done

bash save.sh 4 ./results/kripke
flux job purge --force --age-limit=0
```

### OSU

```bash
kubectl apply -f crd/osu-caliper.yaml
kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash
```

Write this to file.

```bash
export app=osu-allreduce
export CALI_LOG_VERBOSITY="2"
mkdir -p /opt/results/osu-allreduce/caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  flux exec -r all mkdir -p /opt/results/osu-allreduce/caliper/trace-$i/
  cd /opt/results/osu-allreduce/caliper/trace-$i/
  export CALI_CONFIG=trace.mpi,event-trace
  flux run --setattr=user.study_id=$app-$size-iter-$i -N4 -n 192 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ../log-$i.out
  unset CALI_CONFIG
  cd -
  sleep 3
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

Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
```bash
oras login ghcr.io
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-4-osu-caliper-trace-0 ./results
```

