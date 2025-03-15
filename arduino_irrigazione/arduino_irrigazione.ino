#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi Configuration
const char* ssid = "TIM_FWA_1";
const char* password = "FamigliaDeFilippo";

// MQTT Configuration
const char* mqtt_server = "192.168.1.106";
const int mqtt_port = 1883;
const char* mqtt_topic_command = "Irrigation_Command";
const char* mqtt_topic_confirm = "Irrigation_Confirm";

// Relay pins for water pumps
#define RELAY_STRAWBERRY 7  // Relay for Strawberry
#define RELAY_BASIL 4 // Relay for Basil (yellow wire)

WiFiClient espClient;
PubSubClient client(espClient);

// Connects the ESP32 to the WiFi network.
void setup_wifi() {
    delay(10);
    Serial.print("Connecting to WiFi...");
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println(" Connected to WiFi!");
}

// Callback function triggered when an MQTT message is received.
void callback(char* topic, byte* payload, unsigned int length) {
    Serial.print("Received message on topic: ");
    Serial.println(topic);

    String message;
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    Serial.println("Received payload: " + message);

    // JSON Parsing
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, message);

    if (error) {
        Serial.println("JSON Parsing Error!");
        return;
    }

    // Extract smartpot_id and action
    String received_smartpot_id = doc["smartpot_id"];
    String action = doc["action"];

    // Check if the message corresponds to one of the SmartPots and activate the correct relay
    if (action.equals("start")) {
        if (received_smartpot_id.equals("Strawberry")) {
            Serial.println("Starting irrigation for Strawberry");
            irrigate(RELAY_STRAWBERRY, "Strawberry");
        } else if (received_smartpot_id.equals("Basil")) {
            Serial.println("Starting irrigation for Basil");
            irrigate(RELAY_BASIL, "Basil");
        } else {
            Serial.println("Error: Unrecognized SmartPot!");
        }
    }
}

// Activates the irrigation for a given relay and sends a confirmation message.
void irrigate(int relay_pin, String smartpot) {
    digitalWrite(relay_pin, LOW);  // Turns on the pump
    delay(1000);  // Keeps it on for 1 second
    digitalWrite(relay_pin, HIGH);  // Turns off the pump
    Serial.println("Irrigation completed for " + smartpot);

    // Send confirmation message via MQTT
    send_confirmation(smartpot);
}

// Publishes an MQTT message to confirm irrigation completion.
void send_confirmation(String smartpot) {
    StaticJsonDocument<200> doc;
    doc["smartpot_id"] = smartpot;
    doc["status"] = "done";

    char buffer[256];
    serializeJson(doc, buffer);
    client.publish(mqtt_topic_confirm, buffer);
    Serial.println("Irrigation confirmation sent for " + smartpot);
}

// Handles MQTT reconnection if the connection is lost.
void reconnect() {
    while (!client.connected()) {
        Serial.print("Connecting to MQTT...");
        if (client.connect("ESP32Client")) {
            Serial.println("Connected!");
            client.subscribe(mqtt_topic_command);  // Subscribe to command topic
        } else {
            Serial.print("Connection failed, rc=");
            Serial.print(client.state());
            Serial.println(" - Retrying in 5 seconds...");
            delay(5000);
        }
    }
}

// Initial setup function for the ESP32.
void setup() {
    Serial.begin(115200);
    
    // Configure relay pins as output
    pinMode(RELAY_STRAWBERRY, OUTPUT);
    pinMode(RELAY_BASIL, OUTPUT);

    // Ensure pumps are off at startup
    digitalWrite(RELAY_STRAWBERRY, HIGH);
    digitalWrite(RELAY_BASIL, HIGH);

    setup_wifi();
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);
}


 // Main loop function to maintain MQTT connection.

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();
}
