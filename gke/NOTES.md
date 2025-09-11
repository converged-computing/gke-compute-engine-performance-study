# Performance Study Follow Up

> Understanding Kubernetes Overhead

We would first need to design a GKE and Compute Engine setup that are as identical as possible. I've done this before, and would primarily want to use updated Flux versions and OSes. For GKE, I think we should still use their Container optimized OS. We would want to use compact placement, TIER 1 networking, and a Titanium enabled instance type.

For applications, I think we should choose 3. One that is CPU bound, one that is I/O bound, and one that is network bound. Probably all of them are network bound so the third could be OSU. What we would want to do is start with basic runs, as we've done before, 10x each, and then compare the means to look for differences. The difference with this study is we would dive in. For networking, since Google isn't doing any bypass techniques we will have a rich set of tooling with eBPF. We can just use bpftrace and similar to watch packets at different spots. This could actually be very fun (and we would learn a lot both about eBPF performance monitoring and Kubernetes components).

## My hypotheses:

- Network: Is subject to the onion problem: This is a very terribly named issue I came up with working in Usernetes. We could remove just about all clear sources of issue, and yet there is stilll some overhead. My hypothesis is that the overhead results just from the packets having to travel through more layers. E.g., the GKE CNI (calico or GKE Dataplane V2) would add several layers of processing (iptables rules, eBPF programs, encapsulation) to every single packet! How could that not add overhead? We could likely do tracing between components to see this.
- CPU: What I've noticed in our eBPF + Flux Operator experiments, where I was able to see everything running on a node, is that there is a TON of stuff. The kubelet, containerd, kube-proxy, constant monitoring checks or agents, metrics, and fluent-bit are constantly running. These are consuming CPU cycles (and interactions with the kernel) that I can't imagine don't add something. I think this might be a variant of the noisy neighbor problem.
- I/O: I'm less interested in I/O but I think we could do it for Hari. My hypothesis is that even when you use the node local storage (via a CSI) you are subject to more layers. This would be another case where we could use eBPF to compare side by side.
If we do the above right, the actual costs of the experiments will be fairly low because most of our eBPF and benchmark learning will be done on single nodes. If we need to do a larger benchmark run, we will have it automated and quick.

- Instruction counts (caliper, thicket, etc)
- Cache misses
- Cloud metal instances to get performance counters
- Start with OSU and then move to Kripke

