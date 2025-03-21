import json
import os
import time
import boto3
import urllib3
from datetime import datetime

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE", "SmartPotAlertsQueue")
S3_BUCKET = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Initialize AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]

# Initialize HTTP PoolManager for Telegram API
http = urllib3.PoolManager()

def send_telegram_message(message_text):
    """Sends a notification message to a Telegram chat using the Telegram Bot API."""
    payload = {
        "text": message_text,
        "chat_id": TELEGRAM_CHAT_ID
    }
    try:
        http.request('POST', TELEGRAM_URL, body=json.dumps(payload), headers={'Content-Type': 'application/json'})
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

def save_event(smartpot_id, alert_type):
    """Saves an event in an S3 file.
       Maintains a history of alerts in events/daily_events_<smartpot_id>.json.
       Appends new events with a timestamp."""

    event_file_path = f"events/daily_events_{smartpot_id}.json"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Retrieve existing event file
        obj = s3.get_object(Bucket=S3_BUCKET, Key=event_file_path)
        events = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        events = []

    # Append new event
    events.append({"timestamp": current_time, "event_type": alert_type})

    # Save updated events to S3
    s3.put_object(Bucket=S3_BUCKET, Key=event_file_path, Body=json.dumps(events))

def process_alert(alert_message):
    """Processes an incoming alert message from an SQS queue.
       Sends the formatted message to Telegram.
       Saves the alert event in S3 for tracking."""

    smartpot_id = alert_message.get("smartpot_id", "ALL")
    alert_type = alert_message.get("issue")
    details = alert_message.get("details", {})

    if not smartpot_id:
        return

    # **Usa direttamente il messaggio fornito per `daily_report` e `manual_report`**
    if alert_type in ["daily_report", "manual_report"]:
        message = details.get("message", "ℹ️ Report notification received.")
    else:
        # **Gestione classica degli altri messaggi**
        if alert_type == "sensor_error":
            error_sensors = [key for key, value in details.items() if value == "ERR"]
            message = f"🚨 Sensor error in SmartPot {smartpot_id}.\n❌ Faulty sensors: {', '.join(error_sensors)}.\nPlease check the device."
        
        elif alert_type == "temperature_high":
            message = f"🔥 High temperature alert in SmartPot {smartpot_id}.\n🌡 Current: {details.get('temperature', 'N/A')}°C (Exceeds max limit)."

        elif alert_type == "temperature_low":
            message = f"❄️ Low temperature alert in SmartPot {smartpot_id}.\n🌡 Current: {details.get('temperature', 'N/A')}°C (Below min limit)."

        elif alert_type == "humidity_high":
            message = f"💦 High humidity alert in SmartPot {smartpot_id}.\n💧 Current: {details.get('humidity', 'N/A')}% (Exceeds max limit)."

        elif alert_type == "humidity_low":
            message = f"🏜️ Low humidity alert in SmartPot {smartpot_id}.\n💧 Current: {details.get('humidity', 'N/A')}% (Below min limit)."

        elif alert_type == "irrigation_triggered":
            message = f"💧 Irrigation activated for SmartPot {smartpot_id}."
        
        elif alert_type == "irrigation_completed":
            message = f"💧 Irrigation completed for SmartPot {smartpot_id}."
        
        elif alert_type == 'irrigation_error':
            message = f"💧 Irrigation error for SmartPot {smartpot_id}."

        elif alert_type == "soil_moisture_high":
            message = f"🌱 High soil moisture alert in SmartPot {smartpot_id}.\n💧 Moisture Level: {details.get('soil_moisture', 'N/A')}% (Above max limit)."

        else:
            message = f"ℹ️ Notification received for SmartPot {smartpot_id}: {alert_type}"

    # **Salva l'evento con timestamp**
    save_event(smartpot_id, alert_type)

    # **Invio del messaggio Telegram**
    send_telegram_message(message)

def lambda_handler(event, context):
    """AWS Lambda handler function to process alerts from SQS and send Telegram notifications."""
    
    os.putenv("TZ", "Europe/Rome")
    time.tzset()

    try:
        if "Records" in event:
            for record in event["Records"]:
                alert_message = json.loads(record["body"])
                process_alert(alert_message)
        
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Notifications sent successfully"})
        }

    except Exception as e:
        print(f"Error in handleAlerts: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
