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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG = {
    'TOKEN': 'TOKEN',
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "5472545113"],
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}


def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None


def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""


def moscow_time():
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']


def get_birthday_data():
    if os.path.exists(CONFIG['CACHE_FILE']):
        if time.time() - os.path.getmtime(CONFIG['CACHE_FILE']) < CONFIG['CACHE_EXPIRY']:
            try:
                with open(CONFIG['CACHE_FILE'], 'r', encoding='utf-8') as f:
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

        with open(CONFIG['CACHE_FILE'], 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)

        return records

    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []


def normalize_date(date_str):
    digits = re.sub(r'\D', '', date_str)
    formats = [
        (2, 2),  # ddmm
        (2, 2),  # mmdd
        (1, 2),  # dmm
        (2, 1),  # mdd
    ]
    if '.' in date_str or '/' in date_str or '-' in date_str:
        for sep in ['.', '/', '-']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 2:
                    day, month = map(int, parts)
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return f"{month:02d}.{day:02d}"
    for f1, f2 in formats:
        if len(digits) >= f1 + f2:
            try:
                day, month = int(digits[:f1]), int(digits[f1:f1 + f2])
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{month:02d}.{day:02d}"
            except:
                continue
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
            upcoming[future_date.strftime("%d.%m.%Y")] = names
    return upcoming


def get_past_birthdays(days=7):
    today = moscow_time().date()
    past = {}
    for i in range(1, days + 1):
        past_date = today - datetime.timedelta(days=i)
        date_key = past_date.strftime("%m.%d")
        if names := get_birthdays(date_key):
            past[past_date.strftime("%d.%m.%Y")] = names
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

    sorted_dates = dict(sorted(
        birthdays.items(),
        key=lambda x: (
            datetime.datetime.strptime(x[0], "%d.%m").month,
            datetime.datetime.strptime(x[0], "%d.%m").day
        )
    ))
    return sorted_dates


def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 {title}\n\nНа данный период дни рождения отсутствуют"

    if isinstance(birthdays, list):
        names_count = len(birthdays)
        congratulation = "админа!" if names_count == 1 else "админов!"
        return f"🎂 {title}:\n" + '\n'.join(f"• {name}" for name in birthdays) + f"\n\nНе забудьте поздравить {congratulation} 🎉"

    if isinstance(birthdays, dict):
        result = [f"📅 {title}:"]
        for date, names in birthdays.items():
            result.append(f"\n🗓️ {date}:")
            result.extend(f"• {name}" for name in names)
        return '\n'.join(result)

    return ""


def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']


# ----------------- Команды -----------------

async def start(update: Update, _):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\n"
        "Используйте /help для просмотра команд."
    )


async def help_command(update: Update, _):
    help_text = (
        "Доступные команды:\n"
        "• /check - Дни рождения сегодня\n"
        "• /upcoming [дни] - Ближайшие дни рождения\n"
        "• /recent [дни] - Недавние дни рождения\n"
        "• /all - Все дни рождения\n"
        "• /myid - Показать ваш ID\n"
        "Для Руководства:\n"
        "• /force_update - Обновить данные\n"
        "• /send_test - Тестовое сообщение"
    )
    await update.message.reply_text(help_text)


async def myid(update: Update, _):
    user = update.effective_user
    status = "Руководство" if is_admin(user.id) else "Куратор"
    await update.message.reply_text(f"Ваш ID: {user.id}\nСтатус: {status}")


async def check_birthdays(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return
    birthdays = get_today_birthdays()
    message = format_birthdays(birthdays, "Дни рождения сегодня")
    try:
        await context.bot.send_message(text=message, **SEND_ARGS)
    except telegram.error.BadRequest:
        await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=message)
    await update.message.reply_text("✅ Информация отправлена")


async def upcoming_birthdays(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_upcoming_birthdays(days)
    message = format_birthdays(birthdays, f"Ближайшие дни рождения ({days} дней)")
    try:
        await context.bot.send_message(text=message, **SEND_ARGS)
    except telegram.error.BadRequest:
        await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=message)
    await update.message.reply_text("✅ Информация отправлена")


async def recent_birthdays(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_past_birthdays(days)
    message = format_birthdays(birthdays, f"Недавние дни рождения ({days} дней)")
    try:
        await context.bot.send_message(text=message, **SEND_ARGS)
    except telegram.error.BadRequest:
        await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=message)
    await update.message.reply_text("✅ Информация отправлена")


async def all_birthdays(update, context):
    birthdays = get_all_birthdays()
    message = format_birthdays(birthdays, "Все дни рождения")
    try:
        await context.bot.send_message(text=message, **SEND_ARGS)
    except telegram.error.BadRequest:
        await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=message)
    await update.message.reply_text("✅ Полный список отправлен")


async def force_update(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для Руководства")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await update.message.reply_text("🔄 Данные обновлены!")


async def send_test(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для Руководства")
        return
    try:
        await context.bot.send_message(text="🔔 Тестовое сообщение", **SEND_ARGS)
    except telegram.error.BadRequest:
        await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text="🔔 Тестовое сообщение")
    await update.message.reply_text("✅ Тестовое сообщение отправлено")


async def daily_check(context):
    bd = get_today_birthdays()
    if bd:
        message = format_birthdays(bd, "Дни рождения сегодня")
        try:
            await context.bot.send_message(text=message, **SEND_ARGS)
        except telegram.error.BadRequest:
            await context.bot.send_message(chat_id=CONFIG['CHAT_ID'], text=message)


async def error_handler(update, context):
    error = context.error
    logger.error(f"Ошибка: {error}")


def main():
    app = Application.builder().token(CONFIG['TOKEN']).build()

    for cmd, handler in {
        "start": start,
        "help": help_command,
        "myid": myid,
    }.items():
        app.add_handler(CommandHandler(cmd, handler))

    group_filter = filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP

    for cmd, handler in {
        "check": check_birthdays,
        "upcoming": upcoming_birthdays,
        "recent": recent_birthdays,
        "all": all_birthdays,
        "force_update": force_update,
        "send_test": send_test,
    }.items():
        app.add_handler(CommandHandler(cmd, handler, group_filter))

    app.add_error_handler(error_handler)

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(daily_check, time=datetime.time(hour=21, minute=0))  # 21:00 UTC = 00:00 MSK

    app.run_polling()


if __name__ == '__main__':
    main()
