#!/bin/bash
set -e

echo "==========================================="
echo " AI-CICD-Monitor Ubuntu Setup Script"
echo "==========================================="

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo bash setup-ubuntu.sh)"
  exit 1
fi

APP_DIR="/opt/ai-cicd-monitor"
USER_NAME="ai-cicd"

echo "[1/6] Installing System Dependencies..."
apt-get update
# Install Node.js 18.x
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
apt-get install -y git python3 python3-venv python3-pip curl nginx nodejs acl

echo "[2/6] Creating Dedicated Users & Sudo Permissions..."
# Create platform user if it doesn't exist
if ! id "$USER_NAME" &>/dev/null; then
    useradd -r -s /bin/bash -m -d /home/$USER_NAME $USER_NAME
fi

# Create unprivileged runner user for user deployments
if ! id "deployrunner" &>/dev/null; then
    useradd -r -s /bin/false -m -d /home/deployrunner deployrunner
fi

# Allow ai-cicd to run commands as deployrunner without a password
echo "$USER_NAME ALL=(deployrunner) NOPASSWD: ALL" > /etc/sudoers.d/ai-cicd-deployrunner
chmod 0440 /etc/sudoers.d/ai-cicd-deployrunner

echo "[3/6] Setting Up Directory Structure..."
mkdir -p $APP_DIR
# Assuming the script is run from inside the cloned repo
cp -r * $APP_DIR/ || true
cp -r .git $APP_DIR/ 2>/dev/null || true

# Ensure necessary directories exist
mkdir -p $APP_DIR/deployment_storage
mkdir -p $APP_DIR/logs

chown -R $USER_NAME:$USER_NAME $APP_DIR
# Give deployrunner access to write inside deployment_storage
setfacl -R -m u:deployrunner:rwx $APP_DIR/deployment_storage || true

echo "[4/6] Setting Up Python Virtual Environment..."
# Run python commands as the dedicated user
sudo -u $USER_NAME bash -c "
    cd $APP_DIR
    python3 -m venv venv
    source venv/bin/activate
    pip install --no-cache-dir -r backend/requirements.txt
    pip install gunicorn
"

echo "[5/6] Configuring Systemd Daemon..."
cat > /etc/systemd/system/ai-cicd.service <<EOF
[Unit]
Description=AI-CICD-Monitor Backend
After=network.target

[Service]
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="FLASK_ENV=production"
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 --threads 4 backend.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-cicd
systemctl restart ai-cicd

echo "[6/6] Configuring Nginx Reverse Proxy..."
if [ -f "$APP_DIR/scripts/nginx.conf" ]; then
    cp $APP_DIR/scripts/nginx.conf /etc/nginx/sites-available/ai-cicd
    ln -sf /etc/nginx/sites-available/ai-cicd /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    systemctl restart nginx
else
    echo "Warning: scripts/nginx.conf not found. Skipping Nginx config."
fi

echo "==========================================="
echo " Setup Complete!"
echo "==========================================="
echo "You can check the service status using:"
echo "  sudo systemctl status ai-cicd"
