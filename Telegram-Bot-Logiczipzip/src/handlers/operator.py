from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.db.admins import is_admin
from src.db.operators import is_operator, get_order_operator_ids, get_ticket_operator_ids
from src.db.orders import get_order, update_order_status, increment_signatures_sent
from src.db.tickets import get_all_tickets
from src.keyboards.admin_kb import operator_tickets_kb
from src.states.user_states import OperatorStates

router = Router()


async def is_staff(user_id: int) -> bool:
    if await is_admin(user_id):
        return True
    return await is_operator(user_id)


@router.callback_query(F.data.startswith("op_done_"))
async def operator_done_order(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    order_id = int(callback.data.split("op_done_")[1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "pending_review":
        await callback.answer("ℹ️ Заказ уже обработан", show_alert=True)
        await callback.message.edit_text(
            f"📝 <b>Заказ #{order_id}</b> — уже обработан.",
            parse_mode="HTML",
        )
        return
    await update_order_status(order_id, "completed")
    staff_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
    await callback.message.edit_text(
        f"✅ <b>Заказ #{order_id} подтверждён</b>\n\n"
        f"👷 Подтвердил: @{staff_name}",
        parse_mode="HTML",
    )
    await callback.answer("✅ Заказ подтверждён", show_alert=True)
    try:
        from src.bot.instance import bot
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from src.db.settings import get_review_bonus
        bonus = await get_review_bonus()
        bonus_text = f"\n💰 За отзыв вы получите <b>{bonus:.2f}$</b> на баланс!" if bonus > 0 else ""
        review_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"leave_review_{order_id}")],
        ])
        await bot.send_message(
            order["user_id"],
            f"✅ <b>Ваш заказ #{order_id} подтверждён!</b>\n\n"
            f"Спасибо за использование нашего сервиса.{bonus_text}",
            parse_mode="HTML",
            reply_markup=review_kb,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("op_sig_done_"))
