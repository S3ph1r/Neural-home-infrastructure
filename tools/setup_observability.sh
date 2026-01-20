#!/bin/bash
# Neural-Home Observability Setup Script
# Run this from the Brain VM (192.168.1.100)
# Targets: 192.168.1.103 (Observability LXC)

TARGET_IP="192.168.1.103"
TARGET_USER="root"
PROJECT_DIR="/root/observability"

echo "Neural-Home Observability Deployment"
echo "Target: $TARGET_IP"

# 1. Check Connectivity
echo "[1/4] Checking connectivity..."
ping -c 1 $TARGET_IP > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: Cannot ping $TARGET_IP. Is the LXC running?"
    exit 1
fi

# 2. Install Docker (Remote)
echo "[2/4] Installing Docker on remote host..."
# Install prereqs first
ssh -o StrictHostKeyChecking=no $TARGET_USER@$TARGET_IP "apt update && apt install -y curl"
ssh -o StrictHostKeyChecking=no $TARGET_USER@$TARGET_IP "curl -fsSL https://get.docker.com | sh"

# 3. Copy Configuration
echo "[3/4] Copying configuration..."
ssh -o StrictHostKeyChecking=no $TARGET_USER@$TARGET_IP "mkdir -p $PROJECT_DIR"
scp -o StrictHostKeyChecking=no -r infrastructure/observability/* $TARGET_USER@$TARGET_IP:$PROJECT_DIR/

# 4. Start Stack
echo "[4/4] Starting Docker Stack..."
ssh -o StrictHostKeyChecking=no $TARGET_USER@$TARGET_IP "cd $PROJECT_DIR && docker compose up -d"

echo "SUCCESS! Grafana should be available at http://$TARGET_IP:3000"
echo "Default Creds: admin/admin"
