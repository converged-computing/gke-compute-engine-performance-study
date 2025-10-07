# Google Performance Study 16 Node Runs

Let's test our larger instance type of 4 nodes and compare between caliper vs. not.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 16 \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-96 \
  --project=llnl-flux

kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

### Kripke

```bash
kubectl apply -f crd/kripke.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash
wget https://gist.githubusercontent.com/vsoch/2663e1e48f806fdca428ee5fa8db1c3d/raw/93f22aaf6423d3e29a7be41522b9c39058b0ba9d/save.sh
```

You'll need to login to oras just once:

```bash
oras login ghcr.io --username vsoch
```

```console
mkdir -p ./results/kripke/no-caliper
app=kripke
size=16

# Without caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  flux run --env OMP_NUM_THREADS=1 -o cpu-affinity=per-task --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 16 -n 768 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,6,8 |& tee ./results/kripke/no-caliper/log-$i.out
done

bash ./save.sh ./results/kripke/no-caliper
flux job purge --force --age-limit=0
```
```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-16-kripke-no-caliper ./results
kubectl delete -f crd/kripke.yaml
```

# With caliper

```bash
kubectl apply -f crd/kripke-caliper.yaml
flux proxy local:///mnt/flux/view/run/flux/local bash
wget https://gist.githubusercontent.com/vsoch/2663e1e48f806fdca428ee5fa8db1c3d/raw/93f22aaf6423d3e29a7be41522b9c39058b0ba9d/save.sh
app=kripke
size=16

mkdir -p ./results/kripke/caliper
for i in $(seq 1 5); do     
  echo "Running iteration $i"
  export CALI_LOG_VERBOSITY="2"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,timeseries,timeseries.iteration_interval=1,timeseries.maxrows=500,mpi.message.count,mpi.message.size
  flux run -o cpu-affinity=per-task --env OMP_NUM_THREADS=1 --env OMPI_MCA_btl_vader_single_copy_mechanism=none --setattr=user.study_id=$app-$size-iter-$i -N 16 -n 768 kripke --layout DGZ --dset 16 --gset 16 --groups 16 --niter 500 --legendre 2 --quad 16 --zones 256,192,128 --procs 16,6,8  |& tee ./results/kripke/caliper/log-$i.out
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
kubectl delete -f crd/kripke-caliper.yaml
```

### OSU

```bash
# use this for both benchmarks
kubectl apply -f crd/osu.yaml
kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash
wget https://gist.githubusercontent.com/vsoch/2663e1e48f806fdca428ee5fa8db1c3d/raw/93f22aaf6423d3e29a7be41522b9c39058b0ba9d/save.sh
```

Write this script to file:

```
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
      -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
  done
done
```

And run:

```bash
mkdir -p ./results/osu-latency/no-caliper
bash run.sh 16 osu-latency
bash ./save.sh ./results/osu-latency/no-caliper
flux job purge --force --age-limit=0

app=osu-allreduce
size=16
mkdir -p ./results/osu-allreduce/no-caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  time flux run --setattr=user.study_id=$app-$size-iter-$i -N 16 -n 768 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/no-caliper/log-$i.out
done

bash ./save.sh ./results/osu-allreduce/no-caliper
flux job purge --force --age-limit=0
```

```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-$size-osu ./results
kubectl delete -f crd/osu.yaml
```

Now with caliper.

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
kubectl apply -f crd/osu-caliper.yaml
kubectl exec -it osu-0-xxx -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash
wget https://gist.githubusercontent.com/vsoch/2663e1e48f806fdca428ee5fa8db1c3d/raw/93f22aaf6423d3e29a7be41522b9c39058b0ba9d/save.sh

outdir=results/osu-latency
mkdir -p $outdir
export CALI_LOG_VERBOSITY="2"
```

Write this to file.

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

```bash
mkdir -p ./results/osu-latency/caliper
bash ./caliper.sh 16 osu-latency

HERE
# Save results
bash ./save.sh ./results/osu-latency/caliper
flux job purge --force --age-limit=0
```

Now osu all reduce.

```bash
app=osu-allreduce
size=16
mkdir -p ./results/osu-allreduce/caliper
for i in $(seq 1 5); do 
  echo "Running iteration $i"
  export CALI_CONFIG=spot,output=/tmp/out.cali,profile.mpi,mpi.message.count,mpi.message.size
  flux run --setattr=user.study_id=$app-$size-iter-$i -N 16 -n 768 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/caliper/log-$i.out
  unset CALI_CONFIG
  sleep 3
  cali-query -Gj /tmp/out.cali |& tee ./results/osu-allreduce/caliper/cali-query-Gj-$i.out
  cali-query -T /tmp/out.cali  |& tee ./results/osu-allreduce/caliper/cali-query-T-$i.out
  mv /tmp/out.cali ./results/osu-allreduce/caliper/cali-$i.out

  # With trace
  export CALI_CONFIG=trace.mpi,event-trace
  flux run --setattr=user.study_id=$app-$size-iter-$i -N 16 -n 768 --env OMPI_MCA_btl_vader_single_copy_mechanism=none -o cpu-affinity=per-task /usr/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce |& tee ./results/osu-allreduce/caliper/log-$i.out
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

```bash
oras push ghcr.io/converged-computing/google-performance-study:gke-cpu-16-osu ./results
```

Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