async def operator_sig_done(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    parts = callback.data.split("_")
    order_id = int(parts[3])
    sig_num = int(parts[4])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] not in ("active", "pending_review"):
        await callback.answer("ℹ️ Заказ уже обработан", show_alert=True)
        return
    current_sent = order.get("signatures_sent", 0)
    current_claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)
    if current_sent >= current_claimed:
        await callback.answer("ℹ️ Все отправленные подписи уже подтверждены", show_alert=True)
        return
    if current_sent >= total:
        await callback.answer("ℹ️ Все подписи уже подтверждены", show_alert=True)
        return
    await increment_signatures_sent(order_id)
    order = await get_order(order_id)
    confirmed = order.get("signatures_sent", 0)
    total = order.get("total_signatures", 1)
    staff_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
    if confirmed >= total:
        await update_order_status(order_id, "completed")
        await callback.message.edit_text(
            f"✅ <b>Подпись #{sig_num} подтверждена</b>\n"
            f"📦 Заказ #{order_id} — все подписи подтверждены!\n\n"
            f"👷 Подтвердил: @{staff_name}\n"
            f"📊 Подтверждено: {confirmed}/{total}",
            parse_mode="HTML",
        )
        await callback.answer("✅ Заказ полностью подтверждён!", show_alert=True)
        try:
            from src.bot.instance import bot
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from src.db.settings import get_review_bonus
            bonus = await get_review_bonus()
            bonus_text = f"\n💰 За отзыв вы получите <b>{bonus:.2f}$</b> на баланс!" if bonus > 0 else ""
            review_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"leave_review_{order_id}")],
            ])
            await bot.send_message(
                order["user_id"],
                f"✅ <b>Заказ #{order_id} полностью подтверждён!</b>\n\n"
                f"Все {total} подписей проверены.\n"
                f"Спасибо за использование нашего сервиса.{bonus_text}",
                parse_mode="HTML",
                reply_markup=review_kb,
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text(
            f"✅ <b>Подпись #{sig_num} подтверждена</b>\n"
            f"📦 Заказ #{order_id}\n\n"
            f"👷 Подтвердил: @{staff_name}\n"
            f"📊 Подтверждено: {confirmed}/{total}",
            parse_mode="HTML",
        )
        await callback.answer(f"✅ Подпись #{sig_num} подтверждена", show_alert=True)
        try:
            from src.bot.instance import bot
            await bot.send_message(
                order["user_id"],
                f"✅ <b>Подпись #{sig_num} по заказу #{order_id} подтверждена!</b>\n\n"
                f"📊 Подтверждено: {confirmed}/{total}",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("op_send_doc_"))
async def operator_send_doc(callback: CallbackQuery, state: FSMContext):
    if not await is_staff(callback.from_user.id):
        return
    parts = callback.data.split("_")
    order_id = int(parts[3])
    sig_num = int(parts[4])
    qty = int(parts[5]) if len(parts) > 5 else 1
    await state.update_data(doc_order_id=order_id, doc_sig_num=sig_num, doc_qty=qty, doc_photos=[], doc_current=0)
    if qty > 1:
        await state.set_state(OperatorStates.waiting_doc_photos_batch)
        await callback.message.edit_text(
            f"📸 <b>Отправка документов</b>\n\n"
            f"📦 Заказ: #{order_id}\n"
            f"📊 Документы: #{sig_num}—#{sig_num + qty - 1}\n\n"
            f"Отправьте <b>{qty}</b> фото (по одному). Отправлено: 0/{qty}",
            parse_mode="HTML",
        )
    else:
        await state.set_state(OperatorStates.waiting_doc_photo)
        await callback.message.edit_text(
            f"📸 <b>Отправка документа</b>\n\n"
            f"📦 Заказ: #{order_id}\n"
            f"📊 Подпись: #{sig_num}\n\n"
            f"Отправьте фото/скриншот подтверждающего документа:",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(OperatorStates.waiting_doc_photo, F.photo)
async def process_doc_photo(message: Message, state: FSMContext):
    if not await is_staff(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data.get("doc_order_id")
    sig_num = data.get("doc_sig_num")
    await state.clear()
    order = await get_order(order_id)
    if not order:
        await message.answer("❌ Заказ не найден.", parse_mode="HTML")
        return
    photo = message.photo[-1]
    try:
        from src.bot.instance import bot
        from src.db.documents import save_order_document
        await bot.send_photo(
            order["user_id"],
            photo.file_id,
            caption=(
                f"📄 <b>Документ по заказу #{order_id}</b>\n\n"
                f"📂 Категория: {order.get('category_name', '—')}\n"
                f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n"
                f"📊 Подпись: #{sig_num}\n\n"
                f"Документ, подтверждающий подписание."
            ),
            parse_mode="HTML",
        )
        await save_order_document(order_id, order["user_id"], photo.file_id, "operator")
        from src.db.database import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE doc_requests SET status = 'sent' WHERE order_id = $1 AND signature_num = $2",
                order_id, sig_num
            )
        await message.answer(
            f"✅ Документ отправлен клиенту для заказа #{order_id}, подпись #{sig_num}.",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer("❌ Не удалось отправить документ клиенту.", parse_mode="HTML")


@router.message(OperatorStates.waiting_doc_photos_batch, F.photo)
async def process_doc_photo_batch(message: Message, state: FSMContext):
    if not await is_staff(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data.get("doc_order_id")
    sig_num = data.get("doc_sig_num")
    qty = data.get("doc_qty", 1)
    photos = data.get("doc_photos", [])
    current = data.get("doc_current", 0)
    photo = message.photo[-1]
    photos.append(photo.file_id)
    current += 1
    await state.update_data(doc_photos=photos, doc_current=current)
    if current < qty:
        await message.answer(
            f"📸 Фото {current}/{qty} получено. Отправьте ещё {qty - current}.",
            parse_mode="HTML",
        )
        return
    await state.clear()
    order = await get_order(order_id)
    if not order:
        await message.answer("❌ Заказ не найден.", parse_mode="HTML")
        return
    try:
        from src.bot.instance import bot
        from src.db.database import get_pool
        from src.db.documents import save_order_document
        pool = await get_pool()
        for i, file_id in enumerate(photos):
            doc_num = sig_num + i
            await bot.send_photo(
                order["user_id"],
                file_id,
                caption=(
                    f"📄 <b>Документ по заказу #{order_id}</b>\n\n"
                    f"📂 Категория: {order.get('category_name', '—')}\n"
                    f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n"
                    f"📊 Подпись: #{doc_num}\n\n"
                    f"Документ {i + 1} из {qty}."
                ),
                parse_mode="HTML",
            )
            await save_order_document(order_id, order["user_id"], file_id, "operator")
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE doc_requests SET status = 'sent' WHERE order_id = $1 AND signature_num = $2",
                    order_id, doc_num
                )
        await message.answer(
            f"✅ Все {qty} документов отправлены клиенту для заказа #{order_id}.",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer("❌ Не удалось отправить документы клиенту.", parse_mode="HTML")


@router.message(OperatorStates.waiting_doc_photo)
async def process_doc_not_photo(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте фото/скриншот документа.")


@router.message(OperatorStates.waiting_doc_photos_batch)
async def process_doc_not_photo_batch(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("doc_current", 0)
    qty = data.get("doc_qty", 1)
    await message.answer(f"❌ Пожалуйста, отправьте фото. Получено: {current}/{qty}.")


@router.message(Command("tickets"))
async def cmd_tickets(message: Message):
    if not await is_staff(message.from_user.id):
        return
    tickets = await get_all_tickets()
    if not tickets:
        await message.answer(
            "🎫 <b>Тикеты</b>\n\n📭 Нет тикетов.",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "🎫 <b>Тикеты:</b>",
        reply_markup=operator_tickets_kb(tickets),
        parse_mode="HTML",
    )
