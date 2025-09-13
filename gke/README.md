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
  --machine-type=c4d-standard-16 \
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
  --machine-type=c4-standard-64 \
  --project=llnl-flux
```


Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
