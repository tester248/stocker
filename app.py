"""Stocker — Flask backend + DynamoDB + SNS. Epic 1 Story 1 & 2."""
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

# ---------- AWS Configuration ----------
# For local development - use environment variables.
# For EC2 deployment with IAM role - credentials come from the instance profile,
# only region is needed. boto3.Session picks up env creds or IAM role automatically.
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

boto3_session = boto3.Session(region_name=AWS_REGION)

# Create DynamoDB resource
dynamodb = boto3_session.resource("dynamodb")

# Define table names
USER_TABLE = "stocker_users"
STOCK_TABLE = "stocker_stocks"
TRANSACTION_TABLE = "stocker_transactions"
PORTFOLIO_TABLE = "stocker_portfolio"

# Create SNS client (reuse the same session so IAM-role mode works)
sns = boto3_session.client("sns")

# SNS Topic ARNs (from environment — never hardcode)
USER_ACCOUNT_TOPIC_ARN = os.environ.get("SNS_USER_TOPIC_ARN", "")
TRANSACTION_TOPIC_ARN = os.environ.get("SNS_TXN_TOPIC_ARN", "")


# ---------- Helpers: serialization ----------
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)


def clean_dynamo_response(response):
    """Convert DynamoDB response to plain Python dict."""
    if not response:
        return None
    return json.loads(json.dumps(response, cls=DecimalEncoder))


def send_notification(topic_arn, subject, message, attributes=None):
    """Send an SNS notification. Returns True on success, False otherwise."""
    if not topic_arn:
        print(f"Warning: Missing SNS topic ARN for notification: {subject}")
        return False
    try:
        kwargs = {
            "TopicArn": topic_arn,
            "Subject": subject[:100],
            "Message": message,
        }
        if attributes:
            kwargs["MessageAttributes"] = attributes
        sns.publish(**kwargs)
        return True
    except Exception as e:
        print(f"SNS notification failed: {str(e)}")
        return False


