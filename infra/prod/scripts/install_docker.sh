#!/usr/bin/env bash
set -eo pipefail

echo "========================================"
echo "    Installing Docker & Docker Compose  "
echo "========================================"

if command -v docker &> /dev/null; then
  echo "Docker is already installed. Versions:"
  docker --version
  docker compose version
  exit 0
fi

echo "Updating apt packages..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

echo "Adding Docker's official GPG key..."
sudo mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "Setting up repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "Installing Docker Engine and Compose..."
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "Enabling Docker service..."
sudo systemctl enable docker
sudo systemctl start docker

echo "Adding current user to docker group..."
sudo usermod -aG docker $USER
echo "Done. Please log out and back in, or run 'newgrp docker'."
