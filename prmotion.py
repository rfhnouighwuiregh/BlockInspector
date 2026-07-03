import aiohttp

import config
import database
from bots import admin_bot


async def check_prmotion_balance():
    async with aiohttp.ClientSession() as session:
        params = {'key': config.PRMOTION_API_KEY, 'action': 'balance'}
        try:
            async with session.get(config.PRMOTION_API_URL, params=params) as resp:
                data = await resp.json()
                return float(data.get('balance', 0))
        except Exception:
            return None


async def create_prmotion_order(channel, quantity):
    async with aiohttp.ClientSession() as session:
        params = {
            'key': config.PRMOTION_API_KEY,
            'action': 'add',
            'service': config.PRMOTION_SERVICE_ID,
            'link': channel,
            'quantity': quantity
        }
        try:
            async with session.get(config.PRMOTION_API_URL, params=params) as resp:
                data = await resp.json()
                print(f"📤 PRmotion ответ: {data}")
                return data.get('order')
        except Exception as e:
            print(f"❌ Ошибка PRmotion: {e}")
            return None


async def send_to_prmotion(order_id):
    order = database.get_order(order_id)
    if not order:
        return False

    try:
        balance = await check_prmotion_balance()
        if balance is None:
            await admin_bot.send_message(config.ADMIN_ID, f"⚠️ Ошибка PRmotion! Заказ #{order_id}")
            return False

        if balance < order['price']:
            await admin_bot.send_message(
                config.ADMIN_ID,
                f"⚠️ Недостаточно средств в PRmotion!\nЗаказ #{order_id}\nНужно: {order['price']:.2f} ₽\nДоступно: {balance:.2f} ₽",
                parse_mode="HTML"
            )
            return False

        prmotion_order_id = await create_prmotion_order(order['channel'], order['count'])

        if prmotion_order_id:
            database.update_prmotion_order_id(order_id, prmotion_order_id)
            database.update_order_status(order_id, "в_работе")

            await admin_bot.send_message(
                config.ADMIN_ID,
                f"🚀 Заказ #{order_id} отправлен в PRmotion!\n"
                f"👤 Клиент: @{order['username']}\n"
                f"📢 Канал: {order['channel']}\n"
                f"👥 Подписчиков: {order['count']}\n"
                f"💰 Сумма: {order['price']:.2f} ₽\n"
                f"🆔 PRmotion ID: {prmotion_order_id}",
                parse_mode="HTML"
            )
            return True
        else:
            await admin_bot.send_message(config.ADMIN_ID, f"❌ Ошибка создания заказа в PRmotion!\nЗаказ #{order_id}", parse_mode="HTML")
            return False
    except Exception as e:
        await admin_bot.send_message(config.ADMIN_ID, f"❌ Ошибка: {str(e)}")
        return False
