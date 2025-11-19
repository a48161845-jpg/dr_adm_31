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
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ------------------- Логирование -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- Конфигурация -------------------
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,  # Укажите существующий thread или None
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# ------------------- Вспомогательные функции -------------------
def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""

def moscow_time():
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']

def get_birthday_data():
    """Возвращает данные ДР из кеша или Google Sheets"""
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = time.time() - os.path.getmtime(CONFIG['CACHE_FILE'])
        if cache_age < CONFIG['CACHE_EXPIRY']:
            try:
                with open(CONFIG['CACHE_FILE'], 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Ошибка кэша: {e}")
    try:
        sheet_id = extract_sheet_id(CONFIG['SPREADSHEET_URL'])
        if not sheet_id:
            logger.error("Некорректная ссылка на таблицу")
            return []

        response = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv')
        response.encoding = 'utf-8'
        content = response.text.lstrip('\ufeff')

        records = []
        for row in csv.DictReader(StringIO(content)):
            nik = clean_text(row.get('Nik', ''))
            date_str = clean_text(row.get('Дата', ''))
            if nik and date_str:
                records.append({'Nik': nik, 'Дата': date_str})

        with open(CONFIG['CACHE_FILE'], 'w') as f:
            json.dump(records, f)
        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

def normalize_date(date_str):
    digits = re.sub(r'\D', '', date_str)
    if len(digits) >= 3:
        day = int(digits[:2])
        month = int(digits[2:4])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}.{day:02d}"
    return None

def get_birthdays(target_date):
    return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == target_date]

def get_today_birthdays():
    return get_birthdays(moscow_time().strftime("%m.%d"))

def get_upcoming_birthdays(days=7):
    today = moscow_time().date()
    upcoming = {}
    for i in range(1, days + 1):
        future_date = today + datetime.timedelta(days=i)
        date_key = future_date.strftime("%m.%d")
        names = get_birthdays(date_key)
        if names:
            upcoming[future_date.strftime("%d.%m.%Y")] = names
    return upcoming

def get_past_birthdays(days=7):
    today = moscow_time().date()
    past = {}
    for i in range(1, days + 1):
        past_date = today - datetime.timedelta(days=i)
        date_key = past_date.strftime("%m.%d")
        names = get_birthdays(date_key)
        if names:
            past[past_date.strftime("%d.%m.%Y")] = names
    return past

def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 *{title}*\n\nДней рождения нет 🎉"
    if isinstance(birthdays, list):
        return f"📅 *{title}*:\n" + ', '.join(f"🎂 {name}" for name in birthdays)
    if isinstance(birthdays, dict):
        result = [f"📅 *{title}*:"]
        for date, names in sorted(birthdays.items(), key=lambda x: datetime.datetime.strptime(x[0], "%d.%m.%Y")):
            result.append(f"🗓️ *{date}*: {', '.join(f'🎂 {n}' for n in names)}")
        return '\n'.join(result)
    return ""

def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

# ------------------- Команды -------------------
async def start(update: Update, _):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\n"
        "Используйте /help для просмотра команд."
    )

async def help_command(update: Update, _):
    text = (
        "Доступные команды:\n"
        "/check - ДР сегодня\n"
        "/upcoming - ближайшие ДР\n"
        "/recent - прошедшие ДР\n"
        "/all - весь список\n"
        "/myid - ваш ID\n\n"
        "Команды для админов:\n"
        "/force_update - обновить данные\n"
        "/send_test - тестовое сообщение"
    )
    await update.message.reply_text(text)

async def myid(update: Update, _):
    user = update.effective_user
    status = "Админ" if is_admin(user.id) else "Пользователь"
    await update.message.reply_text(f"Ваш ID: {user.id}\nСтатус: {status}")

async def check_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays = get_today_birthdays()
    message = format_birthdays(birthdays, "Дни рождения сегодня")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
    try:
        await update.message.reply_text("❤️")
    except:
        pass

async def upcoming_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_upcoming_birthdays(days)
    message = format_birthdays(birthdays, f"Ближайшие дни рождения (на {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
    try:
        await update.message.reply_text("❤️")
    except:
        pass

async def recent_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_past_birthdays(days)
    message = format_birthdays(birthdays, f"Прошедшие дни рождения (за {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
    try:
        await update.message.reply_text("❤️")
    except:
        pass

async def all_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays_dict = {}
    for r in get_birthday_data():
        nik = r['Nik']
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            birthdays_dict.setdefault(date_str, []).append(nik)
    message = format_birthdays(birthdays_dict, "Все дни рождения")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
    try:
        await update.message.reply_text("❤️")
    except:
        pass

async def force_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await update.message.reply_text("🔄 Данные обновлены")

async def send_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    await context.bot.send_message(**SEND_ARGS, text="🔔 Тестовое сообщение")
    try:
        await update.message.reply_text("❤️")
    except:
        pass

# ------------------- Автонапоминания -------------------
async def send_daily_birthdays(context: ContextTypes.DEFAULT_TYPE):
    birthdays = get_today_birthdays()
    if birthdays:
        message = format_birthdays(birthdays, "Сегодняшние дни рождения")
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")

def schedule_jobs(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: app.create_task(send_daily_birthdays(app)), 'cron', hour=9, minute=0)
    scheduler.start()

# ------------------- Запуск -------------------
def main():
    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Основные команды
    global_cmds = {
        "start": start,
        "help": help_command,
        "myid": myid
    }
    for cmd, fn in global_cmds.items():
        app.add_handler(CommandHandler(cmd, fn))

    group_filter = filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP

    group_cmds = {
        "check": check_birthdays,
        "upcoming": upcoming_birthdays_cmd,
        "recent": recent_birthdays_cmd,
        "all": all_birthdays_cmd,
        "force_update": force_update,
        "send_test": send_test
    }
    for cmd, fn in group_cmds.items():
        app.add_handler(CommandHandler(cmd, fn, filters=group_filter))

    # Запуск планировщика
    schedule_jobs(app)

    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()
