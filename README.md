<h1>🌱 SmartPot System</h1>
<p><strong>SmartPot System</strong> is a simple yet complete project designed to simulate an automated plant irrigation system capable of self-maintenance. It was developed as part of the <strong>Serverless Computing for IoT</strong> course during the Computer Science Master's Degree program at <strong>UNISA</strong>.</p>
<h1>Architecture</h1>
<img src="images/ScIoT%20Architecture.png" alt="Architecture">
<p>The architecture consists of several services working independently but in sync to let the system work as a whole. In the setting presented here, the system is composed of 2 pots and ideally each pot contains a single species of plant (Basil and Strawberry).</p>
<p>The system is composed of two SmartPots, each consisting of an ESP32 equipped with a DHT22 sensor that captures environmental values such as temperature and humidity, and a soil moisture sensor that monitors the soil's humidity percentage.</p>
<p>Using two sketches (esp_fragola and esp_basilico), the ESP32 devices send their data to an MQTT broker via the following topics:</p>
<ul>
  <li>Basil_Temp, Basil_Hum, Basil_Soil</u>
  <li>Strawberry_Temp, Strawberry_Hum, Strawberry_Soil</u>
</ul>
<p>A Python script subscribes to these topics, collects the data, and forwards it to a Kinesis stream, capable of efficiently handling high-throughput data. Theoretically, the sensors could be configured to send hundreds of readings per second.</p>
<p>The Kinesis stream triggers a Lambda function called ProcessSensorData, which performs the following operations:</p>
<ul>
  <li>Validates sensor readings for each SmartPot and each sensor type against predefined thresholds.</li>
  <li>Saves the data in DynamoDB.</li>
  <li>Stores the raw data in an S3 bucket, excluding any records containing "ERR" values.</li>
  <li>If any value exceeds its defined threshold, it sends a message to the SmartPotAlertsQueue (SQS) specifying the type of issue (e.g., temperature below limits).</li>
  <li>If the soil moisture value is below threshold, it sends a message to the SmartPotIrrigationQueue (SQS) to initiate irrigation.</li>
</ul>
<p>At this point, another Lambda function, IrrigateNow, is triggered by the SQS message. It sends an irrigation command via the MQTT topic Irrigation_Command. An Arduino UNO Rev4 equipped with a 2-channel relay activates one of two water pumps depending on whether it needs to irrigate Basilico or Fragola.</p>
<p>Once the Arduino receives the command, it activates the appropriate pump and, upon completion, sends a confirmation message on the MQTT topic Irrigation_Confirm.
The IrrigateNow Lambda function waits up to 10 seconds for this confirmation. When received, it updates the last_irrigation field in DynamoDB and sends a notification via the SmartPotAlertsQueue (SQS).</p>
<p>Additionally, this function can be invoked manually via an API Gateway.</p>
<p>Other Lambda functions available in the system include:</p>
<ul>
  <li><strong>createDailyReport</strong>: triggered daily via EventBridge, it calculates daily averages for temperature, humidity, and soil moisture, includes event counts (e.g., temperature_high alerts), and stores the report in S3.</li>
  <li><strong>createManualReport</strong>: similar to createDailyReport, but can be triggered via API Gateway, specifying a start_hour and end_hour to focus on a specific time range.</li>
  <li><strong>getLatestSensorData</strong>: fetches the latest sensor data from DynamoDB via API Gateway.</li>
  <li><strong>getReport</strong>: retrieves a specific report by name or lists all report names available in S3, via API Gateway.</li>
  <li><strong>getAllReports</strong>: returns the full content of all reports stored in the S3 bucket, via API Gateway.</li>
  <li><strong>handleAlerts</strong>: specialized in handling messages from SmartPotAlertsQueue (SQS). Based on the issue type, it sends a Telegram notification via bot and logs the alert timestamp in S3 for tracking purposes.</li>
</ul>

<h1>Amazon Web Services used</h1>
<ul>
  <li><a href="https://aws.amazon.com/lambda/">Lambda</a></li>
  <li><a href="https://aws.amazon.com/dynamodb/">DynamoDB</a></li>
  <li><a href="https://aws.amazon.com/s3/">S3</a></li>
  <li><a href="http://aws.amazon.com/kinesis/data-streams/">Kinesis</a></li>
  <li><a href="https://aws.amazon.com/sqs/">SQS</a></li>
  <li><a href="https://aws.amazon.com/api-gateway/">API Gateway</a></li>
  <li><a href="https://aws.amazon.com/eventbridge/">EventBridge</a></li>
