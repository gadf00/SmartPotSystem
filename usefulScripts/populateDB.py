import boto3
import json
import os
from datetime import datetime

# AWS LocalStack Configuration
LOCALSTACK_HOST = os.getenv("LOCALSTACK_HOST", "localhost")
ENDPOINT_URL = f"http://{LOCALSTACK_HOST}:4566"
REGION = "us-east-1"

# AWS Resources
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=REGION)

# SmartPotSystem Configuration
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE")

# Initial Data for Smart Pots
POTS_DATA = [
    {
        "smartpot_id": {"S": "Fragola"},
        "temperature": {"S": "20"},
        "humidity": {"S": "70"},
        "soil_moisture": {"S": "65"},
        "last_irrigation": {"S": "2025-02-23 13:20:00"},
        "measure_date": {"S": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    },
    {
        "smartpot_id": {"S": "Basilico"},
        "temperature": {"S": "22"},
        "humidity": {"S": "60"},
        "soil_moisture": {"S": "55"},
        "last_irrigation": {"S": "2025-02-23 11:30:00"},
        "measure_date": {"S": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    }
]

def populate_dynamodb():
    """Populates the DynamoDB table with initial Smart Pot data."""
    for pot in POTS_DATA:
        try:
            dynamodb.put_item(TableName=DYNAMODB_TABLE, Item=pot)
            print(f"✅ Added {pot['smartpot_id']['S']} to {DYNAMODB_TABLE}")
        except Exception as e:
            print(f"❌ Error adding {pot['smartpot_id']['S']} to {DYNAMODB_TABLE}: {e}")

if __name__ == "__main__":
    populate_dynamodb()
