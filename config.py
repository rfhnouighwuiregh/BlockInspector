import os
from dotenv import load_dotenv

load_dotenv()

# ========== ТОКЕНЫ И ID ==========
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ========== ЦЕНЫ И ЛИМИТЫ ==========
PRICE_PER_SUBSCRIBER_RUB = 0.40
STARS_MULTIPLIER = 1.35
PRICE_PER_SUBSCRIBER_STARS = round(PRICE_PER_SUBSCRIBER_RUB * STARS_MULTIPLIER, 2)
MIN_ORDER = 50
MAX_ORDER = 50000

# Минимальное количество подписчиков на канале клиента, чтобы принять заказ
MIN_CHANNEL_SUBSCRIBERS = 5

# ========== PRMOTION API ==========
PRMOTION_API_KEY = os.getenv("PRMOTION_API_KEY")
PRMOTION_SERVICE_ID = int(os.getenv("PRMOTION_SERVICE_ID", 0))
PRMOTION_API_URL = os.getenv("PRMOTION_API_URL", "https://api.prmotion.me/v1")

# ========== ПРОВЕРКА ПРИ СТАРТЕ ==========
print(f"✅ BOT_TOKEN: {TOKEN[:10]}..." if TOKEN else "❌ BOT_TOKEN не найден!")
print(f"✅ ADMIN_BOT_TOKEN: {ADMIN_BOT_TOKEN[:10]}..." if ADMIN_BOT_TOKEN else "❌ ADMIN_BOT_TOKEN не найден!")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

if not all([TOKEN, ADMIN_BOT_TOKEN, PRMOTION_API_KEY]):
    print("❌ ОШИБКА: Проверь .env файл!")
    exit()
