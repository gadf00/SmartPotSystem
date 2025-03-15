import json
import os
import time
from datetime import datetime
import boto3

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

# Configurations
S3_BUCKET = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")
SQS_ALERTS_QUEUE = os.getenv("SQS_ALERTS_QUEUE", "SmartPotAlertsQueue")
RAW_FOLDER = "raw/"
REPORT_FOLDER = "reports/daily/"
EVENTS_FOLDER = "events/"

def calculate_average(values):
    """Calculates the average ignoring 'ERR' values."""
    numeric_values = [float(v) for v in values if v != "ERR"]
    return round(sum(numeric_values) / len(numeric_values), 2) if numeric_values else None

def delete_s3_folder(prefix):
    """Deletes all objects in an S3 folder."""
    objects = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    if "Contents" in objects:
        delete_keys = [{"Key": obj["Key"]} for obj in objects["Contents"]]
        s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": delete_keys})
        print(f"🗑️ Deleted {len(delete_keys)} objects from {prefix}")

def get_event_data(smartpot_id):
    """Retrieves all event timestamps from S3 for a specific SmartPot."""
    event_file_path = f"{EVENTS_FOLDER}daily_events_{smartpot_id}.json"

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=event_file_path)
        event_records = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        print(f"ℹ️ No event file found for {smartpot_id}. Returning empty list.")
        event_records = []

    # Aggrega gli eventi in base al tipo
    event_counts = {
        "sensor_errors": 0,
        "temperature_high": 0,
        "temperature_low": 0,
        "humidity_high": 0,
        "humidity_low": 0,
        "soil_moisture_high": 0,
        "irrigation_triggered": 0
    }

    for event in event_records:
        event_type = event.get("event_type")
        if event_type in event_counts:
            event_counts[event_type] += 1

    return event_counts

def generate_daily_report():
    """Generates a daily report based on the raw data available in S3, grouped by SmartPot."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    report_data = {}

    # Retrieve all RAW files from S3
    raw_files = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=RAW_FOLDER)
    if "Contents" not in raw_files:
        print("⚠️ No raw data found in S3. Report not generated.")
        return False  # Indica che il report non è stato generato

    # Process each raw data file
    for file in raw_files["Contents"]:
        file_key = file["Key"]
        if not file_key.endswith(".json"):
            continue

        # Download file from S3
        file_obj = s3.get_object(Bucket=S3_BUCKET, Key=file_key)
        data = json.loads(file_obj["Body"].read().decode("utf-8"))

        # Process sensor data grouped by smartpot_id
        for record in data:
            smartpot_id = record.get("smartpot_id")
            if not smartpot_id:
                continue

            if smartpot_id not in report_data:
                report_data[smartpot_id] = {
                    "smartpot_id": smartpot_id,
                    "temperature": [],
                    "humidity": [],
                    "soil_moisture": []
                }

            if "temperature" in record:
                report_data[smartpot_id]["temperature"].append(float(record["temperature"]))
            if "humidity" in record:
                report_data[smartpot_id]["humidity"].append(float(record["humidity"]))
            if "soil_moisture" in record:
                report_data[smartpot_id]["soil_moisture"].append(float(record["soil_moisture"]))

    if not report_data:
        print("⚠️ No valid data found in S3. Sending SQS alert.")
        alert_message = {
            "smartpot_id": "ALL",
            "issue": "daily_report",
            "details": {"message": "⚠️ No valid sensor data found. Unable to generate daily report."}
        }
        sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=json.dumps(alert_message))
        return False

    # Generate report
    final_report = []
    for smartpot_id, data in report_data.items():
        report_entry = {
            "smartpot_id": smartpot_id,
            "avg_temperature": calculate_average(data["temperature"]),
            "avg_humidity": calculate_average(data["humidity"]),
            "avg_soil_moisture": calculate_average(data["soil_moisture"]),
        }

        # Retrieve and include event data
        event_data = get_event_data(smartpot_id)
        report_entry.update(event_data)
        
        final_report.append(report_entry)

    # Save the report to S3
    report_filename = f"{REPORT_FOLDER}daily_report_{current_date}.json"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=report_filename,
        Body=json.dumps(final_report, indent=4)
    )

    print(f"✅ Daily report generated and saved: {report_filename}")

    # Send notification via handleAlerts
    alert_message = {
        "smartpot_id": "ALL",
        "issue": "daily_report",
        "details": {"message": f"✅ Daily report successfully generated: {report_filename}."}
    }
    sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=json.dumps(alert_message))

    # Delete all raw data and event records
    delete_s3_folder(RAW_FOLDER)
    delete_s3_folder(EVENTS_FOLDER)

    return True  # Indica che il report è stato generato

def lambda_handler(event, context):
    """AWS Lambda handler function to create the daily report."""
    os.putenv("TZ", "Europe/Rome")
    time.tzset()

    try:
        generated = generate_daily_report()
        return {
            "statusCode": 200 if generated else 500,
            "body": json.dumps("Daily report successfully generated." if generated else "No valid sensor data found.")
        }
    except Exception as e:
        print(f"❌ Error in createDailyReport: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
