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

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_COMMAND = os.getenv("MQTT_TOPIC_COMMAND", "Irrigation_Command")
MQTT_TOPIC_CONFIRM = os.getenv("MQTT_TOPIC_CONFIRM", "Irrigation_Confirm")

# Initialize AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
queue_url = sqs.get_queue_url(QueueName=SQS_ALERTS_QUEUE)["QueueUrl"]

# Global variable for irrigation confirmation
irrigation_confirmed = False

# Configure MQTT Client
client = mqtt.Client()
client.max_inflight_messages_set(20)  # Aumenta il numero massimo di messaggi in volo

def on_mqtt_message(client, userdata, msg):
    """Handles incoming MQTT messages for irrigation confirmation.
       If the message contains "status": "done", sets irrigation_confirmed = True."""
    global irrigation_confirmed
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        smartpot_id = payload.get("smartpot_id")
        status = payload.get("status")

        if status == "done":
            irrigation_confirmed = True
    except Exception as e:
        print(f"Error processing MQTT confirmation message: {e}")

def send_irrigation_command(smartpot_id):
    """Sends an MQTT command to start irrigation.
       Uses QoS 2 to guarantee exactly-once delivery.
       Subscribes to the MQTT confirmation topic (Irrigation_Confirm)."""

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC_CONFIRM, qos=2)
    payload = json.dumps({"smartpot_id": smartpot_id, "action": "start"})
    client.publish(MQTT_TOPIC_COMMAND, payload, qos=2)

def update_last_irrigation(smartpot_id):
    """Updates the last_irrigation timestamp in DynamoDB for the given SmartPot."""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dynamodb.update_item(
        TableName=DYNAMODB_TABLE,
        Key={"smartpot_id": {"S": smartpot_id}},
        UpdateExpression="SET last_irrigation = :timestamp",
        ExpressionAttributeValues={":timestamp": {"S": timestamp}}
    )

def send_alert(smartpot_id, issue_type):
    """Sends an alert message to the SQS queue.
       Used for both successful and failed irrigation events."""

    alert_msg = json.dumps({
        "smartpot_id": smartpot_id,
        "issue": issue_type
    })
    sqs.send_message(QueueUrl=queue_url, MessageBody=alert_msg)

def lambda_handler(event, context):
    """AWS Lambda handler for irrigation activation."""

    global irrigation_confirmed
    irrigation_confirmed = False

    os.putenv('TZ', 'Europe/Rome')
    time.tzset()

    try:
        smartpot_id = None

        if "Records" in event:  # Triggered by SQS (processSensorData detected dry soil)
            for record in event["Records"]:
                message = json.loads(record["body"])
                smartpot_id = message.get("smartpot_id")
                send_irrigation_command(smartpot_id)

        elif event.get("httpMethod") == "POST":  # Triggered manually via API Gateway (Bot Telegram)
            body = json.loads(event["body"])
            smartpot_id = body.get("smartpot_id")
            if not smartpot_id:
                return {"statusCode": 400, "body": json.dumps({"error": "smartpot_id is required"})}

            send_irrigation_command(smartpot_id)

        client.on_message = on_mqtt_message

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": "MQTT connection failed"})}

        client.subscribe(MQTT_TOPIC_CONFIRM, qos=2)

        for _ in range(20):
            client.loop()
            if irrigation_confirmed:
                update_last_irrigation(smartpot_id)
                send_alert(smartpot_id, "irrigation_completed")
                return {"statusCode": 200, "body": json.dumps({"message": "Irrigation completed successfully"})}
            time.sleep(0.5)

        # After 10 seconds, it sends an error
        send_alert(smartpot_id, "irrigation_error")
        return {"statusCode": 500, "body": json.dumps({"error": "Irrigation confirmation not received"})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
