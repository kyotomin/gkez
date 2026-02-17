from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.db.users import get_user_profile_data, get_user_order_count
from src.db.settings import has_user_deposit, get_deposit_amount, get_user_deposit_amount, create_user_deposit, get_user_effective_deposit
from src.utils.formatters import format_profile
from src.keyboards.user_kb import main_menu_kb, profile_kb, topup_amounts_kb
from src.states.user_states import PaymentStates
from src.utils.cryptobot import create_invoice
from src.db.payments import create_payment
from src.db.users import get_user, update_balance

router = Router()


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    data = await get_user_profile_data(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    if not data or data.get("is_blocked"):
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    dep_required = (data["effective_deposit"] or 0) > 0
    actual_dep = data["has_deposit"]
    await message.answer(
        format_profile(data, data["order_count"], actual_dep, dep_required),
        parse_mode="HTML",
        reply_markup=profile_kb(actual_dep, dep_required),
    )


@router.callback_query(F.data == "pay_deposit")
async def pay_deposit(callback: CallbackQuery):
    deposit_amount = await get_user_effective_deposit(callback.from_user.id)
    if deposit_amount <= 0:
        await callback.answer("ℹ️ Депозит не требуется.", show_alert=True)
        return
    already = await has_user_deposit(callback.from_user.id)
    if already:
        await callback.answer("✅ Депозит уже внесён.", show_alert=True)
        return
    user = await get_user(callback.from_user.id)
    balance = user.get("balance", 0) if user else 0
    if balance < deposit_amount:
        await callback.answer(
            f"❌ Недостаточно средств. Нужно: {deposit_amount:.2f}$. Пополните баланс.",
            show_alert=True,
        )
        return
    await update_balance(callback.from_user.id, -deposit_amount)
    await create_user_deposit(callback.from_user.id, deposit_amount)
    await callback.answer("✅ Депозит внесён!", show_alert=True)
    user = await get_user(callback.from_user.id)
    order_count = await get_user_order_count(callback.from_user.id)
    try:
        await callback.message.edit_text(
            format_profile(user, order_count, True, True),
            parse_mode="HTML",
            reply_markup=profile_kb(True, True),
        )
    except Exception:
        pass


@router.callback_query(F.data == "withdraw_deposit")
async def withdraw_deposit(callback: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оформить возврат", callback_data="deposit_return_support")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")],
    ])
    await callback.answer()
    try:
        await callback.message.edit_text(
            "💸 <b>Возврат депозита</b>\n\n"
            "Для возврата депозита необходимо оформить обращение.\n\n"
            "⏰ Возврат занимает до 3 рабочих дней после проверки.",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass


@router.callback_query(F.data == "topup_balance")
async def topup_balance(callback: CallbackQuery):
    await callback.message.edit_text(
        "💰 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:",
        reply_markup=topup_amounts_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "topup_custom")
async def topup_custom(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ Введите сумму пополнения (например: 15.50):",
        parse_mode="HTML",
    )
    await state.set_state(PaymentStates.waiting_amount)
    await callback.answer()


@router.message(PaymentStates.waiting_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму (число больше 0).")
        return
    await state.clear()
    await _create_and_send_invoice(message, amount)


@router.callback_query(F.data.startswith("topup_") & ~F.data.in_({"topup_balance", "topup_custom"}))
async def topup_fixed_amount(callback: CallbackQuery):
    amount = float(callback.data.split("_")[1])
    await callback.answer()
    await _create_and_send_invoice(callback.message, amount, edit=True, user_id=callback.from_user.id)


async def _create_and_send_invoice(message, amount: float, edit: bool = False, user_id: int = None):
    uid = user_id or message.from_user.id
    invoice = await create_invoice(amount, f"Пополнение баланса — {amount}$ USDT")
    if not invoice:
        text = "❌ Не удалось создать счёт. Попробуйте позже."
        if edit:
            await message.edit_text(text, parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")
        return

    await create_payment(uid, invoice["invoice_id"], amount, invoice.get("bot_invoice_url", ""))

    from src.handlers.payment import start_payment_check
    await start_payment_check(invoice["invoice_id"])

    pay_url = invoice.get("bot_invoice_url", "")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")],
    ])
    text = (
        f"💰 <b>Счёт на оплату</b>\n\n"
        f"💵 Сумма: <b>{amount:.2f} USDT</b>\n"
        f"⏰ Счёт действителен 30 минут\n\n"
        f"Нажмите кнопку ниже для оплаты.\n"
        f"Баланс пополнится автоматически после оплаты."
    )
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
