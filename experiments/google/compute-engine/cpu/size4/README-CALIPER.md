# "Bare Metal" on Compute Engine Size 4

We first tested this with Singularity, and caliper was inconsistent and then stopped working.

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
cd /mnt/share
sudo chown $(whoami) -R .
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

#### Kripke With caliper

```bash
mkdir -p /mnt/share/results/kripke/caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  mkdir -p /mnt/share/results/kripke/caliper/trace-${i}
  cd /mnt/share/results/kripke/caliper/trace-$i/
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=trace.mpi,event-trace
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 4 -n 192 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 8,6,4 |& tee ../log-$i.out
  unset CALI_CONFIG
  cd -
  sleep 3
done

bash ./save.sh ./results/kripke/caliper
flux job purge --force --age-limit=0
```

```bash
cd /mnt/share
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-kripke-4-trace-0 ./results/kripke/caliper/trace-1
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-kripke-4-trace-1 ./results/kripke/caliper/trace-2
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-kripke-4-trace-2 ./results/kripke/caliper/trace-3
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-kripke-4-trace-3 ./results/kripke/caliper/trace-4
```


#### OSU with caliper

Now osu all reduce.

```bash
mkdir -p /mnt/share/results/osu-allreduce/caliper
for i in $(seq 1 5); do 
  export CALI_CONFIG=trace.mpi,event-trace
  mkdir -p /mnt/share/results/osu-allreduce/caliper/trace-$i/
  cd /mnt/share/results/osu-allreduce/caliper/trace-$i/
  flux run --setattr=user.study_id=$app-$size-iter-$i -N4 -n 192 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task osu_allreduce |& tee ../log-$i.out
  unset CALI_CONFIG
  cd -  
done

bash ./save.sh ./results/osu-allreduce/caliper
flux job purge --force --age-limit=0
```

When they are done:

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-$size-redo ./results/
```

### Clean up

When you are done, exit and:

```bash
export GOOGLE_PROJECT=myproject
make destroy
```
