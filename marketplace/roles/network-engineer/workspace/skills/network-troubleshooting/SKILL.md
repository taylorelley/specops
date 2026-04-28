---
name: network-troubleshooting
description: "Systematic approaches to diagnosing connectivity issues, performance problems, and routing failures."
metadata: {"specialagent":{"emoji":"🔧","requires":{"bins":["ping","traceroute","ip","ss","tcpdump"]}}}
---

# Network Troubleshooting

Systematic approach to diagnosing and resolving network issues.

## OSI Layer Methodology

Work from Layer 1 up — most problems are at layers 1–4.

| Layer | Check |
|-------|-------|
| 1 Physical | Cable, SFP, interface up/down, LED |
| 2 Data Link | MAC learning, VLAN, STP, duplex/speed mismatch |
| 3 Network | IP address, subnet mask, routing table, ARP |
| 4 Transport | Port reachability, firewall rules, NAT |
| 5–7 Application | DNS resolution, TLS certificate, application config |

## Essential Diagnostic Commands

### Connectivity

```bash
# Basic reachability
ping -c 4 <destination>

# Trace path
traceroute <destination>
tracepath <destination>

# MTR (combined ping + traceroute)
mtr --report <destination>
```

### Routing

```bash
# Show routing table
ip route show
ip route get <destination>   # shows which route is used

# Show ARP table
ip neigh show

# Add a temporary route for testing
ip route add <network>/<prefix> via <gateway>
```

### Interface State

```bash
# List interfaces with state and IP
ip addr show
ip link show

# Interface statistics (errors, drops)
ip -s link show <interface>

# Detect duplex/speed mismatch
ethtool <interface>
```

### Port Connectivity

```bash
# Check if port is open (TCP)
nc -zv <host> <port>

# List listening sockets
ss -tuln

# Show all established connections
ss -tun

# Test UDP
nc -zuv <host> <port>
```

### DNS

```bash
# Query DNS record
dig <domain> A
dig <domain> AAAA
dig <domain> MX
dig @<nameserver> <domain>   # query specific DNS server

# Reverse lookup
dig -x <ip>

# Trace DNS delegation
dig +trace <domain>
```

### Packet Capture

```bash
# Capture on interface, save to file
tcpdump -i eth0 -w /tmp/capture.pcap

# Capture traffic to/from specific host
tcpdump -i eth0 host 10.0.10.5

# Capture specific port
tcpdump -i eth0 port 443

# Read capture file
tcpdump -r /tmp/capture.pcap -nn

# Capture ICMP
tcpdump -i eth0 icmp
```

## Common Issues and Fixes

### No connectivity at all
1. Check physical link (`ip link show` — state UP?)
2. Check IP address assigned (`ip addr show`)
3. Check default gateway (`ip route show default`)
4. Ping default gateway
5. Ping next hop / DNS server
6. Check firewall (`iptables -L -n` or `nft list ruleset`)

### Intermittent packet loss
1. Run `mtr --report` for 100+ cycles to spot patterns
2. Check interface error counters (`ip -s link show`)
3. Look for duplex mismatch (`ethtool`)
4. Check for oversubscription (high CPU/buffer on switch or router)
5. Check STP topology changes (flapping port causing MAC table flush)

### Routing loop / unreachable network
1. Check routing table on source host
2. Trace path (`traceroute`) — look for where packets stop
3. Verify routing protocol neighbours are up
4. Check for route redistribution misconfiguration
5. Inspect BGP/OSPF route attributes for unexpected values

### DNS failures
1. Check `/etc/resolv.conf` for correct nameserver entries
2. Query configured nameserver directly: `dig @<ns-ip> <domain>`
3. Check if nameserver is reachable: `ping <ns-ip>`
4. Check if port 53 is open on nameserver: `nc -zuv <ns-ip> 53`
5. Look for split-horizon or VLAN-specific DNS policy issues

## Escalation

If issue cannot be resolved at network layer:

- Server / OS issues → System Administrator
- Application-layer issues → Software Engineer or SRE
- Security-related blocking → Security Engineer
- ISP / upstream provider issues → Contact ISP with relevant traceroute and packet capture evidence
