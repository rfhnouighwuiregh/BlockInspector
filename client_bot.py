import re

from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)

import config
import database
from bots import bot, dp, admin_bot
from prmotion import send_to_prmotion

# ========== СОСТОЯНИЯ ==========
class OrderStates(StatesGroup):
    waiting_for_count = State()
    waiting_for_channel = State()
    waiting_for_payment = State()


class SupportStates(StatesGroup):
    waiting_for_question = State()


# ========== КЛАВИАТУРЫ ==========
payment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⭐ Оплатить Stars")],
        [KeyboardButton(text="🏦 Оплата картой / СБП (временно не работает)")],
        [KeyboardButton(text="❌ Отменить заказ")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❌ Отменить заказ")]
    ],
    resize_keyboard=True
)

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Новый заказ")],
        [KeyboardButton(text="📞 Поддержка")],
        [KeyboardButton(text="📋 Мои заказы")]
    ],
    resize_keyboard=True
)


def cancel_created_order_kb(order_id: int) -> ReplyKeyboardMarkup:
    """Закреплённая снизу клавиатура с кнопкой отмены конкретного заказа."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"❌ Отменить заказ #{order_id}")]],
        resize_keyboard=True
    )


# ========== СТАРТ / МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для заказа накрутки подписчиков.\n\n"
        f"💰 <b>Цена:</b> {config.PRICE_PER_SUBSCRIBER_RUB} ₽ за подписчика\n"
        f"⭐ <b>В Stars:</b> ~{config.PRICE_PER_SUBSCRIBER_STARS:.2f} Stars за подписчика\n"
        f"📊 <b>Мин. заказ:</b> {config.MIN_ORDER} подписчиков\n"
        f"📊 <b>Макс. заказ:</b> {config.MAX_ORDER} подписчиков\n\n"
        "🛒 <b>Новый заказ</b> — оформить накрутку\n"
        "📞 <b>Поддержка</b> — задать вопрос администратору\n"
        "📋 <b>Мои заказы</b> — посмотреть статус заказов\n\n"
        "Выберите действие:",
        reply_markup=main_menu_kb,
        parse_mode="HTML"
    )


@dp.message(lambda message: message.text == "🛒 Новый заказ")
async def new_order(message: types.Message, state: FSMContext):
    await message.answer(
        f"📝 Введите количество подписчиков (от {config.MIN_ORDER} до {config.MAX_ORDER}):",
        reply_markup=cancel_kb
    )
    await state.set_state(OrderStates.waiting_for_count)


def _build_orders_text(user_id: int) -> str:
    user_orders = sorted(
        (o for o in database.orders.values() if o['user_id'] == user_id),
        key=lambda o: o['id']
    )
    if not user_orders:
        return "📭 У вас пока нет заказов."

    status_map = {
        'ожидает_подтверждения': '⏳ Ожидает подтверждения',
        'ожидает_оплаты': '💳 Ожидает оплаты',
        'оплачено': '✅ Оплачено',
        'в_работе': '🔄 В работе (PRmotion)',
        'выполнен': '🎉 Выполнен!',
        'отклонен': '❌ Отклонён',
        'отменен_клиентом': '🚫 Отменён вами'
    }

    text = "📋 <b>Ваши заказы:</b>\n\n"
    for order in user_orders[-database.MAX_ORDERS_PER_USER:]:
        text += (
            f"─────────────────\n"
            f"🆔 Заказ #{order['id']}\n"
            f"📢 Канал: {order['channel']}\n"
            f"👥 {order['count']} подписчиков\n"
            f"💰 {order['price']:.2f} ₽\n"
            f"📊 Статус: {status_map.get(order['status'], order['status'])}\n"
        )
    return text


ORDERS_REFRESH_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_orders")]
    ]
)


@dp.message(lambda message: message.text == "📋 Мои заказы")
async def my_orders(message: types.Message):
    text = _build_orders_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=ORDERS_REFRESH_KB)


@dp.callback_query(lambda call: call.data == "refresh_orders")
async def refresh_orders(callback: types.CallbackQuery):
    text = _build_orders_text(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=ORDERS_REFRESH_KB)
        await callback.answer("Обновлено ✅")
    except Exception:
        # Telegram ругается, если текст не изменился — это не ошибка
        await callback.answer("Изменений нет")


@dp.message(Command("support"))
@dp.message(lambda message: message.text == "📞 Поддержка")
async def support_start(message: types.Message, state: FSMContext):
    await message.answer(
        "📞 <b>Служба поддержки</b>\n\nОпишите вашу проблему.\n✏️ Напишите текст обращения:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await state.set_state(SupportStates.waiting_for_question)


@dp.message(Command("cancel"))
@dp.message(lambda message: message.text == "❌ Отменить заказ")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено!", reply_markup=main_menu_kb)


@dp.message(lambda message: bool(message.text) and message.text.startswith("❌ Отменить заказ #"))
async def cancel_created_order(message: types.Message, state: FSMContext):
    try:
        order_id = int(message.text.rsplit("#", 1)[1])
    except (IndexError, ValueError):
        await message.answer("❌ Не удалось определить номер заказа.", reply_markup=main_menu_kb)
        return

    order = database.get_order(order_id)
    if not order or order['user_id'] != message.from_user.id:
        await message.answer("❌ Заказ не найден.", reply_markup=main_menu_kb)
        return
    if order['status'] not in ('ожидает_подтверждения', 'ожидает_оплаты'):
        await message.answer(f"⚠️ Заказ уже {order['status']}, отменить нельзя.", reply_markup=main_menu_kb)
        return

    database.update_order_status(order_id, 'отменен_клиентом')
    await message.answer(f"❌ Заказ #{order_id} отменён.", reply_markup=main_menu_kb)

    await admin_bot.send_message(
        config.ADMIN_ID,
        f"❌ <b>Клиент отменил заказ #{order_id}</b>\n"
        f"👤 @{order['username']}\n"
        f"📢 Канал: {order['channel']}",
        parse_mode="HTML"
    )


@dp.message(SupportStates.waiting_for_question)
async def support_question(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    if len(message.text.strip()) < 5:
        await message.answer("❌ Напишите более развёрнутое сообщение.")
        return

    admin_message = (
        f"📞 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b>\n"
        f"─────────────────\n"
        f"👤 Клиент: @{message.from_user.username or 'нет юзернейма'}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"─────────────────\n"
        f"📝 <b>Сообщение:</b>\n"
        f"{message.text}\n"
        f"─────────────────\n"
        f"⏳ Статус: <b>Ожидает ответа</b>"
    )

    reply_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_{message.from_user.id}")]
        ]
    )

    await admin_bot.send_message(config.ADMIN_ID, admin_message, parse_mode="HTML", reply_markup=reply_keyboard)
    await message.answer("✅ Обращение отправлено!", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await state.clear()


def normalize_channel_username(channel: str) -> str:
    """
    Telegram Bot API в get_chat() принимает ТОЛЬКО '@username', полные ссылки
    вида https://t.me/username он не понимает и вернёт "chat not found".
    Приводим любой из разрешённых форматов к '@username'.
    """
    channel = channel.strip()
    match = re.match(r'^https?://(?:t\.me|telegram\.me)/([\w_]+)$', channel, re.IGNORECASE)
    if match:
        return f"@{match.group(1)}"
    return channel


async def validate_channel(channel: str):
    """
    Проверяет, что канал реально существует и доступен боту, и что в нём
    достаточно подписчиков.

    ВАЖНО: Bot API Telegram не даёт способа узнать количество постов в
    канале (ни через get_chat, ни через любой другой метод) — это
    ограничение самого API, а не библиотеки. Поэтому проверяем только
    существование канала и число подписчиков.

    Возвращает (ok, error_text, chat).
    """
    channel = normalize_channel_username(channel)
    try:
        chat = await bot.get_chat(channel)
    except TelegramForbiddenError:
        return False, (
            "❌ Бот не может получить доступ к этому каналу.\n"
            "Убедитесь, что канал публичный (есть @username), и что бот не заблокирован в нём."
        ), None
    except TelegramBadRequest:
        return False, (
            "❌ Канал не найден.\n"
            "Проверьте ссылку — возможно, опечатка, канал приватный или был удалён."
        ), None
    except Exception as e:
        print(f"❌ Ошибка проверки канала {channel}: {e}")
        return False, "❌ Не удалось проверить канал. Попробуйте ещё раз чуть позже.", None

    if chat.type != "channel":
        return False, "❌ Эта ссылка ведёт не на канал (группа/чат/пользователь). Укажите именно канал.", None

    try:
        members_count = await bot.get_chat_member_count(chat.id)
    except Exception as e:
        print(f"⚠️ Не удалось получить число подписчиков {channel}: {e}")
        members_count = None

    if members_count is not None and members_count < config.MIN_CHANNEL_SUBSCRIBERS:
        return False, (
            f"❌ В канале должно быть минимум {config.MIN_CHANNEL_SUBSCRIBERS} подписчиков "
            f"(сейчас: {members_count})."
        ), None

    return True, None, chat


# ========== ЗАКАЗ (КОЛИЧЕСТВО) ==========
@dp.message(OrderStates.waiting_for_count)
async def get_count(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    try:
        count = int(message.text)
    except ValueError:
        await message.answer(f"❌ Введите число от {config.MIN_ORDER} до {config.MAX_ORDER}.", parse_mode="HTML")
        return
    if count < config.MIN_ORDER or count > config.MAX_ORDER:
        await message.answer(f"❌ Введите число от {config.MIN_ORDER} до {config.MAX_ORDER}.", parse_mode="HTML")
        return
    await state.update_data(count=count)
    await message.answer(
        f"✅ Принято! <b>{count}</b> подписчиков.\n"
        f"💰 Стоимость: <b>{count * config.PRICE_PER_SUBSCRIBER_RUB:.2f} ₽</b>\n"
        f"⭐ В Stars: <b>{round(count * config.PRICE_PER_SUBSCRIBER_STARS)} Stars</b>\n\n"
        "📢 Теперь укажите ссылку на канал.\nПример: @my_channel или https://t.me/my_channel",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await state.set_state(OrderStates.waiting_for_channel)


@dp.message(OrderStates.waiting_for_channel)
async def get_channel(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    channel = message.text.strip()
    if not re.match(r'^@[\w_]{5,}$|^https?://(t\.me|telegram\.me)/[\w_]{5,}$', channel, re.IGNORECASE):
        await message.answer("❌ Неверный формат! Используйте: @my_channel или https://t.me/my_channel", reply_markup=cancel_kb, parse_mode="HTML")
        return

    checking_msg = await message.answer("🔍 Проверяю канал...")
    ok, error_text, chat = await validate_channel(channel)
    await checking_msg.delete()

    if not ok:
        await message.answer(error_text, reply_markup=cancel_kb, parse_mode="HTML")
        return

    # Дальше используем @username из get_chat — он точнее того, что ввёл клиент
    channel = f"@{chat.username}" if chat.username else channel

    await state.update_data(channel=channel)
    data = await state.get_data()
    count = data['count']
    price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)

    cart_text = (
        f"📦 <b>Ваш заказ:</b>\n─────────────────\n"
        f"👥 Подписчиков: <b>{count}</b>\n"
        f"📢 Канал: <b>{channel}</b>\n"
        f"💰 Стоимость: <b>{price_rub:.2f} ₽</b>\n"
        f"⭐ В Stars: <b>{price_stars} Stars</b>\n─────────────────\n\n"
        f"✅ Выберите способ оплаты:"
    )
    await message.answer(cart_text, reply_markup=payment_kb, parse_mode="HTML")
    await state.set_state(OrderStates.waiting_for_payment)


@dp.message(OrderStates.waiting_for_payment)
async def get_payment(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return

    data = await state.get_data()
    count = data['count']
    channel = data['channel']
    price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB

    if "Stars" in message.text:
        payment_method = "Stars"
    elif "карт" in message.text.lower() or "сбп" in message.text.lower():
        # Оплата картой пока не работает — не создаём заказ и не шлём на модерацию,
        # просто просим клиента выбрать Stars (или отменить).
        await message.answer(
            "⚠️ <b>Оплата картой / СБП сейчас не работает.</b>\n\n"
            "Пожалуйста, выберите оплату через ⭐ Stars.\n"
            "Если хотите оплатить именно картой — напишите в поддержку, "
            "мы подключим её в ближайшее время.",
            reply_markup=payment_kb,
            parse_mode="HTML"
        )
        return
    else:
        await message.answer("❌ Выберите способ оплаты с клавиатуры.", reply_markup=payment_kb)
        return

    order_id = database.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username or "нет юзернейма",
        channel=channel,
        count=count,
        price=price_rub,
        payment=payment_method
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}")]
        ]
    )

    order_text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n─────────────────\n"
        f"👤 Клиент: @{message.from_user.username or 'нет юзернейма'}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"👥 Подписчиков: <b>{count}</b>\n"
        f"📢 Канал: <b>{channel}</b>\n"
        f"💰 Стоимость: <b>{price_rub:.2f} ₽</b>\n"
        f"💳 Оплата: <b>{payment_method}</b>\n─────────────────\n"
        f"📅 Создан: {database.orders[order_id]['created_at']}\n"
        f"⏳ Статус: <b>Ожидает подтверждения</b>"
    )

    print(f"📤 Отправляю заказ #{order_id} в админ-бота (ADMIN_ID: {config.ADMIN_ID})")
    try:
        await admin_bot.send_message(config.ADMIN_ID, order_text, parse_mode="HTML", reply_markup=admin_kb)
        print(f"✅ Заказ #{order_id} отправлен в админ-бота")
    except Exception as e:
        print(f"❌ Ошибка при отправке в админ-бота: {e}")
        await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        return

    await message.answer(
        f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
        f"👥 Подписчиков: {count}\n"
        f"💰 Стоимость: {price_rub:.2f} ₽\n\n"
        "Администратор подтвердит заказ в ближайшее время.\n\n"
        "Передумали? Можно отменить, пока он не подтверждён — кнопка снизу 👇",
        reply_markup=cancel_created_order_kb(order_id),
        parse_mode="HTML"
    )
    await state.clear()


def _order_id_from_callback(data: str, index: int) -> int:
    return int(data.split("_")[index])


# ========== КЛИЕНТ НАЖАЛ "ОПЛАТИТЬ" ==========
# ВАЖНО: фильтр сужен, чтобы не перехватывать "pay_stars_..." и "pay_card_...",
# которые тоже начинаются с "pay_" — раньше это ломало кнопку Stars/карта.
@dp.callback_query(
    lambda call: call.data.startswith("pay_")
    and not call.data.startswith("pay_stars_")
    and not call.data.startswith("pay_card_")
)
async def client_pay(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 1)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    if order['status'] != 'ожидает_оплаты':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    await callback.answer()

    # чистим кнопки предыдущего шага, чтобы в чате не копились рабочие кнопки
    await callback.message.edit_reply_markup(reply_markup=None)

    count = order['count']
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)
    price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB

    pay_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pay_stars_{order_id}")],
            [InlineKeyboardButton(text="🏦 Оплатить картой (временно не работает)", callback_data=f"pay_card_{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]
        ]
    )
    await callback.message.answer(
        f"💳 <b>Выберите способ оплаты для заказа #{order_id}</b>\n\n"
        f"💰 Сумма: {price_rub:.2f} ₽\n"
        f"⭐ В Stars: {price_stars} Stars",
        parse_mode="HTML",
        reply_markup=pay_kb
    )


@dp.callback_query(lambda call: call.data.startswith("pay_card_"))
async def pay_card(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 2)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    await callback.answer("Оплата картой временно не работает", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"🏦 <b>Оплата картой / СБП пока не работает</b>\n\n"
        "Мы дорабатываем приём платежей картой и СБП, скоро всё заработает.\n"
        "Сейчас доступна оплата через ⭐ Stars, либо напишите в поддержку — "
        "оформим заказ и подскажем, как оплатить.",
        parse_mode="HTML"
    )


@dp.callback_query(lambda call: call.data.startswith("cancel_order_"))
async def cancel_order_by_client(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 2)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    if order['status'] not in ('ожидает_подтверждения', 'ожидает_оплаты'):
        await callback.answer(f"⚠️ Заказ уже {order['status']}, отменить нельзя", show_alert=True)
        return

    database.update_order_status(order_id, 'отменен_клиентом')
    await callback.answer("❌ Заказ отменён")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заказ #{order_id} отменён.")

    await admin_bot.send_message(
        config.ADMIN_ID,
        f"❌ <b>Клиент отменил заказ #{order_id}</b>\n"
        f"👤 @{order['username']}\n"
        f"📢 Канал: {order['channel']}",
        parse_mode="HTML"
    )


@dp.callback_query(lambda call: call.data.startswith("pay_stars_"))
async def pay_stars(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    await callback.answer()

    count = order['count']
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"Накрутка подписчиков #{order_id}",
            description=f"Канал: {order['channel']}\nПодписчиков: {count}",
            payload=f"stars_order_{order_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{count} подписчиков", amount=price_stars)],
            start_parameter=f"order_{order_id}",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")


@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.payload
    if payload.startswith("stars_order_"):
        order_id = int(payload.split("_")[2])
    else:
        order_id = int(payload.split("_")[1])
    order = database.get_order(order_id)
    if not order:
        await pre_checkout_query.answer(ok=False, error_message="Заказ не найден!")
        return
    await pre_checkout_query.answer(ok=True)
    print(f"✅ Pre-checkout для заказа #{order_id}")


@dp.message(lambda message: message.successful_payment is not None)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.payload
    if payload.startswith("stars_order_"):
        order_id = int(payload.split("_")[2])
    else:
        order_id = int(payload.split("_")[1])
    database.update_order_status(order_id, "оплачено")
    await message.answer("✅ Оплата прошла успешно! Заказ отправлен в работу.")
    await send_to_prmotion(order_id)
