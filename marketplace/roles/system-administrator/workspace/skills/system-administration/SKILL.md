---
name: system-administration
description: "OS-level administration baseline for Linux and Windows: users, services, scheduled jobs, logs, performance triage, and config drift."
metadata: {"specialagent":{"emoji":"🛠️"}}
---

# System Administration

Day-to-day operating-system administration for the fleet. Pair with the Network Engineer for layer-3 issues and the Security Engineer for hardening.

## Linux Baseline

### Users, groups, sudoers

```bash
# Create a service user with no shell
useradd --system --shell /usr/sbin/nologin --home /var/lib/myapp myapp

# Add an interactive user to a group
usermod -aG docker alice

# SSH key install (preferred over passwords)
install -d -m 700 -o alice -g alice ~alice/.ssh
install -m 600 -o alice -g alice key.pub ~alice/.ssh/authorized_keys

# Sudoers — ALWAYS use visudo to validate syntax
visudo -f /etc/sudoers.d/10-ops
```

Conventions:
- Disable password authentication for SSH; use keys or signed certificates.
- Per-environment groups (`prod-admin`, `staging-admin`); never share root.
- `/etc/sudoers.d/` for per-team policy; never edit `/etc/sudoers` directly.

### systemd units

```bash
systemctl status myapp
systemctl restart myapp
journalctl -u myapp -f --since "1 hour ago"
systemd-analyze blame             # slow boot diagnosis
systemd-analyze critical-chain    # boot dependency graph
```

Unit hygiene:
- `Restart=on-failure`, `RestartSec=` set deliberately
- `User=` / `Group=` specified — never run as root unless required
- `LimitNOFILE`, `LimitNPROC` matched to workload
- `ProtectSystem=strict`, `ProtectHome=true` where possible

### Cron / timers

Prefer systemd timers over cron — they log to journald, support dependencies, and survive missed runs.

```ini
# /etc/systemd/system/cleanup.timer
[Unit]
Description=Nightly cleanup
[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=15min
[Install]
WantedBy=timers.target
```

### Log management

```bash
journalctl --disk-usage
journalctl --vacuum-time=14d
journalctl --vacuum-size=2G
logrotate -d /etc/logrotate.d/myapp   # dry-run check
```

Rules:
- Log rotation configured for every long-running service
- Logs shipped off-host (so a wiped host doesn't take its evidence)
- Standard format includes UTC timestamps

## Windows Notes

When operating Windows hosts:

- PowerShell remoting (`Enter-PSSession`, `Invoke-Command`) over WinRM HTTPS
- Group Policy / `Set-LocalGroupMember`, `New-LocalUser` for identity
- `Get-EventLog -LogName System -Newest 100` for system events
- Scheduled Tasks via `Register-ScheduledTask`
- `sconfig` on Server Core for baseline config
- Patch via WSUS or `PSWindowsUpdate` module

## Healthcheck Commands

Quick fleet-wide health snapshot:

```bash
uptime                            # load average
df -h                             # disk usage
free -m                           # memory
ss -tan state established | wc -l # active TCP connections
who                               # logged-in users
systemctl --failed                # failed services
journalctl -p err -b              # errors since last boot
```

## Performance Triage

When a host is slow, work down the layers:

| Layer | First check | Tool |
|-------|-------------|------|
| CPU | Saturated? Per-core breakdown? | `top`, `mpstat -P ALL 1` |
| Memory | Free vs used vs cache; swapping? | `free -m`, `vmstat 1` |
| Disk IO | Latency, queue depth, util% | `iostat -xz 1`, `iotop` |
| Filesystem | Inodes, full mounts | `df -hi`, `df -h` |
| Network | Packet loss, retransmits | `ss -s`, `nstat` |
| Process | Per-process CPU / mem / IO | `pidstat 1`, `ps auxf` |

If multiple layers are saturated, find the upstream constraint (the one driving the others) before tuning anything.

## Config Drift Management

- Define the desired state in version control (Ansible, Salt, Puppet, Chef, or scripts in git).
- Run a drift scan on a schedule; alert on unexpected changes.
- Categorize drift: **expected** (manual remediation in flight), **harmless** (tighten the model), **dangerous** (revert immediately).
- Quarantine drifted hosts that can't be reconciled — don't leave snowflakes in the fleet.

## Anti-Patterns

- SSH-ing into prod to fix things by hand without recording the change
- Disabling SELinux / AppArmor instead of writing a policy
- `chmod 777` as a debugging step
- Running services as root "for now"
- Cron jobs that silently fail (no `MAILTO=` or equivalent monitoring)
