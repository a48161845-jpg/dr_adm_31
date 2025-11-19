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

# -------------------- Логирование --------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация --------------------
CONFIG = {
    'TOKEN': 'BOT_TOKEN',  # <- Замените на ваш токен
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "5472545113"],
}

SEND_ARGS = {'chat_id': CONFIG['CHAT_ID'], 'message_thread_id': CONFIG['THREAD_ID']}

# -------------------- Вспомогательные функции --------------------
def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""

def moscow_time():
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']

def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

def normalize_date(date_str):
    digits = re.sub(r'\D', '', date_str)
    try:
        if len(digits) == 4:  # ДДММ
            day, month = int(digits[:2]), int(digits[2:])
        elif len(digits) == 3:  # ДММ
            day, month = int(digits[0]), int(digits[1:])
        elif len(digits) >= 6:  # ДДММГГ или ДДММГГГГ
            day, month = int(digits[:2]), int(digits[2:4])
        else:
            return None
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{month:02d}.{day:02d}"
    except:
        return None
    return None

def get_birthday_data(force_update=False):
    if not force_update and os.path.exists(CONFIG['CACHE_FILE']):
        if time.time() - os.path.getmtime(CONFIG['CACHE_FILE']) < CONFIG['CACHE_EXPIRY']:
            try:
                with open(CONFIG['CACHE_FILE'], 'r') as f:
                    return json.load(f)
            except:
                pass

    sheet_id = extract_sheet_id(CONFIG['SPREADSHEET_URL'])
    if not sheet_id:
        logger.error("Некорректная ссылка на таблицу")
        return []

    try:
        resp = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv')
        resp.encoding = 'utf-8'
        content = resp.text.lstrip('\ufeff')
        records = [
            {'Nik': clean_text(row.get('Nik', '')), 'Дата': clean_text(row.get('Дата', ''))}
            for row in csv.DictReader(StringIO(content))
            if clean_text(row.get('Nik', '')) and clean_text(row.get('Дата', ''))
        ]
        with open(CONFIG['CACHE_FILE'], 'w') as f:
            json.dump(records, f)
        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

def get_birthdays_by_date(target_date):
    return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == target_date]

def split_message(msg, limit=3000):
    """Разбиваем длинное сообщение на части"""
    return [msg[i:i+limit] for i in range(0, len(msg), limit)]

def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 {title}\n\nНет дней рождения"

    msg_parts = [f"📅 {title}"]
    if isinstance(birthdays, list):
        msg_parts.append("🎂 Сегодняшние именинники:")
        msg_parts.extend(f"• {name}" for name in birthdays)
        msg_parts.append("🎉 Поздравляйте! 🎉")
    elif isinstance(birthdays, dict):
        for date, names in birthdays.items():
            msg_parts.append(f"\n🗓️ {date}:")
            msg_parts.extend(f"• {name}" for name in names)
        msg_parts.append("\n🎉 Не забудьте поздравить! 🎉")
    return "\n".join(msg_parts)

# -------------------- Telegram Handlers --------------------
async def start(update: Update, _):
    await update.message.reply_text("👋 Привет! Я бот-помощник. Используйте /help для команд.")

async def help_command(update: Update, _):
    await update.message.reply_text(
        "📌 Команды:\n"
        "/check - Сегодняшние дни рождения\n"
        "/upcoming [дни] - Ближайшие дни рождения\n"
        "/recent [дни] - Недавние дни рождения\n"
        "/all - Все дни рождения\n"
        "/myid - Ваш ID\n"
        "/force_update - Обновить данные (админы)\n"
        "/send_test - Тестовое сообщение (админы)"
    )

async def myid(update: Update, _):
    user = update.effective_user
    status = "Руководство" if is_admin(user.id) else "Куратор"
    await update.message.reply_text(f"Ваш ID: {user.id}\nСтатус: {status}")

async def send_message(update, context, message):
    for part in split_message(message):
        try:
            await context.bot.send_message(text=part, **SEND_ARGS)
        except telegram.error.BadRequest as e:
            if "Message thread not found" in str(e):
                await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=part)

# -------------------- Команды --------------------
async def check_birthdays(update, context):
    names = get_today_birthdays()
    msg = format_birthdays(names, "Дни рождения сегодня")
    await send_message(update, context, msg)
    await update.message.reply_text("✅ Сообщение отправлено")

async def upcoming_birthdays_handler(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    data = {k: v for k, v in get_upcoming_birthdays(days).items()}
    msg = format_birthdays(data, f"Ближайшие дни рождения ({days} дней)")
    await send_message(update, context, msg)
    await update.message.reply_text("✅ Сообщение отправлено")

async def recent_birthdays_handler(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    data = {k: v for k, v in get_past_birthdays(days).items()}
    msg = format_birthdays(data, f"Недавние дни рождения ({days} дней)")
    await send_message(update, context, msg)
    await update.message.reply_text("✅ Сообщение отправлено")

async def all_birthdays_handler(update, context):
    data = get_all_birthdays()
    msg = format_birthdays(data, "Все дни рождения")
    await send_message(update, context, msg)
    await update.message.reply_text("✅ Полный список отправлен")

async def force_update_handler(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    get_birthday_data(force_update=True)
    await update.message.reply_text("🔄 Данные обновлены")

async def send_test_handler(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    await send_message(update, context, "🔔 Тестовое сообщение: бот работает")
    await update.message.reply_text("✅ Тестовое сообщение отправлено")

# -------------------- Авто-уведомление --------------------
async def daily_check(context):
    names = get_today_birthdays()
    if names:
        msg = format_birthdays(names, "🔔 Авто-уведомление: Дни рождения сегодня")
        await send_message(None, context, msg)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# -------------------- Запуск бота --------------------
def main():
    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Глобальные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid))

    # Команды для группы
    group_filter = filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP
    app.add_handler(CommandHandler("check", check_birthdays, group_filter))
    app.add_handler(CommandHandler("upcoming", upcoming_birthdays_handler, group_filter))
    app.add_handler(CommandHandler("recent", recent_birthdays_handler, group_filter))
    app.add_handler(CommandHandler("all", all_birthdays_handler, group_filter))
    app.add_handler(CommandHandler("force_update", force_update_handler, group_filter))
    app.add_handler(CommandHandler("send_test", send_test_handler, group_filter))

    app.add_error_handler(error_handler)

    # Ежедневная проверка в 00:00 по Москве
    job_time = datetime.time(hour=21, minute=0)  # UTC 21:00 = MSK 00:00
    app.job_queue.run_daily(daily_check, time=job_time)

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == '__main__':
    main()
