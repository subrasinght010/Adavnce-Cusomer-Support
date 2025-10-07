#!/bin/bash

# AI Agent Installation Script for Ubuntu/Debian

set -e

echo "=========================================="
echo "AI Communication Agent - Installation"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Variables
APP_USER="www-data"
APP_DIR="/opt/ai-agent"
SERVICE_NAME="ai-agent"

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3.9 \
    python3.9-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    supervisor \
    git \
    curl \
    build-essential

# Create application directory
echo "Creating application directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# Copy application files
echo "Copying application files..."
# Assuming you're running from the repo directory
cp -r /path/to/your/repo/* $APP_DIR/

# Create virtual environment
echo "Creating virtual environment..."
python3.9 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "Creating data directories..."
mkdir -p audio_data chroma_db knowledge_base
chown -R $APP_USER:$APP_USER $APP_DIR

# Setup PostgreSQL database
echo "Setting up PostgreSQL database..."
sudo -u postgres psql <<EOF
CREATE DATABASE aiagent_db;
CREATE USER aiagent WITH PASSWORD 'change_this_password';
GRANT ALL PRIVILEGES ON DATABASE aiagent_db TO aiagent;
\q
EOF

# Copy environment file
echo "Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Please edit /opt/ai-agent/.env with your configuration"
fi

# Run database migrations
echo "Running database migrations..."
.venv/bin/alembic upgrade head

# Setup systemd service
echo "Setting up systemd service..."
cp deployment/ai-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# Setup Nginx
echo "Setting up Nginx..."
if [ -f deployment/nginx.conf ]; then
    cp deployment/nginx.conf /etc/nginx/sites-available/ai-agent
    ln -sf /etc/nginx/sites-available/ai-agent /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
fi

# Install Ollama
echo "Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull mistral
fi

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit configuration: nano $APP_DIR/.env"
echo "2. Start service: systemctl start $SERVICE_NAME"
echo "3. Check status: systemctl status $SERVICE_NAME"
echo "4. View logs: journalctl -u $SERVICE_NAME -f"
echo ""
echo "⚠️  Don't forget to configure Twilio webhooks!"
echo ""