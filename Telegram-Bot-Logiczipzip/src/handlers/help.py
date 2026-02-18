from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.states.user_states import TicketStates
from src.db.tickets import create_ticket, add_ticket_message, get_user_tickets, get_ticket, get_ticket_messages, can_create_general_support, check_daily_ticket_limit
from src.db.orders import get_user_orders
from src.db.users import is_user_blocked
from src.db.settings import get_faq_text
from src.utils.formatters import format_ticket
from src.keyboards.user_kb import (
    help_menu_kb, user_tickets_kb, ticket_detail_kb,
    select_order_for_ticket_kb, reputation_kb, attach_file_choice_kb,
)
from src.db.admins import get_admin_ids

router = Router()


@router.message(F.text == "💬 Помощь")
async def show_help(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    await message.answer(
        "💬 <b>Центр поддержки</b>\n\n"
        "Выберите тип обращения:",
        reply_markup=help_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "help_menu")
async def help_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "💬 <b>Центр поддержки</b>\n\n"
        "Выберите тип обращения:",
        reply_markup=help_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "user_faq")
async def show_faq(callback: CallbackQuery):
    faq_text = await get_faq_text()
    await callback.message.edit_text(
        f"📖 <b>Инструкция</b>\n\n{faq_text}",
        reply_markup=help_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "create_ticket")
