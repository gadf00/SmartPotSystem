import os
import json
import telebot
import requests
from telebot import types
from dotenv import load_dotenv
import io

# Carica variabili d'ambiente
load_dotenv()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
AWS_GATEWAY_URL = os.environ.get('AWS_GATEWAY_URL', '')

bot = telebot.TeleBot(BOT_TOKEN)

def fetch_data(endpoint: str, method="GET", payload=None):
    """Helper function to make HTTP requests (GET/POST)."""
    url = f'{AWS_GATEWAY_URL}{endpoint}'
    headers = {'Content-Type': 'application/json'}
    
    if method == "POST":
        response = requests.post(url, json=payload, headers=headers)
    else:
        response = requests.get(url, headers=headers)
    
    return response.json() if response.status_code == 200 else None

# **Get Latest Data**
def get_latest_data(message: telebot.types.Message):
    data = fetch_data("getLatestData")
    if data:
        output_msg = "<b>📊 Latest SmartPot Data:</b>\n\n" + "\n".join(
            f"🪴 <b>Pot:</b> {pot['smartpot_id']}\n"
            f"🌡 <b>Temperature:</b> {pot['temperature']}°C\n"
            f"💧 <b>Humidity:</b> {pot['humidity']}%\n"
            f"🪴 <b>Soil Moisture:</b> {pot['soil_moisture']}%\n"
            f"⏳ <b>Last Irrigation:</b> {pot['last_irrigation']}\n"
            f"📅 <b>Last Update:</b> {pot['measure_date']}\n" for pot in data["latestData"])
        bot.send_message(message.chat.id, output_msg, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ Error fetching latest data.")
    send_welcome(message)

# **Get All Reports (Scarica tutti i report)**
def get_all_reports(message: telebot.types.Message):
    data = fetch_data("getAllReports?onlyNames=false")
    if data:
        for report in data:
            file = io.BytesIO(report["bytes"].encode('utf-8'))
            file.name = report["key"]
            bot.send_document(message.chat.id, file)
    else:
        bot.send_message(message.chat.id, "❌ No reports found.")
    send_welcome(message)

# **Get Report (Mostra solo i nomi dei report e poi chiede il numero)**
def get_report_list(message: telebot.types.Message):
    data = fetch_data("getAllReports?onlyNames=true")
    if data:
        daily_reports = [r["key"] for r in data if r["type"] == "daily"]
        manual_reports = [r["key"] for r in data if r["type"] == "manual"]

        if not daily_reports and not manual_reports:
            bot.send_message(message.chat.id, "❌ No reports found.")
            send_welcome(message)
            return

        output_msg = "<b>📂 Available Reports:</b>\n\n"
        all_reports = []

        if daily_reports:
            output_msg += "<b>📆 Daily Reports:</b>\n" + "\n".join(f"{i+1}. {r}" for i, r in enumerate(daily_reports)) + "\n\n"
            all_reports.extend(daily_reports)

        if manual_reports:
            output_msg += "<b>📝 Manual Reports:</b>\n" + "\n".join(f"{i+1+len(daily_reports)}. {r}" for i, r in enumerate(manual_reports))
            all_reports.extend(manual_reports)

        bot.send_message(message.chat.id, output_msg, parse_mode="HTML")
        sent_msg = bot.send_message(message.chat.id, "🔢 Enter the report number to download it:")
        bot.register_next_step_handler(sent_msg, get_report_by_number, all_reports)
    else:
        bot.send_message(message.chat.id, "❌ No reports found.")
        send_welcome(message)

# **Get Report by Number (Scarica il report selezionato)**
def get_report_by_number(message: telebot.types.Message, reports: list):
    try:
        index = int(message.text) - 1
        if 0 <= index < len(reports):
            report_name = reports[index]
            data = fetch_data(f"getReport?reportName={report_name}")
            if data:
                file = io.BytesIO(data["bytes"].encode('utf-8'))
                file.name = data["key"]
                bot.send_document(message.chat.id, file)
            else:
                bot.send_message(message.chat.id, "❌ Error retrieving the report.")
        else:
            bot.send_message(message.chat.id, "❌ Invalid report number.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Please enter a valid number.")
    send_welcome(message)

# **Create Manual Report**
def create_manual_report_handler(message: telebot.types.Message):
    bot.send_message(message.chat.id, "Enter the **SmartPot ID** (leave empty for all):")
    bot.register_next_step_handler(message, ask_manual_report_hours)

def ask_manual_report_hours(message: telebot.types.Message):
    smartpot_id = message.text.strip()
    bot.send_message(message.chat.id, "Enter the **start hour (0-23)** for the report:")
    bot.register_next_step_handler(message, ask_end_hour, smartpot_id)

def ask_end_hour(message: telebot.types.Message, smartpot_id: str):
    try:
        start_hour = int(message.text)
        if 0 <= start_hour <= 23:
            bot.send_message(message.chat.id, "Enter the **end hour (1-24)** for the report:")
            bot.register_next_step_handler(message, create_manual_report, smartpot_id, start_hour)
        else:
            bot.send_message(message.chat.id, "❌ Please enter a valid start hour (0-23).")
            create_manual_report_handler(message)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Please enter a valid number.")
        create_manual_report_handler(message)

def create_manual_report(message: telebot.types.Message, smartpot_id: str, start_hour: int):
    try:
        end_hour = int(message.text)
        if start_hour < end_hour <= 24:
            payload = {
                "smartpot_id": smartpot_id if smartpot_id else "", 
                "start_hour": start_hour, 
                "end_hour": end_hour
            }
            response = fetch_data("createManualReport", method="POST", payload=payload)

            if response and "Manual report successfully generated." in response:
                bot.send_message(message.chat.id, "✅ Manual report successfully generated!")
            else:
                bot.send_message(message.chat.id, "❌ Error generating manual report.")
        else:
            bot.send_message(message.chat.id, "❌ End hour must be greater than start hour and <= 24.")
            create_manual_report_handler(message)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Please enter a valid number.")
        create_manual_report_handler(message)

# **Irrigate Now**
def irrigate_now_handler(message: telebot.types.Message):
    bot.send_message(message.chat.id, "Enter the **Pot ID** (e.g., Fragola, Basilico):")
    bot.register_next_step_handler(message, irrigate_now)

def irrigate_now(message: telebot.types.Message):
    smartpot_id = message.text.capitalize()
    payload = {"smartpot_id": smartpot_id}
    response = fetch_data("irrigateNow", method="POST", payload=payload)

    if response:
        bot.send_message(message.chat.id, f"💦 Irrigation started for {smartpot_id}.")
    else:
        bot.send_message(message.chat.id, "❌ Error starting irrigation.")
    send_welcome(message)

# **Command Handlers**
def action_handler(message: telebot.types.Message):
    actions = {
        'Get latest data': get_latest_data,
        'Get all reports': get_all_reports,
        'Get report': get_report_list,
        'Irrigate now': irrigate_now_handler,
        'Create manual report': create_manual_report_handler
    }
    action = message.text
    actions.get(action, send_welcome)(message)

@bot.message_handler(commands=['start', 'hello'])
def send_welcome(message: telebot.types.Message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    buttons = [
        'Get latest data',
        'Get all reports',
        'Get report',
        'Irrigate now',
        'Create manual report'
    ]
    markup.add(*buttons)
    sent_msg = bot.send_message(message.chat.id, "🛠 What would you like to do?", reply_markup=markup)
    bot.register_next_step_handler(sent_msg, action_handler)

bot.infinity_polling()
