import asyncio
import logging
import os
import re
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, SuccessfulPayment
)
from dotenv import load_dotenv
import aiohttp

load_dotenv()

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

PRICE_PER_SUBSCRIBER_RUB = 0.40
STARS_MULTIPLIER = 1.35
PRICE_PER_SUBSCRIBER_STARS = round(PRICE_PER_SUBSCRIBER_RUB * STARS_MULTIPLIER, 2)
MIN_ORDER = 50
MAX_ORDER = 50000

PRMOTION_API_KEY = os.getenv("PRMOTION_API_KEY")
PRMOTION_SERVICE_ID = int(os.getenv("PRMOTION_SERVICE_ID", 0))
PRMOTION_API_URL = os.getenv("PRMOTION_API_URL", "https://api.prmotion.me/v1")

print(f"✅ BOT_TOKEN: {TOKEN[:10]}..." if TOKEN else "❌ BOT_TOKEN не найден!")
print(f"✅ ADMIN_BOT_TOKEN: {ADMIN_BOT_TOKEN[:10]}..." if ADMIN_BOT_TOKEN else "❌ ADMIN_BOT_TOKEN не найден!")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

if not all([TOKEN, ADMIN_BOT_TOKEN, PRMOTION_API_KEY]):
    print("❌ ОШИБКА: Проверь .env файл!")
    exit()

# ========== БАЗА ДАННЫХ ==========
orders = {}
order_counter = 0
ORDERS_FILE = "orders.json"

def load_orders():
    global orders, order_counter
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            orders = {int(k): v for k, v in data.get('orders', {}).items()}
            order_counter = data.get('order_counter', 0)
        print(f"📂 Загружено {len(orders)} заказов из файла")
    else:
        orders = {}
        order_counter = 0
        print("📂 Создан новый файл заказов")

def save_orders():
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'orders': orders,
            'order_counter': order_counter
        }, f, ensure_ascii=False, indent=2)

