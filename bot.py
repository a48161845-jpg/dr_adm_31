import os
import datetime
import requests
import logging
import time
import json
import re
import asyncio
from io import StringIO
import csv

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, filters

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': os.environ.get('SPREADSHEET_URL', "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk"),
    'CHAT_ID': os.environ.get('CHAT_ID', "-1002124864225"),
    'THREAD_ID': int(os.environ.get('THREAD_ID', 16232)) if os.environ.get('THREAD_ID') else 16232,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),  # MSK
    'CACHE_FILE': os.environ.get('CACHE_FILE', 'birthday_cache.json'),
    'CACHE_EXPIRY': int(os.environ.get('CACHE_EXPIRY', 300)),  # сек
    'ADMINS': os.environ.get('ADMINS', "1004974578,7233257134,6195550631").split(','),
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# --- Утилиты ---
MD_V2_CHARS = r"_*-[]()~`>#+=|{}.!\""

def escape_md_v2(text: str) -> str:
    # Экранируем специальные символы MarkdownV2
    if not text:
        return ""
    return re.sub(r'([%s])' % re.escape(MD_V2_CHARS), r"\\\1", str(text))

def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def clean_text(text):
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""

def moscow_now():
    tz = datetime.timezone(CONFIG['TIMEZONE_OFFSET'])
    return datetime.datetime.now(tz)

# --- Работа с таблицей и кэшем ---
def read_cache_if_valid():
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = time.time() - os.path.getmtime(CONFIG['CACHE_FILE'])
        if cache_age < CONFIG['CACHE_EXPIRY']:
            try:
                with open(CONFIG['CACHE_FILE'], 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Ошибка чтения кэша: {e}")
    return None

def write_cache(records):
    try:
        with open(CONFIG['CACHE_FILE'], 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка записи кэша: {e}")

def fetch_sheet_as_csv(sheet_id):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv'
    resp = requests.get(url, timeout=20)
    resp.encoding = 'utf-8'
    return resp.text.lstrip('\ufeff')

def parse_csv_to_records(csv_text):
    records = []
    for row in csv.DictReader(StringIO(csv_text)):
        nik = clean_text(row.get('Nik', ''))
        date_str = clean_text(row.get('Дата', ''))
        if nik and date_str:
            records.append({'Nik': nik, 'Дата': date_str})
    return records

def get_birthday_data(force_refresh=False):
    if not force_refresh:
        cached = read_cache_if_valid()
        if cached is not None:
            return cached

    try:
        sheet_id = extract_sheet_id(CONFIG['SPREADSHEET_URL'])
        if not sheet_id:
            logger.error("Некорректная ссылка на таблицу")
            return []

        csv_text = fetch_sheet_as_csv(sheet_id)
        records = parse_csv_to_records(csv_text)
        write_cache(records)
        logger.info(f"Данные таблицы обновлены, записей: {len(records)}")
        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

# --- Нормализация даты ---
def normalize_date(date_str):
    digits = re.sub(r'\D', '', str(date_str))
    if len(digits) >= 3:
        day = int(digits[:2])
        month = int(digits[2:4])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}.{day:02d}"
    return None

def get_birthdays_for_key(target_key):
    # target_key формат mm.dd
    return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == target_key]

def get_today_birthdays():
    return get_birthdays_for_key(moscow_now().strftime("%m.%d"))

def get_upcoming_birthdays(days=7):
    today = moscow_now().date()
    upcoming = {}
    for i in range(1, days + 1):
        future_date = today + datetime.timedelta(days=i)
        date_key = future_date.strftime("%m.%d")
        names = get_birthdays_for_key(date_key)
        if names:
            upcoming[future_date.strftime("%d.%m.%Y")] = names
    return upcoming

def get_past_birthdays(days=7):
    today = moscow_now().date()
    past = {}
    for i in range(1, days + 1):
        past_date = today - datetime.timedelta(days=i)
        date_key = past_date.strftime("%m.%d")
        names = get_birthdays_for_key(date_key)
        if names:
            past[past_date.strftime("%d.%m.%Y")] = names
    return past

# --- Форматирование Markdown сообщений ---
def md_title(text: str) -> str:
    return f"*{escape_md_v2(text)}*"

def md_bold(text: str) -> str:
    return f"*{escape_md_v2(text)}*"

def md_italic(text: str) -> str:
    return f"_{escape_md_v2(text)}_"

