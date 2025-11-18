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
import telegram.error

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 16232,  # Укажите существующий thread или оставьте None
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "6195550631"],
}

SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
}

# Функции для работы с таблицей
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

# Нормализация даты
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

# Форматирование сообщений
def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 {title}\n\nДней рождения нет"
    if isinstance(birthdays, list):
        return f"🎉 {title}:\n\n" + '\n'.join([f"🎂 {name}" for name in birthdays])
    if isinstance(birthdays, dict):
        result = [f"📅 {title}:"]
        for date, names in birthdays.items():
            result.append(f"🗓️ {date}: {', '.join(names)}")
        return '\n'.join(result)
    return ""

def is_admin(user_id):
    return str(user_id) in CONFIG['ADMINS']

# Команды
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
        "/send_test - тестовое сообщение\n"
        "/set_reminder - включить/выключить напоминания"
    )
    await update.message.reply_text(text)

async def myid(update: Update, _):
    user = update.effective_user
    status = "Админ" if is_admin(user.id) else "Пользователь"
    await update.message.reply_text(f"Ваш ID: {user.id}\nСтатус: {status}")

async def check_birthdays(update, context):
    birthdays = get_today_birthdays()
    message = format_birthdays(birthdays, "Дни рождения сегодня")
    await context.bot.send_message(**SEND_ARGS, text=message)
    await update.message.reply_text("✅ Отправлено в ветку")

async def upcoming_birthdays_cmd(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_upcoming_birthdays(days)
    message = format_birthdays(birthdays, f"Ближайшие дни рождения (на {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message)
    await update.message.reply_text("✅ Отправлено в ветку")

async def recent_birthdays_cmd(update, context):
    days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
    birthdays = get_past_birthdays(days)
    message = format_birthdays(birthdays, f"Прошедшие дни рождения (за {days} дней)")
    await context.bot.send_message(**SEND_ARGS, text=message)
    await update.message.reply_text("✅ Отправлено в ветку")

async def all_birthdays_cmd(update, context):
    birthdays_dict = {}
    for r in get_birthday_data():
        nik = r['Nik']
        if nd := normalize_date(r['Дата']):
            date_str = datetime.datetime.strptime(nd, "%m.%d").strftime("%d.%m")
            birthdays_dict.setdefault(date_str, []).append(nik)
    message = format_birthdays(birthdays_dict, "Все дни рождения")
    await context.bot.send_message(**SEND_ARTS, text=message)
    await update.message.reply_text("✅ Отправлено в ветку")

async def force_update(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    if os.path.exists(CONFIG['CACHE_FILE']):
        os.remove(CONFIG['CACHE_FILE'])
    get_birthday_data()
    await update.message.reply_text("🔄 Данные обновлены")

async def send_test(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    await context.bot.send_message(**SEND_ARGS, text="🔔 Тестовое сообщение")
    await update.message.reply_text("✅ Отправлено в ветку")

# Функции для напоминаний
class ReminderManager:
    def __init__(self):
        self.enabled = True
        self.last_reminder_date = None
    
    async def send_daily_reminder(self, application):
        """Отправка ежедневного напоминания о днях рождения"""
        if not self.enabled:
            return
            
        today = moscow_time().date()
        
        # Проверяем, не отправляли ли уже напоминание сегодня
        if self.last_reminder_date == today:
            return
            
        birthdays = get_today_birthdays()
        if birthdays:
            message = format_birthdays(birthdays, "🎉 Дни рождения сегодня!")
            message += "\n\nНе забудьте поздравить! 🎂"
        else:
            # Если дней рождения нет, можно отправлять сообщение или молчать
            # Раскомментируйте следующую строку, если хотите сообщения даже когда ДР нет
            # message = "📅 Сегодня дней рождения нет"
            return
        
        try:
            await application.bot.send_message(**SEND_ARGS, text=message)
            self.last_reminder_date = today
            logger.info(f"Ежедневное напоминание отправлено: {len(birthdays)} ДР")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания: {e}")
    
    def toggle_reminders(self, enable=None):
        """Включить/выключить напоминания"""
        if enable is None:
            self.enabled = not self.enabled
        else:
            self.enabled = enable
        return self.enabled

# Глобальный менеджер напоминаний
reminder_manager = ReminderManager()

async def set_reminder(update, context):
    """Команда для управления напоминаниями"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для админов")
        return
    
    if context.args:
        arg = context.args[0].lower()
        if arg in ['on', 'вкл', '1', 'true']:
            reminder_manager.toggle_reminders(True)
            status = "включены"
        elif arg in ['off', 'выкл', '0', 'false']:
            reminder_manager.toggle_reminders(False)
            status = "выключены"
        else:
            await update.message.reply_text("❌ Используйте: /set_reminder on/off")
            return
    else:
        # Без аргумента - переключить состояние
        current_state = reminder_manager.toggle_reminders()
        status = "включены" if current_state else "выключены"
    
    await update.message.reply_text(f"🔔 Ежедневные напоминания {status}")

async def schedule_daily_reminder(application):
    """Планировщик ежедневных напоминаний"""
    while True:
        try:
            now = moscow_time()
            
            # Вычисляем время до следующей полночи
            target_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= target_time:
                target_time += datetime.timedelta(days=1)
            
            wait_seconds = (target_time - now).total_seconds()
            
            logger.info(f"Следующее напоминание в {target_time.strftime('%H:%M %d.%m.%Y')} (через {wait_seconds:.0f} секунд)")
            
            # Ждем до полночи
            await asyncio.sleep(wait_seconds)
            
            # Отправляем напоминание
            await reminder_manager.send_daily_reminder(application)
            
            # Ждем 1 минуту перед следующей проверкой (на случай ошибок)
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")
            await asyncio.sleep(300)  # Ждем 5 минут перед повторной попыткой

# Запуск
def main():
    app = Application.builder().token(CONFIG['TOKEN']).build()

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
        "send_test": send_test,
        "set_reminder": set_reminder
    }
    for cmd, fn in group_cmds.items():
        app.add_handler(CommandHandler(cmd, fn, group_filter))

    # Запускаем планировщик напоминаний
    app.create_task(schedule_daily_reminder(app))

    app.run_polling()

if __name__ == "__main__":
    main()
