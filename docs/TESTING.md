# Epic 7 — Functional Testing Checklist

Run offline suite first (no AWS needed):

```bash
pip install -r requirements.txt
pytest -q
```

Expected: 9 passed.

## Manual scenarios (against real DynamoDB once AWS is set up)

1. **Auth**
   - [ ] Signup creates `stocker_users` row with `password_hash` (not plaintext), SNS signup email received
   - [ ] Duplicate email → redirected to login with warning
   - [ ] Wrong password → "Invalid email or password", no session
   - [ ] Inactive user (`is_active=false`) blocked with message
   - [ ] Admin → `/admin/dashboard`, trader → `/trader/dashboard`; cross-role URL → denied
   - [ ] `/buy` logged-out → 302 to `/login`; `/logout` clears session
2. **Trade execution**
   - [ ] Buy new symbol → portfolio row `quantity` + `average_price` = buy price, txn `COMPLETED`
   - [ ] Buy more → weighted average correct (e.g. 2@80 + 2@120 = 4@100)
   - [ ] Buy unknown symbol → `FAILED` txn, danger flash
   - [ ] Sell partial → quantity reduced; sell all → row deleted
   - [ ] Oversell → `FAILED` txn, holdings unchanged, "Insufficient holdings"
   - [ ] SNS trade email received on buy/sell
3. **Portfolio**
   - [ ] `/trader/dashboard` and `/portfolio` show same holdings shape (symbol, qty, avg, live, value, P&L)
   - [ ] Total value = Σ qty × live price
   - [ ] Txn history newest-first (up to 20 on dashboard, 50 on portfolio)
4. **Admin**
   - [ ] Add stock appears in market list; duplicate symbol rejected
   - [ ] Dashboard counts users/stocks/txns
5. **Resilience**
   - [ ] Unset `SNS_*_ARN` → trade still succeeds, warning logged
   - [ ] `pytest` green + `python -m py_compile app.py setup_dynamodb.py` clean
