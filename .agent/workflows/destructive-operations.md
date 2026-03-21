---
description: Mandatory approval gate before any destructive data operations
---

# Destructive Operations — Mandatory User Approval

## Rule

**Before executing ANY of the following operations, you MUST stop and ask the user for explicit permission.** Do NOT auto-run these. Do NOT set `SafeToAutoRun` to true. Do NOT proceed without a clear "yes" from the user.

This rule applies to ALL workspaces and projects — not just Nexus.

## Covered Operations

### Database & Volumes
- `docker system prune` (especially with `--volumes`)
- `docker volume rm` / `docker volume prune`
- `DROP DATABASE`, `DROP TABLE`, `TRUNCATE`
- `alembic downgrade`
- Any SQL `DELETE` without a `WHERE` clause
- Deleting or overwriting database backup files

### Docker Containers & Images
- `docker compose down --volumes` or `down -v`
- `docker system prune -a`
- `docker image prune -a`
- Removing named volumes that may contain persistent data

### Filesystem
- `rm -rf` on data directories (e.g., `/var/lib/docker`, `/opt/nexus/data`)
- Overwriting `.env` files that contain credentials or secrets
- Deleting migration files

### Remote / Production
- Any destructive command run via SSH on production servers
- Restarting Docker daemon on production (`systemctl restart docker`)
- Rebooting production VMs

## What To Say

When you encounter a situation where one of these operations seems necessary, notify the user with:

1. **What** you want to do (exact command)
2. **Why** you need to do it
3. **What data will be lost** if you proceed
4. **Alternatives** you considered that are less destructive

Example:
> I need to run `docker system prune -a --volumes` to clear a stuck container naming conflict.
> ⚠️ **This will delete all Docker volumes, including the Postgres database.**
> Data that would be lost: secrets vault, server configs, audit trail, user accounts.
> Less destructive alternatives I've already tried: `docker rm -f`, `docker compose down`, daemon restart.
> Should I proceed, or would you prefer I try another approach first?

## Why This Rule Exists

A `docker system prune --volumes` wiped an entire production database, losing hours of configuration data. This is a mission-critical safeguard that applies globally.
