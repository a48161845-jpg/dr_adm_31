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

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),  # В BotHost задайте переменную BOT_TOKEN
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 1,  # Укажите существующий thread или оставьте None
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "5472545113"],
}

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
            if nik := clean_text(row.get('Nik', '')):
                if date_str := clean_text(row.get('Дата', '')):
                    records.append({'Nik': nik, 'Дата': date_str})

        with open(CONFIG['CACHE_FILE'], 'w') as f:
            json.dump(records, f)

        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

def normalize_date(date_str):
    if '.' in date_str or '/' in date_str or '-' in date_str:
        separators = ['.', '/', '-']
        for sep in separators:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 2:
                    day_str, month_str = parts
                    try:
                        day = int(day_str)
                        month = int(month_str)
                        if 1 <= month <= 12 and 1 <= day <= 31:
                            return f"{month:02d}.{day:02d}"
                    except ValueError:
                        continue
    digits = re.sub(r'\D', '', date_str)
    if len(digits) == 4:
        for p in [(0,2,2,4),(2,4,0,2)]:
            try:
                day = int(digits[p[0]:p[1]])
                month = int(digits[p[2]:p[3]])
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{month:02d}.{day:02d}"
            except:
                pass
    elif len(digits) == 3:
        try:
            day = int(digits[0])
            month = int(digits[1:])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}.{day:02d}"
        except:
            pass
        try:
            month = int(digits[0])
            day = int(digits[1:])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}.{day:02d}"
        except:
            pass
    elif len(digits) == 8:
        for p in [(0,2,2,4),(2,4,0,2)]:
            try:
                day = int(digits[p[0]:p[1]])
                month = int(digits[p[2]:p[3]])
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{month:02d}.{day:02d}"
            except:
                pass
    logger.warning(f"Не удалось нормализовать дату: {date_str}")
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
        if names := get_birthdays(date_key):
            formatted_date = future_date.strftime("%d.%m.%Y")
            upcoming[formatted_date] = names
    return upcoming

def get_past_birthdays(days=7):
    today = moscow_time().date()
    past = {}
    for i in range(1, days + 1):
        past_date = today - datetime.timedelta(days=i)
        date_key = past_date.strftime("%m.%d")
        if names := get_birthdays(date_key):
            formatted_date = past_date.strftime("%d.%m.%Y")
            past[formatted_date] = names
    return past

def get_all_birthdays():
    birthdays = {}
    for record in get_birthday_data():
        nik = record['Nik']
        date_str = record['Дата']
        if normalized := normalize_date(date_str):
            try:
                month, day = normalized.split('.')
                display_date = f"{int(day):02d}.{int(month):02d}"
            except:
                display_date = normalized
        else:
            display_date = date_str
        birthdays.setdefault(display_date, []).append(nik)
    sorted_dates = sorted(
        birthdays.items(),
        key=lambda x: (
            datetime.datetime.strptime(x[0], "%d.%m").month,
            datetime.datetime.strptime(x[0], "%d.%m").day
        ) if '.' in x[0] else (0,0)
    )
    return dict(sorted_dates)

def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 {title}\n\nНа данный период дни рождения отсутствуют"
    if isinstance(birthdays, list):
        names_count = len(birthdays)
        congratulation = "Не забудьте поздравить админа!" if names_count == 1 else "Не забудьте поздравить админов!"
        return (f"🎂 {title}:\n\n" + '\n'.join(f"• {name}" for name in birthdays) + f"\n\n{congratulation} 🎉")
    if isinstance(birthdays, dict):
        result = [f"📅 {title}:"]
        for date, names in birthdays.items():
            names_count = len(names)
            congratulation = "админа!" if names_count == 1 else "админов!"
            result.append(f"\n🗓️ {date}:")
            result.extend(f"• {name}" for name in names)
            if "Ближайшие" in title:
                result.append(f"\nУ вас есть время подготовить поздравления {congratulation} 🎁")
            elif "Недавние" in title:
                result.append(f"\nПроверьте, не пропустили ли вы кого-то из {congratulation}")
        return '\n'.join(result)
    return ""

