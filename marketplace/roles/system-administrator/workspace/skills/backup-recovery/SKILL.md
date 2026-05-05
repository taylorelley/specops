---
name: backup-recovery
description: "Backup strategy, restore drills, RPO/RTO targets, and encryption. Use for designing backup schedules and verifying recovery actually works."
metadata: {"specialagent":{"emoji":"💾"}}
---

# Backup & Recovery

A backup that has never been restored is a hope, not a backup. The only metric that matters is whether you can recover within the agreed time, with the agreed data loss.

## 3-2-1 Strategy

- **3** copies of the data — the original plus two backups
- **2** different storage media or providers
- **1** copy off-site (different region or provider, not just a different rack)

Add **+ 1**: an immutable / WORM copy that ransomware can't rewrite.

## Backup Classes

| Class | Frequency | Retention | Use case |
|-------|-----------|-----------|----------|
| **Full** | Weekly | 4–12 weeks | Restore base |
| **Incremental** | Daily | 30 days | Day-to-day point-in-time |
| **Snapshot (filesystem / volume)** | Hourly | 24–72 hours | Fast operator-error recovery |
| **Transaction log / WAL** | Continuous | Days | Point-in-time recovery for databases |
| **Archive / cold** | Monthly | 1–7 years | Compliance, legal hold |

Tier the data: not everything needs every class. Critical data → all classes; ephemeral build artifacts → maybe none.

## RPO / RTO Targets

Define and agree per dataset:

- **RPO (Recovery Point Objective)** — How much data can we afford to lose? (e.g., 5 minutes, 1 hour, 24 hours.)
- **RTO (Recovery Time Objective)** — How long can we be down? (e.g., 15 minutes, 4 hours, next business day.)

Cheaper backup classes hit longer RPO / RTO. Match cost to business need with the Finance Controller and product owner; don't promise sub-minute RPO on cold storage.

## Restore Drills

Schedule restore drills like fire drills:

| Drill | Frequency | What it proves |
|-------|-----------|----------------|
| **File restore** | Monthly | Tooling works; permissions intact |
| **Database point-in-time** | Quarterly | WAL chain is complete; tooling works |
| **Full host rebuild** | Quarterly | Image / config / data combine cleanly |
| **Region / provider failover** | Annually | Off-site copy is actually usable; runbooks current |

Capture for each drill: data restored vs expected, time taken vs RTO, surprises encountered. File anything below target as an action item.

## Verification Checklist

Per backup job:

- [ ] Backup completed without errors (alert on failure, not silence)
- [ ] Backup size in expected range (sudden ±50% is suspicious)
- [ ] Checksums match across copies
- [ ] At least one off-site copy confirmed
- [ ] Encryption at rest verified
- [ ] Sample restore from this week's backup succeeded

Per dataset, monthly:

- [ ] Backup catalog reconciles with actual storage
- [ ] Old backups beyond retention are purged (cost + compliance)
- [ ] Access logs reviewed (who pulled backups?)

## Encryption

- **At rest** — AES-256 minimum; managed keys with rotation policy
- **In transit** — TLS 1.2+ for backup transport
- **Keys** — Separate from the data; loss of keys = loss of backups
- **Key recovery** — Documented break-glass procedure with split custody (pair with Security Engineer)

## Common Restore Scenarios

| Scenario | Likely tool |
|----------|-------------|
| User deleted a file | Snapshot, then file-level restore |
| App corrupted a row | Database PITR to just before the corruption |
| Host died | Image rebuild + data restore from latest full + incremental chain |
| Region down | Failover to off-site copy in second region |
| Ransomware | Immutable copy → clean rebuild → selective data restore (loop in Security + Legal) |

Document the runbook for each scenario in the workspace; rehearse it in the drill.

## Anti-Patterns

- "We have backups" with no documented restore procedure
- Backup destination on the same host / volume as the source
- Backups that nobody monitors — silent failure for months
- Encryption keys stored next to the encrypted backups
- Restore drill skipped this quarter "because we're busy" (you'll be busier when you need it)
- Retention set to "forever" on hot storage — expensive and a discovery liability
