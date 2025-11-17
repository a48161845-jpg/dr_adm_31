import os
import datetime
import requests
import logging
import time
import json
import re
from io import StringIO
import csv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
import telegram.error

# ЛОГИ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("BirthdayBot")

# ИМПОРТ КОНФИГА
from config import CONFIG, SEND_ARGS


def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)|/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) or match.group(2) if match else None


def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""


def moscow_time():
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']


def get_birthday_data():
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = time.time() - os.path.getmtime(CONFIG['CACHE_FILE'])
        if cache_age < CONFIG['CACHE_EXPIRY']:
            try:
                with open(CONFIG['CACHE_FILE'], 'r') as f:
                    return json.load(f)
            except:
                pass

    try:
        sheet_id = extract_sheet_id(CONFIG['SPREADSHEET_URL'])
        if not sheet_id:
            return []

        response = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv')
        content = response.text.lstrip('\ufeff')

        records = []
        for row in csv.DictReader(StringIO(content)):
            if nik := clean_text(row.get('Nik', '')):
                if date_str := clean_text(row.get('Дата', '')):
                    records.append({'Nik': nik, 'Дата': date_str})

        with open(CONFIG['CACHE_FILE'], 'w') as f:
            json.dump(records, f)

        return records

    except:
        return []


def normalize_date(s):
    if '.' in s or '/' in s or '-' in s:
        parts = re.split(r"[./-]", s)
        if len(parts) == 2:
            d, m = parts
            if d.isdigit() and m.isdigit():
                return f"{int(m):02d}.{int(d):02d}"
    return None


def get_today_birthdays():
    today = moscow_time().strftime("%m.%d")
    return [r['Nik'] for r in get_birthday_data() if normalize_date(r['Дата']) == today]


async def start(update, _):
    await update.message.reply_text("👋 Бот работает!\n/help — список команд")


async def help_cmd(update, _):
    await update.message.reply_text(
        "/check — ДР сегодня\n"
        "/upcoming — ближайшие ДР\n"
        "/recent — прошлые ДР\n"
        "/all — весь список\n"
        "/myid — ваш ID\n"
        "\n⚠ Команды /force_update и /send_test — только для админов"
    )


async def myid(update, _):
    await update.message.reply_text(f"Ваш ID: {update.effective_user.id}")


async def check_birthdays(update, context):
    try:
        names = get_today_birthdays()
        message = "🎂 Сегодня ДР:\n" + "\n".join("• " + i for i in names) if names else "Сегодня нет ДР"
        await context.bot.send_message(text=message, **SEND_ARGS)
        await update.message.reply_text("✔ Готово!")
    except Exception as e:
        await update.message.reply_text(str(e))


# ====================== ЗАПУСК =======================

def main():
    TOKEN = os.getenv("BOT_TOKEN")  # ← ТУТ ТОКЕН!
    if not TOKEN:
        raise RuntimeError("❌ Переменная BOT_TOKEN не установлена!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("check", check_birthdays))

    app.run_polling()


if __name__ == "__main__":
    main()
