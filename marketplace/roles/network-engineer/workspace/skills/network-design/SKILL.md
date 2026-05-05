---
name: network-design
description: "Topology, IP planning, DNS architecture, and load-balancer tiers. Use when designing a new environment, region, or major segmentation change."
metadata: {"specialagent":{"emoji":"🗺️"}}
---

# Network Design

Design networks that are predictable, segmented, and easy to reason about under failure.

## Topology Choices

| Pattern | Use case | Notes |
|---------|----------|-------|
| **Tiered (core / aggregation / access)** | Traditional DC, branch campus | Familiar but oversubscribed at aggregation |
| **Spine-leaf (Clos)** | Modern DC, AI / data workloads | Predictable east-west bandwidth; ECMP everywhere |
| **Hub-and-spoke** | Cloud transit, branch VPN | Central inspection point, simple but a chokepoint |
| **Mesh (full or partial)** | Multi-region, low-latency overlays | Costly to operate; reserve for justified cases |

Document the chosen pattern and its failure model before adding services.

## IP Address Management (IPAM)

- **One source of truth** — IPAM tool (NetBox, Infoblox, or a versioned YAML) feeds everything else
- **Hierarchical allocation** — `/16` per region → `/20` per environment → `/24` per tier — leaves room for growth
- **Reserve, don't sprinkle** — Reserve future ranges; allocating contiguously prevents fragmentation
- **No-NAT inside the trust boundary** — NAT only at edges; otherwise it complicates every diagnosis

Sample allocation (RFC1918):

```
10.0.0.0/8
├── 10.10.0.0/16   us-east
│   ├── 10.10.0.0/20    prod
│   │   ├── 10.10.0.0/24    public
│   │   ├── 10.10.1.0/24    app
│   │   └── 10.10.2.0/24    data
│   ├── 10.10.16.0/20   staging
│   └── 10.10.32.0/20   dev
└── 10.20.0.0/16   eu-west
```

## VLAN / Subnet Planning

- One VLAN per security tier per AZ — not one giant VLAN spanning everything
- Subnets sized for ~50% utilization at steady state to absorb bursts
- Document broadcast / multicast usage explicitly; avoid relying on it across security boundaries
- Tag VLANs at the access switch; do not trunk to endpoints unless the device truly needs it

## DNS Architecture

Two separate planes — keep them simple and split:

**Authoritative (what the world resolves)**
- Two providers minimum for the public zone (avoid single-vendor blast radius)
- Short TTLs (60–300s) for records that need fast failover; long TTLs (24h) for static records
- DNSSEC enabled where compliance or threat model requires
- Zone changes via version control + automation, never console-edit

**Resolver (what your hosts use)**
- Multiple resolver IPs per region (anycast preferred)
- Internal split horizon for private records — never leak internal names to public resolvers
- Negative-caching tuned (don't cache NXDOMAIN for hours during deploys)
- Logging of lookups for security observability (paired with Security Engineer)

## Load-Balancer Tiers

| Tier | Layer | Examples | Job |
|------|-------|----------|-----|
| **Edge / global** | L4/L7 anycast | Cloud LB, CDN | Geo routing, DDoS, TLS termination |
| **Regional** | L7 | Cloud ALB, NGINX, HAProxy | Path routing, header rewrites |
| **Service mesh / internal** | L7 | Envoy, Linkerd | Per-service policy, mTLS |

Health checks:
- Active health checks at every tier; passive (eject on errors) where supported
- Healthcheck path is cheap, deterministic, and excludes external dependencies
- Drain time at least the longest in-flight request budget

## Redundancy Patterns

- **N+1 minimum** for any device whose failure stops traffic
- **Active-active** preferred over active-passive (failover paths get exercised continuously)
- **Diverse paths** — Two links from the same provider via the same conduit is one link
- **BGP** for dynamic failover at the edge; static routes only when you can prove the failure mode

## Documentation Per Environment

Every environment ships with:

- Topology diagram (versioned, with timestamp)
- IPAM export
- VLAN / subnet table
- Firewall rule export
- DNS zone export
- BGP / routing summary
- Failure-mode notes ("if X dies, Y picks up; estimated RTO Z")

## Anti-Patterns

- "Temporary" /23 allocated from the middle of an unallocated /16 (locks future planning)
- VLAN 1 used for production traffic
- Single DNS provider for the public apex
- Healthchecks that hit the database (cascading failure pattern)
- Asymmetric routing left in place "because it works"