### Vanessa To do:
- Bare metal instance setups for GKE and Compute Engine
- Instrument apps with caliper thicket
- Basic tests
  - Instance types (CPU) - 256 (based on cost)
  - Metal prices for instances in the c family that support Titanium (and not H3, which doesn't scale well). Notably, metal means we get the whole machine so we pay the largest price.

```console
c4-standard-288-metal, $14.23224 / 1 hour (144 cores)
c4d-standard-384-metal, $17.927351808 / 1 hour (192 cores)
c3-standard-192-metal, $9.677184 / 1 hour (96 cores)
```

We are likely going to need to do smaller scale, but the nodes are larger. I think.

## Cluster Testing

My notes for the planning are [here](NOTES.md). Let's test creating a bare metal instance with the c3 type, which we have some quota for.

I first confirmed the c3 type metal does not work in Kubernetes:

```bash
gcloud container clusters create hpc-metal-cluster \
  --region us-central1 \
  --machine-type c3-standard-192-metal \
  --num-nodes 1 \
  --release-channel "regular" \
  --image-type "UBUNTU_CONTAINERD" \
  --metadata=disable-legacy-endpoints=true \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --no-enable-shielded-nodes \
  --enable-ip-alias
```
```
ERROR: (gcloud.container.clusters.create) ResponseError: code=400, message=C3 Bare Metal machine type is not supported.
```

But I am reading PMU is [supported for c4](https://cloud.google.com/kubernetes-engine/docs/how-to/analyzing-cpu-performance-using-pmu). Let's test for a smaller instance type and see if we are allowed to do that:

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 1 \
  --image-type "UBUNTU_CONTAINERD" \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-16 \
  --project=llnl-flux
```

- If I do `enhanced` it isn't supported on a smaller instance type. If I do `standard` it does seem to be!
To shell in, get the node name with `kubectl get nodes -o wide` then do `gcloud compute ssh <node>`. See the counters:

```bash
$ sudo dmesg |grep -A10 -i "Performance"
[    0.588495] Performance Events: Sapphire Rapids events, full-width counters, Intel PMU driver.
[    0.589484] core: CPUID marked event: 'cache references' unavailable
[    0.590483] core: CPUID marked event: 'cache misses' unavailable
[    0.591486] ... version:                2
[    0.592483] ... bit width:              48
[    0.593483] ... generic registers:      8
[    0.594483] ... value mask:             0000ffffffffffff
[    0.595483] ... max period:             00007fffffffffff
[    0.596484] ... fixed-purpose events:   4
[    0.597484] ... event mask:             0000000f000000ff
[    0.598567] signal: max sigframe size: 11952
```

Here is lscpu:

```console
Architecture:                x86_64
  CPU op-mode(s):            32-bit, 64-bit
  Address sizes:             52 bits physical, 57 bits virtual
  Byte Order:                Little Endian
CPU(s):                      16
  On-line CPU(s) list:       0-15
Vendor ID:                   GenuineIntel
  Model name:                INTEL(R) XEON(R) PLATINUM 8581C CPU @ 2.30GHz
    CPU family:              6
    Model:                   207
    Thread(s) per core:      2
    Core(s) per socket:      8
    Socket(s):               1
    Stepping:                2
    BogoMIPS:                4600.00
    Flags:                   fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ss ht syscall nx pdpe1gb rdtscp lm consta
                             nt_tsc arch_perfmon rep_good nopl xtopology nonstop_tsc cpuid tsc_known_freq pni pclmulqdq monitor ssse3 fma cx16 pdcm pcid sse4_1 sse4_2 x
                             2apic movbe popcnt aes xsave avx f16c rdrand hypervisor lahf_lm abm 3dnowprefetch ssbd ibrs ibpb stibp ibrs_enhanced fsgsbase tsc_adjust bm
                             i1 hle avx2 smep bmi2 erms invpcid rtm avx512f avx512dq rdseed adx smap avx512ifma clflushopt clwb avx512cd sha_ni avx512bw avx512vl xsaveo
                             pt xsavec xgetbv1 xsaves avx_vnni avx512_bf16 wbnoinvd arat avx512vbmi umip avx512_vbmi2 gfni vaes vpclmulqdq avx512_vnni avx512_bitalg avx
                             512_vpopcntdq rdpid cldemote movdiri movdir64b fsrm md_clear serialize tsxldtrk amx_bf16 avx512_fp16 amx_tile amx_int8 arch_capabilities
Virtualization features:     
  Hypervisor vendor:         KVM
  Virtualization type:       full
Caches (sum of all):         
  L1d:                       384 KiB (8 instances)
  L1i:                       256 KiB (8 instances)
  L2:                        16 MiB (8 instances)
  L3:                        260 MiB (1 instance)
NUMA:                        
  NUMA node(s):              1
  NUMA node0 CPU(s):         0-15
Vulnerabilities:             
  Gather data sampling:      Not affected
  Indirect target selection: Mitigation; Aligned branch/return thunks
  Itlb multihit:             Not affected
  L1tf:                      Not affected
  Mds:                       Not affected
  Meltdown:                  Not affected
  Mmio stale data:           Not affected
  Reg file data sampling:    Not affected
  Retbleed:                  Not affected
  Spec rstack overflow:      Not affected
  Spec store bypass:         Mitigation; Speculative Store Bypass disabled via prctl
  Spectre v1:                Mitigation; usercopy/swapgs barriers and __user pointer sanitization
  Spectre v2:                Mitigation; Enhanced / Automatic IBRS; IBPB disabled; PBRSB-eIBRS SW sequence; BHI SW loop, KVM SW loop
  Srbds:                     Not affected
  Tsx async abort:           Not affected
```

nproc is 16. 

```bash
$ lspci 
00:00.0 Host bridge: Intel Corporation 440FX - 82441FX PMC [Natoma] (rev 02)
00:01.0 ISA bridge: Intel Corporation 82371AB/EB/MB PIIX4 ISA (rev 03)
00:01.3 Bridge: Intel Corporation 82371AB/EB/MB PIIX4 ACPI (rev 03)
00:03.0 Ethernet controller: Google, Inc. Compute Engine Virtual Ethernet [gVNIC]
00:04.0 Unclassified device [00ff]: Red Hat, Inc. Virtio RNG
00:05.0 PCI bridge: Google, Inc. Device 0f48
01:00.0 PCI bridge: Google, Inc. Device 0f48
02:00.0 PCI bridge: Google, Inc. Device 0f48
02:01.0 PCI bridge: Google, Inc. Device 0f48
02:02.0 PCI bridge: Google, Inc. Device 0f48
02:03.0 PCI bridge: Google, Inc. Device 0f48
02:04.0 PCI bridge: Google, Inc. Device 0f48
02:05.0 PCI bridge: Google, Inc. Device 0f48
02:06.0 PCI bridge: Google, Inc. Device 0f48
02:07.0 PCI bridge: Google, Inc. Device 0f48
02:08.0 PCI bridge: Google, Inc. Device 0f48
02:09.0 PCI bridge: Google, Inc. Device 0f48
02:0a.0 PCI bridge: Google, Inc. Device 0f48
02:0b.0 PCI bridge: Google, Inc. Device 0f48
02:0c.0 PCI bridge: Google, Inc. Device 0f48
02:0d.0 PCI bridge: Google, Inc. Device 0f48
02:0e.0 PCI bridge: Google, Inc. Device 0f48
02:0f.0 PCI bridge: Google, Inc. Device 0f48
02:10.0 PCI bridge: Google, Inc. Device 0f48
02:11.0 PCI bridge: Google, Inc. Device 0f48
02:12.0 PCI bridge: Google, Inc. Device 0f48
02:13.0 PCI bridge: Google, Inc. Device 0f48
02:14.0 PCI bridge: Google, Inc. Device 0f48
02:15.0 PCI bridge: Google, Inc. Device 0f48
02:16.0 PCI bridge: Google, Inc. Device 0f48
02:17.0 PCI bridge: Google, Inc. Device 0f48
02:18.0 PCI bridge: Google, Inc. Device 0f48
02:19.0 PCI bridge: Google, Inc. Device 0f48
02:1a.0 PCI bridge: Google, Inc. Device 0f48
02:1b.0 PCI bridge: Google, Inc. Device 0f48
02:1c.0 PCI bridge: Google, Inc. Device 0f48
02:1d.0 PCI bridge: Google, Inc. Device 0f48
02:1e.0 PCI bridge: Google, Inc. Device 0f48
02:1f.0 PCI bridge: Google, Inc. Device 0f48
03:00.0 Non-Volatile memory controller: Google, Inc. NVMe device (rev 01)
```

lsmod

```bash
Module                  Size  Used by
xt_statistic           12288  2
veth                   36864  0
xt_nfacct              12288  1
xt_nat                 12288  8
xt_mark                12288  4
nfnetlink_acct         12288  2 xt_nfacct
bfq                   102400  1
xt_CT                  12288  2
nft_chain_nat          12288  6
xt_MASQUERADE          12288  3
nf_nat                 53248  3 xt_nat,nft_chain_nat,xt_MASQUERADE
xt_addrtype            12288  3
nft_compat             20480  143
nf_tables             348160  549 nft_compat,nft_chain_nat
crc32c_intel           16384  4
aesni_intel           360448  0
crypto_simd            16384  1 aesni_intel
gve                   126976  0
cryptd                 28672  1 crypto_simd
vfio_pci               12288  0
vfio_pci_core          73728  1 vfio_pci
vfio_iommu_type1       40960  0
vfio                   53248  3 vfio_pci_core,vfio_iommu_type1,vfio_pci
irqbypass              12288  1 vfio_pci_core
fuse                  184320  1
```

To clean up:

```bash
gcloud container clusters delete pmu-cluster --region us-central1-a --quiet
```

Before we test the daemonset, let's test the largest instance to see if we can do enhanced.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 1 \
  --image-type "UBUNTU_CONTAINERD" \
  --performance-monitoring-unit=enhanced \
  --machine-type=c4-standard-288 \
  --project=llnl-flux
```

Yes, that works!

```bash
sudo dmesg |grep -A10 -i "Performance"
[    8.008544] Performance Events: Granite Rapids events, full-width counters, Intel PMU driver.
[    8.009537] ... version:                2
[    8.010535] ... bit width:              48
[    8.011535] ... generic registers:      8
[    8.012535] ... value mask:             0000ffffffffffff
[    8.013542] ... max period:             00007fffffffffff
[    8.014535] ... fixed-purpose events:   4
[    8.015535] ... event mask:             0001000f000000ff
[    8.016834] signal: max sigframe size: 11952
[    8.018540] rcu: Hierarchical SRCU implementation.
[    8.019535] rcu: 	Max phase no-delay instances is 400.
```
```
lscpu
Architecture:             x86_64
  CPU op-mode(s):         32-bit, 64-bit
  Address sizes:          52 bits physical, 57 bits virtual
  Byte Order:             Little Endian
CPU(s):                   288
  On-line CPU(s) list:    0-287
Vendor ID:                GenuineIntel
  Model name:             Intel(R) Xeon(R) 6985P-C CPU @ 2.30GHz
    CPU family:           6
    Model:                173
    Thread(s) per core:   2
    Core(s) per socket:   72
    Socket(s):            2
    Stepping:             1
    BogoMIPS:             4600.00
    Flags:                fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ss ht syscall nx pdpe1gb rdts
                          cp lm constant_tsc arch_perfmon rep_good nopl xtopology nonstop_tsc cpuid aperfmperf tsc_known_freq pni pclmulqdq monitor ssse3
                           fma cx16 pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt aes xsave avx f16c rdrand hypervisor lahf_lm abm 3dnowprefetch ssbd ibrs 
                          ibpb stibp ibrs_enhanced fsgsbase tsc_adjust bmi1 hle avx2 smep bmi2 erms invpcid rtm avx512f avx512dq rdseed adx smap avx512if
                          ma clflushopt clwb avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves avx_vnni avx512_bf16 wbnoinvd arat avx512vb
                          mi umip pku ospke waitpkg avx512_vbmi2 gfni vaes vpclmulqdq avx512_vnni avx512_bitalg avx512_vpopcntdq la57 rdpid bus_lock_dete
                          ct cldemote movdiri movdir64b fsrm md_clear serialize tsxldtrk amx_bf16 avx512_fp16 amx_tile amx_int8 flush_l1d arch_capabiliti
                          es
Virtualization features:  
  Hypervisor vendor:      KVM
  Virtualization type:    full
Caches (sum of all):      
  L1d:                    6.8 MiB (144 instances)
  L1i:                    9 MiB (144 instances)
  L2:                     288 MiB (144 instances)
  L3:                     1008 MiB (2 instances)
NUMA:                     
  NUMA node(s):           6
  NUMA node0 CPU(s):      0-23,144-167
  NUMA node1 CPU(s):      24-47,168-191
  NUMA node2 CPU(s):      48-71,192-215
  NUMA node3 CPU(s):      72-95,216-239
  NUMA node4 CPU(s):      96-119,240-263
  NUMA node5 CPU(s):      120-143,264-287
Vulnerabilities:          
  Gather data sampling:   Not affected
  Itlb multihit:          Not affected
  L1tf:                   Not affected
  Mds:                    Not affected
  Meltdown:               Not affected
  Mmio stale data:        Not affected
  Reg file data sampling: Not affected
  Retbleed:               Not affected
  Spec rstack overflow:   Not affected
  Spec store bypass:      Mitigation; Speculative Store Bypass disabled via prctl
  Spectre v1:             Mitigation; usercopy/swapgs barriers and __user pointer sanitization
  Spectre v2:             Mitigation; Enhanced / Automatic IBRS; IBPB conditional; RSB filling; PBRSB-eIBRS SW sequence; BHI BHI_DIS_S
  Srbds:                  Not affected
  Tsx async abort:        Not affected
```
```
$ lspci
00:00.0 Host bridge: Intel Corporation 440FX - 82441FX PMC [Natoma] (rev 02)
00:01.0 ISA bridge: Intel Corporation 82371AB/EB/MB PIIX4 ISA (rev 03)
00:01.3 Bridge: Intel Corporation 82371AB/EB/MB PIIX4 ACPI (rev 03)
00:03.0 Ethernet controller: Google, Inc. Compute Engine Virtual Ethernet [gVNIC]
00:04.0 Unclassified device [00ff]: Red Hat, Inc. Virtio RNG
00:05.0 PCI bridge: Google, Inc. Device 0f48
00:06.0 PCI bridge: Google, Inc. Device 0f48
00:07.0 PCI bridge: Google, Inc. Device 0f48
00:08.0 PCI bridge: Google, Inc. Device 0f48
01:00.0 PCI bridge: Google, Inc. Device 0f48
02:00.0 PCI bridge: Google, Inc. Device 0f48
02:01.0 PCI bridge: Google, Inc. Device 0f48
02:02.0 PCI bridge: Google, Inc. Device 0f48
02:03.0 PCI bridge: Google, Inc. Device 0f48
02:04.0 PCI bridge: Google, Inc. Device 0f48
02:05.0 PCI bridge: Google, Inc. Device 0f48
02:06.0 PCI bridge: Google, Inc. Device 0f48
02:07.0 PCI bridge: Google, Inc. Device 0f48
02:08.0 PCI bridge: Google, Inc. Device 0f48
02:09.0 PCI bridge: Google, Inc. Device 0f48
02:0a.0 PCI bridge: Google, Inc. Device 0f48
02:0b.0 PCI bridge: Google, Inc. Device 0f48
02:0c.0 PCI bridge: Google, Inc. Device 0f48
02:0d.0 PCI bridge: Google, Inc. Device 0f48
02:0e.0 PCI bridge: Google, Inc. Device 0f48
02:0f.0 PCI bridge: Google, Inc. Device 0f48
02:10.0 PCI bridge: Google, Inc. Device 0f48
02:11.0 PCI bridge: Google, Inc. Device 0f48
02:12.0 PCI bridge: Google, Inc. Device 0f48
02:13.0 PCI bridge: Google, Inc. Device 0f48
02:14.0 PCI bridge: Google, Inc. Device 0f48
02:15.0 PCI bridge: Google, Inc. Device 0f48
02:16.0 PCI bridge: Google, Inc. Device 0f48
02:17.0 PCI bridge: Google, Inc. Device 0f48
02:18.0 PCI bridge: Google, Inc. Device 0f48
02:19.0 PCI bridge: Google, Inc. Device 0f48
02:1a.0 PCI bridge: Google, Inc. Device 0f48
02:1b.0 PCI bridge: Google, Inc. Device 0f48
02:1c.0 PCI bridge: Google, Inc. Device 0f48
02:1d.0 PCI bridge: Google, Inc. Device 0f48
02:1e.0 PCI bridge: Google, Inc. Device 0f48
02:1f.0 PCI bridge: Google, Inc. Device 0f48
03:00.0 Non-Volatile memory controller: Google, Inc. NVMe device (rev 01)
23:00.0 PCI bridge: Google, Inc. Device 0f48
24:00.0 PCI bridge: Google, Inc. Device 0f48
24:01.0 PCI bridge: Google, Inc. Device 0f48
24:02.0 PCI bridge: Google, Inc. Device 0f48
24:03.0 PCI bridge: Google, Inc. Device 0f48
24:04.0 PCI bridge: Google, Inc. Device 0f48
24:05.0 PCI bridge: Google, Inc. Device 0f48
24:06.0 PCI bridge: Google, Inc. Device 0f48
24:07.0 PCI bridge: Google, Inc. Device 0f48
24:08.0 PCI bridge: Google, Inc. Device 0f48
24:09.0 PCI bridge: Google, Inc. Device 0f48
24:0a.0 PCI bridge: Google, Inc. Device 0f48
24:0b.0 PCI bridge: Google, Inc. Device 0f48
24:0c.0 PCI bridge: Google, Inc. Device 0f48
24:0d.0 PCI bridge: Google, Inc. Device 0f48
24:0e.0 PCI bridge: Google, Inc. Device 0f48
24:0f.0 PCI bridge: Google, Inc. Device 0f48
24:10.0 PCI bridge: Google, Inc. Device 0f48
24:11.0 PCI bridge: Google, Inc. Device 0f48
24:12.0 PCI bridge: Google, Inc. Device 0f48
24:13.0 PCI bridge: Google, Inc. Device 0f48
24:14.0 PCI bridge: Google, Inc. Device 0f48
24:15.0 PCI bridge: Google, Inc. Device 0f48
24:16.0 PCI bridge: Google, Inc. Device 0f48
24:17.0 PCI bridge: Google, Inc. Device 0f48
24:18.0 PCI bridge: Google, Inc. Device 0f48
24:19.0 PCI bridge: Google, Inc. Device 0f48
24:1a.0 PCI bridge: Google, Inc. Device 0f48
24:1b.0 PCI bridge: Google, Inc. Device 0f48
24:1c.0 PCI bridge: Google, Inc. Device 0f48
24:1d.0 PCI bridge: Google, Inc. Device 0f48
24:1e.0 PCI bridge: Google, Inc. Device 0f48
24:1f.0 PCI bridge: Google, Inc. Device 0f48
45:00.0 PCI bridge: Google, Inc. Device 0f48
46:00.0 PCI bridge: Google, Inc. Device 0f48
46:01.0 PCI bridge: Google, Inc. Device 0f48
46:02.0 PCI bridge: Google, Inc. Device 0f48
46:03.0 PCI bridge: Google, Inc. Device 0f48
46:04.0 PCI bridge: Google, Inc. Device 0f48
46:05.0 PCI bridge: Google, Inc. Device 0f48
46:06.0 PCI bridge: Google, Inc. Device 0f48
46:07.0 PCI bridge: Google, Inc. Device 0f48
46:08.0 PCI bridge: Google, Inc. Device 0f48
46:09.0 PCI bridge: Google, Inc. Device 0f48
46:0a.0 PCI bridge: Google, Inc. Device 0f48
46:0b.0 PCI bridge: Google, Inc. Device 0f48
46:0c.0 PCI bridge: Google, Inc. Device 0f48
46:0d.0 PCI bridge: Google, Inc. Device 0f48
46:0e.0 PCI bridge: Google, Inc. Device 0f48
46:0f.0 PCI bridge: Google, Inc. Device 0f48
46:10.0 PCI bridge: Google, Inc. Device 0f48
46:11.0 PCI bridge: Google, Inc. Device 0f48
46:12.0 PCI bridge: Google, Inc. Device 0f48
46:13.0 PCI bridge: Google, Inc. Device 0f48
46:14.0 PCI bridge: Google, Inc. Device 0f48
46:15.0 PCI bridge: Google, Inc. Device 0f48
46:16.0 PCI bridge: Google, Inc. Device 0f48
46:17.0 PCI bridge: Google, Inc. Device 0f48
46:18.0 PCI bridge: Google, Inc. Device 0f48
46:19.0 PCI bridge: Google, Inc. Device 0f48
46:1a.0 PCI bridge: Google, Inc. Device 0f48
46:1b.0 PCI bridge: Google, Inc. Device 0f48
46:1c.0 PCI bridge: Google, Inc. Device 0f48
46:1d.0 PCI bridge: Google, Inc. Device 0f48
46:1e.0 PCI bridge: Google, Inc. Device 0f48
46:1f.0 PCI bridge: Google, Inc. Device 0f48
67:00.0 PCI bridge: Google, Inc. Device 0f48
68:00.0 PCI bridge: Google, Inc. Device 0f48
68:01.0 PCI bridge: Google, Inc. Device 0f48
68:02.0 PCI bridge: Google, Inc. Device 0f48
68:03.0 PCI bridge: Google, Inc. Device 0f48
68:04.0 PCI bridge: Google, Inc. Device 0f48
68:05.0 PCI bridge: Google, Inc. Device 0f48
68:06.0 PCI bridge: Google, Inc. Device 0f48
68:07.0 PCI bridge: Google, Inc. Device 0f48
68:08.0 PCI bridge: Google, Inc. Device 0f48
68:09.0 PCI bridge: Google, Inc. Device 0f48
68:0a.0 PCI bridge: Google, Inc. Device 0f48
68:0b.0 PCI bridge: Google, Inc. Device 0f48
68:0c.0 PCI bridge: Google, Inc. Device 0f48
68:0d.0 PCI bridge: Google, Inc. Device 0f48
68:0e.0 PCI bridge: Google, Inc. Device 0f48
68:0f.0 PCI bridge: Google, Inc. Device 0f48
68:10.0 PCI bridge: Google, Inc. Device 0f48
68:11.0 PCI bridge: Google, Inc. Device 0f48
68:12.0 PCI bridge: Google, Inc. Device 0f48
68:13.0 PCI bridge: Google, Inc. Device 0f48
68:14.0 PCI bridge: Google, Inc. Device 0f48
68:15.0 PCI bridge: Google, Inc. Device 0f48
68:16.0 PCI bridge: Google, Inc. Device 0f48
68:17.0 PCI bridge: Google, Inc. Device 0f48
68:18.0 PCI bridge: Google, Inc. Device 0f48
68:19.0 PCI bridge: Google, Inc. Device 0f48
68:1a.0 PCI bridge: Google, Inc. Device 0f48
68:1b.0 PCI bridge: Google, Inc. Device 0f48
68:1c.0 PCI bridge: Google, Inc. Device 0f48
68:1d.0 PCI bridge: Google, Inc. Device 0f48
68:1e.0 PCI bridge: Google, Inc. Device 0f48
68:1f.0 PCI bridge: Google, Inc. Device 0f48
```
```
$ lsmod
Module                  Size  Used by
tls                   155648  0
xt_statistic           12288  2
xt_nfacct              12288  1
veth                   45056  0
xt_nat                 12288  8
xt_mark                12288  4
ipt_REJECT             12288  2
nf_reject_ipv4         12288  1 ipt_REJECT
nfnetlink_acct         16384  2 xt_nfacct
xt_CT                  16384  2
xt_tcpudp              16384  8
xt_comment             12288  88
xt_conntrack           12288  18
nft_chain_nat          12288  6
xt_MASQUERADE          16384  3
nf_nat                 61440  3 xt_nat,nft_chain_nat,xt_MASQUERADE
xfrm_user              61440  1
xfrm_algo              16384  1 xfrm_user
xt_addrtype            12288  3
nft_compat             20480  139
nf_tables             376832  461 nft_compat,nft_chain_nat
br_netfilter           32768  0
bridge                421888  1 br_netfilter
overlay               212992  44
cfg80211             1347584  0
8021q                  45056  0
garp                   20480  1 8021q
mrp                    20480  1 8021q
stp                    12288  2 bridge,garp
llc                    16384  3 bridge,stp,garp
sunrpc                802816  1
binfmt_misc            24576  1
nls_iso8859_1          12288  1
skx_edac_common        24576  0
nfit                   81920  1 skx_edac_common
crct10dif_pclmul       12288  1
crc32_pclmul           12288  0
polyval_clmulni        12288  0
polyval_generic        12288  1 polyval_clmulni
ghash_clmulni_intel    16384  0
sha256_ssse3           32768  0
sha1_ssse3             32768  0
aesni_intel           356352  0
crypto_simd            16384  1 aesni_intel
cryptd                 24576  2 crypto_simd,ghash_clmulni_intel
psmouse               217088  0
pvpanic_mmio           12288  0
pvpanic                12288  1 pvpanic_mmio
i2c_piix4              32768  0
gve                   122880  0
input_leds             12288  0
mac_hid                12288  0
serio_raw              20480  0
sch_fq_codel           24576  17
dm_multipath           45056  0
vfio_pci               16384  0
vfio_pci_core          90112  1 vfio_pci
vfio_iommu_type1       49152  0
vfio                   69632  3 vfio_pci_core,vfio_iommu_type1,vfio_pci
iommufd                98304  1 vfio
irqbypass              12288  1 vfio_pci_core
nvme_fabrics           36864  0
efi_pstore             12288  0
dmi_sysfs              24576  0
virtio_rng             12288  0
ip_tables              32768  0
x_tables               65536  13 xt_conntrack,xt_statistic,nft_compat,xt_tcpudp,xt_addrtype,xt_nat,xt_comment,ipt_REJECT,xt_nfacct,xt_CT,ip_tables,xt_MASQUERADE,xt_mark
autofs4                57344  3
```

```
$ ip addr 
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute 
       valid_lft forever preferred_lft forever
2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc mq state UP group default qlen 1000
    link/ether 42:01:0a:80:00:1f brd ff:ff:ff:ff:ff:ff
    altname enp0s3
    inet 10.128.0.31/32 metric 100 scope global dynamic ens3
       valid_lft 85867sec preferred_lft 85867sec
    inet6 fe80::4001:aff:fe80:1f/64 scope link 
       valid_lft forever preferred_lft forever
3: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default 
    link/ether 02:42:10:37:59:97 brd ff:ff:ff:ff:ff:ff
    inet 169.254.123.1/24 brd 169.254.123.255 scope global docker0
       valid_lft forever preferred_lft forever
4: veth77a5c196@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether 56:c9:12:df:5b:eb brd ff:ff:ff:ff:ff:ff link-netns cni-48e8c1ba-7986-e114-2c2e-1920bf82205c
    inet 10.8.0.1/32 scope global veth77a5c196
       valid_lft forever preferred_lft forever
    inet6 fe80::54c9:12ff:fedf:5beb/64 scope link 
       valid_lft forever preferred_lft forever
5: veth32b75c09@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether 76:34:05:79:3a:63 brd ff:ff:ff:ff:ff:ff link-netns cni-9504104e-2124-6471-4b88-c485d1ae1d7e
    inet 10.8.0.1/32 scope global veth32b75c09
       valid_lft forever preferred_lft forever
    inet6 fe80::7434:5ff:fe79:3a63/64 scope link 
       valid_lft forever preferred_lft forever
6: veth52428fca@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether d2:ea:3f:01:8d:14 brd ff:ff:ff:ff:ff:ff link-netns cni-a3dc434b-abed-05c2-2294-369156ea51c6
    inet 10.8.0.1/32 scope global veth52428fca
       valid_lft forever preferred_lft forever
    inet6 fe80::d0ea:3fff:fe01:8d14/64 scope link 
       valid_lft forever preferred_lft forever
7: veth9eed17e9@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether b2:ab:85:67:59:ea brd ff:ff:ff:ff:ff:ff link-netns cni-192590ec-b9f8-4f89-10f1-4fe727894c6e
    inet 10.8.0.1/32 scope global veth9eed17e9
       valid_lft forever preferred_lft forever
    inet6 fe80::b0ab:85ff:fe67:59ea/64 scope link 
       valid_lft forever preferred_lft forever
8: veth440bcf07@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether 56:98:ff:2b:68:ed brd ff:ff:ff:ff:ff:ff link-netns cni-4b33df46-7569-3e82-86b5-64c81ba17157
    inet 10.8.0.1/32 scope global veth440bcf07
       valid_lft forever preferred_lft forever
    inet6 fe80::5498:ffff:fe2b:68ed/64 scope link 
       valid_lft forever preferred_lft forever
9: veth1ab2f886@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether 5a:0d:39:55:30:35 brd ff:ff:ff:ff:ff:ff link-netns cni-41b84c15-2c6a-c5be-c802-e83e144423a5
    inet 10.8.0.1/32 scope global veth1ab2f886
       valid_lft forever preferred_lft forever
    inet6 fe80::34ee:8aff:fe15:b616/64 scope link 
       valid_lft forever preferred_lft forever
11: veth60f1ab36@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether 9a:95:99:89:54:fa brd ff:ff:ff:ff:ff:ff link-netns cni-b40f7036-504b-0ab0-aca2-5b84af53fbe8
    inet 10.8.0.1/32 scope global veth60f1ab36
       valid_lft forever preferred_lft forever
    inet6 fe80::9895:99ff:fe89:54fa/64 scope link 
       valid_lft forever preferred_lft forever
12: veth5a47a246@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether aa:20:f8:09:c0:2e brd ff:ff:ff:ff:ff:ff link-netns cni-d14d7cfd-6bbe-23e8-85c5-dde09e048d53
    inet 10.8.0.1/32 scope global veth5a47a246
       valid_lft forever preferred_lft forever
    inet6 fe80::a820:f8ff:fe09:c02e/64 scope link 
       valid_lft forever preferred_lft forever
13: veth9c17b2a6@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether a6:18:57:f3:ee:fa brd ff:ff:ff:ff:ff:ff link-netns cni-16bec08c-fe9f-e215-249e-9305436a4c2a
    inet 10.8.0.1/32 scope global veth9c17b2a6
       valid_lft forever preferred_lft forever
    inet6 fe80::4aa:fbff:fe95:a2ee/64 scope link 
       valid_lft forever preferred_lft forever
14: vethf9d7ede4@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether f6:d2:a5:b9:b6:6a brd ff:ff:ff:ff:ff:ff link-netns cni-b69c15fc-4fa3-26a9-f59e-1231fec28963
    inet 10.8.0.1/32 scope global vethf9d7ede4
       valid_lft forever preferred_lft forever
    inet6 fe80::f4d2:a5ff:feb9:b66a/64 scope link 
       valid_lft forever preferred_lft forever
15: veth83365488@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460 qdisc noqueue state UP group default qlen 1000
    link/ether fa:6f:df:15:4e:c5 brd ff:ff:ff:ff:ff:ff link-netns cni-d8e2864b-41c3-9e80-3dbf-06e08ab8623a
    inet 10.8.0.1/32 scope global veth83365488
       valid_lft forever preferred_lft forever
    inet6 fe80::f86f:dfff:fe15:4ec5/64 scope link 
       valid_lft forever preferred_lft forever
```

Let's try the ContainerOS base to see if it comes with perf.

```bash
gcloud container clusters create pmu-cluster \
  --region=us-central1-a \
  --enable-ip-alias \
  --num-nodes 1 \
  --performance-monitoring-unit=standard \
  --machine-type=c4-standard-16 \
  --project=llnl-flux
```
