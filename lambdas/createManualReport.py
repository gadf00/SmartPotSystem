import json
import os
import time
from datetime import datetime, timedelta
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
SQS_ALERTS_QUEUE = os.getenv("SQS_ALERTS_QUEUE")
RAW_FOLDER = "raw/"
REPORT_FOLDER = "reports/manual/"

def calculate_average(values):
    """Computes the average value from a list while ignoring 'ERR' values.
       Returns None if there are no valid values."""

    numeric_values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(numeric_values) / len(numeric_values), 2) if numeric_values else None

def get_event_data(smartpot_id, start_time, end_time):
    """Retrieves event data from S3 for a given SmartPot and time range.
       Filters events like sensor errors, temperature/humidity alerts, and irrigation status.
       Returns a dictionary with event counts."""

    event_file_path = f"events/daily_events_{smartpot_id}.json"

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=event_file_path)
        events = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        return {
            "sensor_errors": 0,
            "temperature_high": 0,
            "temperature_low": 0,
            "humidity_high": 0,
            "humidity_low": 0,
            "soil_moisture_high": 0,
            "irrigation_completed": 0,
            "irrigation_error": 0
        }

    # Filtra eventi nell'intervallo di tempo specificato
    event_counts = {
        "sensor_errors": 0,
        "temperature_high": 0,
        "temperature_low": 0,
        "humidity_high": 0,
        "humidity_low": 0,
        "soil_moisture_high": 0,
        "irrigation_completed": 0,
        "irrigation_error": 0
    }

    for event in events:
        event_time = datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
        if start_time <= event_time < end_time:
            event_type = event["event_type"]
            if event_type in event_counts:
                event_counts[event_type] += 1

    return event_counts

def generate_manual_report(smartpot_id, start_hour, end_hour):
    """Generates a manual report for a given SmartPot and time interval.
    Extracts raw temperature, humidity, and soil moisture values from S3.
    Computes averages and aggregates event data.
    Returns the final report data."""

    current_date = datetime.now().strftime("%Y-%m-%d")
    previous_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Determinare se il range attraversa la mezzanotte
    if start_hour > end_hour:
        dates_to_check = [previous_date, current_date]  # Controlla ieri e oggi
    else:
        dates_to_check = [current_date]  # Controlla solo oggi

    start_time = datetime.strptime(f"{current_date} {start_hour}:00:00", "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(f"{current_date} {end_hour}:00:00", "%Y-%m-%d %H:%M:%S")

    report_data = {
        "smartpot_id": smartpot_id,
        "date_range": dates_to_check,
        "time_range": f"{start_hour}:00 - {end_hour}:00",
        "temperature": [],
        "humidity": [],
        "soil_moisture": []
    }

    data_found = False

    for date in dates_to_check:
        file_key = f"{RAW_FOLDER}{date}/{smartpot_id}.json"

        try:
            file_obj = s3.get_object(Bucket=S3_BUCKET, Key=file_key)
            data = json.loads(file_obj["Body"].read().decode("utf-8"))

            for record in data:
                if record.get("smartpot_id") != smartpot_id:
                    continue

                if "measure_date" not in record:
                    continue

                record_time = datetime.strptime(record["measure_date"], "%Y-%m-%d %H:%M:%S")

                if start_time <= record_time < end_time:
                    data_found = True

                # Aggiungere i dati validi
                if "temperature" in record and record["temperature"] != "ERR":
                    report_data["temperature"].append(float(record["temperature"]))
                if "humidity" in record and record["humidity"] != "ERR":
                    report_data["humidity"].append(float(record["humidity"]))
                if "soil_moisture" in record and record["soil_moisture"] != "ERR":
                    report_data["soil_moisture"].append(float(record["soil_moisture"]))

        except s3.exceptions.NoSuchKey:
            print(f"No data found for {smartpot_id} on {date}")

    if not data_found:
        return None

    # Calculate averages
    report = {
        "smartpot_id": smartpot_id,
        "date_range": dates_to_check,
        "time_range": f"{start_hour}:00 - {end_hour}:00",
        "avg_temperature": calculate_average(report_data["temperature"]),
        "avg_humidity": calculate_average(report_data["humidity"]),
        "avg_soil_moisture": calculate_average(report_data["soil_moisture"])
    }

    # Retrieve and include event data
    event_data = get_event_data(smartpot_id, start_time, end_time)
    report.update(event_data)

    return report

def lambda_handler(event, context):
    """AWS Lambda handler function to create the manual report."""
    
    os.putenv("TZ", "Europe/Rome")
    time.tzset()

    try:
        body = json.loads(event["body"])
        smartpot_id = body.get("smartpot_id", "").strip()
        start_hour = int(body.get("start_hour"))
        end_hour = int(body.get("end_hour"))

        if start_hour == end_hour:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Start hour and end hour cannot be the same."})
            }

        reports = []

        if smartpot_id and smartpot_id != "All":
            report = generate_manual_report(smartpot_id, start_hour, end_hour)
            if report:
                reports.append(report)
                report_filename = f"{REPORT_FOLDER}manual_report_{smartpot_id}_{start_hour}-{end_hour}_{datetime.now().strftime('%Y-%m-%d')}.json"
        else:
            for smartpot in ["Strawberry", "Basil"]:
                report = generate_manual_report(smartpot, start_hour, end_hour)
                if report:
                    reports.append(report)

            report_filename = f"{REPORT_FOLDER}manual_report_All_{start_hour}-{end_hour}_{datetime.now().strftime('%Y-%m-%d')}.json"

        if not reports:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "No valid data found for the requested time range."})
            }

        # Save report to S3
        s3.put_object(Bucket=S3_BUCKET, Key=report_filename, Body=json.dumps(reports, indent=4))

        return {
            "statusCode": 200,
            "body": json.dumps(report_filename)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
