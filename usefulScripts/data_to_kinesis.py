import boto3
import json
import time
import datetime

# Configura la connessione a Kinesis
kinesis_client = boto3.client("kinesis", endpoint_url="http://localhost:4566", region_name="us-east-1")
KINESIS_STREAM_NAME = "SmartPotSensors"

# Dati predefiniti per i sensori
default_sensor_data = {
    "Strawberry": {"temperature": "14", "humidity": "60", "soil_moisture": "10"},
    "Basil": {"temperature": "14", "humidity": "60", "soil_moisture": "10"},
}

def send_to_kinesis(smartpot_id, data):
    """Invia i dati predefiniti alla stream Kinesis"""

    measure_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    kinesis_payload = json.dumps({
        "smartpot_id": smartpot_id,
        "measure_date": measure_date,
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "soil_moisture": data["soil_moisture"]
    })

    print(f"Sending to Kinesis: {kinesis_payload}")
    try:
        kinesis_client.put_record(StreamName=KINESIS_STREAM_NAME, PartitionKey=smartpot_id, Data=kinesis_payload)
    except Exception as e:
        print(f"Error sending to Kinesis: {e}")

# Loop per inviare dati ogni 5 secondi
while True:
    for smartpot, data in default_sensor_data.items():
        send_to_kinesis(smartpot, data)
    
    print("⏳ Waiting 15 seconds before sending new data...")
    time.sleep(15)
