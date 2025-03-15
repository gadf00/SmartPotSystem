#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>  // ✅ Aggiunta la libreria JSON

// Configurazione WiFi
const char* ssid = "TIM_FWA_1";
const char* password = "FamigliaDeFilippo";

// Configurazione MQTT
const char* mqtt_server = "192.168.1.106";
const int mqtt_port = 1883;
const char* mqtt_topic_command = "Irrigation_Command";
const char* mqtt_topic_confirm = "Irrigation_Confirm";

// Pin dei relay per le pompe
#define RELAY_FRAGOLA 7  // Relay per Fragola
#define RELAY_BASILICO 4 // Relay per Basilico

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
    delay(10);
    Serial.print("🔌 Connessione a WiFi...");
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("✅ Connesso al WiFi!");
}

void callback(char* topic, byte* payload, unsigned int length) {
    Serial.print("📥 Messaggio ricevuto su topic: ");
    Serial.println(topic);

    // Convertire il payload in stringa
    String message;
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    Serial.println("📩 Payload: " + message);

    // Parsing del JSON
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, message);

    if (error) {
        Serial.println("❌ Errore nel parsing del JSON!");
        return;
    }

    // Estrarre smartpot_id e action
    String received_smartpot_id = doc["smartpot_id"];
    String action = doc["action"];

    // Controlla se il messaggio è per uno dei due vasi e attiva il relay corrispondente
    if (action.equals("start")) {
        if (received_smartpot_id.equals("Fragola")) {
            Serial.println("💦 Attivazione irrigazione per Fragola");
            irrigate(RELAY_FRAGOLA, "Fragola");
        } else if (received_smartpot_id.equals("Basilico")) {
            Serial.println("💦 Attivazione irrigazione per Basilico");
            irrigate(RELAY_BASILICO, "Basilico");
        } else {
            Serial.println("❌ Errore: SmartPot non riconosciuto!");
        }
    }
}

void irrigate(int relay_pin, String smartpot) {
    digitalWrite(relay_pin, LOW);  // Accende la pompa
    delay(1000);  // Mantiene acceso per 1 secondo
    digitalWrite(relay_pin, HIGH);  // Spegne la pompa
    Serial.println("✅ Irrigazione completata per " + smartpot);

    // Invia conferma su MQTT
    send_confirmation(smartpot);
}

void send_confirmation(String smartpot) {
    StaticJsonDocument<200> doc;
    doc["smartpot_id"] = smartpot;
    doc["status"] = "done";

    char buffer[256];
    serializeJson(doc, buffer);
    client.publish(mqtt_topic_confirm, buffer);
    Serial.println("📤 Conferma irrigazione inviata per " + smartpot);
}

void reconnect() {
    while (!client.connected()) {
        Serial.print("🔌 Connessione a MQTT...");
        if (client.connect("ESP32Client")) {
            Serial.println("✅ Connesso!");
            client.subscribe(mqtt_topic_command);  // Sottoscrive al topic
        } else {
            Serial.print("❌ Fallito, rc=");
            Serial.print(client.state());
            Serial.println(" - Ritento in 5 secondi...");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    
    // Configura i pin dei relay come output
    pinMode(RELAY_FRAGOLA, OUTPUT);
    pinMode(RELAY_BASILICO, OUTPUT);

    // Assicura che le pompe siano spente all'avvio
    digitalWrite(RELAY_FRAGOLA, HIGH);
    digitalWrite(RELAY_BASILICO, HIGH);

    setup_wifi();
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);
}

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();
}
