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

# **Selezione SmartPot per Report Manuale**
def create_manual_report_handler(message: telebot.types.Message):
    """Mostra i pulsanti per scegliere tra Basilico, Fragola o Tutti."""
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    buttons = [types.KeyboardButton(sp) for sp in ["Basilico", "Fragola", "All"]]
    markup.add(*buttons)

    sent_msg = bot.send_message(message.chat.id, "🪴 **Seleziona il tipo di SmartPot:**", reply_markup=markup)
    bot.register_next_step_handler(sent_msg, ask_manual_report_start_hour)

# **Selezione Start Hour**
def ask_manual_report_start_hour(message: telebot.types.Message):
    """Mostra i pulsanti per selezionare l'ora di inizio."""
    smartpot_id = message.text.strip()
    
    markup = types.ReplyKeyboardMarkup(row_width=6, one_time_keyboard=True)
    buttons = [types.KeyboardButton(str(hour)) for hour in range(24)]
    markup.add(*buttons)

    sent_msg = bot.send_message(message.chat.id, "⏳ **Seleziona l'ora di inizio (0-23):**", reply_markup=markup)
    bot.register_next_step_handler(sent_msg, ask_manual_report_end_hour, smartpot_id)

# **Selezione End Hour**
def ask_manual_report_end_hour(message: telebot.types.Message, smartpot_id: str):
    """Mostra i pulsanti per selezionare l'ora di fine."""
    try:
        start_hour = int(message.text)
    except ValueError:
        bot.send_message(message.chat.id, "❌ **Inserisci un numero valido tra 0 e 23!**")
        return ask_manual_report_start_hour(message)

    markup = types.ReplyKeyboardMarkup(row_width=6, one_time_keyboard=True)
    buttons = [types.KeyboardButton(str(hour)) for hour in range(24)]
    markup.add(*buttons)

    sent_msg = bot.send_message(message.chat.id, "⏳ **Seleziona l'ora di fine (0-23):**", reply_markup=markup)
    bot.register_next_step_handler(sent_msg, create_manual_report, smartpot_id, start_hour)

# **Invio della richiesta al Server**
def create_manual_report(message: telebot.types.Message, smartpot_id: str, start_hour: int):
    """Invia la richiesta per creare il report manuale e gestisce la risposta."""
    try:
        end_hour = int(message.text)
        if start_hour == end_hour:
            raise ValueError("Start and end hour cannot be the same.")

        payload = {
            "smartpot_id": smartpot_id,
            "start_hour": start_hour,
            "end_hour": end_hour
        }
        response = fetch_data("createManualReport", method="POST", payload=payload)

        # **LOG: Stampa la risposta della Lambda**
        print(f"🛠️ Response from createManualReport Lambda: {response}")

        if response and isinstance(response, str):  # Il nome del file viene restituito come stringa
            bot.send_message(message.chat.id, f"✅ **Manual report successfully generated!**\n📄 File: `{response}`", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "📛 **Errore: Nessun dato disponibile per il range di ore selezionato!**")

    except ValueError:
        bot.send_message(message.chat.id, "❌ **L'ora di fine deve essere diversa da start hour!**")
        create_manual_report_handler(message)

    send_welcome(message)
        
# **Irrigate Now**
def irrigate_now_handler(message: telebot.types.Message):
    """Mostra i pulsanti per selezionare il vaso."""
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    buttons = [
        types.KeyboardButton("Basilico"),
        types.KeyboardButton("Fragola"),
    ]
    markup.add(*buttons)
    
    bot.send_message(message.chat.id, "💧 Select the pot for the irrigation:", reply_markup=markup)
    bot.register_next_step_handler(message, irrigate_now)

def irrigate_now(message: telebot.types.Message):
    smartpot_id = message.text.capitalize()
    payload = {"smartpot_id": smartpot_id}
    bot.send_message(message.chat.id,f"💧 Sent irrigation trigger for {smartpot_id}")
    fetch_data("irrigateNow", method="POST", payload=payload)
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
    sent_msg = bot.send_message(message.chat.id, "🛠️ What would you like to do?", reply_markup=markup)
    bot.register_next_step_handler(sent_msg, action_handler)

bot.infinity_polling()
