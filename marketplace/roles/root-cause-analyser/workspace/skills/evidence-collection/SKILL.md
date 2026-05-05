---
name: evidence-collection
description: "Gathering logs, metrics, traces, and state snapshots before they age out. Use during and immediately after an incident to preserve a defensible record."
metadata: {"specialagent":{"emoji":"🧾"}}
---

# Evidence Collection

Logs rotate. Metrics get downsampled. Memory clears. Snapshot what you need before it disappears, in a way you can defend later.

## The Golden Rule

**Snapshot before you mitigate.** Mitigation often destroys the evidence needed to understand the cause. If active mitigation is in flight, designate one engineer to capture state in parallel with the responders.

## Standard Capture Set

For every incident, capture:

- [ ] **Timeline** — alert times, deploy times, human actions, with UTC timestamps
- [ ] **Logs** — affected services, ±15 min around the event, raw and queryable
- [ ] **Metrics** — at original resolution, exported (downsampling happens fast)
- [ ] **Traces** — exemplar slow / failing requests
- [ ] **Config diffs** — what changed in the 24 hours before the incident
- [ ] **Deploy / release ledger** — what shipped, when, by whom
- [ ] **Dependency state** — third-party status, upstream incidents
- [ ] **Customer reports** — paste raw text into evidence, not summaries

## Capture Commands (Linux baseline)

Pair with the System Administrator and SRE for environment-specific tooling.

```bash
# System state at moment of capture
date -u > evidence/capture-time.txt
uptime > evidence/uptime.txt
ps auxf > evidence/ps.txt
ss -tan > evidence/connections.txt
df -h > evidence/disk.txt
free -m > evidence/memory.txt
dmesg --ctime > evidence/dmesg.txt

# Logs (adjust paths)
journalctl --since "30 minutes ago" --utc > evidence/journal.txt
tar czf evidence/app-logs.tar.gz /var/log/app/

# Metric exports — use your tool's CLI / API to export raw data
```

## Chain of Custody (Security-Adjacent Incidents)

When the incident may involve unauthorised access, data exfiltration, or regulatory exposure, treat evidence like Legal would:

- Capture original artifacts read-only; never edit the original
- Compute SHA-256 of every captured artifact at collection time
- Log who collected what, from where, at what UTC time
- Store evidence in a path no normal workflow writes to
- Loop in Security Engineer and Legal Counsel before any further analysis

```bash
sha256sum evidence/*.{txt,gz} > evidence/SHA256SUMS
chmod -R a-w evidence/
```

## Reproducible Repro

If the failure can be reproduced, capture:

- Minimal reproducer (smallest input that triggers it)
- Environment specification (versions of every dependency)
- Expected vs actual output, with diff
- Whether it reproduces on `main` HEAD vs the deployed commit

A reproducer is worth more than a hundred lines of theory.

## Evidence Layout

Keep evidence per incident under a stable structure so future you (or an auditor) can find it:

```
incidents/{YYYY-MM-DD}-{slug}/
├── capture-time.txt
├── timeline.md
├── logs/
├── metrics/
├── traces/
├── configs/
├── customer-reports/
├── repro/
└── SHA256SUMS
```

## What Decays Fastest

Capture in this order — the top items disappear first:

1. **In-memory state** of running processes (gone on restart)
2. **Live connections / sockets** (closed in seconds–minutes)
3. **High-resolution metrics** (downsampled within hours)
4. **Container / VM state** (replaced on next deploy or autoscale)
5. **Application logs** (rotated daily–weekly)
6. **Audit / system logs** (rotated weekly–monthly)
7. **Deploy / config history** (typically retained, but verify)

## Anti-Patterns

- Summarising logs into a doc and discarding the originals
- Editing raw evidence to "clean it up" — preserve originals, annotate copies
- Capturing only the failing service; the cause often lives upstream
- Trusting screenshots as evidence (no machine-readable timestamp, easy to edit)
- Letting one person capture, analyse, and conclude with no second pair of eyes
