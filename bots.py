import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config

# В оригинале оба диспетчера используют один и тот же storage — сохраняю это поведение
storage = MemoryStorage()

# Клиентский бот
bot = Bot(token=config.TOKEN)
dp = Dispatcher(storage=storage)

# Админский бот
admin_bot = Bot(token=config.ADMIN_BOT_TOKEN)
admin_dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)
