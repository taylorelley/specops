---
name: network-security
description: "Firewall hygiene, segmentation, VPN, DDoS posture, and TLS at the network edge. Use when designing controls or reviewing existing ones."
metadata: {"specialagent":{"emoji":"🛡️"}}
---

# Network Security

Network controls that are actually enforced, actually audited, and don't quietly degrade. The Security Engineer owns policy; the Network Engineer owns implementation and operational hygiene.

## Firewall Rule Hygiene

Rules rot. The ones added in a hurry never get removed. Fight rot with structure.

- **Default deny** at every boundary. Allowlist explicitly.
- **Named objects** (host groups, port groups) — never raw IPs in the rule body
- **Owner and ticket** in every rule comment: `owner=team-x ticket=NET-1234 expires=2026-12-01`
- **No `any` to `any` on any port** — if you need it, document why
- **Rule order matters** on stateful firewalls — most specific first
- **Quarterly audit** — flag rules with no hits, no owner, or past expiry; remove or refresh

Rule-base review checklist:

- [ ] Every rule has an owner
- [ ] Every rule has a creation date and expiry / next-review date
- [ ] No `permit any any` rules outside justified exceptions
- [ ] Logging enabled on deny rules at perimeter
- [ ] Rules sourced from version control, applied by automation

## Segmentation

Segment so that a compromise is contained.

| Boundary | Default policy | Notes |
|----------|----------------|-------|
| **Internet → DMZ** | Deny; allow specific services | TLS termination, WAF |
| **DMZ → app tier** | Deny; allow service ports | Stateful, logged |
| **App → data tier** | Deny; allow DB ports per service identity | Pair with mTLS where possible |
| **Cross-environment (prod ↔ staging)** | Deny — no exceptions casually | Human approval for any allow |
| **Admin / management plane** | Separate VRF or VLAN | Jump host or zero-trust gateway |

Zero-trust principles, network-side:
- Identity per workload, not per IP
- Authenticate every flow, even inside the trust boundary
- Encrypt every flow that crosses a host boundary

## VPN Patterns

| Pattern | Use case | Notes |
|---------|----------|-------|
| **IPsec site-to-site** | Office / DC interconnect | IKEv2; PSK only with strong rotation, prefer certs |
| **WireGuard** | Modern site-to-site or admin overlay | Smaller surface, fewer knobs |
| **SSL / OpenVPN client** | Legacy remote workforce | Phasing out in favour of zero-trust |
| **Zero-trust gateway (BeyondCorp-style)** | Modern remote workforce | Per-app, per-identity, per-device |

Hygiene:
- Disable unused tunnels; idle tunnels accumulate risk
- Rotate PSKs on schedule (quarterly minimum) and on personnel changes
- Log VPN session start / stop with user identity, ship to SIEM
- Enforce device posture (patch level, disk encryption) before granting access

## DDoS Mitigation

Layer the response — no single control stops everything.

| Layer | Control | Stops |
|-------|---------|-------|
| **Edge / scrubbing** | DDoS provider (cloud-native or third party) | Volumetric, amplification |
| **Anycast / global LB** | Geographic distribution | Volumetric, regional saturation |
| **Rate limiting** | At LB / WAF | L7 floods, scraping |
| **Connection limits** | At LB | SYN floods, slow-loris |
| **Application** | Backpressure, queues, circuit breakers | Anything that gets through |

Practice the runbook (regional failover, scrubbing engagement, capacity expansion) before you need it.

## TLS Posture at the Network Edge

- **TLS 1.2 minimum**, TLS 1.3 preferred; disable everything older
- **Cipher suite list** curated and reviewed annually
- **Certificate inventory** — expiry monitored with at least 30-day warning
- **HSTS** at the edge; preload list considered for marketing-facing domains
- **OCSP stapling** enabled where the LB supports it
- **Wildcard certs** used judiciously — convenient but a bigger blast radius if leaked

## Audit Cadence

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Firewall rule review | Quarterly | Network Engineer |
| Segmentation review (cross-zone allows) | Quarterly | Network Engineer + Security Engineer |
| TLS / cert posture | Quarterly | Network Engineer |
| Penetration test of perimeter | Annually | Security Engineer (Network supports) |
| DDoS runbook drill | Annually | Network Engineer + SRE |
| VPN config review | Bi-annually | Network Engineer + Security Engineer |

## Anti-Patterns

- Permanent "temporary" firewall rules
- VPN PSK shared by email
- Wildcard certificates issued to everyone "for convenience"
- Self-signed certs in production "behind the LB" — make mTLS routing impossible later
- DDoS plan that depends on one vendor with no tested failover
- Logging deny events but never reviewing them
