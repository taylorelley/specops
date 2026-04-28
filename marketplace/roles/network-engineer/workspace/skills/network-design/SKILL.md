---
name: network-design
description: "IP addressing, VLAN design, routing topology, and network architecture patterns for reliable and segmented networks."
metadata: {"specialagent":{"emoji":"🌐"}}
---

# Network Design

Principles and patterns for designing reliable, scalable, and secure networks.

## IP Addressing

### Subnetting Quick Reference

| CIDR | Subnet Mask | Hosts |
|------|-------------|-------|
| /24 | 255.255.255.0 | 254 |
| /25 | 255.255.255.128 | 126 |
| /26 | 255.255.255.192 | 62 |
| /27 | 255.255.255.224 | 30 |
| /28 | 255.255.255.240 | 14 |
| /29 | 255.255.255.248 | 6 |
| /30 | 255.255.255.252 | 2 (point-to-point links) |

### RFC 1918 Private Ranges

| Range | CIDR | Common Use |
|-------|------|-----------|
| 10.0.0.0 – 10.255.255.255 | 10.0.0.0/8 | Large enterprise, data centre |
| 172.16.0.0 – 172.31.255.255 | 172.16.0.0/12 | Medium networks |
| 192.168.0.0 – 192.168.255.255 | 192.168.0.0/16 | Small office, lab |

## VLAN Segmentation

Segment the network by function and trust level:

| VLAN | Purpose | Example Range |
|------|---------|--------------|
| Management | Out-of-band management (switches, routers, BMC) | 10.0.1.0/24 |
| Servers | Production servers | 10.0.10.0/24 |
| DMZ | Internet-facing services | 10.0.20.0/24 |
| Clients | End-user workstations | 10.0.30.0/24 |
| IoT / OT | Isolated devices | 10.0.40.0/24 |
| Guests | Untrusted internet access | 10.0.50.0/24 |

**Rules:**
- Management VLAN must be reachable from admin hosts only
- DMZ must never have direct routed access to Servers VLAN
- Guests must only access the internet; all internal traffic blocked

## Routing Topology Patterns

### Spine-Leaf (data centre)
- All leaf switches connect to every spine switch
- No leaf-to-leaf links; no spine-to-spine links
- Predictable latency; horizontal scaling

### Hub-and-Spoke (WAN)
- Central hub site connects to remote spoke sites
- Simple; hub is a single point of failure — add redundant hub for HA

### Full Mesh (small core)
- Every site connects to every other site
- Maximum redundancy; does not scale beyond ~6 sites

## BGP Fundamentals

```
# Key attributes for path selection (in order)
1. Weight (Cisco-proprietary, local to router)
2. Local Preference (iBGP, higher = preferred)
3. AS Path (fewer hops = preferred)
4. Origin (IGP > EGP > Incomplete)
5. MED (lower = preferred)
6. eBGP over iBGP
7. Lowest Router ID
```

## OSPF Fundamentals

```
# Area design rules
- Area 0 (backbone) must be contiguous
- All non-backbone areas must connect to Area 0
- Use stub areas to reduce LSA flooding in remote areas

# Cost = Reference bandwidth / Interface bandwidth
# Default reference: 100 Mbps
# 1 Gbps interface → cost 1 (adjust reference to 10000 for modern networks)
```

## Redundancy Checklist

- [ ] No single point of failure on the path for critical services
- [ ] Dual uplinks from each access/leaf switch to the core/spine
- [ ] Redundant WAN links (different ISPs where possible)
- [ ] VRRP/HSRP configured on gateway interfaces
- [ ] Spanning Tree configured correctly (RSTP or MSTP preferred; no legacy STP)
- [ ] BFD enabled on routing protocol sessions for fast failover
