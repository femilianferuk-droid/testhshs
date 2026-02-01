import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import Config
from database import Database

logging.basicConfig(level=logging.INFO)

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
db = Database()

class WithdrawState(StatesGroup):
    choosing_amount = State()

# Проверка подписки на спонсоров
async def check_subscriptions(user_id: int) -> bool:
    sponsors = await db.get_user_sponsors_status(user_id)
    if not sponsors:
        return True
    
    for sponsor in sponsors:
        if not sponsor[4]:  # is_subscribed
            return False
    return True

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # Обработка реферальной ссылки
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
        except:
            pass
    
    await db.create_user(user_id, username, referrer_id)
    
    # Проверка подписки
    if not await check_subscriptions(user_id):
        await show_sponsors(message, user_id)
        return
    
    # Начисление реферальных бонусов
    if referrer_id:
        user = await db.get_user(user_id)
        if user and not user[3]:  # Если у пользователя еще нет referrer_id
            # Обновляем referrer_id
            await db.update_user_referrer(user_id, referrer_id)
            
            # Начисляем бонусы
            await db.update_balance(referrer_id, Config.REFERRAL_REWARD_REFERRER)
            await db.add_transaction(
                referrer_id, 
                Config.REFERRAL_REWARD_REFERRER, 
                "referral_bonus",
                f"За приглашение пользователя {username}"
            )
            
            await db.update_balance(user_id, Config.REFERRAL_REWARD_REFEREE)
            await db.add_transaction(
                user_id,
                Config.REFERRAL_REWARD_REFEREE,
                "referral_bonus",
                "За регистрацию по реферальной ссылке"
            )
    
    await show_main_menu(message)

async def show_sponsors(message: Message, user_id: int):
    sponsors = await db.get_sponsors()
    if not sponsors:
        await show_main_menu(message)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for sponsor in sponsors:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"📢 {sponsor[1]}",
                url=sponsor[3]
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="✅ Я подписался",
            callback_data="check_subscriptions"
        )
    ])
    
    await message.answer(
        "📢 Чтобы начать, подпишитесь на наших спонсоров!",
        reply_markup=keyboard
    )

