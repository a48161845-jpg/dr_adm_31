import os
import datetime
import requests
import logging
import json
import re
import csv
from io import StringIO
import asyncio
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ----------------- Логирование -----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------- Конфигурация -----------------
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,  # Ветка для сообщений
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

bot = Bot(token=CONFIG['TOKEN'])
dp = Dispatcher()
scheduler = AsyncIOScheduler()

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# ----------------- Вспомогательные функции -----------------
def extract_sheet_id(url: str) -> str | None:
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def clean_text(text: str) -> str:
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text).strip() if text else ""

def moscow_time() -> datetime.datetime:
    return datetime.datetime.utcnow() + CONFIG['TIMEZONE_OFFSET']

def get_birthday_data() -> list[dict]:
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = datetime.datetime.now().timestamp() - os.path.getmtime(CONFIG['CACHE_FILE'])
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

        response = requests.get(f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv')
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

def normalize_date(date_str: str) -> str | None:
    digits = re.sub(r'\D', '', date_str)
    if len(digits) >= 3:
        day = int(digits[:2])
        month = int(digits[2:4])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}.{day:02d}"
    return None

def get_birthdays(target_date: str) -> list[str]:
    return [r['Nik'] for r in get_birthday_data() if (nd := normalize_date(r['Дата'])) and nd == target_date]

def get_today_birthdays() -> list[str]:
    return get_birthdays(moscow_time().strftime("%m.%d"))

def get_upcoming_birthdays(days=7) -> dict:
    today = moscow_time().date()
    upcoming = {}
    for i in range(1, days + 1):
        future_date = today + datetime.timedelta(days=i)
        date_key = future_date.strftime("%m.%d")
        names = get_birthdays(date_key)
        if names:
            upcoming[future_date.strftime("%d.%m.%Y")] = names
    return upcoming

def get_past_birthdays(days=7) -> dict:
    today = moscow_time().date()
    past = {}
    for i in range(1, days + 1):
        past_date = today - datetime.timedelta(days=i)
        date_key = past_date.strftime("%m.%d")
        names = get_birthdays(date_key)
        if names:
            past[past_date.strftime("%d.%m.%Y")] = names
    return past

def format_birthdays(birthdays: list[str], title: str) -> str:
    if not birthdays:
        return f"📅 {title}\n\nДней рождения нет"
    return f"📅 {title}:\n" + ', '.join(birthdays)

def format_birthdays_dict(birthdays: dict, title: str) -> str:
    if not birthdays:
        return f"📅 {title}\n\nДней рождения нет"
    result = [f"📅 {title}:"]
    for date, names in birthdays.items():
        result.append(f"🗓️ {date}: {', '.join(names)}")
    return "\n".join(result)

def is_admin(user_id: int) -> bool:
    return str(user_id) in CONFIG['ADMINS']

# ----------------- Команды -----------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.reply(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\n"
        "Используйте /help для просмотра команд."
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "Доступные команды:\n"
        "/check - ДР сегодня\n"
        "/all - весь список\n"
        "/upcoming - ближайшие ДР\n"
        "/recent - прошедшие ДР\n"
        "/myid - ваш ID\n\n"
        "Команды для админов:\n"
        "/force_update - обновить данные\n"
        "/send_test - тестовое сообщение\n"
        "/del_link <ссылка> - удалить сообщение бота по ссылке"
    )
    await message.reply(text)

@dp.message(Command("myid"))
async def myid_cmd(message: types.Message):
    status = "Админ" if is_admin(message.from_user.id) else "Пользователь"
    await message.reply(f"Ваш ID: {message.from_user.id}\nСтатус: {status}")

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    birthdays = get_today_birthdays()
    message_text = format_birthdays(birthdays, "Дни рождения сегодня")
    await bot.send_message(**SEND_ARGS, text=message_text)
    await message.reply("✅ Отправлено в ветку")

@dp.message(Command("all"))
async def all_cmd(message: types.Message):
    birthdays_dict = {}
    for r in get_birthday_data():
        nik = r['Nik']
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            birthdays_dict.setdefault(date_str, []).append(nik)
    result = [f"📅 Все дни рождения:"]
    for date, names in birthdays_dict.items():
        result.append(f"🗓️ {date}: {', '.join(names)}")
    await bot.send_message(**SEND_ARGS, text="\n".join(result))
    await message.reply("✅ Отправлено в ветку")

@dp.message(Command("upcoming"))
async def upcoming_cmd(message: types.Message):
    birthdays = get_upcoming_birthdays(7)
    message_text = format_birthdays_dict(birthdays, "Ближайшие дни рождения (7 дней)")
    await bot.send_message(**SEND_ARGS, text=message_text)
    await message.reply("✅ Отправлено в ветку")

@dp.message(Command("recent"))
async def recent_cmd(message: types.Message):
    birthdays = get_past_birthdays(7)
    message_text = format_birthdays_dict(birthdays, "Прошедшие дни рождения (7 дней)")
    await bot.send_message(**SEND_ARGS, text=message_text)
    await message.reply("✅ Отправлено в ветку")

@dp.message(Command("force_update"))
async def force_update_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только для админов")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await message.reply("🔄 Данные обновлены")

@dp.message(Command("send_test"))
async def send_test_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только для админов")
        return
    await bot.send_message(**SEND_ARGS, text="🔔 Тестовое сообщение")
    await message.reply("✅ Отправлено в ветку")

# ----------------- Удаление сообщений по ссылке -----------------
@dp.message(Command("del_link"))
async def del_link_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только для админов")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❌ Укажите ссылку на сообщение")
        return
    link = args[1].strip()
    try:
        # Пример ссылки: https://t.me/c/CHAT_ID/MESSAGE_ID
        parts = urlparse(link).path.split('/')
        message_id = int(parts[-1])
        await bot.delete_message(chat_id=CONFIG['CHAT_ID'], message_id=message_id)
        await message.reply("✅ Сообщение удалено")
    except Exception as e:
        await message.reply(f"❌ Ошибка удаления: {e}")

# ----------------- Планировщик -----------------
async def daily_birthday_reminder():
    birthdays = get_today_birthdays()
    message_text = format_birthdays(birthdays, "Дни рождения сегодня")
    await bot.send_message(**SEND_ARGS, text=message_text)

async def start_scheduler():
    scheduler.add_job(daily_birthday_reminder, 'cron', hour=0, minute=0)
    scheduler.start()

# ----------------- Запуск -----------------
async def main():
    await start_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
