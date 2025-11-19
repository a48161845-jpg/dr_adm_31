import os
import datetime
import requests
import json
import csv
import re
import asyncio
from io import StringIO

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Конфигурация ---
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': -1002124864225,
    'THREAD_ID': 16232,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

# --- Инициализация бота ---
bot = Bot(token=CONFIG['TOKEN'])
dp = Dispatcher()

# --- Вспомогательные функции ---
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
    if len(digits) >= 3:
        day = int(digits[:2])
        month = int(digits[2:4])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}.{day:02d}"
    return None

def get_birthday_data():
    if os.path.exists(CONFIG['CACHE_FILE']):
        cache_age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(CONFIG['CACHE_FILE']))).total_seconds()
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
    except:
        return []

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

def format_birthdays(bd, title):
    if not bd:
        return f"📅 *{title}*\n\nНет дней рождения"
    if isinstance(bd, list):
        return f"📅 *{title}*\n\n🎉 " + ', '.join(bd)
    if isinstance(bd, dict):
        lines = [f"📅 *{title}*"]
        for date, names in bd.items():
            lines.append(f"🗓️ {date}: {', '.join(names)}")
        return "\n".join(lines)
    return ""

# --- Хэндлеры команд ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\nИспользуйте /help для просмотра команд."
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
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
    await message.answer(text)

@dp.message(Command("myid"))
async def myid_cmd(message: types.Message):
    status = "Админ" if is_admin(message.from_user.id) else "Пользователь"
    await message.answer(f"Ваш ID: {message.from_user.id}\nСтатус: {status}")

async def add_heart(message: types.Message):
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=message.text + " 🔥❤️"
        )
    except:
        pass

@dp.message(Command("check"))
async def check_birthdays_cmd(message: types.Message):
    bd = get_today_birthdays()
    text = format_birthdays(bd, "Дни рождения сегодня")
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text=text, parse_mode="Markdown")
    await add_heart(message)

@dp.message(Command("upcoming"))
async def upcoming_birthdays_cmd(message: types.Message):
    days = int(message.get_args()) if message.get_args().isdigit() else 7
    bd = get_upcoming_birthdays(days)
    text = format_birthdays(bd, f"Ближайшие дни рождения ({days} дней)")
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text=text, parse_mode="Markdown")
    await add_heart(message)

@dp.message(Command("recent"))
async def recent_birthdays_cmd(message: types.Message):
    days = int(message.get_args()) if message.get_args().isdigit() else 7
    bd = get_past_birthdays(days)
    text = format_birthdays(bd, f"Прошедшие дни рождения ({days} дней)")
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text=text, parse_mode="Markdown")
    await add_heart(message)

@dp.message(Command("all"))
async def all_birthdays_cmd(message: types.Message):
    birthdays_dict = {}
    admins = set(CONFIG['ADMINS'])
    for r in get_birthday_data():
        nik = r['Nik']
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            birthdays_dict.setdefault(date_str, []).append(f"*{nik}*" if nik in admins else nik)
    sorted_dates = sorted(birthdays_dict.keys(), key=lambda d: datetime.datetime.strptime(d, "%d.%m"))
    lines = ["🎂 *Все дни рождения* 🎂\n"]
    for date in sorted_dates:
        lines.append(f"🗓️ {date}: {', '.join(birthdays_dict[date])}")
    text = "\n".join(lines)
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text=text, parse_mode="Markdown")
    await add_heart(message)

@dp.message(Command("force_update"))
async def force_update_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только для админов")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await message.reply("🔄 Данные обновлены")
    await add_heart(message)

@dp.message(Command("send_test"))
async def send_test_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только для админов")
        return
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text="🔔 Тестовое сообщение")
    await add_heart(message)

# --- Ежедневное напоминание ---
async def daily_birthdays():
    bd = get_today_birthdays()
    text = format_birthdays(bd, "Дни рождения сегодня")
    await bot.send_message(chat_id=CONFIG['CHAT_ID'], message_thread_id=CONFIG['THREAD_ID'], text=text, parse_mode="Markdown")

scheduler = AsyncIOScheduler()
scheduler.add_job(daily_birthdays, 'cron', hour=0, minute=0)
scheduler.start()

# --- Запуск бота ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
