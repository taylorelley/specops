---
name: linux-administration
description: "Core Linux system administration — user management, service control, performance diagnostics, and OS configuration."
metadata: {"specialagent":{"emoji":"🐧","requires":{"bins":["bash","systemctl","journalctl"]}}}
---

# Linux Administration

Essential operations for managing Linux servers and services.

## User and Group Management

```bash
# Create user with home directory
useradd -m -s /bin/bash username

# Set password
passwd username

# Add to group
usermod -aG groupname username

# Lock / unlock account
passwd -l username   # lock
passwd -u username   # unlock

# List users
cut -d: -f1 /etc/passwd

# Show user's groups
id username

# Remove user (keep home dir)
userdel username

# Remove user and home dir
userdel -r username
```

## Service Management (systemd)

```bash
# Start / stop / restart a service
systemctl start nginx
systemctl stop nginx
systemctl restart nginx

# Enable / disable on boot
systemctl enable nginx
systemctl disable nginx

# Check service status
systemctl status nginx

# View recent logs for a service
journalctl -u nginx -n 50 --no-pager

# Follow logs live
journalctl -u nginx -f

# List all failed services
systemctl --failed
```

## File System and Disk

```bash
# Disk usage overview
df -h

# Directory size
du -sh /var/log/

# Find large files
find /var -type f -size +100M -ls

# Check inodes
df -i

# Mount a filesystem
mount /dev/sdb1 /mnt/data

# Persistent mount (add to /etc/fstab)
# UUID=xxxx /mnt/data ext4 defaults 0 2
```

## Performance Diagnostics

```bash
# CPU and memory overview
top
htop     # if installed

# Memory usage
free -h

# CPU load averages
uptime

# Process list sorted by CPU
ps aux --sort=-%cpu | head -20

# Network connections
ss -tuln

# Open files by process
lsof -p <pid>

# I/O wait
iostat -x 1 5   # if sysstat installed
```

## SSH Hardening

Key settings in `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers <specific users>
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

After editing: `systemctl restart sshd`

## Cron Jobs

```bash
# Edit crontab for current user
crontab -e

# List cron jobs
crontab -l

# System-wide cron
ls /etc/cron.d/
ls /etc/cron.daily/

# Cron expression format
# m h dom mon dow command
# 0 2 * * * /usr/local/bin/backup.sh   # 2 AM daily
```

## Log Locations

| Log | Path |
|-----|------|
| Auth / SSH | `/var/log/auth.log` (Debian) / `/var/log/secure` (RHEL) |
| System | `/var/log/syslog` or `journalctl` |
| Kernel | `/var/log/kern.log` |
| Application | `/var/log/<app>/` |
| Cron | `/var/log/cron` |