def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

async def send_message_safe(context, text, chat_id=None, thread_id=None):
    chat_id = chat_id or CONFIG['CHAT_ID']
    kwargs = {'chat_id': chat_id}
    if thread_id:
        kwargs['message_thread_id'] = thread_id
    try:
        await context.bot.send_message(text=text, **kwargs)
    except telegram.error.BadRequest as e:
        if "Message thread not found" in str(e):
            await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            raise e

# Команды
async def start(update: Update, _):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\n"
        "Используйте /help для просмотра доступных команд."
    )

async def help_command(update: Update, _):
    text = (
        "Доступные команды:\n\n"
        "/check — ДР сегодня\n"
        "/upcoming [дни] — ближайшие ДР\n"
        "/recent [дни] — прошлые ДР\n"
        "/all — весь список\n"
        "/myid — ваш ID\n\n"
        "⚠ /force_update и /send_test — только для админов"
    )
    await update.message.reply_text(text)

async def myid(update: Update, _):
    user = update.effective_user
    status = "Руководство младшей" if is_admin(user.id) else "Куратор младшей администрации"
    await update.message.reply_text(f"Ваш ID: {user.id}\nСтатус: {status}")

async def check_birthdays(update, context):
    birthdays = get_today_birthdays()
    message = format_birthdays(birthdays, "Дни рождения сегодня")
    await send_message_safe(context, message, chat_id=update.effective_chat.id, thread_id=CONFIG.get('THREAD_ID'))

async def upcoming_birthdays(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    days = max(1, min(days, 60))
    birthdays = get_upcoming_birthdays(days)
    message = format_birthdays(birthdays, f"Ближайшие дни рождения (на {days} дней)")
    await send_message_safe(context, message, chat_id=update.effective_chat.id, thread_id=CONFIG.get('THREAD_ID'))

async def recent_birthdays(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    days = max(1, min(days, 60))
    birthdays = get_past_birthdays(days)
    message = format_birthdays(birthdays, f"Недавние дни рождения (за {days} дней)")
    await send_message_safe(context, message, chat_id=update.effective_chat.id, thread_id=CONFIG.get('THREAD_ID'))

async def all_birthdays(update, context):
    birthdays = get_all_birthdays()
    message = format_birthdays(birthdays, "Все дни рождения команды")
    max_length = 3000
    for i in range(0, len(message), max_length):
        await send_message_safe(context, message[i:i+max_length], chat_id=update.effective_chat.id, thread_id=CONFIG.get('THREAD_ID'))

async def force_update(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await update.message.reply_text("🔄 Данные обновлены!")

async def send_test(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    await send_message_safe(context, "🔔 Тестовое сообщение: бот работает!")

async def daily_check(context):
    bd = get_today_birthdays()
    if bd:
        message = format_birthdays(bd, "Авто: ДР сегодня")
        await send_message_safe(context, message, thread_id=CONFIG.get('THREAD_ID'))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# Запуск
def main():
    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Общие команды
    for cmd, handler in {
        "start": start,
        "help": help_command,
        "myid": myid
    }.items():
        app.add_handler(CommandHandler(cmd, handler))

    # Групповые команды
    group_filter = filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP
    for cmd, handler in {
        "check": check_birthdays,
        "upcoming": upcoming_birthdays,
        "recent": recent_birthdays,
        "all": all_birthdays,
        "force_update": force_update,
        "send_test": send_test
    }.items():
        app.add_handler(CommandHandler(cmd, handler, group_filter))

    app.add_error_handler(error_handler)

    # Ежедневная проверка ДР в 00:00 МСК (21:00 UTC)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(daily_check, time=datetime.time(hour=21, minute=0))
        logger.info("Ежедневная проверка настроена")

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
