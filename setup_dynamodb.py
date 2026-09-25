"""Create Stocker DynamoDB tables + seed demo stocks. Epic 6 Story 3.

Usage:
    python setup_dynamodb.py
    python setup_dynamodb.py --seed-only
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
session = boto3.Session(region_name=AWS_REGION)
dynamodb = session.resource("dynamodb")
client = session.client("dynamodb")


def table_exists(name: str) -> bool:
    try:
        client.describe_table(TableName=name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def create_table(name, key_schema, attr_defs, gsis=()):
    if table_exists(name):
        print(f"SKIP {name} (already exists)")
        return dynamodb.Table(name)
    print(f"CREATE {name} ...")
    kwargs = {
        "TableName": name,
        "KeySchema": key_schema,
        "AttributeDefinitions": attr_defs,
        "BillingMode": "PAY_PER_REQUEST",
    }
    if gsis:
        kwargs["GlobalSecondaryIndexes"] = list(gsis)
    table = dynamodb.create_table(**kwargs)
    table.wait_until_exists()
    print(f"OK {name}")
    return table


def main(seed_only=False):
    if not seed_only:
        create_table(
            "stocker_users",
            [{"AttributeName": "id", "KeyType": "HASH"}],
            [
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "email", "AttributeType": "S"},
            ],
            gsis=[
                {
                    "IndexName": "email-index",
                    "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        create_table(
            "stocker_stocks",
            [{"AttributeName": "id", "KeyType": "HASH"}],
            [
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "symbol", "AttributeType": "S"},
            ],
            gsis=[
                {
                    "IndexName": "symbol-index",
                    "KeySchema": [{"AttributeName": "symbol", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        create_table(
            "stocker_transactions",
            [{"AttributeName": "id", "KeyType": "HASH"}],
            [
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "transaction_date", "AttributeType": "S"},
                {"AttributeName": "stock_id", "AttributeType": "S"},
            ],
            gsis=[
                {
                    "IndexName": "user_id-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "transaction_date", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "stock_id-index",
                    "KeySchema": [{"AttributeName": "stock_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )
        create_table(
            "stocker_portfolio",
            [{"AttributeName": "id", "KeyType": "HASH"}],
            [
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "stock_id", "AttributeType": "S"},
            ],
            gsis=[
                {
                    "IndexName": "user_id-index",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "user_stock-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "stock_id", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )

    # Seed stocks (idempotent via symbol check)
    stocks = [
        ("RELIANCE", "Reliance Industries", "2850.50", 1930000, "Energy", "Oil & Gas"),
        ("TCS", "Tata Consultancy Services", "4120.75", 1500000, "Technology", "IT Services"),
        ("INFY", "Infosys Ltd", "1785.20", 740000, "Technology", "IT Services"),
        ("HDFCBANK", "HDFC Bank", "1640.00", 1250000, "Financial", "Banking"),
        ("TATAMOTORS", "Tata Motors", "980.45", 350000, "Automobile", "Auto Manufacturing"),
        ("SBIN", "State Bank of India", "815.30", 730000, "Financial", "Banking"),
        ("AAPL", "Apple Inc", "232.50", 35000000, "Technology", "Consumer Electronics"),
        ("TSLA", "Tesla Inc", "248.90", 7900000, "Automobile", "EV Manufacturing"),
    ]
    table = dynamodb.Table("stocker_stocks")
    now = datetime.now(timezone.utc).isoformat()
    for i, (sym, name, price, mcap, sector, industry) in enumerate(stocks, start=1):
        existing = table.query(
            IndexName="symbol-index",
            KeyConditionExpression="symbol = :s",
            ExpressionAttributeValues={":s": sym},
        ).get("Count", 0)
        if existing:
            print(f"SKIP stock {sym}")
            continue
        table.put_item(
            Item={
                "id": f"stock-{i:02d}",
                "symbol": sym,
                "name": name,
                "price": Decimal(str(price)),
                "market_cap": Decimal(str(mcap)),
                "sector": sector,
                "industry": industry,
                "date_added": now,
            }
        )
        print(f"SEEDED {sym}")
    print("DONE")


if __name__ == "__main__":
    main(seed_only="--seed-only" in sys.argv)
