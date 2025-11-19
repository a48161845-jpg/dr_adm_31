import os
import datetime
import requests
import logging
import time
import json
import re
from io import StringIO
import csv
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# -------------------
# Логирование
# -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------
# Конфигурация
# -------------------
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),  # Ваш токен
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,  # Существующий thread или None
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# -------------------
# Функции для работы с таблицей
# -------------------
def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""

def moscow_time():
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']

def get_birthday_data():
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = time.time() - os.path.getmtime(CONFIG['CACHE_FILE'])
        if cache_age < CONFIG['CACHE_EXPIRY']:
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

        response = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv', timeout=10)
        response.encoding = 'utf-8'
        content = response.text.lstrip('\ufeff')

        records = []
        for row in csv.DictReader(StringIO(content)):
            nik = clean_text(row.get('Nik', ''))
            date_str = clean_text(row.get('Дата', ''))
            if nik and date_str:
                records.append({'Nik': nik, 'Дата': date_str})

        with open(CONFIG['CACHE_FILE'], 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)
        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

# -------------------
# Даты
# -------------------
def normalize_date(date_str):
    try:
        digits = re.sub(r'\D', '', date_str)
        if len(digits) >= 4:
            day = int(digits[:2])
            month = int(digits[2:4])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{day:02d}.{month:02d}"  # Исправлено: день.месяц
        return None
    except (ValueError, IndexError):
        return None

def get_birthdays(target_date):
    try:
        # target_date в формате "dd.mm"
        return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == target_date]
    except Exception as e:
        logger.error(f"Ошибка в get_birthdays: {e}")
        return []

def get_today_birthdays():
    return get_birthdays(moscow_time().strftime("%d.%m"))  # Исправлено: день.месяц

def get_upcoming_birthdays(days=7):
    try:
        today = moscow_time().date()
        upcoming = {}
        for i in range(1, days + 1):
            future_date = today + datetime.timedelta(days=i)
            date_key = future_date.strftime("%d.%m")  # Исправлено: день.месяц
            names = get_birthdays(date_key)
            if names:
                upcoming[future_date.strftime("%d.%m.%Y")] = names
        return upcoming
    except Exception as e:
        logger.error(f"Ошибка в get_upcoming_birthdays: {e}")
        return {}

def get_past_birthdays(days=7):
    try:
        today = moscow_time().date()
        past = {}
        for i in range(1, days + 1):
            past_date = today - datetime.timedelta(days=i)
            date_key = past_date.strftime("%d.%m")  # Исправлено: день.месяц
            names = get_birthdays(date_key)
            if names:
                past[past_date.strftime("%d.%m.%Y")] = names
        return past
    except Exception as e:
        logger.error(f"Ошибка в get_past_birthdays: {e}")
        return {}

# -------------------
# Форматирование сообщений
# -------------------
def format_birthdays(birthdays, title):
    try:
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
    except Exception as e:
        logger.error(f"Ошибка форматирования: {e}")
        return f"❌ Ошибка при форматировании сообщения"

def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

# -------------------
# Команды
# -------------------
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
    try:
        birthdays = get_today_birthdays()
        message = format_birthdays(birthdays, "Дни рождения сегодня")
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
        await update.message.reply_text("❤️")
    except Exception as e:
        logger.error(f"Ошибка в check_birthdays: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды")

async def upcoming_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
        birthdays = get_upcoming_birthdays(days)
        message = format_birthdays(birthdays, f"Ближайшие дни рождения (на {days} дней)")
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
        await update.message.reply_text("❤️")
    except Exception as e:
        logger.error(f"Ошибка в upcoming_birthdays_cmd: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды")

async def recent_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
        birthdays = get_past_birthdays(days)
        message = format_birthdays(birthdays, f"Прошедшие дни рождения (за {days} дней)")
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
        await update.message.reply_text("❤️")
    except Exception as e:
        logger.error(f"Ошибка в recent_birthdays_cmd: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды")

async def all_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        birthdays_dict = {}
        for r in get_birthday_data():
            nik = r['Nik']
            if nd := normalize_date(r['Дата']):
                # nd в формате "dd.mm", преобразуем к "dd.mm" для отображения
                date_str = nd  # уже в правильном формате
                birthdays_dict.setdefault(date_str, []).append(nik)
        
        # Сортируем по дате
        sorted_birthdays = {}
        for date_str in sorted(birthdays_dict.keys(), key=lambda x: datetime.datetime.strptime(x, "%d.%m")):
            sorted_birthdays[date_str] = birthdays_dict[date_str]
            
        message = format_birthdays(sorted_birthdays, "Все дни рождения")
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
        await update.message.reply_text("❤️")
    except Exception as e:
        logger.error(f"Ошибка в all_birthdays_cmd: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды")

async def force_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    try:
        if os.path.exists(CONFIG['CACHE_FILE']):
            os.remove(CONFIG['CACHE_FILE'])
        get_birthday_data()
        await update.message.reply_text("🔄 Данные обновлены")
    except Exception as e:
        logger.error(f"Ошибка в force_update: {e}")
        await update.message.reply_text("❌ Ошибка при обновлении данных")

async def send_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    try:
        await context.bot.send_message(**SEND_ARGS, text="🔔 Тестовое сообщение")
        await update.message.reply_text("❤️")
    except Exception as e:
        logger.error(f"Ошибка в send_test: {e}")
        await update.message.reply_text("❌ Ошибка при отправке тестового сообщения")

# -------------------
# Функция для ежедневной отправки ДР
# -------------------
async def send_daily_birthdays():
    try:
        birthdays = get_today_birthdays()
        if birthdays:
            message = format_birthdays(birthdays, "Дни рождения сегодня")
            # Получаем application из глобального контекста
            from telegram.ext import Application
            app = Application.builder().token(CONFIG['TOKEN']).build()
            await app.bot.send_message(**SEND_ARGS, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в send_daily_birthdays: {e}")

# -------------------
# Запуск бота
# -------------------
def main():
    if not CONFIG['TOKEN']:
        logger.error("Токен бота не найден! Установите переменную окружения BOT_TOKEN")
        return

    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Глобальные команды
    global_cmds = {
        "start": start,
        "help": help_command,
        "myid": myid
    }
    for cmd, fn in global_cmds.items():
        app.add_handler(CommandHandler(cmd, fn))

    # Команды для групп
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
        app.add_handler(CommandHandler(cmd, fn, group_filter))

    # APScheduler
    scheduler = AsyncIOScheduler()
    # Исправлено: передаем корутину правильно
    scheduler.add_job(
        send_daily_birthdays,
        'cron', 
        hour=6, 
        minute=0,
        timezone=datetime.timezone(datetime.timedelta(hours=3))  # МСК
    )
    scheduler.start()

    # Запуск бота
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
