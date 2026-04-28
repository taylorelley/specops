---
name: firewall-management
description: "Firewall rule design, ACL management, VPN configuration, and network security policy for perimeter and internal segmentation."
metadata: {"specialagent":{"emoji":"🔥"}}
---

# Firewall Management

Principles and procedures for managing firewalls, ACLs, and network security policies.

## Rule Design Principles

1. **Default deny** — Block all traffic not explicitly permitted
2. **Least privilege** — Allow only the minimum ports and sources required
3. **Direction matters** — Define rules by source → destination, not just destination
4. **Explicit egress** — Don't assume outbound is safe; restrict egress too
5. **Expiring rules** — Temporary rules must have an expiry date noted in the comments

## Rule Template

```
# Format: [ID] [Action] [Protocol] [Source] [Destination] [Port] [Comment]

PERMIT  TCP  10.0.10.0/24    0.0.0.0/0         443   Allow servers to reach HTTPS
PERMIT  TCP  10.0.30.0/24    10.0.10.0/24      443   Clients → Servers HTTPS
PERMIT  TCP  0.0.0.0/0       10.0.20.5/32      443   Internet → DMZ web server
DENY    ANY  0.0.0.0/0       0.0.0.0/0         ANY   Default deny (log)
```

## Firewall Audit Checklist

Run quarterly or after significant topology changes:

- [ ] No rules with source `any` AND destination `any` (without strong justification)
- [ ] No rules allowing inbound access from the internet to internal networks without explicit business need
- [ ] All rules have a comment stating purpose and owner
- [ ] Expired temporary rules removed
- [ ] Overly broad rules (large CIDR blocks where single IPs suffice) tightened
- [ ] Unused rules removed (check hit counts)
- [ ] Management access (SSH, HTTPS to firewall UI) restricted to management VLAN only
- [ ] Logging enabled on DENY rules

## Common iptables / nftables Commands

```bash
# List current rules with line numbers
iptables -L -n -v --line-numbers

# Allow established connections (add early in chain)
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow specific port from specific source
iptables -A INPUT -p tcp -s 10.0.1.0/24 --dport 22 -j ACCEPT

# Drop all other input
iptables -P INPUT DROP

# Save rules (Debian)
iptables-save > /etc/iptables/rules.v4

# nftables — list all rules
nft list ruleset
```

## VPN Configuration

### IPsec (site-to-site)

Key parameters to document for each tunnel:

| Parameter | Value |
|-----------|-------|
| Local endpoint | [IP] |
| Remote endpoint | [IP] |
| Phase 1 (IKE) | AES-256, SHA-256, DH Group 14+ |
| Phase 2 (ESP) | AES-256, SHA-256, PFS enabled |
| Pre-shared key / cert | [location of secret] |
| Local subnet | [CIDR] |
| Remote subnet | [CIDR] |

### WireGuard (remote access or site-to-site)

```bash
# Generate key pair
wg genkey | tee privatekey | wg pubkey > publickey

# Basic server config (/etc/wireguard/wg0.conf)
[Interface]
Address = 10.200.0.1/24
ListenPort = 51820
PrivateKey = <server-private-key>

[Peer]
PublicKey = <client-public-key>
AllowedIPs = 10.200.0.2/32

# Start
wg-quick up wg0
systemctl enable wg-quick@wg0
```

## Zero-Trust Principles

Apply to all new network access requests:

- **Verify explicitly** — Authenticate every connection; don't trust because it originates from inside the network
- **Least privilege access** — Grant access to specific resources, not broad network segments
- **Assume breach** — Log all access; detect lateral movement
- **Micro-segmentation** — Internal firewalls between application tiers, not just perimeter firewalls

## Change Control

All firewall rule changes must follow this workflow:

1. **Request** — Document source, destination, port, protocol, and business justification
2. **Review** — Security Engineer or Network Engineer reviews for compliance
3. **Test** — Apply to a lab or pre-production firewall first where possible
4. **Implement** — Apply change in a maintenance window with a rollback plan
5. **Verify** — Confirm permitted traffic flows; confirm blocked traffic is still blocked
6. **Document** — Update the firewall rule register in `memory/MEMORY.md`
