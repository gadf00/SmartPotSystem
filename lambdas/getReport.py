import os
import json
import time
import boto3

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")

# Initialize AWS Clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

def get_file_from_name(name: str):
    """Check if a specific file exists and retrieve it, first from 'daily/' then from 'manual/'."""
    for folder in ["reports/daily/", "reports/manual/"]:
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=folder)
        if 'Contents' in response:
            for content in response['Contents']:
                if content["Key"].endswith(name):
                    try:
                        response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=content["Key"])
                        return {
                            "key": content["Key"],
                            "bytes": response['Body'].read().decode('utf-8')
                        }
                    except s3.exceptions.NoSuchKey:
                        return None
    return None

def lambda_handler(event, context):
    """AWS Lambda entry point."""
    os.putenv('TZ', 'Europe/Rome')
    time.tzset()
    
    try:
        query_params = event.get('queryStringParameters', {})
        report_name = query_params.get('reportName', None)

        if not report_name:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({'message': 'Missing reportName parameter'})
            }

        to_be_returned = get_file_from_name(report_name)

        if to_be_returned:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(to_be_returned)
            }
        else:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({'message': 'Report not found'})
            }

    except Exception as e:
        print(f"Error retrieving the report: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
