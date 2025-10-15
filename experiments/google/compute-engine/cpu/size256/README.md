# "Bare Metal" on Compute Engine Size 256

$1280/hour
up at 7:05pm
down at...

## Experiment

Bring up:

```bash
make
```

Shell in:

```bash
gcloud compute ssh fux-0 --zone us-central1-a --tunnel-through-iap
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
wget https://gist.githubusercontent.com/vsoch/2663e1e48f806fdca428ee5fa8db1c3d/raw/93f22aaf6423d3e29a7be41522b9c39058b0ba9d/save.sh
```

#### Kripke

```console
mkdir -p ./results/kripke/no-caliper
app=kripke
size=256

# Without caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 256 -n 12288 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,24,32 |& tee ./results/kripke/no-caliper/log-$i.out
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
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 256 -n 12288 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,24,32 |& tee ./results/kripke/caliper/log-$i.out
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

Now osu all reduce.

```bash
mkdir -p ./results/osu-allreduce/caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
  flux run --setattr=user.study_id=$app-$size-iter-$i -N 256 -n 12288 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task osu_allreduce |& tee ./results/osu-allreduce/caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  cali-query -Gj /tmp/out.cali |& tee ./results/osu-allreduce/caliper/cali-query-Gj-$i.out
  cali-query -T /tmp/out.cali  |& tee ./results/osu-allreduce/caliper/cali-query-T-$i.out
  mv /tmp/out.cali ./results/osu-allreduce/caliper/cali-$i.out
done

bash ./save.sh ./results/osu-allreduce/caliper
flux job purge --force --age-limit=0
```

When they are done:

```bash
oras push ghcr.io/converged-computing/google-performance-study:compute-engine-cpu-256 ./results/
```

### Clean up

When you are done, exit and:

```bash
export GOOGLE_PROJECT=myproject
make destroy
```
