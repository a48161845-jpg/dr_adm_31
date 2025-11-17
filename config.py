import datetime

CONFIG = {
    'SPREADSHEET_URL': "https://docs.google.com/spreadsheets/d/1o_qYVyRkbQ-bw5f9RwEm4ThYEGltHCfeLLf7BgPgGmI",
    'CHAT_ID': "-1003452972632",
    'THREAD_ID': 1,
    'CACHE_FILE': "birthday_cache.json",
    'CACHE_EXPIRY': 300,
    'TIMEZONE_OFFSET': datetime.timedelta(hours=3),
    'ADMINS': ["1004974578", "7233257134", "5472545113"],
}

SEND_ARGS = {
    "chat_id": CONFIG["CHAT_ID"],
    "message_thread_id": CONFIG["THREAD_ID"]
}
