#!/bin/bash
# AI-CICD-Monitor VPS Deployment Script
# Run this on a fresh Ubuntu 22.04/24.04 VPS

set -e

echo "🚀 Starting AI-CICD-Monitor VPS Setup..."

# 1. Update and install dependencies
echo "📦 Installing prerequisites (Docker, Caddy, Git)..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git debian-keyring debian-archive-keyring apt-transport-https

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
fi

# Install Caddy
if ! command -v caddy &> /dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update
    sudo apt-get install caddy -y
fi

# 2. Clone the repository
if [ ! -d "/opt/AI-CICD-Monitor" ]; then
    echo "📥 Cloning AI-CICD-Monitor..."
    # Replace with your actual repository URL
    sudo git clone https://github.com/your-username/AI-CICD-Monitor.git /opt/AI-CICD-Monitor
else
    echo "🔄 Updating existing repository..."
    cd /opt/AI-CICD-Monitor
    sudo git pull origin main
fi

cd /opt/AI-CICD-Monitor

# 3. Setup environment variables
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file..."
    echo "FLASK_ENV=production" > .env
    echo "GITHUB_WEBHOOK_SECRET=your_secret_here" >> .env
    echo "Please edit /opt/AI-CICD-Monitor/.env to set your secrets!"
fi

# 4. Start the system
echo "🐳 Starting Docker containers..."
sudo docker compose up -d --build

echo "✅ Deployment complete! AI-CICD-Monitor is running."
echo "👉 Make sure your domain's DNS A Record points to this VPS IP."
echo "👉 The system will automatically configure Caddy for new deployments."
