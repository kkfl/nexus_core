#!/usr/bin/env bash
set -eo pipefail

echo "========================================"
echo "      Host Bootstrap (Nexus Ubuntu)     "
echo "========================================"

# Basic UFW Firewall
echo "Setting up UFW rules..."
sudo apt-get update
sudo apt-get install -y ufw curl jq fail2ban

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow http
sudo ufw allow https
sudo ufw --force enable
echo "Firewall active."

echo "Basic fail2ban setup..."
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Setup directories
echo "Creating application directories..."
sudo mkdir -p /opt/nexus
sudo chown -R $USER:$USER /opt/nexus

# Link Caddy setup if on host (not inside container)
# We assume Caddy is installed via apt on host:
echo "Installing Caddy..."
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https 
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install caddy

echo "Host configuration complete. Next: copy repo to /opt/nexus and run deploy.sh"
