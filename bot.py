Mr. Spooky 👻, [18.10.2025 0:47]
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
logger = logging.getLogger(name)

# Конфигурация
CONFIG = {
    'TOKEN': os.environ.get('BOT_TOKEN'),
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI/edit?usp=drivesdk",
    'CHAT_ID': "-1002124864225",
    'THREAD_ID': 25,  # Укажите существующий thread или оставьте None
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'CACHE_FILE': 'birthday_cache.json',
    'CACHE_EXPIRY': 300,
    'ADMINS': ["1004974578", "7233257134", "5472545113"],
}

# Параметры для отправки в ветку
SEND_ARGS = {
    'chat_id': CONFIG['CHAT_ID'],
    'message_thread_id': CONFIG['THREAD_ID']
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
        try:
            day = int(digits[:2])
            month = int(digits[2:])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}.{day:02d}"
        except:
            pass

        try:
            month = int(digits[:2])
            day = int(digits[2:])
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

Mr. Spooky 👻, [18.10.2025 0:47]
try:
            month = int(digits[0])
            day = int(digits[1:])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}.{day:02d}"
        except:
            pass

    elif len(digits) == 8:
        try:
            day = int(digits[:2])
            month = int(digits[2:4])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}.{day:02d}"
        except:
            pass

        try:
            month = int(digits[:2])
            day = int(digits[2:4])
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

        if display_date not in birthdays:
            birthdays[display_date] = []
        birthdays[display_date].append(nik)

    sorted_dates = sorted(
        birthdays.items(),
        key=lambda x: (
            datetime.datetime.strptime(x[0], "%d.%m").month,
            datetime.datetime.strptime(x[0], "%d.%m").day
        ) if '.' in x[0] else (0, 0)
    )
    return dict(sorted_dates)


def format_birthdays(birthdays, title):
    if not birthdays:
        return f"📅 {title}\n\nНа данный период дни рождения отсутствуют"

    if isinstance(birthdays, list):
        names_count = len(birthdays)
        congratulation = "Не забудьте поздравить админа!" if names_count == 1 else "Не забудьте поздравить админов!"
        return (f"🎂 Дни рождения сегодня:\n\n" +
                '\n'.join(f"• {name}" for name in birthdays) +
                f"\n\n{congratulation} 🎉")

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


async def handle_force_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await force_update(update, context)


async def handle_send_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_test(update, context)

Mr. Spooky 👻, [18.10.2025 0:47]
async def start(update: Update, _):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник для младшей администрации.\n\n"
        "Моя задача - помогать ГСУ и ЗГСУ, чтобы у них было меньше обязанностей и больше сил!\n\n"
        "Используйте /help для просмотра доступных команд."
    )


async def help_command(update: Update, _):
    help_text = (
        "Доступные команды:\n\n"
        "• /check - Показать дни рождения на сегодня\n"
        "• /upcoming [дни] - Ближайшие дни рождения (по умолчанию 7 дней)\n"
        "• /recent [дни] - Недавние дни рождения (по умолчанию 7 дней)\n"
        "• /all - Все дни рождения\n"
        "• /myid - Показать ваш ID\n\n"
        "Команды для Руководства младшей:\n"
        "• /force_update - Обновить данные из таблицы\n"
        "• /send_test - Отправить тестовое сообщение"
    )
    await update.message.reply_text(help_text)


async def myid(update: Update, _):
    user = update.effective_user
    status = "Руководство младшей" if is_admin(user.id) else "Куратор младшей администрации"
    await update.message.reply_text(
        f"Ваш ID: {user.id}\n"
        f"Статус: {status}"
    )
