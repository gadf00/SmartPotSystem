import json
import os
import time
from datetime import datetime, timezone
import boto3

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

# Configurations
S3_BUCKET = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE")
SQS_ALERTS_QUEUE = os.getenv("SQS_ALERTS_QUEUE")
RAW_FOLDER = "raw/"
REPORT_FOLDER = "manual_reports/"

def calculate_average(values):
    """Calculates the average ignoring 'ERR' values."""
    numeric_values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(numeric_values) / len(numeric_values), 2) if numeric_values else None

def get_event_data(smartpot_id):
    """Retrieves the daily event data from S3 for a specific SmartPot."""
    event_file_path = f"events/daily_events_{smartpot_id}.json"

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=event_file_path)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        print(f"ℹ️ No event file found for {smartpot_id}. Initializing with empty values.")
        return {
            "sensor_errors": 0,
            "temperature_high": 0,
            "temperature_low": 0,
            "humidity_high": 0,
            "humidity_low": 0,
            "irrigation_triggered": 0
        }

def generate_manual_report(smartpot_id, start_hour, end_hour):
    """Generates a manual report for a given time range."""
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_time = datetime.strptime(f"{current_date} {start_hour}:00:00", "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(f"{current_date} {end_hour}:00:00", "%Y-%m-%d %H:%M:%S")

    if start_hour >= end_hour:
        raise ValueError("Start hour must be before end hour.")
    
    report_data = {
        "smartpot_id": smartpot_id,
        "date": current_date,
        "time_range": f"{start_hour}:00 - {end_hour}:00",
        "temperature": [],
        "humidity": [],
        "soil_moisture": []
    }

    # Retrieve list of RAW files from S3
    raw_files = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=RAW_FOLDER)

    if "Contents" not in raw_files:
        print(f"⚠️ No raw data found for {smartpot_id}. Report not generated.")
        return False  # Indica che il report non è stato generato

    data_found = False
    for file in raw_files["Contents"]:
        file_key = file["Key"]
        if not file_key.endswith(".json"):
            continue

        # Download file from S3
        file_obj = s3.get_object(Bucket=S3_BUCKET, Key=file_key)
        data = json.loads(file_obj["Body"].read().decode("utf-8"))

        # Process only the relevant SmartPot data
        for record in data:
            if record.get("smartpot_id") != smartpot_id:
                continue

            record_time = datetime.strptime(record["timestamp"], "%Y-%m-%d %H:%M:%S")
            if start_time <= record_time <= end_time:
                data_found = True
                if "temperature" in record and record["temperature"] != "ERR":
                    report_data["temperature"].append(float(record["temperature"]))
                if "humidity" in record and record["humidity"] != "ERR":
                    report_data["humidity"].append(float(record["humidity"]))
                if "soil_moisture" in record and record["soil_moisture"] != "ERR":
                    report_data["soil_moisture"].append(float(record["soil_moisture"]))

    if not data_found:
        print(f"⚠️ No data found in the selected time range for {smartpot_id}. Sending SQS alert.")
        alert_message = {
            "smartpot_id": smartpot_id if smartpot_id else "ALL",
            "issue": "manual_report",
            "details": {"message": f"⚠️ No valid data found for {smartpot_id} in time range {start_hour}:00 - {end_hour}:00. Unable to generate report."}
        }
        sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=json.dumps(alert_message))
        return False  # Indica che il report non è stato generato

    # Calculate averages
    report = {
        "smartpot_id": smartpot_id,
        "date": current_date,
        "time_range": f"{start_hour}:00 - {end_hour}:00",
        "avg_temperature": calculate_average(report_data["temperature"]),
        "avg_humidity": calculate_average(report_data["humidity"]),
        "avg_soil_moisture": calculate_average(report_data["soil_moisture"])
    }

    # Retrieve and include event data
    event_data = get_event_data(smartpot_id)
    report.update(event_data)

    # Save the report to S3
    report_filename = f"{REPORT_FOLDER}manual_report_{smartpot_id}_{start_hour}-{end_hour}_{current_date}.json"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=report_filename,
        Body=json.dumps(report, indent=4)
    )

    print(f"✅ Manual report generated: {report_filename}")

    # Send notification via handleAlerts
    alert_message = {
        "smartpot_id": smartpot_id if smartpot_id else "ALL",
        "issue": "manual_report",
        "details": {"message": f"📄 Manual report successfully generated for {smartpot_id} ({start_hour}:00 - {end_hour}:00)."}
    }
    sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=json.dumps(alert_message))
    
    return True  # Indica che il report è stato generato

def lambda_handler(event, context):
    """AWS Lambda handler function to create the manual report."""
    os.putenv("TZ", "Europe/Rome")
    time.tzset()

    try:
        body = json.loads(event["body"])
        smartpot_id = body.get("smartpot_id", "").strip()
        start_hour = int(body.get("start_hour"))
        end_hour = int(body.get("end_hour"))

        if start_hour >= end_hour:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Start hour must be before end hour."})
            }

        generated = False
        if smartpot_id:
            generated = generate_manual_report(smartpot_id, start_hour, end_hour)
        else:
            print("ℹ️ No smartpot_id provided, generating reports for all SmartPots.")
            for smartpot in ["Fragola", "Basilico"]:  # Estendibile con altri SmartPots
                generated |= generate_manual_report(smartpot, start_hour, end_hour)

        return {
            "statusCode": 200 if generated else 500,
            "body": json.dumps("Manual report successfully generated." if generated else "No valid data found for the requested time range.")
        }

    except Exception as e:
        print(f"❌ Error in createManualReport: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
