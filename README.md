# Stocker — Cloud-Native Paper Trading Platform

Flask + DynamoDB + SNS stock trading simulator. Secure auth, real-time (paper) trade execution, portfolio tracking. Deploys to AWS EC2 with IAM role.

## Stack
- Backend: Python 3.9+, Flask 3, boto3, Werkzeug (password hashing)
- DB: Amazon DynamoDB (on-demand, 4 tables + GSIs)
- Notifications: Amazon SNS (user events + trade events, email)
- Infra: EC2 (IAM role, no static keys), CloudWatch, S3 (future static hosting)
- Frontend: Jinja templates + modern CSS

## Quickstart (local)
```bash
pip install -r requirements.txt
cp .env.example .env   # fill FLASK_SECRET_KEY, AWS_REGION, creds, SNS ARNs
python setup_dynamodb.py
python app.py          # http://localhost:5000
```

## Tests (no AWS needed)
```bash
pytest -q   # 9 offline tests, DynamoDB/SNS stubbed
```
Manual Epic 7 checklist: `docs/TESTING.md`.

## Deploy (when AWS is ready)
Guide: `docs/DEPLOY.md`. Assets: `gunicorn.conf.py`, `deploy/stocker.service`, `deploy/user-data.sh`, `deploy/iam-stocker-ec2-policy.json`. CI: `.github/workflows/ci.yml`.

On EC2, omit `AWS_ACCESS_KEY_ID/SECRET` — the instance IAM role (`StockerEC2Role`: DynamoDB on `stocker_*` + `sns:Publish`) provides credentials.

## DynamoDB schema
| Table | PK | GSIs |
|---|---|---|
| `stocker_users` | `id` | `email-index` |
| `stocker_stocks` | `id` | `symbol-index` |
| `stocker_transactions` | `id` | `user_id-index`, `stock_id-index` |
| `stocker_portfolio` | `id` | `user_id-index`, `user_stock-index` |

ER relations (User 1→M Transaction/Portfolio, Stock 1→M Transaction/Portfolio) are enforced in app code via GSI queries. All money fields are `Decimal`.

## Routes
`/`, `/signup`, `/login`, `/logout`, `/trader/dashboard`, `/admin/dashboard`, `/portfolio`, `/buy`, `/sell`, `/admin/add-stock`, `/health`, `/service-details-N`

## SNS events
Signup, login → `SNS_USER_TOPIC_ARN`; buy, sell → `SNS_TXN_TOPIC_ARN`. Missing ARN = logged warning, trade still succeeds (graceful degrade).
