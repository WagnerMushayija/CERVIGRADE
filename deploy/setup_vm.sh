#!/usr/bin/env bash
# CerviGrade on a fresh Ubuntu 22.04 VM (Azure x86 or Oracle ARM). Run on the VM after copying the repo and models.
# Usage:  bash setup_vm.sh /home/azureuser/CERVIGRADE
set -euo pipefail
REPO="${1:-$HOME/CERVIGRADE}"
cd "$REPO"

sudo apt-get update
export DEBIAN_FRONTEND=noninteractive
sudo apt-get install -y python3-venv python3-pip libgl1 libglib2.0-0

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
# CPU-only torch first, so pip does not download the huge GPU build. Then the same pins as the laptop.
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r src/app/backend/requirements.txt

test -f models/efficientnetb0_cric_retrained.keras || { echo "Missing models/efficientnetb0_cric_retrained.keras"; exit 1; }
test -f models/stage2_severity_oversampled_best.pt   || { echo "Missing models/stage2_severity_oversampled_best.pt"; exit 1; }

# The classifier was saved with a newer Keras than Python 3.10 can install. This removes one unused setting from its config.
.venv/bin/python deploy/fix_keras_config.py models/efficientnetb0_cric_retrained.keras

# Secrets and settings live in one file that only this user can read.
if [ ! -f /etc/cervigrade.env ]; then
  ADMIN_PW="$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')"
  sudo tee /etc/cervigrade.env >/dev/null <<ENV
CERVIGRADE_DATA=$REPO/app_data
CERVIGRADE_ADMIN_PASSWORD=$ADMIN_PW
CERVIGRADE_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
ENV
  sudo chmod 600 /etc/cervigrade.env
  echo "Admin sign-in: admin@alustudent.com   Admin password: $ADMIN_PW   (write it down; it is not shown again)"
fi

sudo tee /etc/systemd/system/cervigrade.service >/dev/null <<UNIT
[Unit]
Description=CerviGrade
After=network.target

[Service]
User=$USER
WorkingDirectory=$REPO/src/app/backend
EnvironmentFile=/etc/cervigrade.env
ExecStart=$REPO/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
UNIT

# Azure: the inbound port is opened in the portal (network rule for TCP 8000). Oracle images also need this line:
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true

sudo systemctl daemon-reload
sudo systemctl enable --now cervigrade
sleep 60
curl -s localhost:8000/health | head -c 400; echo
echo "If using_real_model is true, the app is up at http://<public-ip>:8000/app"
