# Google Performance Study 2 Node Exploration

Let's explore the path a packet takes between nodes.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 2 \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-96 \
  --project=llnl-flux

kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

### Kripke

```bash
kubectl apply -f crd/kripke.yaml
# shell into lead broker pod
flux proxy local:///mnt/flux/view/run/flux/local bash
flux exec -r all /bin/bash -c "apt-get update && apt-get install -y iperf3 sockperf"
```

#### iperf3

```
# On pod 0/1:
iperf3 -s

# On machine-B (GCE VM or GKE Pod)
# Use the private IP of machine-A
iperf3 -c <ip_of_machine_A> -t 30
```

#### sockperf

ping-pong

```bash
# On machine-A
sockperf server

# On machine-B
# This measures latency for 30 seconds.
sockperf ping-pong -i <ip_of_machine_A> -t 30
```

And throughput

```bash
# On machine-A
sockperf server

# On machine-B
sockperf throughput -i <ip_of_machine_A> -t 30
```

#### 

Mount kernel debug in each pod.

```bash
mount -t debugfs none /sys/kernel/debug
echo 0 > /sys/kernel/debug/tracing/tracing_on
echo "function_graph" > /sys/kernel/debug/tracing/current_tracer
echo > /sys/kernel/debug/tracing/trace
#"vxlan_*" doesn't work, it's ok
echo "ip_*" "tcp_*" "udp_*" "br_*" "veth_*" > /sys/kernel/debug/tracing/set_graph_function

cd /sys/kernel/debug/tracing
echo 1 > tracing_on
sleep 10 # Trace for 10 seconds
echo 0 > tracing_on

# Save to file
cat /sys/kernel/debug/tracing/trace > ~/gke_packet_trace.log
```

I wrote a file to run instead (still with ping running from sender).

```bash
kubectl cp kripke-1-czwvv:/root/gke_packet_trace.log ./results/gke-packet-trace.log
```

We can also use kernelshark (this is from the same pod receiving the ping)

```bash
sudo apt-get install -y trace-cmd

trace-cmd record \
  -p function_graph \
  -g "ip_*" \
  -g "tcp_*" \
  -g "udp_*" \
  -g "veth_*" \
  -g "br_*" \
  sleep 10
```



Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```
