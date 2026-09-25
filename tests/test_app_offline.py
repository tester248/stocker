"""Offline tests for Stocker — no AWS credentials needed.

All DynamoDB/SNS access is stubbed. Run: pytest -q
"""
from decimal import Decimal

import pytest

import app as m


class FakeTable:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.puts = []
        self.updates = []
        self.deletes = []

    def put_item(self, Item):
        self.puts.append(Item)
        self.items.append(Item)
        return {}

    def get_item(self, Key):
        for it in self.items:
            if all(it.get(k) == v for k, v in Key.items()):
                return {"Item": it}
        return {}

    def query(self, **kwargs):
        return {"Items": self.items, "Count": len(self.items)}

    def scan(self, **kwargs):
        return {"Items": self.items, "Count": len(self.items)}

    def update_item(self, Key, UpdateExpression="", ExpressionAttributeValues=None):
        self.updates.append((Key, ExpressionAttributeValues or {}))
        return {"Attributes": {}}

    def delete_item(self, Key):
        self.deletes.append(Key)
        return {}


@pytest.fixture()
def client():
    m.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with m.app.test_client() as c:
        yield c


def login_session(client, user_id="u-1", role="trader", username="tester"):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["role"] = role
        s["username"] = username


def test_index_and_health_ok(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").get_json() == {"status": "ok"}


def test_buy_requires_login(client):
    resp = client.get("/buy")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_signup_happy_path(client, monkeypatch):
    users = FakeTable()
    monkeypatch.setattr(m, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(m, "get_table", lambda name: users)
    monkeypatch.setattr(m, "send_notification", lambda *a, **k: True)
    resp = client.post("/signup", data={
        "username": "ash", "email": "ash@example.com",
        "password": "secret123", "role": "trader",
    })
    assert resp.status_code == 302
    assert len(users.puts) == 1
    saved = users.puts[0]
    assert saved["email"] == "ash@example.com"
    assert saved["password_hash"] != "secret123"  # hashed
    assert saved["role"] == "trader"


def test_signup_duplicate_email(client, monkeypatch):
    monkeypatch.setattr(m, "get_user_by_email", lambda email: {"id": "u-9"})
    resp = client.post("/signup", data={
        "username": "x", "email": "dup@example.com", "password": "secret123",
    })
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_wrong_password(client, monkeypatch):
    from werkzeug.security import generate_password_hash
    monkeypatch.setattr(m, "get_user_by_email", lambda email: {
        "id": "u-1", "username": "t", "email": email,
        "password_hash": generate_password_hash("correct"), "role": "trader",
        "is_active": True,
    })
    resp = client.post("/login", data={"email": "t@e.com", "password": "wrong"})
    assert resp.status_code == 200
    assert b"Invalid email or password" in resp.data


def test_buy_new_position(client, monkeypatch):
    login_session(client)
    stock = {"id": "stock-03", "symbol": "INFY", "price": Decimal("100")}
    portfolio = FakeTable()
    txns = FakeTable()
    tables = {m.PORTFOLIO_TABLE: portfolio, m.TRANSACTION_TABLE: txns,
              m.STOCK_TABLE: FakeTable([stock])}

    monkeypatch.setattr(m, "get_stock_by_symbol", lambda s: stock)
    monkeypatch.setattr(m, "get_holding", lambda u, s: None)
    monkeypatch.setattr(m, "get_table", lambda name: tables[name])
    monkeypatch.setattr(m, "send_notification", lambda *a, **k: True)

    resp = client.post("/buy", data={"symbol": "INFY", "quantity": "3"})
    assert resp.status_code == 302
    assert len(portfolio.puts) == 1
    assert portfolio.puts[0]["quantity"] == Decimal("3")
    assert portfolio.puts[0]["average_price"] == Decimal("100")
    assert len(txns.puts) == 1
    assert txns.puts[0]["action"] == "BUY"


def test_buy_averages_existing_position(client, monkeypatch):
    """2 @ 80 + 2 @ 120 -> 4 @ 100."""
    login_session(client)
    stock = {"id": "stock-03", "symbol": "INFY", "price": Decimal("120")}
    holding = {"id": "p-1", "user_id": "u-1", "stock_id": "stock-03",
               "quantity": Decimal("2"), "average_price": Decimal("80")}
    portfolio = FakeTable([holding])
    txns = FakeTable()
    tables = {m.PORTFOLIO_TABLE: portfolio, m.TRANSACTION_TABLE: txns,
              m.STOCK_TABLE: FakeTable([stock])}

    monkeypatch.setattr(m, "get_stock_by_symbol", lambda s: stock)
    monkeypatch.setattr(m, "get_holding", lambda u, s: holding)
    monkeypatch.setattr(m, "get_table", lambda name: tables[name])
    monkeypatch.setattr(m, "send_notification", lambda *a, **k: True)

    resp = client.post("/buy", data={"symbol": "INFY", "quantity": "2"})
    assert resp.status_code == 302
    assert len(portfolio.updates) == 1
    vals = portfolio.updates[0][1]
    assert vals[":q"] == Decimal("4")
    assert vals[":a"] == Decimal("100")


def test_sell_insufficient_holdings(client, monkeypatch):
    login_session(client)
    stock = {"id": "stock-03", "symbol": "INFY", "price": Decimal("100")}
    txns = FakeTable()
    monkeypatch.setattr(m, "get_stock_by_symbol", lambda s: stock)
    monkeypatch.setattr(m, "get_holding", lambda u, s: None)
    monkeypatch.setattr(m, "get_table", lambda name: txns)
    resp = client.post("/sell", data={"symbol": "INFY", "quantity": "5"})
    assert resp.status_code == 200
    assert b"Insufficient holdings" in resp.data
    assert txns.puts[0]["status"] == "FAILED"


def test_enriched_portfolio_pnl(monkeypatch):
    holding = {"id": "p-1", "user_id": "u-1", "stock_id": "s-1",
               "quantity": Decimal("10"), "average_price": Decimal("90")}
    stock = {"id": "s-1", "symbol": "INFY", "name": "Infosys",
             "price": Decimal("100")}
    monkeypatch.setattr(m, "get_user_portfolio", lambda u: [holding])
    monkeypatch.setattr(m, "get_stock_by_id", lambda s: stock)
    enriched, total = m.build_enriched_portfolio("u-1")
    assert enriched[0]["market_value"] == pytest.approx(1000.0)
    assert enriched[0]["pnl"] == pytest.approx(100.0)
    assert total == Decimal("1000")
