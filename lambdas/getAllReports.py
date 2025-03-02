import os
import json
import time
import boto3

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

# Configurations
S3_BUCKET = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")
MANUAL_REPORTS_FOLDER = "reports/manual/"
DAILY_REPORTS_FOLDER = "reports/daily/"

def get_all_reports_keys():
    """Retrieves the keys of all available reports (daily and manual) in the S3 bucket."""
    reports = []
    for folder in [MANUAL_REPORTS_FOLDER, DAILY_REPORTS_FOLDER]:
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=folder)
        if "Contents" in response:
            reports.extend([content["Key"] for content in response["Contents"] if "Key" in content])
    return reports if reports else None

def get_all_reports(only_names=False):
    """
    Retrieves all stored reports.
    If only_names=True, returns only the report names instead of full content.
    """
    keys = get_all_reports_keys()
    if keys is not None:
        reports = []
        for key in keys:
            report_entry = {
                "key": key.replace(MANUAL_REPORTS_FOLDER, "").replace(DAILY_REPORTS_FOLDER, ""),  # Remove folder prefix
                "type": "manual" if MANUAL_REPORTS_FOLDER in key else "daily"
            }
            if not only_names:
                response = s3.get_object(Bucket=S3_BUCKET, Key=key)
                report_entry["bytes"] = response["Body"].read().decode("utf-8")
            
            reports.append(report_entry)
        
        return reports
    return None

def lambda_handler(event, context):
    """AWS Lambda entry point for retrieving all stored reports."""
    os.putenv("TZ", "Europe/Rome")
    time.tzset()
    
    try:
        # Controlla se la richiesta include il parametro `onlyNames`
        query_params = event.get("queryStringParameters", {})
        only_names = query_params.get("onlyNames", "false").lower() == "true"

        reports = get_all_reports(only_names=only_names)

        if reports is not None:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(reports)
            }
        else:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"message": "No reports found"})
            }

    except Exception as e:
        print(f"Error retrieving reports: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"})
        }
