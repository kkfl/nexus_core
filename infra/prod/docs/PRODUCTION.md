# Nexus Core V1 - Production Hardening

## 1. Host Prerequisites
- **OS**: Ubuntu 22.04+ Recommended.
- **Firewall (UFW)**: The `bootstrap_host.sh` script installs UFW and allows only ports 22 (SSH), 80 (HTTP), and 443 (HTTPS).
- **Intrusion Prevention (Fail2Ban)**: The bootstrap script also enables basic Fail2Ban to block brute-force SSH attacks automatically.
- **Docker**: Installed via `install_docker.sh` using official repositories. 

## 2. Directory Structure & Permissions
All production application files must reside under `/opt/nexus`:
```bash
sudo mkdir -p /opt/nexus
sudo chown -R $USER:$USER /opt/nexus
```
Docker compose will map named volumes to the server (managed dynamically by Docker).
*It is highly recommended to mount `/var/lib/docker/volumes` to a dedicated, high-IOPS disk.*

## 3. Reverse Proxy & TLS (Caddy)
We strongly recommend running Caddy directly on the Host machine (not inside docker) to allow it full control of ports 80/443 without overlay networking overhead.
- Ensure your DNS A/AAAA records point to the host IP.
- Edit `infra/prod/caddy/Caddyfile` to replace `nexus.example.com` with your real domain.
- Caddy handles Let's Encrypt certificate provisioning and rotation automatically.

## 4. Key Security Assumptions
1. **NEXUS_MASTER_KEY**: This is a 32-byte AES-GCM key used to envelope-encrypt database secrets (e.g., Agent API Keys). If you lose this key, you lose access to all connected agents for that deployment.
   *Generation:* `python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"`
2. **SECRET_KEY**: A random string for JWT session token signing.
   *Generation:* `openssl rand -hex 32`

## 5. First Production Run
1. Run `./infra/prod/scripts/install_docker.sh` then log out and log back in.
2. Run `./infra/prod/scripts/bootstrap_host.sh`.
3. Copy your `.env.example` to `infra/prod/env/nexus.env` and fill all secrets.
4. Run `./infra/prod/scripts/deploy.sh` to build, spin up, and migrate the DB.
5. Setup the SystemD auto-start:
   ```bash
   sudo cp infra/prod/systemd/nexus-compose.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now nexus-compose
   ```

## 6. Upgrade & Rollback Strategy
Instead of mutating the live container, our `deploy.sh`:
- Pulls new code
- Rebuilds container images locally
- Recreates only changed containers (Docker Compose standard behavior)
- Runs Alembic Migrations
- Runs local healthchecks against API readiness.

If `deploy.sh` healthchecks fail, you should immediately rollback git to the previous commit and re-run `deploy.sh`. 
Note: If a database migration was applied and fails backward compatibility, you must restore from the latest backup (see `BACKUPS.md`).
