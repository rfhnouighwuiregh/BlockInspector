from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import database
from bots import bot, admin_bot, admin_dp

admin_replies = {}


# ========== ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ ЗАКАЗА ==========
@admin_dp.callback_query(lambda call: call.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return

    database.update_order_status(order_id, 'ожидает_оплаты')
    await callback.answer("✅ Заказ подтверждён!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Заказ #{order_id} подтверждён!")

    await bot.send_message(
        order['user_id'],
        f"✅ <b>Заказ #{order_id} подтверждён!</b>\n\n"
        f"📢 Канал: {order['channel']}\n"
        f"👥 Подписчиков: {order['count']}\n"
        f"💰 Сумма: {order['price']:.2f} ₽\n\n"
        f"Нажмите кнопку ниже, чтобы оплатить:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{order_id}")],
                [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]
            ]
        )
    )


@admin_dp.callback_query(lambda call: call.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    database.update_order_status(order_id, 'отклонен')
    await callback.answer("❌ Заказ отклонён!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заказ #{order_id} отклонён!")
    await bot.send_message(order['user_id'], f"❌ Заказ #{order_id} отклонён! Свяжитесь с поддержкой.", parse_mode="HTML")


# ========== ОТВЕТЫ В ПОДДЕРЖКУ ==========
@admin_dp.callback_query(lambda call: call.data.startswith("reply_"))
async def handle_reply(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[1])
    await callback.answer("✏️ Введите ваш ответ")
    admin_replies[config.ADMIN_ID] = user_id
    await callback.message.answer(f"✏️ Введите ответ для клиента (ID: {user_id}):")


@admin_dp.message(lambda message: message.from_user.id == config.ADMIN_ID)
async def admin_reply(message: types.Message):
    if config.ADMIN_ID not in admin_replies:
        return
    user_id = admin_replies[config.ADMIN_ID]
    reply_text = message.text.strip()
    if message.text == "/cancel":
        del admin_replies[config.ADMIN_ID]
        await message.answer("❌ Отменено.")
        return
    if len(reply_text) < 2:
        await message.answer("❌ Слишком коротко.")
        return
    try:
        await bot.send_message(user_id, f"📩 <b>Ответ администратора:</b>\n\n{reply_text}", parse_mode="HTML")
        del admin_replies[config.ADMIN_ID]
        await message.answer("✅ Ответ отправлен!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