async def start_create_ticket(callback: CallbackQuery, state: FSMContext):
    can_create = await check_daily_ticket_limit(callback.from_user.id)
    if not can_create:
        await callback.answer(
            "❌ Вы достигли дневного лимита обращений. Попробуйте завтра.",
            show_alert=True,
        )
        return
    orders = await get_user_orders(callback.from_user.id)
    if not orders:
        await callback.answer(
            "❌ У вас нет заказов. Помощь с заказом доступна только при наличии заказов.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        "📝 <b>Помощь с заказом</b>\n\n"
        "Выберите заказ, по которому у вас вопрос:",
        reply_markup=select_order_for_ticket_kb(orders),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_order_"))
async def ticket_order_selected(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    from src.db.orders import get_order
    order = await get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    await state.update_data(ticket_order_id=order_id)
    await callback.message.edit_text(
        f"📝 <b>Помощь по заказу #{order_id}</b>\n\n"
        "Опишите вашу проблему подробно:",
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_message)
    await callback.answer()


@router.message(TicketStates.waiting_message)
async def process_ticket_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение.", parse_mode="HTML")
        return
    data = await state.get_data()
    order_id = data.get("ticket_order_id")
    await state.update_data(ticket_text=message.text, ticket_order_id=order_id)
    await message.answer(
        "📎 Хотите прикрепить фото или документ к обращению?",
        reply_markup=attach_file_choice_kb(),
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_attach_choice)


@router.callback_query(F.data == "general_support")
async def general_support(callback: CallbackQuery, state: FSMContext):
    can_create = await can_create_general_support(callback.from_user.id)
    if not can_create:
        await callback.answer(
            "❌ Вы достигли дневного лимита обращений. Попробуйте завтра.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        "📝 <b>Поддержка</b>\n\n"
        "Опишите ваш вопрос подробно:",
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_general_message)
    await callback.answer()


@router.message(TicketStates.waiting_general_message)
async def process_general_support(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение.", parse_mode="HTML")
        return
    await state.update_data(ticket_text=message.text, ticket_order_id=None, ticket_subject="Общее обращение")
    await message.answer(
        "📎 Хотите прикрепить фото или документ к обращению?",
        reply_markup=attach_file_choice_kb(),
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_attach_choice)


@router.callback_query(F.data == "deposit_return_support")
async def deposit_return_support(callback: CallbackQuery, state: FSMContext):
    can_create = await check_daily_ticket_limit(callback.from_user.id)
    if not can_create:
        await callback.answer(
            "❌ Вы достигли дневного лимита обращений. Попробуйте завтра.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        "💸 <b>Возврат депозита</b>\n\n"
        "Укажите причину возврата депозита:",
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_deposit_reason)
    await callback.answer()


@router.message(TicketStates.waiting_deposit_reason)
async def process_deposit_reason(message: Message, state: FSMContext):
    reason = message.text.strip() if message.text else "Не указана"
    ticket_id = await create_ticket(message.from_user.id, "Возврат депозита", None)
    await add_ticket_message(ticket_id, message.from_user.id, f"Причина возврата депозита: {reason}")
    await state.clear()
    await message.answer(
        f"✅ <b>Обращение #{ticket_id} создано!</b>\n\n"
        f"📋 Тема: Возврат депозита\n"
        f"⏰ Ожидайте ответа администратора.",
        reply_markup=help_menu_kb(),
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import bot
        user_name = message.from_user.username or message.from_user.full_name or str(message.from_user.id)
        notify_text = (
            f"🔔 <b>Запрос возврата депозита #{ticket_id}</b>\n\n"
            f"👤 Пользователь: @{user_name}\n"
            f"💬 Причина: {reason[:200]}"
        )
        for admin_id in await get_admin_ids():
            try:
                await bot.send_message(admin_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass


async def _finalize_ticket(user, text: str, order_id, file_id: str = None, subject: str = None):
    if not subject:
        subject = f"Заказ #{order_id}" if order_id else "Обращение"
    ticket_id = await create_ticket(user.id, subject, order_id)
    await add_ticket_message(ticket_id, user.id, text, file_id=file_id)
    try:
        from src.bot.instance import bot
        from src.db.operators import get_ticket_operator_ids
        user_name = user.username or user.full_name or str(user.id)
        file_mark = " 📎" if file_id else ""
        notify_text = (
            f"🔔 <b>Новое обращение #{ticket_id}</b>\n\n"
            f"👤 Пользователь: @{user_name}\n"
        )
        if order_id:
            notify_text += f"📦 По заказу: #{order_id}\n"
        notify_text += f"💬 {text[:200]}{file_mark}"
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        ticket_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Обращение", callback_data=f"admin_ticket_{ticket_id}"),
                InlineKeyboardButton(text="👤 Профиль", callback_data=f"admin_user_{user.id}"),
            ]
        ])
        for admin_id in await get_admin_ids():
            try:
                await bot.send_message(admin_id, notify_text, parse_mode="HTML", reply_markup=ticket_kb)
            except Exception:
                pass
        operator_ids = await get_ticket_operator_ids()
        for op_id in operator_ids:
            try:
                await bot.send_message(op_id, notify_text, parse_mode="HTML", reply_markup=ticket_kb)
            except Exception:
                pass
    except Exception:
        pass
    return ticket_id


@router.callback_query(F.data == "ticket_skip_file")
async def ticket_skip_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("ticket_text", "")
    order_id = data.get("ticket_order_id")
    subject = data.get("ticket_subject")
    await state.clear()
    ticket_id = await _finalize_ticket(callback.from_user, text, order_id, subject=subject)
    result_text = f"✅ <b>Обращение #{ticket_id} создано!</b>\n\n"
    if order_id:
        result_text += f"📦 По заказу: #{order_id}\n\n"
    result_text += "⏰ Ожидайте ответа."
    await callback.message.edit_text(result_text, reply_markup=help_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ticket_attach_file")
async def ticket_attach_file(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📎 Отправьте фото или документ:",
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_file)
    await callback.answer()


@router.message(TicketStates.waiting_file)
async def process_ticket_file(message: Message, state: FSMContext):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    else:
        await message.answer("❌ Отправьте фото или документ.", parse_mode="HTML")
        return
    data = await state.get_data()
    text = data.get("ticket_text", "")
    order_id = data.get("ticket_order_id")
    subject = data.get("ticket_subject")
    await state.clear()
    ticket_id = await _finalize_ticket(message.from_user, text, order_id, file_id=file_id, subject=subject)
    result_text = f"✅ <b>Обращение #{ticket_id} создано!</b>\n\n"
    if order_id:
        result_text += f"📦 По заказу: #{order_id}\n\n"
    result_text += "📎 Файл прикреплён.\n⏰ Ожидайте ответа."
    await message.answer(result_text, reply_markup=help_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "my_tickets")
async def show_my_tickets(callback: CallbackQuery):
    tickets = await get_user_tickets(callback.from_user.id)
    if not tickets:
        await callback.message.edit_text(
            "📭 У вас пока нет обращений.",
            reply_markup=help_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📋 <b>Ваши обращения:</b>",
        reply_markup=user_tickets_kb(tickets),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_ticket_"))
async def view_ticket(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[-1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await callback.answer("❌ Обращение не найдено", show_alert=True)
        return
    messages = await get_ticket_messages(ticket_id)
    text = format_ticket(ticket) + "\n\n"
    text += "💬 <b>Сообщения:</b>\n\n"
    has_files = False
    for msg in messages:
        sender = "👤 Вы" if msg["sender_id"] == callback.from_user.id else "👨‍💼 Поддержка"
        file_mark = " 📎" if msg.get("file_id") else ""
        text += f"{sender}: {msg['message']}{file_mark}\n"
        text += f"<i>{msg['created_at'].strftime('%Y-%m-%d %H:%M') if msg.get('created_at') else '—'}</i>\n\n"
        if msg.get("file_id"):
            has_files = True
    if has_files:
        from src.bot.instance import bot
        for msg in messages:
            if msg.get("file_id"):
                try:
                    await bot.send_document(callback.from_user.id, msg["file_id"])
                except Exception:
                    try:
                        await bot.send_photo(callback.from_user.id, msg["file_id"])
                    except Exception:
                        pass
    await callback.message.edit_text(
        text,
        reply_markup=ticket_detail_kb(ticket),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_reply_"))
async def start_ticket_reply(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[-1])
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.edit_text(
        "💬 Напишите ваше сообщение:",
        parse_mode="HTML",
    )
    await state.set_state(TicketStates.waiting_reply)
    await callback.answer()


@router.message(TicketStates.waiting_reply)
async def process_ticket_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data["reply_ticket_id"]
    file_id = None
    text = message.text or message.caption or ""
    if message.photo:
        file_id = message.photo[-1].file_id
        if not text:
            text = "[Фото]"
    elif message.document:
        file_id = message.document.file_id
        if not text:
            text = "[Документ]"
    await add_ticket_message(ticket_id, message.from_user.id, text, file_id=file_id)
    await state.clear()
    file_mark = " 📎" if file_id else ""
    await message.answer(
        f"✅ Сообщение отправлено в обращение #{ticket_id}.{file_mark}",
        reply_markup=help_menu_kb(),
        parse_mode="HTML",
    )


@router.message(F.text == "⭐ Репутация")
async def show_reputation(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    from src.db.reputation import get_all_reputation_links
    links = await get_all_reputation_links()
    if not links:
        await message.answer(
            "⭐ <b>Репутация</b>\n\n"
            "ℹ️ Ссылки на репутацию пока не добавлены.",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "⭐ <b>Репутация</b>\n\n"
        "Наши депозиты на проверенных площадках — гарантия надёжности:",
        reply_markup=reputation_kb(links),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_reputation")
async def back_to_reputation(callback: CallbackQuery):
    from src.db.reputation import get_all_reputation_links
    links = await get_all_reputation_links()
    if not links:
        await callback.message.edit_text(
            "⭐ <b>Репутация</b>\n\n"
            "ℹ️ Ссылки на репутацию пока не добавлены.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "⭐ <b>Репутация</b>\n\n"
            "Наши депозиты на проверенных площадках — гарантия надёжности:",
            reply_markup=reputation_kb(links),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(F.text == "💰 Пополнить баланс 💰")
async def topup_balance_menu(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    from src.keyboards.user_kb import topup_amounts_kb
    await message.answer(
        "💰 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:",
        reply_markup=topup_amounts_kb(),
        parse_mode="HTML",
    )
