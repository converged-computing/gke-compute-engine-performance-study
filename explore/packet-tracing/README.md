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

## Perf

We need to create a pod that shares a volume with the host, then do the same ping from the other pod to it.

```bash
apt-get install -y libdw-dev libelf-dev
```

We need to install deps from the profile pod (either via pod or on VM).
Then I tried a ping from one pod (or VM) TO a pod and did:

```bash
perf record -F 99 -a -g -- sleep 30
git clone https://github.com/brendangregg/FlameGraph.git /FlameGraph
perf script | /FlameGraph/stackcollapse-perf.pl | /FlameGraph/flamegraph.pl > gke_profile.svg
perf script | /FlameGraph/stackcollapse-perf.pl | /FlameGraph/flamegraph.pl > compute_engine_profile_ping.svg
```

Then I ran kripke, and perf from the performance pod.

```bash
flux run -N2 -n 96 kripke --procs 3,4,8 --zones 18,64,64 --niter 500

# Smaller testing size
flux run -N2 -n 16 kripke --procs 2,4,2 --zones 16,16,16 --niter 100

# From performance pod - perf and bpftrace
#  (captures most of run, not all of it)
mkdir kripke
cd kripke
perf record -F 99 -a -g -- sleep 80
perf script | /FlameGraph/stackcollapse-perf.pl | /FlameGraph/flamegraph.pl > ../compute_engine_profile_kripke.svg

perf record \
  -e net:net_dev_xmit \
  -e net:netif_receive_skb \
  -a -g -- \
  sleep 30
perf script > network_trace.log
```

Clean up

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a
```

## Analysis

```
# See the path of a packet for the report (gke)
python trace_packet_path.py results/gke/trace.report ip_rcv
python trace_packet_path.py results/compute-engine/trace.report ip_rcv

# See summary of timestamps (gke)
python parse_trace.py results/gke/trace.report 
python parse_trace.py results/compute-engine/trace.report 

Parsing 'results/trace.report'...
Parsing complete. Processed 490394 lines.

Function Profile Report (sorted by Self-Time)
Process Name     | Function Name                       |  Self-Time (ms) | Total Time (ms) |   Call Count
---------------------------------------------------------------------------------------------------------
proxy-agent      | __local_bh_enable_ip                |           0.429 |           0.868 |         2106
proxy-agent      | _raw_spin_unlock_bh                 |           0.404 |           0.764 |         1617
kubelet          | __local_bh_enable_ip                |           0.346 |           1.475 |         2068
kubelet          | __pv_queued_spin_lock_slowpath      |           0.318 |           0.318 |           30
kubelet          | save_fpregs_to_fpstate              |           0.250 |           0.250 |           13
kubelet          | nft_do_chain                        |           0.203 |           0.958 |          400
kubelet          | _raw_spin_unlock_bh                 |           0.201 |           0.350 |          800
proxy-agent      | is_vmalloc_addr                     |           0.199 |           0.411 |          403
kubelet          | psi_task_switch                     |           0.196 |           0.247 |           19
kubelet          | _raw_spin_lock_irqsave              |           0.190 |           1.002 |          691
kubelet          | schedule                            |           0.171 |           0.397 |            7
kubelet          | nft_immediate_eval                  |           0.170 |           0.784 |          584
kubelet          | nft_match_eval                      |           0.160 |           1.042 |          495
proxy-agent      | _raw_spin_lock_irqsave              |           0.157 |           0.526 |          379
kubelet          | _raw_spin_unlock_irqrestore         |           0.156 |           0.195 |          855
kubelet          | nft_counter_eval                    |           0.153 |           0.788 |          488
proxy-agent      | __virt_addr_valid                   |           0.149 |           0.149 |          372
proxy-agent      | tcp_release_cb                      |           0.142 |           0.287 |          439
kubelet          | enter_lazy_tlb                      |           0.139 |           0.327 |           20
kubelet          | dev_fetch_sw_netstats               |           0.138 |           0.138 |           69
proxy-agent      | nft_match_large_eval                |           0.136 |           2.335 |          271
kubelet          | dequeue_entity                      |           0.134 |           0.514 |           55
kubelet          | conntrack_mt_v3                     |           0.132 |           0.249 |          681
sidecar          | __local_bh_enable_ip                |           0.131 |           0.247 |          568
kubelet          | _raw_spin_lock                      |           0.131 |           0.557 |          466
kubelet          | kmem_cache_free                     |           0.126 |           0.171 |          424
kubelet          | should_failslab                     |           0.120 |           0.123 |          518
kubelet          | _raw_spin_lock_bh                   |           0.119 |           0.577 |          533
kubelet          | conntrack_mt                        |           0.117 |           0.117 |          681
proxy-agent      | __tcp_cleanup_rbuf                  |           0.116 |           0.119 |          475
proxy-agent      | dma_map_page_attrs                  |           0.115 |           0.162 |          233
sidecar          | pick_next_task_fair                 |           0.115 |           0.120 |            2
proxy-agent      | cgroup_rstat_updated                |           0.114 |           0.230 |          353
kubelet          | deactivate_task                     |           0.113 |           0.393 |           11
kubelet          | page_counter_cancel                 |           0.111 |           0.221 |          375
proxy-agent      | fib_table_lookup                    |           0.110 |           0.265 |          177
sidecar          | _raw_spin_lock_irqsave              |           0.106 |           0.585 |          276
proxy-agent      | tcp_stream_memory_free              |           0.106 |           0.106 |          273
proxy-agent      | should_failslab                     |           0.104 |           0.106 |          415
kubelet          | pick_next_task_fair                 |           0.102 |           0.160 |           19
```
