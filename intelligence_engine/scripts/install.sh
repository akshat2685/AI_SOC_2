#!/bin/bash
# install.sh
set -e

echo "Starting AI SOC Intelligence Engine setup..."

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root"
  exit 1
fi

echo "Installing system dependencies..."
if [ -x "$(command -v apt-get)" ]; then
    apt-get update
    apt-get install -y python3 python3-pip python3-venv
elif [ -x "$(command -v dnf)" ]; then
    dnf install -y python3 python3-pip
elif [ -x "$(command -v yum)" ]; then
    yum install -y python3 python3-pip
else
    echo "Error: Unsupported package manager"
    exit 1
fi

echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found."
fi

echo "Setting up systemd service..."
cat << 'EOF' > /etc/systemd/system/intelligence_engine.service
[Unit]
Description=AI SOC Intelligence Engine
After=network.target

[Service]
User=root
WorkingDirectory=/opt/ai_soc/intelligence_engine
ExecStart=/opt/ai_soc/intelligence_engine/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable intelligence_engine.service || true
systemctl start intelligence_engine.service || true

echo "Setup complete."
