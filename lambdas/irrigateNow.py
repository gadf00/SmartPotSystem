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

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-broker")  # Usa il nome del container Mosquitto
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

def on_mqtt_message(client, userdata, msg):
    """Handles incoming MQTT messages for irrigation confirmation."""
    global irrigation_confirmed
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        smartpot_id = payload.get("smartpot_id")
        status = payload.get("status")

        if status == "done":
            irrigation_confirmed = True
            print(f"✅ Irrigation confirmed for {smartpot_id}.")
    except Exception as e:
        print(f"❌ Error processing MQTT confirmation message: {e}")

def send_irrigation_command(smartpot_id):
    """Connects to MQTT, subscribes, then sends an irrigation command."""
    
    print(f"🔌 Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print(f"✅ Successfully connected to MQTT broker!")

    client.subscribe(MQTT_TOPIC_CONFIRM)
    print(f"📡 Subscribed to MQTT topic: {MQTT_TOPIC_CONFIRM}")

    payload = json.dumps({"smartpot_id": smartpot_id, "action": "start"})
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
    """Sends an irrigation completion alert message to the Alerts SQS queue."""
    alert_msg = json.dumps({
        "smartpot_id": smartpot_id,
        "issue": "irrigation_completed"
    })
    sqs.send_message(QueueUrl=queue_url, MessageBody=alert_msg)
    print(f"📢 Sent irrigation completion alert to handleAlerts: {alert_msg}")

def lambda_handler(event, context):
    """AWS Lambda handler for irrigation activation."""
    global irrigation_confirmed
    irrigation_confirmed = False

    os.putenv('TZ', 'Europe/Rome')
    time.tzset()

    try:
        print(f"📩 Received event: {json.dumps(event, indent=4)}")

        smartpot_id = None

        if "Records" in event:  # Triggered by SQS (processSensorData detected dry soil)
            for record in event["Records"]:
                message = json.loads(record["body"])
                smartpot_id = message.get("smartpot_id")
                print(f"📥 Irrigation request received for {smartpot_id}")
                send_irrigation_command(smartpot_id)

        elif event.get("httpMethod") == "POST":  # Triggered manually via API Gateway (Bot Telegram)
            body = json.loads(event["body"])
            smartpot_id = body.get("smartpot_id")
            if not smartpot_id:
                print("❌ ERROR: Missing smartpot_id in request body!")
                return {"statusCode": 400, "body": json.dumps({"error": "smartpot_id is required"})}
            
            print(f"📥 Manual irrigation activation for {smartpot_id}")
            send_irrigation_command(smartpot_id)

        # **Wait for MQTT confirmation (timeout: 10s)**
        client.on_message = on_mqtt_message

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print(f"✅ Successfully connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        except Exception as e:
            print(f"❌ ERROR: Failed to connect to MQTT broker: {e}")
            return {"statusCode": 500, "body": json.dumps({"error": "MQTT connection failed"})}

        client.subscribe(MQTT_TOPIC_CONFIRM)
        print(f"📡 Subscribed to MQTT topic: {MQTT_TOPIC_CONFIRM}")

        for _ in range(20):
            client.loop()
            if irrigation_confirmed:
                update_last_irrigation(smartpot_id)
                send_alert(smartpot_id)
                return {"statusCode": 200, "body": json.dumps({"message": "Irrigation completed successfully"})}
            time.sleep(0.5)

        print("❌ ERROR: No irrigation confirmation received!")
        return {"statusCode": 500, "body": json.dumps({"error": "Irrigation confirmation not received"})}

    except Exception as e:
        print(f"❌ Error in irrigateNow: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
