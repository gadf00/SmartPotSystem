import paho.mqtt.client as mqtt
import boto3
import json
import time
import datetime

# Configura la connessione a Kinesis
kinesis_client = boto3.client("kinesis", endpoint_url="http://localhost:4566", region_name="us-east-1")
KINESIS_STREAM_NAME = "SmartPotSensors"

# Dizionario per tenere traccia dei dati ricevuti
sensor_data = {
    "Fragola": {"temperature": None, "humidity": None, "soil_moisture": None},
    "Basilico": {"temperature": None, "humidity": None, "soil_moisture": None},
}

# Funzione per inviare i dati a Kinesis
def send_to_kinesis(smartpot_id):
    """Invia i dati completi alla stream Kinesis"""
    measure_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    kinesis_payload = json.dumps({
        "smartpot_id": smartpot_id,
        "measure_date": measure_date,
        "temperature": sensor_data[smartpot_id]["temperature"],
        "humidity": sensor_data[smartpot_id]["humidity"],
        "soil_moisture": sensor_data[smartpot_id]["soil_moisture"]
    })

    print(f"🚀 Sending to Kinesis: {kinesis_payload}")
    try:
        kinesis_client.put_record(StreamName=KINESIS_STREAM_NAME, PartitionKey=smartpot_id, Data=kinesis_payload)
    except Exception as e:
        print(f"❌ Error sending to Kinesis: {e}")

    # Reset dati per il prossimo ciclo
    sensor_data[smartpot_id] = {"temperature": None, "humidity": None, "soil_moisture": None}

# Funzione callback quando si riceve un messaggio
def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        smartpot_id = payload["smartpot_id"]

        if message.topic.endswith("_Temp"):
            sensor_data[smartpot_id]["temperature"] = payload["temperature"]
            print(f"🌡 Received temperature: {payload['temperature']} from {smartpot_id}")
        elif message.topic.endswith("_Hum"):
            sensor_data[smartpot_id]["humidity"] = payload["humidity"]
            print(f"💧 Received humidity: {payload['humidity']} from {smartpot_id}")
        elif message.topic.endswith("_Soil"):
            sensor_data[smartpot_id]["soil_moisture"] = payload["soil_moisture"]
            print(f"🪴 Received soil moisture: {payload['soil_moisture']} from {smartpot_id}")

        # Se tutti i valori sono disponibili, invia a Kinesis
        if None not in sensor_data[smartpot_id].values():
            send_to_kinesis(smartpot_id)

    except Exception as e:
        print(f"❌ Error processing MQTT message: {e}")

# Funzione callback per la connessione al broker MQTT
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT Broker")
        # Sottoscrizione ai topic per entrambi i vasi
        for plant in ["Fragola", "Basilico"]:
            client.subscribe(f"{plant}_Temp")
            client.subscribe(f"{plant}_Hum")
            client.subscribe(f"{plant}_Soil")
    else:
        print(f"⚠️ Connection failed with result code {rc}")

# Funzione callback per gestire disconnessioni
def on_disconnect(client, userdata, rc):
    print("❌ Disconnected from MQTT Broker. Attempting to reconnect...")
    while True:
        try:
            client.reconnect()
            print("🔄 Reconnected to MQTT Broker!")
            return
        except Exception as e:
            print(f"⚠️ Reconnection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

# Configura il client MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Loop per mantenere il client sempre in ascolto
while True:
    try:
        print("🔗 Connecting to MQTT Broker...")
        client.connect("localhost", 1883, 60)
        client.loop_forever()
    except Exception as e:
        print(f"❌ Connection error: {e}. Retrying in 5 seconds...")
        time.sleep(5)
