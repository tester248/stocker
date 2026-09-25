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
# .env on EC2 needs ONLY: FLASK_SECRET_KEY, AWS_REGION, SNS_*_ARN, FLASK_PORT.
# No AWS keys — the instance IAM role (StockerEC2Role) provides credentials.
./venv/bin/python setup_dynamodb.py
sudo cp deploy/stocker.service /etc/systemd/system/stocker.service
sudo systemctl daemon-reload
sudo systemctl enable --now stocker
