import json
import os
import boto3

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "SmartPotData")

# Initialize AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

def get_latest_data():
    """Fetches the latest data from DynamoDB for each pot and returns structured JSON."""
    try:
        # Scan the table for all available records
        response = dynamodb.scan(TableName=DYNAMODB_TABLE)

        # If no items are found, return a 404 response
        if "Items" not in response or not response["Items"]:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "No data found in the table."})
            }

        # Format the data into a structured list
        pots_data = []
        for item in response["Items"]:
            pots_data.append({
                "smartpot_id": item["smartpot_id"]["S"],  # Pot identifier (e.g., Fragola, Basilico)
                "temperature": item["temperature"]["S"],
                "humidity": item["humidity"]["S"],
                "soil_moisture": item["soil_moisture"]["S"],
                "last_irrigation": item.get("last_irrigation", {}).get("S", "N/A"),
                "measure_date": item.get("measure_date", {}).get("S", "N/A")
            })

        # Return structured data
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"latestData": pots_data})
        }

    except Exception as e:
        print(f"Error in getLatestData: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def lambda_handler(event, context):
    """Handles API Gateway request to fetch the latest pot data."""
    return get_latest_data()