async def show_main_menu(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🐵 Заработать звезды", callback_data="earn")],
            [InlineKeyboardButton(text="📊 Профиль", callback_data="profile")],
            [InlineKeyboardButton(text="👥 Реферальная система", callback_data="referral")],
            [InlineKeyboardButton(text="🎮 Игры (Перейти на сайт)", url=f"http://{Config.WEB_HOST}:{Config.WEB_PORT}")]
        ]
    )
    
    await message.answer(
        "🐵 *Monkey Stars* - Зарабатывай и играй!\n\n"
        "Баланс: *{:.2f} STAR*\n"
        "Выберите действие:".format(
            (await db.get_user(message.from_user.id))[2] if await db.get_user(message.from_user.id) else 0
        ),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_subscriptions")
async def check_subscriptions_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    # Здесь должна быть логика проверки подписки через getChatMember
    # Для примера считаем, что пользователь подписался
    sponsors = await db.get_sponsors()
    for sponsor in sponsors:
        await db.update_user_sponsor(user_id, sponsor[0], True)
    
    await callback.message.delete()
    await show_main_menu(callback.message)

@dp.callback_query(F.data == "earn")
async def earn_menu(callback: CallbackQuery):
    if not await check_subscriptions(callback.from_user.id):
        await callback.answer("❌ Сначала подпишитесь на спонсоров!")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Кликнуть (+0.2 STAR)", callback_data="click")],
            [InlineKeyboardButton(text="💸 Вывод", callback_data="withdraw")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )
    
    await callback.message.edit_text(
        "🐵 *Заработать звезды*\n\n"
        "Выберите способ заработка:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "click")
async def click_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscriptions(user_id):
        await callback.answer("❌ Сначала подпишитесь на спонсоров!")
        return
    
    user = await db.get_user(user_id)
    if not user:
        return
    
    last_click = user[4]
    current_time = int(datetime.now().timestamp())
    
    if last_click and (current_time - last_click) < Config.CLICK_COOLDOWN:
        remaining = Config.CLICK_COOLDOWN - (current_time - last_click)
        await callback.answer(f"⏳ Подождите {remaining//60} мин. {remaining%60} сек.")
        return
    
    # Начисляем клик
    reward = Config.CLICK_REWARD
    await db.update_balance(user_id, reward)
    
    # Обновляем время последнего клика
    async with aiosqlite.connect(Config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET last_click = ? WHERE user_id = ?",
            (current_time, user_id)
        )
        await conn.commit()
    
    await db.add_transaction(user_id, reward, "click", "Кликер")
    
    # Реферальный бонус (10%)
    referrer_id = user[3]
    if referrer_id:
        referral_bonus = reward * (Config.CLICK_REFERRAL_PERCENT / 100)
        await db.update_balance(referrer_id, referral_bonus)
        await db.add_transaction(
            referrer_id, 
            referral_bonus, 
            "referral_income",
            f"10% от клика пользователя {callback.from_user.username or user_id}"
        )
    
    await callback.answer(f"✅ +{reward} STAR")
    
    # Обновляем сообщение
    user = await db.get_user(user_id)
    await callback.message.edit_text(
        f"🐵 *Кликер*\n\n"
        f"✅ Вы получили *{reward} STAR*\n"
        f"💰 Баланс: *{user[2]:.2f} STAR*\n\n"
        f"Следующий клик через 1 час",
        parse_mode="Markdown",
        reply_markup=callback.message.reply_markup
    )

@dp.callback_query(F.data == "withdraw")
async def withdraw_menu(callback: CallbackQuery, state: FSMContext):
    if not await check_subscriptions(callback.from_user.id):
        await callback.answer("❌ Сначала подпишитесь на спонсоров!")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="15 STAR", callback_data="withdraw_15")],
            [InlineKeyboardButton(text="25 STAR", callback_data="withdraw_25")],
            [InlineKeyboardButton(text="50 STAR", callback_data="withdraw_50")],
            [InlineKeyboardButton(text="100 STAR", callback_data="withdraw_100")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="earn")]
        ]
    )
    
    await callback.message.edit_text(
        "💸 *Вывод средств*\n\n"
        "Выберите сумму для вывода:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    amount = float(callback.data.split("_")[1])
    
    user = await db.get_user(user_id)
    if not user:
        return
    
    # Проверка баланса
    if user[2] < amount:
        await callback.answer(f"❌ Недостаточно STAR. Ваш баланс: {user[2]:.2f}")
        return
    
    # Проверка активных рефералов
    total_ref, active_ref = await db.get_user_referrals(user_id)
    if active_ref < 3:
        await callback.answer(f"❌ Нужно 3 активных реферала. У вас: {active_ref}")
        return
    
    # Создаем заявку на вывод
    withdrawal_id = await db.create_withdrawal(user_id, amount)
    
    # Списание баланса
    await db.update_balance(user_id, -amount)
    await db.add_transaction(user_id, -amount, "withdrawal", f"Вывод средств #{withdrawal_id}")
    
    await callback.message.edit_text(
        f"✅ *Заявка на вывод одобрена!*\n\n"
        f"💰 Сумма: *{amount} STAR*\n"
        f"📝 ID заявки: *#{withdrawal_id}*\n\n"
        f"Для получения средств свяжитесь с поддержкой: @MonkeyStarsov\n"
        f"Укажите ваш ID: `{user_id}` и сумму: `{amount} STAR`",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "profile")
async def profile_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscriptions(user_id):
        await callback.answer("❌ Сначала подпишитесь на спонсоров!")
        return
    
    user = await db.get_user(user_id)
    if not user:
        return
    
    total_ref, active_ref = await db.get_user_referrals(user_id)
    
    last_click = user[4]
    current_time = int(datetime.now().timestamp())
    if last_click:
        time_passed = current_time - last_click
        if time_passed < Config.CLICK_COOLDOWN:
            remaining = Config.CLICK_COOLDOWN - time_passed
            next_click = f"{remaining//60}:{remaining%60:02d}"
        else:
            next_click = "Сейчас"
    else:
        next_click = "Сейчас"
    
    text = (
        f"📊 *Профиль*\n\n"
        f"👤 ID: `{user_id}`\n"
        f"💰 Баланс: *{user[2]:.2f} STAR*\n"
        f"👥 Рефералов: *{active_ref}* / {total_ref}\n"
        f"⏰ Кликер доступен: {next_click}"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "referral")
async def referral_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscriptions(user_id):
        await callback.answer("❌ Сначала подпишитесь на спонсоров!")
        return
    
    total_ref, active_ref = await db.get_user_referrals(user_id)
    
    text = (
        f"👥 *Реферальная система*\n\n"
        f"🔗 Ваша ссылка:\n"
        f"`https://t.me/MonkeyStarsBot?start={user_id}`\n\n"
        f"📊 Статистика:\n"
        f"• Приглашено: *{total_ref}*\n"
        f"• Активных: *{active_ref}*\n\n"
        f"🎁 *Правила:*\n"
        f"• Вы получаете *3 STAR*, а друг *2 STAR* после подписки на спонсоров\n"
        f"• Вы получаете *10%* от всех кликов реферала\n"
        f"• Для вывода нужно *3 активных реферала*"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await show_main_menu(callback.message)

# Проверка подписки перед любым действием
@dp.callback_query()
async def check_subscription_before_action(callback: CallbackQuery):
    if callback.data not in ["check_subscriptions", "main_menu"]:
        if not await check_subscriptions(callback.from_user.id):
            await callback.answer("❌ Доступ ограничен! Подпишитесь на спонсоров!", show_alert=True)
            
            # Показываем спонсоров
            await callback.message.delete()
            await show_sponsors(callback.message, callback.from_user.id)
            return
    
    # Передаем обработку дальше
    await dp.feed_update(bot=bot, update=callback)

async def main():
    # Инициализация БД
    await db.init_db()
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
