# Google Performance Study

## TODO Items

```
# osu add mpi report 
# what ebpf metrics?
# need to test size 4
# Instance choice is c4d-standard-96
# Do cost spec.
# Go up to size 32 at least
# Let's start up to size 32, analyze, then go up.
```

This is technically round 3, to supplement the original [oerformance study](https://github.com/converged-computing/performance-study) and the follow up [ebpf study](https://github.com/converged-computing/google-performance-study).

## Single Node Runs

Here we want to test that the applications execute (on small sizes) with caliper.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 1 \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-16 \
  --project=llnl-flux
```

Install the Flux Operator.

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

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

### Kripke

```bash
outdir=results/size-4/kripke
mkdir -p $outdir
for iter in $(seq 1 4)
  do
  kubectl apply -f crd/kripke-4.yaml
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=kripke --timeout=600s
  sleep 5
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f  |& tee $outdir/$iter.out
  sleep 5
  kubectl delete -f crd/kripke-4.yaml  
done

outdir=results/size-4/kripke-caliper
mkdir -p $outdir
for iter in $(seq 1 10)
  do
  kubectl apply -f crd/kripke-caliper-4.yaml
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=kripke --timeout=600s
  sleep 5
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f  |& tee $outdir/$iter.out
  sleep 5
  kubectl delete -f crd/kripke-caliper-4.yaml  
done
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

outdir=results/size-4/osu-caliper
mkdir -p $outdir
for iter in $(seq 1 10)
  do
  kubectl apply -f crd/osu-caliper.yaml
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
  sleep 5
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f  |& tee $outdir/$iter.out
  sleep 5
  kubectl delete -f crd/osu-caliper.yaml  
done
```



Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