# ---------- Helpers: data access ----------
def get_table(name):
    return dynamodb.Table(name)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_user_by_email(email):
    try:
        resp = get_table(USER_TABLE).query(
            IndexName="email-index",
            KeyConditionExpression="email = :e",
            ExpressionAttributeValues={":e": email.lower().strip()},
            Limit=1,
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    except ClientError as e:
        print(f"DynamoDB get_user_by_email failed: {e}")
        return None


def get_user_by_id(user_id):
    try:
        resp = get_table(USER_TABLE).get_item(Key={"id": user_id})
        return resp.get("Item")
    except ClientError as e:
        print(f"DynamoDB get_user_by_id failed: {e}")
        return None


def get_stock_by_symbol(symbol):
    try:
        resp = get_table(STOCK_TABLE).query(
            IndexName="symbol-index",
            KeyConditionExpression="symbol = :s",
            ExpressionAttributeValues={":s": symbol.upper().strip()},
            Limit=1,
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    except ClientError as e:
        print(f"DynamoDB get_stock_by_symbol failed: {e}")
        return None


def get_stock_by_id(stock_id):
    try:
        resp = get_table(STOCK_TABLE).get_item(Key={"id": stock_id})
        return resp.get("Item")
    except ClientError as e:
        print(f"DynamoDB get_stock_by_id failed: {e}")
        return None


def get_holding(user_id, stock_id):
    """Fetch one portfolio row via user_stock-index."""
    try:
        resp = get_table(PORTFOLIO_TABLE).query(
            IndexName="user_stock-index",
            KeyConditionExpression="user_id = :u AND stock_id = :s",
            ExpressionAttributeValues={":u": user_id, ":s": stock_id},
            Limit=1,
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    except ClientError as e:
        print(f"DynamoDB get_holding failed: {e}")
        return None


def get_user_portfolio(user_id):
    try:
        resp = get_table(PORTFOLIO_TABLE).query(
            IndexName="user_id-index",
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": user_id},
        )
        return resp.get("Items", [])
    except ClientError as e:
        print(f"DynamoDB get_user_portfolio failed: {e}")
        return []


def get_user_transactions(user_id, limit=20):
    try:
        resp = get_table(TRANSACTION_TABLE).query(
            IndexName="user_id-index",
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": user_id},
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])
    except ClientError as e:
        print(f"DynamoDB get_user_transactions failed: {e}")
        return []


def record_transaction(user_id, stock_id, action, price, quantity, status="COMPLETED"):
    txn = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "stock_id": stock_id,
        "action": action,
        "price": Decimal(str(price)),
        "quantity": Decimal(str(quantity)),
        "status": status,
        "transaction_date": now_iso(),
    }
    get_table(TRANSACTION_TABLE).put_item(Item=txn)
    return txn


def build_enriched_portfolio(user_id):
    """Return (enriched_holdings, total_value) with live price + P&L.

    Shared by /trader/dashboard and /portfolio so both templates
    receive the same holding shape.
    """
    holdings = get_user_portfolio(user_id)
    enriched = []
    total_value = Decimal("0")
    for h in holdings:
        stock = get_stock_by_id(h["stock_id"])
        if not stock:
            continue
        qty = Decimal(str(h.get("quantity", 0)))
        avg = Decimal(str(h.get("average_price", 0)))
        live = Decimal(str(stock.get("price", 0)))
        market_value = qty * live
        total_value += market_value
        enriched.append({
            "symbol": stock.get("symbol"),
            "name": stock.get("name"),
            "quantity": float(qty),
            "average_price": float(avg),
            "live_price": float(live),
            "market_value": float(market_value),
            "pnl": float((live - avg) * qty),
        })
    return enriched, total_value


# ---------- Auth decorators ----------
def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Access denied for your role.", "danger")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return deco


def current_user():
    if "user_id" not in session:
        return None
    return get_user_by_id(session["user_id"])


# ---------- Routes: pages ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "trader").strip().lower()
        if role not in ("trader", "admin"):
            role = "trader"
        if not username or not email or len(password) < 6:
            flash("Provide username, valid email and password (min 6 chars).", "danger")
            return render_template("signup.html")
        if get_user_by_email(email):
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))
        user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "is_active": True,
            "created_at": now_iso(),
        }
        try:
            get_table(USER_TABLE).put_item(Item=user)
        except ClientError as e:
            flash(f"Registration failed: {e.response['Error']['Message']}", "danger")
            return render_template("signup.html")
        send_notification(
            USER_ACCOUNT_TOPIC_ARN,
            "Stocker: new signup",
            f"New user registered: {username} <{email}> role={role}",
        )
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        user = get_user_by_email(email)
        if not user or not check_password_hash(user.get("password_hash", ""), password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")
        if not user.get("is_active", True):
            flash("Account is deactivated. Contact admin.", "danger")
            return render_template("login.html")
        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user.get("role", "trader")
        session["username"] = user.get("username", "")
        send_notification(
            USER_ACCOUNT_TOPIC_ARN,
            "Stocker: user login",
            f"User logged in: {user.get('username')} <{email}> at {now_iso()}",
        )
        flash(f"Welcome back, {user.get('username')}!", "success")
        if session["role"] == "admin":
            return redirect(url_for("dashboard_admin"))
        return redirect(url_for("dashboard_trader"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out securely.", "info")
    return redirect(url_for("index"))


# ---------- Routes: dashboards ----------
@app.route("/admin/dashboard")
@login_required(role="admin")
def dashboard_admin():
    users = get_table(USER_TABLE).scan(Limit=100).get("Items", [])
    stocks = get_table(STOCK_TABLE).scan(Limit=100).get("Items", [])
    txns = get_table(TRANSACTION_TABLE).scan(Limit=50).get("Items", [])
    return render_template(
        "dashboard_admin.html",
        users=clean_dynamo_response(users),
        stocks=clean_dynamo_response(stocks),
        transactions=clean_dynamo_response(txns),
        user=current_user(),
    )


@app.route("/trader/dashboard")
@login_required(role="trader")
def dashboard_trader():
    user_id = session["user_id"]
    stocks = get_table(STOCK_TABLE).scan(Limit=100).get("Items", [])
    enriched, total_value = build_enriched_portfolio(user_id)
    txns = get_user_transactions(user_id)
    return render_template(
        "dashboard_trader.html",
        stocks=clean_dynamo_response(stocks),
        holdings=enriched,
        total_value=float(total_value),
        transactions=clean_dynamo_response(txns),
        user=current_user(),
    )


@app.route("/portfolio")
@login_required()
def portfolio():
    user_id = session["user_id"]
    enriched, total_value = build_enriched_portfolio(user_id)
    txns = get_user_transactions(user_id, limit=50)
    return render_template(
        "dashboard_trader.html",
        stocks=clean_dynamo_response(get_table(STOCK_TABLE).scan(Limit=100).get("Items", [])),
        holdings=enriched,
        total_value=float(total_value),
        transactions=clean_dynamo_response(txns),
        user=current_user(),
        view="portfolio",
    )


# ---------- Routes: trading ----------
@app.route("/buy", methods=["GET", "POST"])
@login_required()
def buy_stock():
    if request.method == "POST":
        symbol = request.form.get("symbol", "").upper().strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0
        if not symbol or quantity <= 0:
            flash("Enter a valid symbol and quantity > 0.", "danger")
            return render_template("buy_stock.html")
        stock = get_stock_by_symbol(symbol)
        if not stock:
            record_transaction(session["user_id"], symbol, "BUY", 0, quantity, status="FAILED")
            flash(f"Stock {symbol} not found.", "danger")
            return render_template("buy_stock.html")
        price = Decimal(str(stock["price"]))
        user_id, stock_id = session["user_id"], stock["id"]
        holding = get_holding(user_id, stock_id)
        try:
            if holding:
                old_qty = Decimal(str(holding["quantity"]))
                old_avg = Decimal(str(holding["average_price"]))
                new_qty = old_qty + Decimal(str(quantity))
                new_avg = (old_qty * old_avg + Decimal(str(quantity)) * price) / new_qty
                get_table(PORTFOLIO_TABLE).update_item(
                    Key={"id": holding["id"]},
                    UpdateExpression="SET quantity = :q, average_price = :a, updated_at = :u",
                    ExpressionAttributeValues={
                        ":q": new_qty, ":a": new_avg, ":u": now_iso()},
                )
            else:
                get_table(PORTFOLIO_TABLE).put_item(Item={
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "stock_id": stock_id,
                    "quantity": Decimal(str(quantity)),
                    "average_price": price,
                    "updated_at": now_iso(),
                })
            record_transaction(user_id, stock_id, "BUY", price, quantity)
        except ClientError as e:
            flash(f"Buy failed: {e.response['Error']['Message']}", "danger")
            return render_template("buy_stock.html")
        send_notification(
            TRANSACTION_TOPIC_ARN,
            f"Stocker: BUY {symbol}",
            f"User {session.get('username')} bought {quantity}x {symbol} @ {price}",
        )
        flash(f"Bought {quantity}x {symbol} @ {price}", "success")
        return redirect(url_for("dashboard_trader" if session.get("role") == "trader" else "dashboard_admin"))
    stocks = get_table(STOCK_TABLE).scan(Limit=100).get("Items", [])
    return render_template("buy_stock.html", stocks=clean_dynamo_response(stocks))


@app.route("/sell", methods=["GET", "POST"])
@login_required()
def sell_stock():
    if request.method == "POST":
        symbol = request.form.get("symbol", "").upper().strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0
        if not symbol or quantity <= 0:
            flash("Enter a valid symbol and quantity > 0.", "danger")
            return render_template("sell_stock.html")
        stock = get_stock_by_symbol(symbol)
        if not stock:
            flash(f"Stock {symbol} not found.", "danger")
            return render_template("sell_stock.html")
        user_id, stock_id = session["user_id"], stock["id"]
        holding = get_holding(user_id, stock_id)
        held = int(float(str(holding["quantity"]))) if holding else 0
        if not holding or held < quantity:
            record_transaction(user_id, stock_id, "SELL", stock["price"], quantity, status="FAILED")
            flash(f"Insufficient holdings. You own {held}x {symbol}.", "danger")
            return render_template("sell_stock.html")
        price = Decimal(str(stock["price"]))
        try:
            new_qty = Decimal(str(held)) - Decimal(str(quantity))
            if new_qty == 0:
                get_table(PORTFOLIO_TABLE).delete_item(Key={"id": holding["id"]})
            else:
                get_table(PORTFOLIO_TABLE).update_item(
                    Key={"id": holding["id"]},
                    UpdateExpression="SET quantity = :q, updated_at = :u",
                    ExpressionAttributeValues={":q": new_qty, ":u": now_iso()},
                )
            record_transaction(user_id, stock_id, "SELL", price, quantity)
        except ClientError as e:
            flash(f"Sell failed: {e.response['Error']['Message']}", "danger")
            return render_template("sell_stock.html")
        send_notification(
            TRANSACTION_TOPIC_ARN,
            f"Stocker: SELL {symbol}",
            f"User {session.get('username')} sold {quantity}x {symbol} @ {price}",
        )
        flash(f"Sold {quantity}x {symbol} @ {price}", "success")
        return redirect(url_for("dashboard_trader" if session.get("role") == "trader" else "dashboard_admin"))
    # Prefill holdings for dropdown
    holdings = get_user_portfolio(session["user_id"])
    owned = []
    for h in holdings:
        s = get_stock_by_id(h["stock_id"])
        if s:
            owned.append({"symbol": s["symbol"], "quantity": h["quantity"]})
    return render_template("sell_stock.html", holdings=clean_dynamo_response(owned))


# ---------- Routes: service pages + admin stock add ----------
@app.route("/service-details-<n>")
def service_details(n):
    return render_template(f"service-details-{n}.html")


@app.route("/admin/add-stock", methods=["POST"])
@login_required(role="admin")
def add_stock():
    symbol = request.form.get("symbol", "").upper().strip()
    name = request.form.get("name", "").strip()
    try:
        price = Decimal(request.form.get("price", "0"))
    except Exception:
        price = Decimal("0")
    if not symbol or not name or price <= 0:
        flash("Symbol, name and price > 0 required.", "danger")
        return redirect(url_for("dashboard_admin"))
    if get_stock_by_symbol(symbol):
        flash(f"{symbol} already exists.", "warning")
        return redirect(url_for("dashboard_admin"))
    get_table(STOCK_TABLE).put_item(Item={
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "name": name,
        "price": price,
        "market_cap": Decimal(request.form.get("market_cap", "0") or "0"),
        "sector": request.form.get("sector", ""),
        "industry": request.form.get("industry", ""),
        "date_added": now_iso(),
        "user_id": session["user_id"],
    })
    flash(f"Stock {symbol} added.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("index.html"), 500


@app.cli.command("create-admin")
def create_admin():
    """Create an admin user without the signup form. Usage: flask create-admin"""
    import getpass
    username = input("Username: ").strip()
    email = input("Email: ").lower().strip()
    password = getpass.getpass("Password (min 6): ")
    if not username or not email or len(password) < 6:
        print("Invalid input.")
        return
    if get_user_by_email(email):
        print("Email already registered.")
        return
    get_table(USER_TABLE).put_item(Item={
        "id": str(uuid.uuid4()),
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": "admin",
        "is_active": True,
        "created_at": now_iso(),
    })
    print(f"Admin {email} created.")


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
