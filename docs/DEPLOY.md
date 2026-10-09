# AWS Setup + Deploy Guide (Epics 2–6) — do this when ready

## Epic 2: Account
1. Create AWS account, sign in to console, select `us-east-1` (must match `AWS_REGION` in `.env`).
2. Enable MFA on root; create admin IAM user for daily use.

## Epic 3: IAM role for EC2
1. Create role `StockerEC2Role` for EC2 (trusted entity `ec2.amazonaws.com`).
2. Attach inline policy from `deploy/iam-stocker-ec2-policy.json` (scoped to `stocker_*` tables + 2 SNS topics, least privilege).
3. You will attach this role at instance launch (Epic 5).

### Troven Labs variation (validated lab)
The lab checker (task 2) expects a role literally named **`StudentUser`** with
**only** the AWS managed policies **`AmazonEC2FullAccess`** +
**`AmazonDynamoDBFullAccess`** — no extra/SNS policies, or the "only" check may
fail. Region must be **N Virginia (us-east-1)**. The app degrades gracefully
without SNS publish rights (missed notifications are logged, trading still works).
`deploy/iam-stocker-ec2-policy.json` / `iam-trust-policy.json` remain the
best-practice reference for non-lab deployments.

### Troven Labs SNS names (task 4)
Create **Standard** topics exactly named **`StockerUserAccountTopic`** and
**`StockerTransactionTopic`**, each with a confirmed **Email** subscription.
Save both Topic ARNs — on EC2 they become `SNS_USER_TOPIC_ARN` (user account
topic) and `SNS_TXN_TOPIC_ARN` (transaction topic) in `.env`.

## Epic 4: SNS topics
```bash
aws sns create-topic --name stocker-user-events --region us-east-1
aws sns create-topic --name stocker-txn-events --region us-east-1
aws sns subscribe --topic-arn <user-topic-arn> --protocol email --notification-endpoint you@example.com --region us-east-1
aws sns subscribe --topic-arn <txn-topic-arn> --protocol email --notification-endpoint you@example.com --region us-east-1
```
Confirm both email subscriptions. Put the ARNs in `.env` as `SNS_USER_TOPIC_ARN` / `SNS_TXN_TOPIC_ARN`.

## Epic 5: EC2 instance
- AMI: Amazon Linux 2023, type `t2.micro`, IAM instance profile = `StockerEC2Role`.
- Security group inbound: `22/tcp` from your IP only; `5000/tcp` (or `80`) from `0.0.0.0/0`. Outbound: all.
- Key pair for SSH.

### Troven Labs variation (task 1)
- AMI: **Amazon Linux 2** (matches `deploy/user-data.sh`, which uses `yum`; Ubuntu would need `apt` edits), type **`t2.micro`**, region N Virginia.
- Create + download a key pair at launch (required by the wizard even if you connect via browser).
- Security group: allow `22/tcp` and custom TCP **`5000`** (Flask) from `0.0.0.0/0`.
- Attach the role **after** launch: instance → **Actions → Security → Modify IAM role** → choose **`StudentUser`** → Update.
- Connect via **EC2 Instance Connect** (browser terminal): select instance → **Connect → EC2 Instance Connect → Connect**.

## Epic 6: Deploy
```bash
ssh -i key.pem ec2-user@<EC2_PUBLIC_IP>
# option A: manual — follow deploy/user-data.sh steps
# option B: paste deploy/user-data.sh (with repo URL filled) as instance user-data
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python setup_dynamodb.py   # uses IAM role, no keys needed
sudo cp deploy/stocker.service /etc/systemd/system/stocker.service
sudo systemctl enable --now stocker
curl http://localhost:5000/health
```
`.env` on EC2 contains only `FLASK_SECRET_KEY`, `AWS_REGION`, `SNS_*_ARN`, `FLASK_PORT`, `FLASK_DEBUG=0`. Never put AWS keys on EC2.

### Troven Labs variation (task 5, via EC2 Instance Connect browser terminal)
Tables already exist from task 3 — the script will skip creation and only seed stocks.
```bash
sudo yum update -y
sudo yum install -y python3 python3-pip git
# confirm the StudentUser role is attached (empty output = go back to Epic 5 step):
curl -s http://169.254.169.254/latest/meta-data/iam/info
git clone https://github.com/tester248/stocker.git
cd stocker
pip3 install -r requirements.txt
python3 -c "import secrets; print(secrets.token_hex(32))"  # generate secret, paste below
cat > .env <<'EOF'
FLASK_SECRET_KEY=<paste-generated-secret>
AWS_REGION=us-east-1
FLASK_DEBUG=0
FLASK_PORT=5000
SNS_USER_TOPIC_ARN=<arn-of-StockerUserAccountTopic>
SNS_TXN_TOPIC_ARN=<arn-of-StockerTransactionTopic>
EOF
python3 setup_dynamodb.py
nohup python3 app.py > flask.log 2>&1 &
curl http://localhost:5000/health
```
Then open `http://<EC2-PUBLIC-IP>:5000` in your browser (plain `http`, not `https`). Keep the app running while hitting task 5 Validate.
