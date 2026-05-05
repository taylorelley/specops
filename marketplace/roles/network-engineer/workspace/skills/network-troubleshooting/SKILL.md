---
name: network-troubleshooting
description: "Layer-by-layer fault isolation: latency, loss, jitter, DNS, TLS, routing. Use during active network incidents and intermittent connectivity reports."
metadata: {"specialagent":{"emoji":"🧪"}}
---

# Network Troubleshooting

Isolate faults systematically. Network problems mimic application problems; jumping to a layer before ruling out the ones beneath wastes time.

## OSI Layered Triage

Work bottom-up unless evidence points elsewhere.

| Layer | Question | Quick check |
|-------|----------|-------------|
| **L1 — Physical** | Cable, port, link, optic | `ethtool eth0`, switch port status |
| **L2 — Link** | ARP, MAC table, VLAN | `ip neigh`, `bridge fdb`, switch CAM |
| **L3 — Network** | Reachability, routing, MTU | `ping`, `traceroute`, `ip route` |
| **L4 — Transport** | TCP / UDP, ports, retransmits | `ss -tan`, `nstat` |
| **L7 — Application** | DNS, TLS, HTTP | `dig`, `openssl s_client`, `curl -v` |

## Command Playbook

### Reachability & path

```bash
ping -c 5 -W 2 host.example.com           # baseline reachability
ping -M do -s 1472 host.example.com       # MTU probe (1500 - 28)
traceroute -n host.example.com            # path
mtr -nrwc 100 host.example.com            # path + loss + latency over time
ip route get 10.20.30.40                  # which route applies
```

### DNS

```bash
dig +trace host.example.com               # delegation chain
dig @1.1.1.1 host.example.com             # specific resolver
dig host.example.com +short               # quick answer
host -a host.example.com                  # all record types
```

If `dig +trace` works but the host's resolver doesn't, the problem is local resolver / search / split-horizon.

### TCP / sockets

```bash
ss -tan | head -50                        # connections by state
ss -tanpe                                 # add process / extended info
ss -i                                     # per-socket TCP info (rtt, retrans)
nstat -az | grep -i 'retrans\|drop'      # kernel-level counters
```

### Packet capture

```bash
# Headers only, ring buffer, rotated
tcpdump -i eth0 -nn -s 96 -W 5 -C 100 -w /tmp/cap.pcap host 10.20.30.40

# Specific flow
tcpdump -i eth0 -nn 'host 10.20.30.40 and port 443'
```

Capture etiquette:
- Capture as little as needed — small files analyse faster and contain less sensitive payload
- Filter at capture time, not in the analyser
- Snapshot length 96 bytes is enough for L3/L4 analysis without payloads
- Rotate (`-W`, `-C`) so a long capture doesn't fill the disk
- Move PCAPs to a controlled location; PCAPs can contain credentials

### TLS / HTTP

```bash
openssl s_client -connect host:443 -servername host -showcerts < /dev/null
curl -v --resolve host:443:10.20.30.40 https://host/path
```

## Latency vs Loss vs Jitter

| Symptom | Likely layer | Diagnose with |
|---------|--------------|---------------|
| **High latency, no loss** | L3 path or congestion | `mtr` (per-hop latency) |
| **Loss without latency change** | L1/L2 (errors), policer, firewall drops | Interface counters, `mtr` loss column |
| **High jitter** | Congestion, half-duplex mismatch | `mtr` interval timing, `ethtool` |
| **Intermittent reset** | L7 timeout, NAT idle, MSS mismatch | `tcpdump` with `-S` for absolute SEQ |
| **Connection succeeds, no data** | MTU / PMTUD black hole | MTU probe with `ping -M do -s` |

## Common Failure Patterns

- **Asymmetric routing** — Reply takes a different path than request; stateful firewall drops
- **MSS / MTU mismatch through tunnel** — Small packets fine, large stall (PMTUD broken)
- **DNS TTL too long** — Failover happened upstream but clients haven't refreshed
- **NAT idle timeout** — Long-lived idle TCP connections die; need keepalives
- **Firewall connection table full** — Random new-flow drops, existing flows fine
- **ARP / neighbour cache stale** — One host unreachable from one host, fine from others
- **Anycast flap** — Path changes mid-session, breaks stateful flows

## Working With Other Roles

- **System Administrator** — host-side networking (interface config, NetworkManager, systemd-networkd)
- **SRE** — service mesh, ingress controllers, cloud LB config
- **Security Engineer** — firewall rule changes, IDS/IPS interpretation
- **Root Cause Analyser** — preserve packet captures and counter snapshots as evidence

## Anti-Patterns

- Concluding "must be the network" before instrumentation rules out app and host
- Long-running unfiltered `tcpdump` on a busy interface (CPU + disk + privacy)
- Capturing only on one side of the conversation
- Restarting interfaces "to see if it helps" before capturing state
- Treating one ping test as proof of reachability (try several sizes, several destinations, over time)
