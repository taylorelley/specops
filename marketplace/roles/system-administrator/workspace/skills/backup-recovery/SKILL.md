---
name: backup-recovery
description: "Backup strategy, scheduling, verification, and recovery procedures for servers and data."
metadata: {"specialagent":{"emoji":"💾"}}
---

# Backup and Recovery

Framework for protecting data and restoring systems reliably.

## Backup Strategy — 3-2-1 Rule

- **3** copies of data
- **2** different storage media types
- **1** copy offsite (or in a different cloud region)

## Backup Types

| Type | Description | Pros | Cons |
|------|-------------|------|------|
| **Full** | Complete copy of all data | Simple restore | Slow, large |
| **Incremental** | Changes since last backup | Fast, small | Restore requires full + all incrementals |
| **Differential** | Changes since last full | Faster restore than incremental | Larger than incremental |
| **Snapshot** | Point-in-time volume/VM state | Near-instant, consistent | Storage overhead |

## Backup Schedule Template

| Data Type | Full | Incremental | Retention |
|-----------|------|-------------|-----------|
| Databases | Weekly | Daily | 30 days |
| Application configs | Daily | — | 90 days |
| Home directories | Weekly | Daily | 14 days |
| System state | Weekly | — | 4 weeks |
| Logs | — | Daily | 7 days (30 days compressed) |

## Common Backup Tools

```bash
# rsync — file-level backup
rsync -avz --delete /source/ user@remote:/destination/

# tar — archive with compression
tar -czf /backups/etc-$(date +%Y%m%d).tar.gz /etc/

# pg_dump — PostgreSQL backup
pg_dump -U postgres dbname > /backups/dbname-$(date +%Y%m%d).sql

# mysqldump — MySQL backup
mysqldump -u root -p dbname > /backups/dbname-$(date +%Y%m%d).sql

# restic — encrypted, deduplicated backups
restic -r /backups/repo backup /data
restic -r /backups/repo snapshots
```

## Backup Verification (required)

A backup that hasn't been tested is not a backup.

### Verification Checklist (run monthly)
- [ ] Confirm backup job completed successfully (check logs)
- [ ] Verify backup file integrity (checksum or tool-native verify)
- [ ] Perform a test restore to a non-production target
- [ ] Confirm restored data is readable and correct
- [ ] Document the test result with date and tester in `memory/MEMORY.md`

```bash
# restic verify
restic -r /backups/repo check

# md5 checksum
md5sum /backups/file.tar.gz > /backups/file.tar.gz.md5
md5sum -c /backups/file.tar.gz.md5
```

## Recovery Procedures

### File Recovery

```bash
# Restore specific file from tar archive
tar -xzf /backups/etc-20260101.tar.gz etc/nginx/nginx.conf -C /restore/

# Restore from rsync backup
rsync -avz /backups/etc/ /etc/
```

### Database Recovery

```bash
# PostgreSQL restore
psql -U postgres dbname < /backups/dbname-20260101.sql

# MySQL restore
mysql -u root -p dbname < /backups/dbname-20260101.sql
```

### RTO and RPO Targets

Define and document for each system:

| System | RTO (max downtime) | RPO (max data loss) |
|--------|--------------------|---------------------|
| [System] | [e.g., 4 hours] | [e.g., 24 hours] |

Review annually and after any recovery event.

## Post-Recovery Checklist

- [ ] Services restored and responding
- [ ] Data integrity verified (checksums, record counts, spot checks)
- [ ] Backup agent re-enabled and next backup scheduled
- [ ] Incident documented in `memory/HISTORY.md`
- [ ] Root cause of data loss or failure identified (escalate to Root Cause Analyser if significant)
