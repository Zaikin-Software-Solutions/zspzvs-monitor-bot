# Hetzner Cloud Support Ticket — Network packet loss on Helsinki cloud1

**Category:** Cloud — Network issue
**Subject:** Persistent intermittent packet loss to VM 37.27.199.136 — likely upstream router issue

---

## Issue summary

Our VM `ubuntu-4gb-hel1-1` (IPv4 **37.27.199.136**, Hetzner Cloud HEL1) is experiencing **recurring incoming packet loss** of 16-71% on multiple windows during 2026-05-27. Loss is **symmetric and reproducible**, isolated to your network: traffic from peers reaches Hetzner edge fine, then drops between `core-spine-rdev2.cloud1.hel1.hetzner.com (213.239.228.10)` and our VM.

Outgoing traffic from our VM is also affected (asymmetric drops on `15328.your-cloud.host (95.216.134.154)` at 44-71%).

We have ruled out our own infrastructure: conntrack, firewall, xray, nginx, DNS — all healthy. The issue is isolated to Hetzner internal path. Status page does not list any HEL1 incident.

## Affected resource

- **VM:** `ubuntu-4gb-hel1-1`
- **IPv4:** 37.27.199.136
- **Datacenter:** HEL1, cloud1
- **Hypervisor reached via:** `core-spine-rdev2.cloud1.hel1.hetzner.com (213.239.228.10)` → `15328.your-cloud.host (95.216.134.154)`

## Timeline of incidents (all 2026-05-27 UTC)

| Window UTC | Duration | Loss observed | Source |
|---|---|---|---|
| 12:38 – 13:57 | ~80 min | 16-40% on hop 5 | Internal monitoring |
| 13:43 – 14:01 | ~18 min | 30-47% on hop 5 | Live MTR |
| 15:25 – 15:40 | ~15 min | 6.7% spinal + 100% on terminal hops | Live MTR |

Pattern: 15-90 minute windows of degraded packet loss recurring every 1-2 hours.

## MTR evidence

### mk1 (AS50340, Russia) → fd1 (37.27.199.136) — during 13:43 UTC incident

```
HOST: keri                                                               Loss%   Snt   Last   Avg
  1. AS50340  135.106.137.2                                               0.0%   100    0.3   0.7
  2. AS49505  92.53.95.25                                                 0.0%   100    0.4   1.8
  3. AS???    as24940.ix.dataix.eu (178.18.226.223)                       0.0%   100   16.7  21.6
  4. AS24940  core31.hel1.hetzner.com (213.239.224.38)                    0.0%   100   16.8  16.9
  5. AS24940  core-spine-rdev2.cloud1.hel1.hetzner.com (213.239.228.10) 30.0%   100   16.7  19.3
  6. AS???    ???                                                       100.0%  100    0.0   0.0
  7. AS???    ???                                                       100.0%  100    0.0   0.0
  8. AS24940  15328.your-cloud.host (95.216.134.154)                      0.0%   100   16.8  16.8
  9. AS???    ???                                                       100.0%  100    0.0   0.0
```

**Reverse MTR (fd1 → mk1)** showed 44-71% loss on hop 2 (your-cloud.host 95.216.134.154) symmetrically.

### TCP retransmission statistics from VM 37.27.199.136

```
TcpRetransSegs / TcpOutSegs = 408 774 / 16 301 468 = 2.51%
```

Normal baseline is <0.1%. Sustained 25x elevated TCP retransmits on outbound from our VM, consistent with loss in your fabric.

### Direct probes against neighboring Hetzner core routers

- `213.239.228.10` itself (when probed via alternative path): 0.0% loss → **the router is healthy**
- `95.216.134.154` (your-cloud.host) reachable: 0% loss when probed standalone
- Loss **only** materializes on the segment delivering traffic to **our specific VM 37.27.199.136**

This strongly suggests: noisy-neighbor on the same hypervisor, hypervisor packet-rate policing triggered by our workload, or a faulty NIC/cable on the specific compute host. **Not** a wide HEL1 outage (other Hetzner targets unaffected).

## Application impact

Each loss window correlates exactly with user-facing connection failures for our service. Sessions break, reconnects fail mid-handshake, retries succeed only after loss subsides.

## What we ask

Could you please:

1. **Check the hypervisor host** hosting VM 37.27.199.136 — look for:
   - CPU/network steal time
   - Noisy-neighbor (large outgoing flows from co-tenants)
   - NIC errors / driver issues
   - Any per-VM packet-rate limit being hit
2. **Migrate the VM to another compute host** if the current one is overloaded or faulty (Hetzner Cloud allows live migration AFAIK)
3. **Acknowledge whether this is a known issue** for the HEL1 cloud1 cluster

We have the VM running on `restart=always` so a brief migration outage is acceptable.

## Diagnostic data available on request

- Full MTR captures (3 directions × 3 timestamps each) — JSON
- 12-hour Prometheus `node_netstat_TcpRetransSegs` and `node_network_*` history
- Application-level latency probes showing the same drop pattern
- tcpdump capture (30 sec, 1242 packets) showing TCP RST and SACK retransmits

Please let us know if you need any of these attached.

Thanks for looking into this.