def create_order(user_id, username, channel, count, price, payment):
    global order_counter
    order_counter += 1
    order_id = order_counter
    
    orders[order_id] = {
        'id': order_id,
        'user_id': user_id,
        'username': username,
        'channel': channel,
        'count': count,
        'price': price,
        'payment': payment,
        'status': 'ожидает_подтверждения',
        'prmotion_order_id': None,
        'created_at': datetime.now().strftime("%d.%m.%Y %H:%M"),
        'updated_at': datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_orders()
    return order_id

def get_order(order_id):
    return orders.get(order_id)

def update_order_status(order_id, status):
    if order_id in orders:
        orders[order_id]['status'] = status
        orders[order_id]['updated_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        save_orders()
        return True
    return False

def update_prmotion_order_id(order_id, prmotion_id):
    if order_id in orders:
        orders[order_id]['prmotion_order_id'] = prmotion_id
        save_orders()
        return True
    return False

load_orders()

# ========== PRMOTION API ==========
async def check_prmotion_balance():
    async with aiohttp.ClientSession() as session:
        params = {'key': PRMOTION_API_KEY, 'action': 'balance'}
        try:
            async with session.get(PRMOTION_API_URL, params=params) as resp:
                data = await resp.json()
                return float(data.get('balance', 0))
        except:
            return None

async def create_prmotion_order(channel, quantity):
    async with aiohttp.ClientSession() as session:
        params = {
            'key': PRMOTION_API_KEY,
            'action': 'add',
            'service': PRMOTION_SERVICE_ID,
            'link': channel,
            'quantity': quantity
        }
        try:
            async with session.get(PRMOTION_API_URL, params=params) as resp:
                data = await resp.json()
                print(f"📤 PRmotion ответ: {data}")
                return data.get('order')
        except Exception as e:
            print(f"❌ Ошибка PRmotion: {e}")
            return None

async def send_to_prmotion(order_id):
    order = get_order(order_id)
    if not order:
        return False
    
    try:
        balance = await check_prmotion_balance()
        if balance is None:
            await admin_bot.send_message(ADMIN_ID, f"⚠️ Ошибка PRmotion! Заказ #{order_id}")
            return False
        
        if balance < order['price']:
            await admin_bot.send_message(
                ADMIN_ID,
                f"⚠️ Недостаточно средств в PRmotion!\nЗаказ #{order_id}\nНужно: {order['price']:.2f} ₽\nДоступно: {balance:.2f} ₽",
                parse_mode="HTML"
            )
            return False
        
        prmotion_order_id = await create_prmotion_order(order['channel'], order['count'])
        
        if prmotion_order_id:
            update_prmotion_order_id(order_id, prmotion_order_id)
            update_order_status(order_id, "в_работе")
            
            await admin_bot.send_message(
                ADMIN_ID,
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
            await admin_bot.send_message(ADMIN_ID, f"❌ Ошибка создания заказа в PRmotion!\nЗаказ #{order_id}", parse_mode="HTML")
            return False
    except Exception as e:
        await admin_bot.send_message(ADMIN_ID, f"❌ Ошибка: {str(e)}")
        return False

# ========== СОСТОЯНИЯ ==========
class OrderStates(StatesGroup):
    waiting_for_count = State()
    waiting_for_channel = State()
    waiting_for_payment = State()

class SupportStates(StatesGroup):
    waiting_for_question = State()

# ========== ИНИЦИАЛИЗАЦИЯ БОТОВ ==========
bot = Bot(token=TOKEN)
admin_bot = Bot(token=ADMIN_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
admin_dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

admin_replies = {}

# ========== КЛАВИАТУРЫ ==========
payment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⭐ Оплатить Stars")],
        [KeyboardButton(text="🏦 Оплата картой / СБП")],
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

# ========== ОСНОВНОЙ БОТ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для заказа накрутки подписчиков.\n\n"
        f"💰 <b>Цена:</b> {PRICE_PER_SUBSCRIBER_RUB} ₽ за подписчика\n"
        f"⭐ <b>В Stars:</b> ~{PRICE_PER_SUBSCRIBER_STARS:.2f} Stars за подписчика\n"
        f"📊 <b>Мин. заказ:</b> {MIN_ORDER} подписчиков\n"
        f"📊 <b>Макс. заказ:</b> {MAX_ORDER} подписчиков\n\n"
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
        f"📝 Введите количество подписчиков (от {MIN_ORDER} до {MAX_ORDER}):",
        reply_markup=cancel_kb
    )
    await state.set_state(OrderStates.waiting_for_count)

@dp.message(lambda message: message.text == "📋 Мои заказы")
async def my_orders(message: types.Message):
    user_orders = [o for o in orders.values() if o['user_id'] == message.from_user.id]
    if not user_orders:
        await message.answer("📭 У вас пока нет заказов.")
        return
    
    status_map = {
        'ожидает_подтверждения': '⏳ Ожидает подтверждения',
        'ожидает_оплаты': '💳 Ожидает оплаты',
        'оплачено': '✅ Оплачено',
        'в_работе': '🔄 В работе (PRmotion)',
        'выполнен': '🎉 Выполнен!',
        'отклонен': '❌ Отклонён'
    }
    
    text = "📋 <b>Ваши заказы:</b>\n\n"
    for order in user_orders[-5:]:
        text += (
            f"─────────────────\n"
            f"🆔 Заказ #{order['id']}\n"
            f"📢 Канал: {order['channel']}\n"
            f"👥 {order['count']} подписчиков\n"
            f"💰 {order['price']:.2f} ₽\n"
            f"📊 Статус: {status_map.get(order['status'], order['status'])}\n"
        )
    await message.answer(text, parse_mode="HTML")

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
    
    await admin_bot.send_message(ADMIN_ID, admin_message, parse_mode="HTML", reply_markup=reply_keyboard)
    await message.answer("✅ Обращение отправлено!", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await state.clear()

# ========== ЗАКАЗ (КОЛИЧЕСТВО) ==========
@dp.message(OrderStates.waiting_for_count)
async def get_count(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    try:
        count = int(message.text)
    except ValueError:
        await message.answer(f"❌ Введите число от {MIN_ORDER} до {MAX_ORDER}.", parse_mode="HTML")
        return
    if count < MIN_ORDER or count > MAX_ORDER:
        await message.answer(f"❌ Введите число от {MIN_ORDER} до {MAX_ORDER}.", parse_mode="HTML")
        return
    await state.update_data(count=count)
    await message.answer(
        f"✅ Принято! <b>{count}</b> подписчиков.\n"
        f"💰 Стоимость: <b>{count * PRICE_PER_SUBSCRIBER_RUB:.2f} ₽</b>\n"
        f"⭐ В Stars: <b>{round(count * PRICE_PER_SUBSCRIBER_STARS)} Stars</b>\n\n"
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
    await state.update_data(channel=channel)
    data = await state.get_data()
    count = data['count']
    price_rub = count * PRICE_PER_SUBSCRIBER_RUB
    price_stars = round(count * PRICE_PER_SUBSCRIBER_STARS)
    
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
    price_rub = count * PRICE_PER_SUBSCRIBER_RUB
    price_stars = round(count * PRICE_PER_SUBSCRIBER_STARS)
    
    if "Stars" in message.text:
        payment_method = "Stars"
    elif "карт" in message.text.lower() or "сбп" in message.text.lower():
        payment_method = "Карта / СБП"
    else:
        await message.answer("❌ Выберите способ оплаты с клавиатуры.", reply_markup=payment_kb)
        return
    
    order_id = create_order(
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
        f"📅 Создан: {orders[order_id]['created_at']}\n"
        f"⏳ Статус: <b>Ожидает подтверждения</b>"
    )
    
    print(f"📤 Отправляю заказ #{order_id} в админ-бота (ADMIN_ID: {ADMIN_ID})")
    try:
        await admin_bot.send_message(ADMIN_ID, order_text, parse_mode="HTML", reply_markup=admin_kb)
        print(f"✅ Заказ #{order_id} отправлен в админ-бота")
    except Exception as e:
        print(f"❌ Ошибка при отправке в админ-бота: {e}")
        await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        return
    
    await message.answer(
        f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
        f"👥 Подписчиков: {count}\n"
        f"💰 Стоимость: {price_rub:.2f} ₽\n\n"
        "Администратор подтвердит заказ в ближайшее время.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await state.clear()

# ========== АДМИН-БОТ ==========

@admin_dp.callback_query(lambda call: call.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    
    update_order_status(order_id, 'ожидает_оплаты')
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
                [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{order_id}")]
            ]
        )
    )

@admin_dp.callback_query(lambda call: call.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    update_order_status(order_id, 'отклонен')
    await callback.answer("❌ Заказ отклонён!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заказ #{order_id} отклонён!")
    await bot.send_message(order['user_id'], f"❌ Заказ #{order_id} отклонён! Свяжитесь с поддержкой.", parse_mode="HTML")

# ========== КЛИЕНТ НАЖАЛ "ОПЛАТИТЬ" ==========
@dp.callback_query(lambda call: call.data.startswith("pay_"))
async def client_pay(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
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
    
    count = order['count']
    price_stars = round(count * PRICE_PER_SUBSCRIBER_STARS)
    price_rub = count * PRICE_PER_SUBSCRIBER_RUB
    
    pay_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pay_stars_{order_id}")],
            [InlineKeyboardButton(text="🏦 Оплатить картой", callback_data=f"pay_card_{order_id}")]
        ]
    )
    await callback.message.answer(
        f"💳 <b>Выберите способ оплаты для заказа #{order_id}</b>\n\n"
        f"💰 Сумма: {price_rub:.2f} ₽\n"
        f"⭐ В Stars: {price_stars} Stars",
        parse_mode="HTML",
        reply_markup=pay_kb
    )

@dp.callback_query(lambda call: call.data.startswith("pay_stars_"))
async def pay_stars(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    await callback.answer()
    
    count = order['count']
    price_stars = round(count * PRICE_PER_SUBSCRIBER_STARS)
    
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
    order = get_order(order_id)
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
    update_order_status(order_id, "оплачено")
    order = get_order(order_id)
    await message.answer("✅ Оплата прошла успешно! Заказ отправлен в работу.")
    await send_to_prmotion(order_id)

# ========== ОТВЕТЫ В ПОДДЕРЖКУ ==========
@admin_dp.callback_query(lambda call: call.data.startswith("reply_"))
async def handle_reply(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[1])
    await callback.answer("✏️ Введите ваш ответ")
    admin_replies[ADMIN_ID] = user_id
    await callback.message.answer(f"✏️ Введите ответ для клиента (ID: {user_id}):")

@admin_dp.message(lambda message: message.from_user.id == ADMIN_ID)
async def admin_reply(message: types.Message):
    if ADMIN_ID not in admin_replies:
        return
    user_id = admin_replies[ADMIN_ID]
    reply_text = message.text.strip()
    if message.text == "/cancel":
        del admin_replies[ADMIN_ID]
        await message.answer("❌ Отменено.")
        return
    if len(reply_text) < 2:
        await message.answer("❌ Слишком коротко.")
        return
    try:
        await bot.send_message(user_id, f"📩 <b>Ответ администратора:</b>\n\n{reply_text}", parse_mode="HTML")
        del admin_replies[ADMIN_ID]
        await message.answer("✅ Ответ отправлен!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# ========== ЗАПУСК ==========
async def main():
    print("🚀 Бот запущен!")
    print(f"💰 Цена: {PRICE_PER_SUBSCRIBER_RUB} ₽/подписчик")
    print(f"⭐ В Stars: ~{PRICE_PER_SUBSCRIBER_STARS:.2f} Stars/подписчик")
    print(f"📊 Лимиты: {MIN_ORDER} - {MAX_ORDER}")
    print("📨 Заказы автоматически отправляются в PRmotion после оплаты")
    await asyncio.gather(
        dp.start_polling(bot),
        admin_dp.start_polling(admin_bot)
    )

if __name__ == "__main__":
    asyncio.run(main())