</ul>

<h1>Installation</h1>
<h3>Requirements</h3>
The following apps / libraries / packages are needed to successfully build and run the project:
<ul>
  <li><a href="https://www.docker.com/">Docker</a></li>
  <li><a href="https://www.localstack.cloud/">Localstack</a></li>
  <li><a href="https://www.python.org/">Python</a></li>
  <li><a href="https://github.com/eternnoir/pyTelegramBotAPI">pyTelegramBotAPI</a></li>
  <li><a href="https://github.com/theskumar/python-dotenv">python-dotenv</a></li>
  <li><a href="https://jqlang.org/">JQ</a></li>
</ul>
<h3>Setting up the environment</h3>
<p>Clone the repo.</p>

```bash
git clone https://github.com/gadf00/SmartPotSystem
cd SmartPotSystem
```
<p>Create a Telegram BOT using <a href="https://telegram.me/BotFather">bot-father</a></p>
<p>create a .env file in the project root folder</p>
<p>Put the Telegram Bot Token and the Telegram Chat ID in the .env file</p>

```bash
TELEGRAM_BOT_TOKEN=XXX
TELEGRAM_CHAT_ID=XXX
```

<p>The file .env should look like this:</p>

```bash
# AWS LocalStack Configuration
LOCALSTACK_HOSTNAME=localhost
EDGE_PORT=4566
AWS_DEFAULT_REGION=us-east-1

# S3 Configuration
S3_BUCKET=smartpotsystem-s3-bucket
RAW_DATA_FOLDER=raw
DAILY_REPORTS_FOLDER=reports/daily
MANUAL_REPORTS_FOLDER=reports/manual

# DynamoDB Configuration
DYNAMODB_TABLE=SmartPotData

# SQS Configuration
SQS_ALERTS_QUEUE=SmartPotAlertsQueue
SQS_IRRIGATION_QUEUE=SmartPotIrrigationQueue

# Kinesis Stream
KINESIS_STREAM=SmartPotSensors

# IAM Role
IAM_ROLE_NAME=LambdaAndKinesisRole

# Telegram Bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_TOPIC_COMMAND=Irrigation_Command
MQTT_TOPIC_CONFIRM=Irrigation_Confirm
```
<p>Source the .env to make the 2 just-declared variables available to the current environment.</p>

```bash
source .env
```
<p>Create a virtual environment and install AwsLocal boto3 and paho-mqtt.</p>

```bash
pip install -r ./bot/requirements.txt
```

<p>Install the dependencies for the Telegram Bot.</p>

```bash
python3 -m venv esame
source esame/bin/activate
pip install --upgrade pip
pip install awscli-local boto3 paho-mqtt python-dotenv
```

<p>Check your IP address.</p>

```bash
ip a
```
<p>Replace these values with your in the filesfile: arduino_irrigazione, esp_basilico, esp_fragola</p>
<ul>
  <li>const char* ssid = "";</li>
  <li>const char* password = "";</li>
  <li>const char* mqtt_server = "";</li>
</ul>

<p>Start the Localstack Docker image.</p>

```bash
docker-compose up
```

<h3>Automated install</h3>
<p>Launch the script to create all the AWS architecture described above on the local Localstack instance.</p>

```bash
chmod +x ./install.sh
bash ./install.sh
```
<p>In addition to create all the required services instances and link them toghether, the script will also make the Telegram Bot Token and Chat ID available to the Lambda functions that require them reading them from the .env file and adding them to the their Environment Variables. Furthermore, it will append to the .env the API Gateway URL right after instantiating it.</p>

<h1>Using the system</h1>
<p>Launch the Telegram Bot.</p>

```bash
python ./bot/bot.py
```
<p>The bot requires the API Gateway URL in order to communicate with the system. It will read it from the .env file, hence the necessity to install python-dotenv as dependency.</p>

<p>Launch the script to retrieve sensors data from esp32 and sending data to the Kinesis stream in real-time.</p>

```bash
chmod +x ./usefulScripts/mqtt_to_kinesis.py
./usefulScripts/mqtt_to_kinesis.py
```

<p>You can check the logs of a lambda function with this command.</p>

```bash
aws logs tail /aws/lambda/yourLambdaFunction --endpoint-url http://localhost:4566 --follow

```

<h1>Future developments</h1>
<p>Future improvements include the development of a web application for real-time monitoring, the integration of machine learning for predictive irrigation, and the use of advanced analytics to optimize plant health and resource usage.</p>