def format_birthdays_md(birthdays, title: str) -> str:
    if not birthdays:
        return f"{md_title(title)}\n\n{escape_md_v2('Дней рождения нет :(')}"
    if isinstance(birthdays, list):
        names = ', '.join(escape_md_v2(n) for n in birthdays)
        return f"{md_title(title)}\n\n{names}"
    if isinstance(birthdays, dict):
        parts = [md_title(title)]
        for date, names in birthdays.items():
            names_escaped = ', '.join(escape_md_v2(n) for n in names)
            parts.append(f"{escape_md_v2('🗓️')} {escape_md_v2(date)}: {names_escaped}")
        return '\n'.join(parts)
    return ''

# --- Проверка прав ---
def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

# --- Команды бота (async) ---
async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{md_title('Привет!')}\n\n"
        f"Я — бот-помощник для младшей администрации.\n\n"
        f"{md_italic('Используйте /help для просмотра команд.')}"
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{md_title('Доступные команды:')}\n"
        f"/check — ДР сегодня\n"
        f"/upcoming [N] — ближайшие ДР (по умолчанию 7)\n"
        f"/recent [N] — прошедшие ДР (по умолчанию 7)\n"
        f"/all — весь список\n"
        f"/myid — ваш ID\n\n"
        f"{md_title('Команды для админов:')}\n"
        f"/force_update — обновить данные\n"
        f"/send_test — тестовое сообщение\n"
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def myid(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = "Админ" if is_admin(user.id) else "Пользователь"
    text = f"{md_title('Ваш ID:')} {escape_md_v2(str(user.id))}\n{md_title('Статус:')} {escape_md_v2(status)}"
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def check_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays = get_today_birthdays()
    message = format_birthdays_md(birthdays, "Дни рождения сегодня")
    try:
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
        await update.message.reply_text("✅ Отправлено в ветку")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await update.message.reply_text("❌ Ошибка при отправке в ветку")

async def upcoming_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_upcoming_birthdays(days)
    message = format_birthdays_md(birthdays, f"Ближайшие дни рождения (на {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Отправлено в ветку")

async def recent_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_past_birthdays(days)
    message = format_birthdays_md(birthdays, f"Прошедшие дни рождения (за {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Отправлено в ветку")

async def all_birthdays_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdays_dict = {}
    for r in get_birthday_data():
        nik = r['Nik']
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            birthdays_dict.setdefault(date_str, []).append(nik)
    message = format_birthdays_md(birthdays_dict, "Все дни рождения")
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Отправлено в ветку")

async def force_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    # Обновляем данные в отдельном потоке
    await asyncio.to_thread(get_birthday_data, True)
    await update.message.reply_text("🔄 Данные обновлены")

async def send_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    message = md_bold('🔔 Тестовое сообщение') + '\n' + escape_md_v2('Если вы это видите — бот умеет отправлять Markdown.')
    await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Отправлено в ветку")

# --- Scheduled jobs ---
async def send_daily_birthday_reminder(context: ContextTypes.DEFAULT_TYPE):
    birthdays = await asyncio.to_thread(get_today_birthdays)
    message = format_birthdays_md(birthdays, "Дни рождения сегодня")
    try:
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
        logger.info("Ежедневное сообщение о ДР успешно отправлено")
    except Exception as e:
        logger.error(f"Ошибка при отправке ежедневного ДР: {e}")

async def hourly_refresh_cache(context: ContextTypes.DEFAULT_TYPE):
    # Подгрузка новых данных раз в час
    await asyncio.to_thread(get_birthday_data, True)
    logger.info("Кэш таблицы обновлён по расписанию (раз в час)")

# --- Запуск бота ---
def main():
    if not CONFIG['TOKEN']:
        logger.error('BOT_TOKEN не задан в переменных окружения')
        return

    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Регистрация команд
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
        app.add_handler(CommandHandler(cmd, fn, group_filter))

    # Jobs: ежедневное в 00:00 MSK и ежечасное обновление кэша
    tz = datetime.timezone(CONFIG['TIMEZONE_OFFSET'])
    job_queue = app.job_queue

    job_queue.run_daily(
        send_daily_birthday_reminder,
        time=datetime.time(hour=0, minute=0, tzinfo=tz),
        name="daily_birthday_job",
    )

    # Запускать раз в час (pooling) — интервал 3600 секунд
    job_queue.run_repeating(hourly_refresh_cache, interval=3600, first=10, name='hourly_cache_refresh')

    # Первичное заполнение кэша
    try:
        get_birthday_data()
    except Exception:
        pass

    app.run_polling()

if __name__ == "__main__":
    main()
