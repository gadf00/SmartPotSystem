import json
import os
import time
import boto3
import paho.mqtt.client as mqtt
from datetime import datetime

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "SmartPotData")
SQS_ALERTS_QUEUE = os.getenv("SQS_ALERTS_QUEUE", "SmartPotAlertsQueue")


MQTT_TOPIC_COMMAND = os.getenv("MQTT_TOPIC_COMMAND", "Irrigation_Command")

# Initialize AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
queue_url = sqs.get_queue_url(QueueName=SQS_ALERTS_QUEUE)["QueueUrl"]

# Configure MQTT Client
client = mqtt.Client()
client.connect("192.168.1.106",1883, 60)

def send_irrigation_command(smartpot_id):
    """Sends an MQTT message to start irrigation for a specific SmartPot."""
    payload = json.dumps({"smartpotID": smartpot_id, "action": "start"})
    client.publish(MQTT_TOPIC_COMMAND, payload)
    print(f"🚀 Sent irrigation command: {payload}")

def update_last_irrigation(smartpot_id):
    """Updates the last_irrigation timestamp in DynamoDB for the given SmartPot."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dynamodb.update_item(
        TableName=DYNAMODB_TABLE,
        Key={"smartpot_id": {"S": smartpot_id}},
        UpdateExpression="SET last_irrigation = :timestamp",
        ExpressionAttributeValues={":timestamp": {"S": timestamp}}
    )
    print(f"✅ Updated last_irrigation for {smartpot_id}: {timestamp}")

def send_alert(smartpot_id):
    """Sends an irrigation alert message to the Alerts SQS queue."""
    alert_msg = json.dumps({
        "smartpot_id": smartpot_id,
        "issue": "irrigation_triggered",
        "details": {"message": f"Irrigation started for {smartpot_id}."}
    })
    sqs.send_message(QueueUrl=queue_url, MessageBody=alert_msg)
    print(f"📢 Sent alert message to handleAlerts: {alert_msg}")

def lambda_handler(event, context):
    """AWS Lambda handler for irrigation activation."""
    os.putenv('TZ', 'Europe/Rome')
    time.tzset()

    try:
        smartpot_id = None

        if "Records" in event:  # Triggered by SQS (processSensorData detected dry soil)
            for record in event["Records"]:
                message = json.loads(record["body"])
                smartpot_id = message.get("smartpot_id")
                print(f"📥 Irrigation request received for {smartpot_id}")
                send_irrigation_command(smartpot_id)

        elif "queryStringParameters" in event:  # Triggered manually via API Gateway
            smartpot_id = event["queryStringParameters"].get("smartpot_id")
            if not smartpot_id:
                return {"statusCode": 400, "body": json.dumps({"error": "smartpot_id is required"})}
            print(f"📥 Manual irrigation activation for {smartpot_id}")
            send_irrigation_command(smartpot_id)

        # **Aggiorna il timestamp dell'irrigazione e invia l'alert immediatamente**
        update_last_irrigation(smartpot_id)
        send_alert(smartpot_id)

        return {"statusCode": 200, "body": json.dumps({"message": "Irrigation command sent successfully"})}

    except Exception as e:
        print(f"❌ Error in irrigateNow: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
