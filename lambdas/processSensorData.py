import base64
import json
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass
import boto3

@dataclass
class SensorData:
    smartpot_id: str
    measure_date: str
    temperature: str
    humidity: str
    soil_moisture: str

# Load environment variables
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME", "localhost")
EDGE_PORT = os.getenv("EDGE_PORT", "4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# AWS service clients
ENDPOINT_URL = f"http://{LOCALSTACK_HOSTNAME}:{EDGE_PORT}"
dynamodb = boto3.client("dynamodb", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=AWS_REGION)

# Configurations
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "SmartPotData")
SQS_ALERTS_QUEUE = os.getenv("SQS_ALERTS_QUEUE", "SmartPotAlertsQueue")
SQS_IRRIGATION_QUEUE = os.getenv("SQS_IRRIGATION_QUEUE", "SmartPotIrrigationQueue")
S3_BUCKET = os.getenv("S3_BUCKET", "smartpotsystem-s3-bucket")
RAW_DATA_FOLDER = "raw"

# Limits for plants
PLANT_LIMITS = {
    "Fragola": {
        "temperature_min_day": 18, "temperature_max_day": 25,
        "temperature_min_night": 8, "temperature_max_night": 15,
        "humidity_min": 60, "humidity_max": 80,
        "soil_moisture_min": 50,
        "soil_moisture_max": 80
    },
    "Basilico": {
        "temperature_min_day": 20, "temperature_max_day": 30,
        "temperature_min_night": 10, "temperature_max_night": 15,
        "humidity_min": 50, "humidity_max": 70,
        "soil_moisture_min": 40,
        "soil_moisture_max": 80
    }
}

