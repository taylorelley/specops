---
name: patch-management
description: "Patch lifecycle management — vulnerability tracking, scheduling, applying OS and software updates, and validating stability post-patch."
metadata: {"specialagent":{"emoji":"🔧"}}
---

# Patch Management

Structured approach to keeping systems up-to-date and secure.

## Patch Classification

| Priority | Criteria | Target Patch Window |
|----------|----------|---------------------|
| **Critical** | CVSS ≥ 9.0 / active exploitation | 24–48 hours |
| **High** | CVSS 7.0–8.9 / likely exploitation | 7 days |
| **Medium** | CVSS 4.0–6.9 / limited exposure | 30 days |
| **Low** | CVSS < 4.0 / no known exploitation | Next maintenance window |
| **Routine** | Non-security updates, enhancements | Monthly maintenance window |

## Patch Workflow

1. **Identify** — Subscribe to vendor advisories; scan with a vulnerability scanner
2. **Assess** — Determine applicability, severity, and affected systems
3. **Test** — Apply to a non-production environment first
4. **Schedule** — Coordinate maintenance window; notify stakeholders
5. **Back up** — Ensure a current backup exists before patching
6. **Apply** — Run the update; document exact commands and versions
7. **Validate** — Run smoke tests; confirm services are healthy
8. **Document** — Log the patch, version change, and any issues

## Common Patch Commands

### Debian / Ubuntu

```bash
# Update package index
apt update

# List upgradable packages
apt list --upgradable

# Apply security updates only
apt upgrade -y --only-upgrade $(apt list --upgradable 2>/dev/null | grep -i security | awk -F/ '{print $1}')

# Full upgrade
apt full-upgrade -y

# Check if reboot required
cat /var/run/reboot-required 2>/dev/null && echo "Reboot required"
```

### RHEL / Rocky / AlmaLinux

```bash
# Check for updates
dnf check-update

# Apply security updates only
dnf update --security -y

# Full update
dnf update -y

# List installed patches
dnf updateinfo list installed
```

### Kernel Updates

```bash
# Check current kernel
uname -r

# List installed kernels (Debian)
dpkg --list | grep linux-image

# Remove old kernels (Debian)
apt autoremove --purge -y
```

## Maintenance Window Checklist

Before patching:
- [ ] Backup completed and verified
- [ ] Maintenance window communicated to stakeholders
- [ ] Rollback plan documented
- [ ] Monitoring alerts silenced for the window

During patching:
- [ ] Snapshot or checkpoint taken (if VM)
- [ ] Patch applied and command output captured
- [ ] Reboot performed if required

After patching:
- [ ] Services confirmed healthy (`systemctl --failed`)
- [ ] Application smoke tests passed
- [ ] Monitoring alerts re-enabled
- [ ] Patch record updated in `memory/MEMORY.md`

## Vulnerability Tracking

Maintain a patch register in `memory/MEMORY.md`:

```
| CVE / Advisory | Severity | Affected Systems | Status | Patched Date |
|---------------|----------|-----------------|--------|-------------|
| CVE-XXXX-XXXX | Critical | web-server-01 | Patched | 2026-01-15 |
```

## Rollback Procedure

If a patch causes instability:

1. Restore from pre-patch snapshot or backup
2. Or revert the specific package:
   ```bash
   # Debian — hold a package at current version
   apt-mark hold <package>

   # RHEL — downgrade a package
   dnf downgrade <package>
   ```
3. Document the regression and open a deferral ticket with expiry date
4. Notify Security Engineer if a critical CVE patch is deferred beyond its target window
