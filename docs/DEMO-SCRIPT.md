# Stocker Demo Video — Shot Script (~4 min)

Target: one continuous screen recording proving Epics 1, 3, 4, 5, 6, 7.
Pre-checks: app live (`curl http://localhost:5000/health`), logged out, inbox open in a second tab, AWS console open in a third.

## Act 1 — App tour (Epic 1, 7) ~2 min
1. **Homepage** (`http://<EC2-IP>:5000`): scroll hero + 3 feature cards. Say: Flask backend, paper trading, bento dashboard.
2. **Signup**: create a new trader live. Note SNS signup mail arrives (cut to inbox).
3. **Login** → trader dashboard: point out portfolio value, holdings table, watchlist, transaction feed.
4. **Buy 2× INFY**: show success flash, holdings row appears, portfolio value updates, transaction logged COMPLETED.
5. **Sell 1× INFY**: holdings decrease, second transaction appears.
6. **Login as admin** (or switch): users table, add-stock form, all transactions.

## Act 2 — AWS proof (Epics 3, 4, 5, 6) ~2 min
7. **EC2 console**: running `t2.micro` instance, `StudentUser` in IAM role field, security group with 5000 (+80).
8. **Terminal** (Instance Connect): `ps` Flask running, `curl /health` → `{"status":"ok"}`.
9. **DynamoDB console**: 4 `stocker_*` tables; open `stocker_transactions` → the buy/sell rows from Act 1.
10. **SNS console**: both topics, Confirmed email subscriptions.
11. **Inbox**: signup + buy + sell notification mails.

## Narration tips
- State the Epic number per shot ("Epic 4: notifications via SNS...").
- Keep mouse movement slow; zoom to 125% for readability.
- Upload unlisted; submit that URL as the SkillWallet Demo Link (never the EC2 IP — it dies with the lab).
