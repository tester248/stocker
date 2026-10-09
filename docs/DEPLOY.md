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
