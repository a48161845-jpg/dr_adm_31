import datetime
import re
import csv
import json
import time
import logging
import requests
import asyncio
from io import StringIO

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, filters

# ------------------- Логирование -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- Конфигурация -------------------
CONFIG = {
    'TOKEN': 'YOUR_BOT_TOKEN_HERE',  # Вставьте токен бота
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# ------------------- Markdown и утилиты -------------------
MD_CHARS = r"_*-[]()~`>#+=|{}.!\""

def escape_md(text: str) -> str:
    return re.sub(f'([{re.escape(MD_CHARS)}])', r"\\\1", str(text)) if text else ""

def md_title(text): return f"🎉 *{escape_md(text)}*"
def md_bold(text): return f"*{escape_md(text)}*"
def md_italic(text): return f"_{escape_md(text)}_"
def md_line(): return "──────────────"

def clean_text(text): return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', str(text)).strip() if text else ""
def moscow_now(): return datetime.datetime.now(datetime.timezone(CONFIG['TIMEZONE_OFFSET']))
def extract_sheet_id(url): 
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return m.group(1) if m else None

# ------------------- Кэш -------------------
def read_cache():
    if os.path.exists(CONFIG['CACHE_FILE']) and (time.time() - os.path.getmtime(CONFIG['CACHE_FILE']) < CONFIG['CACHE_EXPIRY']):
        try:
            with open(CONFIG['CACHE_FILE'], 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def write_cache(records):
    try:
        with open(CONFIG['CACHE_FILE'], 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка записи кэша: {e}")

# ------------------- Работа с таблицей -------------------
def fetch_sheet_csv(sheet_id):
    resp = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv', timeout=20)
    resp.encoding = 'utf-8'
    return resp.text.lstrip('\ufeff')

def parse_csv(text):
    records = []
    for r in csv.DictReader(StringIO(text)):
        nik, date_str = clean_text(r.get('Nik', '')), clean_text(r.get('Дата', ''))
        if nik and date_str:
            records.append({'Nik': nik, 'Дата': date_str})
    return records

def get_birthday_data(force_refresh=False):
    if not force_refresh:
        cached = read_cache()
        if cached is not None:
            return cached
    try:
        sheet_id = extract_sheet_id(CONFIG['SPREADSHEET_URL'])
        if not sheet_id: 
            logger.error("Некорректная ссылка на таблицу")
            return []
        records = parse_csv(fetch_sheet_csv(sheet_id))
        write_cache(records)
        logger.info(f"Данные таблицы обновлены, записей: {len(records)}")
        return records
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

# ------------------- Работа с датами -------------------
def normalize_date(date_str):
    digits = re.sub(r'\D', '', str(date_str))
    if len(digits) >= 3:
        day, month = int(digits[:2]), int(digits[2:4])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}.{day:02d}"
    return None

def get_birthdays_for_key(key): 
    return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == key]

def get_today_birthdays(): return get_birthdays_for_key(moscow_now().strftime("%m.%d"))

def get_birthdays_range(days=7, past=False):
    today = moscow_now().date()
    result = {}
    for i in range(1, days + 1):
        d = today - datetime.timedelta(days=i) if past else today + datetime.timedelta(days=i)
        key = d.strftime("%m.%d")
        names = get_birthdays_for_key(key)
        if names: result[d.strftime("%d.%m.%Y")] = names
    return result

# ------------------- Форматирование сообщений -------------------
def format_birthdays_md(bdays, title):
    parts = [md_line(), md_title(title), md_line()]
    if not bdays: 
        parts.append("Дней рождения нет 😔")
    elif isinstance(bdays, list):
        parts.append(", ".join(escape_md(n) for n in bdays))
    elif isinstance(bdays, dict):
        for date, names in bdays.items():
            parts.append(f"📅 {escape_md(date)}: {', '.join(escape_md(n) for n in names)}")
    parts.append(md_line())
    return '\n'.join(parts)

def is_admin(uid): return str(uid) in CONFIG['ADMINS']

async def react_success(update: Update):
    try:
        await update.message.reply_text("❤️‍🔥")
    except Exception as e:
        logger.error(f"Не удалось поставить реакцию: {e}")
        await update.message.reply_text("❌ Ошибка реакции")

# ------------------- Команды -------------------
async def start(update: Update, _):
    await update.message.reply_text(
        f"{md_title('Привет!')}\nЯ — бот для младшей администрации.\n{md_italic('Используйте /help для списка команд.')}",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )

async def help_command(update: Update, _):
    text = (
        f"{md_title('Доступные команды:')}\n"
        "/check — ДР сегодня\n"
        "/upcoming [N] — ближайшие ДР\n"
        "/recent [N] — прошедшие ДР\n"
        "/all — весь список\n"
        "/myid — ваш ID\n\n"
        f"{md_title('Команды для админов:')}\n"
        "/force_update — обновить данные\n"
        "/send_test — тестовое сообщение"
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def myid(update: Update, _):
    user = update.effective_user
    status = "Админ" if is_admin(user.id) else "Пользователь"
    text = f"{md_title('Ваш ID:')} {escape_md(str(user.id))}\n{md_title('Статус:')} {escape_md(status)}"
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def send_birthdays(update, context, bdays, title):
    message = format_birthdays_md(bdays, title)
    try:
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
        await react_success(update)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await update.message.reply_text("❌ Ошибка отправки")

async def check_birthdays(update, context):
    await send_birthdays(update, context, get_today_birthdays(), "Дни рождения сегодня")

async def upcoming_birthdays_cmd(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    await send_birthdays(update, context, get_birthdays_range(days), f"Ближайшие дни рождения (на {days} дней)")

async def recent_birthdays_cmd(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    await send_birthdays(update, context, get_birthdays_range(days, past=True), f"Прошедшие дни рождения (за {days} дней)")

async def all_birthdays_cmd(update, context):
    all_bd = {}
    for r in get_birthday_data():
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            all_bd.setdefault(date_str, []).append(r['Nik'])
    await send_birthdays(update, context, all_bd, "Все дни рождения")

async def force_update(update, context):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Только для админов")
    await asyncio.to_thread(get_birthday_data, True)
    await update.message.reply_text("🔄 Данные обновлены")

async def send_test(update, context):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Только для админов")
    msg = f"{md_bold('🔔 Тестовое сообщение')}\nЕсли вы это видите — бот умеет Markdown."
    await context.bot.send_message(**SEND_ARGS, text=msg, parse_mode=constants.ParseMode.MARKDOWN_V2)
    await react_success(update)

# ------------------- Scheduled jobs -------------------
async def send_daily_birthday_reminder(context):
    bdays = await asyncio.to_thread(get_today_birthdays)
    message = format_birthdays_md(bdays, "Дни рождения сегодня")
    try:
        await context.bot.send_message(**SEND_ARGS, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Ошибка при отправке ежедневного ДР: {e}")

async def hourly_refresh_cache(context):
    await asyncio.to_thread(get_birthday_data, True)
    logger.info("Кэш таблицы обновлён по расписанию (раз в час)")

# ------------------- Запуск бота -------------------
def main():
    if not CONFIG['TOKEN']:
        logger.error('BOT_TOKEN не задан')
        return

    # Создаём приложение
    app = Application.builder().token(CONFIG['TOKEN']).build()

    # Проверяем, что job_queue доступен
    if app.job_queue is None:
        from telegram.ext import JobQueue
        app.job_queue = JobQueue(application=app)

    # --- Регистрация команд ---
    global_cmds = {"start": start, "help": help_command, "myid": myid}
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

    # --- Scheduled jobs ---
    tz = datetime.timezone(CONFIG['TIMEZONE_OFFSET'])
    jq = app.job_queue

    # Ежедневное сообщение в 00:00 MSK
    jq.run_daily(send_daily_birthday_reminder, time=datetime.time(hour=0, minute=0, tzinfo=tz), name="daily_birthday_job")

    # Ежечасное обновление кэша
    jq.run_repeating(hourly_refresh_cache, interval=3600, first=10, name='hourly_cache_refresh')

    # Первичная загрузка кэша
    try:
        get_birthday_data()
    except Exception:
        pass

    # Запуск бота
    app.run_polling()
