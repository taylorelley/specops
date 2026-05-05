---
name: patch-management
description: "Patch cadence, CVE prioritization, staging-to-prod promotion, and rollback. Use for scheduled patch cycles and emergency vulnerability response."
metadata: {"specialagent":{"emoji":"🩹"}}
---

# Patch Management

Apply security and maintenance patches predictably, with rollback always in reach. Pair with the Security Engineer for CVE triage and the SRE for change windows.

## Cadence

| Class | Cadence | Owner | Window |
|-------|---------|-------|--------|
| **Critical security (CVSS 9.0+, actively exploited)** | Within 72 hours of release | SysAdmin + Security | Emergency change |
| **High security (CVSS 7.0–8.9)** | Within 7 days | SysAdmin | Next available window |
| **Standard security & bugfix** | Monthly | SysAdmin | Scheduled patch window |
| **Kernel / reboot-required** | Quarterly | SysAdmin + SRE | Coordinated maintenance |
| **Major version upgrades** | Per OS lifecycle | SysAdmin + relevant team | Project-managed |

Document the next four windows in MEMORY.md so they're easy to plan around.

## CVE Prioritization

CVSS score is a starting point, not the answer. Adjust by:

- **Exposure** — Internet-facing? Internal-only? Air-gapped?
- **Exploitability** — Public PoC? Known active exploitation (CISA KEV)?
- **Compensating controls** — WAF rule, network ACL, or feature flag that blunts the risk?
- **Blast radius** — One service or fleet-wide?

Pair scoring with the Security Engineer; the Security role owns the final risk call.

## Staging → Production Promotion

Never patch prod first. Standard pipeline:

```
dev → canary (1 host) → staging (full env) → prod-wave-1 (10%) → prod-wave-2 (50%) → prod-wave-3 (100%)
```

Between waves:
- Soak time: ≥ 24 hours for non-critical, ≥ 1 hour for emergency
- Healthcheck: error rate, latency p99, restart loops, cron success rate
- Rollback if any healthcheck regresses beyond threshold

## Reboot Windows vs Live Patching

| Situation | Approach |
|-----------|----------|
| Userspace patch only | Restart affected services |
| Kernel patch, kpatch / livepatch available | Live patch, schedule reboot at next window |
| Kernel patch, no live patch | Drain → reboot → verify |
| Firmware / microcode | Coordinate with Network Engineer (if it touches NICs) and SRE |

For drain-reboot cycles:
1. Mark the host out of rotation (load balancer, scheduler)
2. Wait for in-flight work to complete or migrate
3. `reboot` and watch boot via console / journald
4. Run post-reboot healthcheck
5. Return to rotation

## Rollback Plan

Every patch operation has a rollback path defined **before** the patch runs:

- Package: pin the previous version, document `apt-get install pkg=1.2.3-1` (or equivalent)
- Kernel: keep the previous kernel installed; document boot menu fallback
- Config: keep the previous config in version control; revert is a `git revert` away
- Image-based hosts: previous image tag identified before the change

If you can't articulate the rollback in two sentences, you aren't ready to patch.

## Change Record Template

```markdown
# Patch Change: {YYYY-MM-DD} — {scope}

**Owner:** {name}
**Reviewer:** {name}
**Risk class:** {critical | high | standard}
**Window:** {start} → {end} UTC

## What's changing
- {package or kernel} {old version} → {new version}
- CVEs addressed: {CVE-IDs}

## Hosts in scope
- {fleet selector / list}

## Pre-change healthcheck
- [ ] Baseline metrics captured
- [ ] Backups verified within last 24h
- [ ] Rollback plan tested in staging

## Steps
1. {step}
2. {step}

## Rollback
{exact commands or runbook link}

## Post-change verification
- [ ] {service} returns 200 on healthcheck
- [ ] Error rate within ±10% of baseline
- [ ] No new entries in `journalctl -p err`

## Notes
{anything observed during the change}
```

## Anti-Patterns

- "Reboot to fix it" without identifying what was actually wrong
- Patching all hosts in parallel ("we tested it once")
- Auto-update on prod without canary
- Disabling unattended-upgrades because "it broke once" — fix the breakage, keep the cadence
- Ignoring patches because "we'll redo this whole stack next quarter"
