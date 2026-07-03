import asyncio

import config
from bots import bot, admin_bot, dp, admin_dp

# Импорт регистрирует все хэндлеры на dp / admin_dp
import client_bot  # noqa: F401
import admin_bot as admin_handlers  # noqa: F401


async def main():
    print("🚀 Бот запущен!")
    print(f"💰 Цена: {config.PRICE_PER_SUBSCRIBER_RUB} ₽/подписчик")
    print(f"⭐ В Stars: ~{config.PRICE_PER_SUBSCRIBER_STARS:.2f} Stars/подписчик")
    print(f"📊 Лимиты: {config.MIN_ORDER} - {config.MAX_ORDER}")
    print("📨 Заказы автоматически отправляются в PRmotion после оплаты")
    await asyncio.gather(
        dp.start_polling(bot),
        admin_dp.start_polling(admin_bot)
    )


if __name__ == "__main__":
    asyncio.run(main())