def save_to_dynamodb(sensor_data: SensorData):
    """Saves sensor data to DynamoDB."""
    try:
        print(f"📝 Saving data for {sensor_data.smartpot_id} in {DYNAMODB_TABLE}")

        update_expression = "SET measure_date = :m, temperature = :t, humidity = :h, soil_moisture = :s"
        expression_values = {
            ":m": {"S": sensor_data.measure_date},
            ":t": {"S": sensor_data.temperature},
            ":h": {"S": sensor_data.humidity},
            ":s": {"S": sensor_data.soil_moisture}
        }

        dynamodb.update_item(
            TableName=DYNAMODB_TABLE,
            Key={"smartpot_id": {"S": sensor_data.smartpot_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        print(f"✅ Data saved to DynamoDB: {sensor_data}")

    except Exception as e:
        print(f"❌ Error saving to DynamoDB: {e}")

def save_to_s3(sensor_data: SensorData):
    """Saves raw sensor data to S3, excluding records with ERR values."""
    if "ERR" in [sensor_data.temperature, sensor_data.humidity, sensor_data.soil_moisture]:
        print(f"⚠️ Skipping S3 save: ERR values detected for {sensor_data.smartpot_id}")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    file_key = f"{RAW_DATA_FOLDER}/{today}/{sensor_data.smartpot_id}.json"

    new_entry = {
        "smartpot_id": sensor_data.smartpot_id,
        "measure_date": sensor_data.measure_date,
        "temperature": sensor_data.temperature,
        "humidity": sensor_data.humidity,
        "soil_moisture": sensor_data.soil_moisture
    }

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=file_key)
        existing_data = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        existing_data = []

    existing_data.append(new_entry)
    s3.put_object(Bucket=S3_BUCKET, Key=file_key, Body=json.dumps(existing_data))
    print(f"✅ Data saved to S3: {file_key}")

def check_and_trigger(sensor_data: SensorData):
    """Checks sensor values and triggers alerts based on time of day."""
    smartpot_id = sensor_data.smartpot_id
    limits = PLANT_LIMITS.get(smartpot_id, {})


    current_time = datetime.now()
    current_hour = current_time.hour
    is_daytime = 8 <= current_hour < 20  # Giorno: 8:00 - 20:00

    # **Imposta i limiti di temperatura basati sull'orario**
    temp_min = limits["temperature_min_night"] if not is_daytime else limits["temperature_min_day"]
    temp_max = limits["temperature_max_night"] if not is_daytime else limits["temperature_max_day"]

    # **Gestione errori sensori**
    if "ERR" in [sensor_data.temperature, sensor_data.humidity, sensor_data.soil_moisture]:
        alert_msg = json.dumps({
            "smartpot_id": smartpot_id,
            "issue": "sensor_error",
            "details": {
                "temperature": sensor_data.temperature,
                "humidity": sensor_data.humidity,
                "soil_moisture": sensor_data.soil_moisture
            }
        })
        sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=alert_msg)
        print(f"🚨 Sent sensor error alert for {smartpot_id}: {alert_msg}")
        return  

    # **Gestione temperatura**
    try:
        temperature_value = float(sensor_data.temperature)
        if temperature_value < temp_min:
            alert_msg = json.dumps({
                "smartpot_id": smartpot_id,
                "issue": "temperature_low",
                "details": {
                    "temperature": sensor_data.temperature,
                    "time_of_day": "night" if not is_daytime else "day"
                }
            })
            sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=alert_msg)
            print(f"⚠️ Sent low temperature alert for {smartpot_id}")

        elif temperature_value > temp_max:
            alert_msg = json.dumps({
                "smartpot_id": smartpot_id,
                "issue": "temperature_high",
                "details": {
                    "temperature": sensor_data.temperature,
                    "time_of_day": "night" if not is_daytime else "day"
                }
            })
            sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=alert_msg)
            print(f"⚠️ Sent high temperature alert for {smartpot_id}")

    except ValueError:
        print(f"❌ Skipping temperature check for {smartpot_id}: Invalid value '{sensor_data.temperature}'")

    # **Gestione umidità**
    try:
        humidity_value = float(sensor_data.humidity)
        if humidity_value < limits["humidity_min"] or humidity_value > limits["humidity_max"]:
            alert_type = "humidity_low" if humidity_value < limits["humidity_min"] else "humidity_high"
            alert_msg = json.dumps({
                "smartpot_id": smartpot_id,
                "issue": alert_type,
                "details": {"humidity": sensor_data.humidity}
            })
            sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=alert_msg)
            print(f"⚠️ Sent {alert_type} alert for {smartpot_id}")

    except ValueError:
        print(f"❌ Skipping humidity check for {smartpot_id}: Invalid value '{sensor_data.humidity}'")

    # **Gestione soil moisture**
    try:
        soil_moisture_value = float(sensor_data.soil_moisture)
        if soil_moisture_value < limits["soil_moisture_min"]:
            # **Verifica l'ultima irrigazione nel database**
            try:
                response = dynamodb.get_item(
                    TableName=DYNAMODB_TABLE,
                    Key={"smartpot_id": {"S": smartpot_id}},
                    AttributesToGet=["last_irrigation"]
                )
                last_irrigation = response.get("Item", {}).get("last_irrigation", {}).get("S", None)

                if last_irrigation:
                    last_irrigation_time = datetime.strptime(last_irrigation, "%Y-%m-%d %H:%M:%S")  
                    time_difference = (current_time - last_irrigation_time).total_seconds() / 60  # Differenza in minuti
                    print(f"🕒 Last irrigation for {smartpot_id}: {last_irrigation_time}")
                    print(f"⏳ Time since last irrigation: {time_difference:.1f} minutes")

                    if time_difference < 5:
                        print(f"⏳ Skipping irrigation for {smartpot_id}: Last irrigation was {time_difference:.1f} minutes ago.")
                        return  # Evita l'irrigazione se non sono trascorsi 5 minuti

            except Exception as e:
                print(f"⚠️ Error retrieving last_irrigation for {smartpot_id}: {e}")

            # **Se i 5 minuti sono passati, attiva l'irrigazione**
            irrigation_msg = json.dumps({
                "smartpot_id": smartpot_id
            })
            sqs.send_message(QueueUrl=SQS_IRRIGATION_QUEUE, MessageBody=irrigation_msg)
            print(f"💧 Sent irrigation trigger for {smartpot_id}")

        elif soil_moisture_value > limits["soil_moisture_max"]:
            # **Se il valore è troppo alto, invia un alert**
            alert_msg = json.dumps({
                "smartpot_id": smartpot_id,
                "issue": "soil_moisture_high",
                "details": {"soil_moisture": sensor_data.soil_moisture}
            })
            sqs.send_message(QueueUrl=SQS_ALERTS_QUEUE, MessageBody=alert_msg)
            print(f"⚠️ Sent high soil moisture alert for {smartpot_id}")

    except ValueError:
        print(f"❌ Skipping soil moisture check for {smartpot_id}: Invalid value '{sensor_data.soil_moisture}'")


def lambda_handler(event, context):
    """AWS Lambda entry point."""
    os.putenv("TZ", "Europe/Rome")
    time.tzset()

    for record in event["Records"]:
        try:
            decoded_data = base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
            json_data = json.loads(decoded_data)

            sensor_data = SensorData(**json_data)
            save_to_dynamodb(sensor_data)
            save_to_s3(sensor_data)
            check_and_trigger(sensor_data)

        except Exception as e:
            print(f"❌ Error processing record: {e}")

    print(f"✅ Processed {len(event['Records'])} records.")