async def check_birthdays(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    try:
        birthdays = get_today_birthdays()
        message = format_birthdays(birthdays, "Дни рождения сегодня")
        try:
            await context.bot.send_message(
                text=message,
                **SEND_ARGS
            )
        except telegram.error.BadRequest as e:
            if "Message thread not found" in str(e):
                await context.bot.send_message(
                    chat_id=CONFIG['CHAT_ID'],
                    text=message
                )
                await update.message.reply_text("⚠️ Ветка не найдена! Сообщение отправлено в основной чат")
            else:
                raise e
        await update.message.reply_text("✅ Информация отправлена в ветку команды")
    except Exception as e:
        logger.error(f"Ошибка в check_birthdays: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def upcoming_birthdays(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    try:
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
        days = max(1, min(days, 60))
        birthdays = get_upcoming_birthdays(days)
        message = format_birthdays(birthdays, f"Ближайшие дни рождения (на {days} дней)")

        try:
            await context.bot.send_message(
                text=message,
                **SEND_ARGS
            )
        except telegram.error.BadRequest as e:
            if "Message thread not found" in str(e):
                await context.bot.send_message(
                    chat_id=CONFIG['CHAT_ID'],
                    text=message
                )
                await update.message.reply_text("⚠️ Ветка не найдена! Сообщение отправлено в основной чат")
            else:
                raise e

        await update.message.reply_text("✅ Информация отправлена в ветку команды")
    except Exception as e:
        logger.error(f"Ошибка в upcoming_birthdays: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def recent_birthdays(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    try:
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
        days = max(1, min(days, 60))
        birthdays = get_past_birthdays(days)
        message = format_birthdays(birthdays, f"Недавние дни рождения (за {days} дней)")

Mr. Spooky 👻, [18.10.2025 0:47]
try:
            await context.bot.send_message(
                text=message,
                **SEND_ARGS
            )
        except telegram.error.BadRequest as e:
            if "Message thread not found" in str(e):
                await context.bot.send_message(
                    chat_id=CONFIG['CHAT_ID'],
                    text=message
                )
                await update.message.reply_text("⚠️ Ветка не найдена! Сообщение отправлено в основной чат")
            else:
                raise e

        await update.message.reply_text("✅ Информация отправлена в ветку команды")
    except Exception as e:
        logger.error(f"Ошибка в recent_birthdays: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def all_birthdays(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    try:
        birthdays = get_all_birthdays()
        message = format_birthdays(birthdays, "Все дни рождения команды")

        max_length = 3000
        if len(message) > max_length:
            parts = [message[i:i + max_length] for i in range(0, len(message), max_length)]
            for part in parts:
                try:
                    await context.bot.send_message(
                        text=part,
                        **SEND_ARGS
                    )
                except telegram.error.BadRequest as e:
                    if "Message thread not found" in str(e):
                        await context.bot.send_message(
                            chat_id=CONFIG['CHAT_ID'],
                            text=part
                        )
                    else:
                        raise e
                time.sleep(1)
        else:
            try:
                await context.bot.send_message(
                    text=message,
                    **SEND_ARGS
                )
            except telegram.error.BadRequest as e:
                if "Message thread not found" in str(e):
                    await context.bot.send_message(
                        chat_id=CONFIG['CHAT_ID'],
                        text=message
                    )
                else:
                    raise e

        await update.message.reply_text("✅ Полный список отправлен в ветку команды")
    except Exception as e:
        logger.error(f"Ошибка в all_birthdays: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def force_update(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только Руководству младшей")
        return

    try:
        if os.path.exists(CONFIG['CACHE_FILE']):
            os.remove(CONFIG['CACHE_FILE'])
        get_birthday_data()
        await update.message.reply_text("🔄 Данные о днях рождениях успешно обновлены!")
    except Exception as e:
        logger.error(f"Ошибка в force_update: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка обновления: {str(e)}")


async def send_test(update, context):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Эта команда работает только в группе!")
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только Руководству младшей")
        return

    try:
        await context.bot.send_message(
            text="🔔 Тестовое сообщение от администратора: бот работает корректно!",
            **SEND_ARGS
        )

Mr. Spooky 👻, [18.10.2025 0:47]
await update.message.reply_text("✅ Тестовое сообщение отправлено в ветку команды!")
    except telegram.error.BadRequest as e:
        if "Message thread not found" in str(e):
            await context.bot.send_message(
                chat_id=CONFIG['CHAT_ID'],
                text="🔔 Тестовое сообщение от администратора: бот работает корректно!"
            )
            await update.message.reply_text("⚠️ Ветка не найдена! Тестовое сообщение отправлено в основной чат")
        else:
            raise e
    except Exception as e:
        logger.error(f"Ошибка в send_test: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка отправки: {str(e)}")


async def daily_check(context):
    try:
        bd = get_today_birthdays()
        if bd:
            message = format_birthdays(bd, "Автоматическое уведомление: Дни рождения сегодня")
            try:
                await context.bot.send_message(
                    text=message,
                    **SEND_ARGS
                )
            except telegram.error.BadRequest as e:
                if "Message thread not found" in str(e):
                    await context.bot.send_message(
                        chat_id=CONFIG['CHAT_ID'],
                        text=message
                    )
                else:
                    raise e
    except Exception as e:
        logger.error(f"Ошибка ежедневной проверки: {str(e)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if isinstance(error, telegram.error.BadRequest) and "Message thread not found" in str(error):
        logger.error("ОШИБКА: Ветка не найдена! Проверьте THREAD_ID в конфиге")
    else:
        logger.error(f"Необработанная ошибка: {error}")


def main():
    try:
        app = Application.builder().token(CONFIG['TOKEN']).build()

        global_commands = {
            "start": start,
            "help": help_command,
            "myid": myid,
        }

        for cmd, handler in global_commands.items():
            app.add_handler(CommandHandler(cmd, handler))

        group_filter = filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP

        group_commands = {
            "check": check_birthdays,
            "upcoming": upcoming_birthdays,
            "recent": recent_birthdays,
            "all": all_birthdays,
            "force_update": force_update,
            "send_test": send_test,
            "forceupdate": handle_force_update,
            "sendtest": handle_send_test,
        }

        for cmd, handler in group_commands.items():
            app.add_handler(CommandHandler(cmd, handler, group_filter))

        app.add_error_handler(error_handler)

        job_queue = app.job_queue
        if job_queue:
            # 21:00 UTC = 00:00 MSK (UTC+3)
            time_utc = datetime.time(hour=21, minute=0)
            job_queue.run_daily(daily_check, time=time_utc)
            logger.info(f"Ежедневная проверка настроена на {time_utc} UTC (00:00 по Москве)")

        logger.info("Бот помощи для младшей администрации запущен")
        app.run_polling()

    except Exception as e:
        logger.error(f"Ошибка запуска бота: {str(e)}")

if name == 'main':
    main()
