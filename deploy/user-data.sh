#!/bin/bash
# Epic 6: EC2 bootstrap — Amazon Linux 2023. Run as ec2-user (or via user-data).
set -eux
sudo yum update -y
sudo yum install -y python3 python3-pip git
cd /home/ec2-user
if [ ! -d stocker ]; then
  git clone <YOUR_REPO_URL> stocker
fi
cd stocker
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# Create production .env if missing (never commit this file).
# No AWS keys here — the instance IAM role (StockerEC2Role) provides credentials.
if [ ! -f .env ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > .env <<EOF
FLASK_SECRET_KEY=${SECRET}
AWS_REGION=us-east-1
FLASK_DEBUG=0
FLASK_PORT=5000
SNS_USER_TOPIC_ARN=
SNS_TXN_TOPIC_ARN=
EOF
  echo "Created .env — fill in SNS_*_ARN values, then restart: sudo systemctl restart stocker"
fi
./venv/bin/python setup_dynamodb.py
sudo cp deploy/stocker.service /etc/systemd/system/stocker.service
sudo systemctl daemon-reload
sudo systemctl enable --now stocker
