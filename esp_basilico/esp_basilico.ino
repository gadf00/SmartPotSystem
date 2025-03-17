#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

#define DEVICE_ID "Basil"
#define DHTPIN 4
#define SOIL_MOISTURE_PIN 36  

#define DRY_VALUE 4000   // dry ground
#define WET_VALUE 100     // wet ground

#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// WiFi e MQTT
const char* ssid = "";
const char* password = "";
const char* mqtt_server = "";

// MQTT Topics
const char* topic_temp = "Basil_Temp";
const char* topic_hum = "Basil_Hum";
const char* topic_soil = "Basil_Soil";

WiFiClient espClient;
PubSubClient client(espClient);

void connectToWiFi() {
    Serial.print("Connecting to WiFi...");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected.");
}

void connectToMQTT() {
    Serial.print("Connecting to MQTT...");
    while (!client.connected()) {
        if (client.connect(DEVICE_ID)) {
            Serial.println("Connected to MQTT broker.");
        } else {
            Serial.print("Failed, retrying in 5s...");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    WiFi.begin(ssid, password);
    client.setServer(mqtt_server, 1883);
    dht.begin();
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        connectToWiFi();
    }
    if (!client.connected()) {
        connectToMQTT();
    }
    client.loop();

    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    int soilMoisture = analogRead(SOIL_MOISTURE_PIN);

    // Soil moisture percentage calculation
    int soilMoisturePercent = 100 - ((soilMoisture - WET_VALUE) * 100 / (DRY_VALUE - WET_VALUE));
    soilMoisturePercent = constrain(soilMoisturePercent, 0, 100);  // Limita tra 0% e 100%


    bool tempError = false;
    bool humError = false;
    bool soilError = false;

    // Error control
    if (isnan(temperature) || temperature < 5 || temperature > 70) {
        tempError = true;
        Serial.println("Error, Temperature out of bounds!");
    }
    
    if (isnan(humidity) || humidity < 10 || humidity > 95) {
        humError = true;
        Serial.println("Error, Humidity out of bounds!");
    }

    if (soilMoisture <= 0 || soilMoisture >= 4095) {
        soilError = true;
        Serial.println("Error, Soil Moisture out of bounds!");
    }

    // Send Data to MQTT
    if (tempError) {
        client.publish(topic_temp, "{\"smartpot_id\": \"" DEVICE_ID "\", \"temperature\": \"ERR\"}");
        Serial.println("Published: Temperature ERR");
    } else {
        String tempPayload = "{\"smartpot_id\": \"" + String(DEVICE_ID) + "\", \"temperature\": \"" + String(temperature) + "\"}";
        client.publish(topic_temp, tempPayload.c_str());
        Serial.println("Published: " + tempPayload);
    }

    if (humError) {
        client.publish(topic_hum, "{\"smartpot_id\": \"" DEVICE_ID "\", \"humidity\": \"ERR\"}");
        Serial.println("Published: Humidity ERR");
    } else {
        String humPayload = "{\"smartpot_id\": \"" + String(DEVICE_ID) + "\", \"humidity\": \"" + String(humidity) + "\"}";
        client.publish(topic_hum, humPayload.c_str());
        Serial.println("Published: " + humPayload);
    }

    if (soilError) {
        client.publish(topic_soil, "{\"smartpot_id\": \"" DEVICE_ID "\", \"soil_moisture\": \"ERR\"}");
        Serial.println("Published: Soil Moisture ERR");
    } else {
        String soilPayload = "{\"smartpot_id\": \"" + String(DEVICE_ID) + "\", \"soil_moisture\": \"" + String(soilMoisturePercent) + "\"}";
        client.publish(topic_soil, soilPayload.c_str());
        Serial.println("Published: " + soilPayload);
    }

    delay(15000);
}
