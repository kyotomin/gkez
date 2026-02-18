from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.db.orders import get_user_orders, get_order, update_order_status, cancel_preorder, get_batch_group_orders
from src.db.users import is_user_blocked, get_user, update_balance
from src.db.admins import get_admin_ids
from src.db.categories import get_category
from src.db.documents import get_user_orders_with_documents, get_order_documents, get_order_doc_count
from src.utils.formatters import format_order_status, format_batch_group_status, get_category_emoji
from src.keyboards.user_kb import orders_list_kb, order_detail_kb, main_menu_kb, batch_group_detail_kb
from src.bot.instance import get_bot

router = Router()


@router.message(F.text == "📋 Мои заказы")
async def show_orders(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    orders = await get_user_orders(message.from_user.id)
    if not orders:
        await message.answer(
            "📭 У вас пока нет заказов.\n\n"
            "Перейдите в раздел «📲 Активировать SIM-Карту» чтобы начать.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return
    await message.answer(
        "📋 <b>Ваши заказы:</b>",
        reply_markup=orders_list_kb(orders),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "my_orders_list")
async def show_orders_cb(callback: CallbackQuery):
    orders = await get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text(
            "📭 У вас пока нет заказов.",
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📋 <b>Ваши заказы:</b>",
        reply_markup=orders_list_kb(orders),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("orders_page_"))
async def orders_page(callback: CallbackQuery):
    page = int(callback.data.split("orders_page_")[1])
    orders = await get_user_orders(callback.from_user.id)
    if not orders:
        await callback.answer("📭 Нет заказов", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Ваши заказы:</b>",
        reply_markup=orders_list_kb(orders, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_batch_"))
async def view_batch(callback: CallbackQuery):
    batch_group_id = callback.data.split("view_batch_")[1]
    orders = await get_batch_group_orders(batch_group_id)
    if not orders:
        await callback.answer("❌ Группа заказов не найдена", show_alert=True)
        return
    if not all(o["user_id"] == callback.from_user.id for o in orders):
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    text = format_batch_group_status(orders)
    await callback.message.edit_text(
        text,
        reply_markup=batch_group_detail_kb(orders, batch_group_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("batch_page_"))
async def batch_page(callback: CallbackQuery):
    raw = callback.data.split("batch_page_")[1]
    bg_id, page_str = raw.rsplit("_", 1)
    page = int(page_str)
    orders = await get_batch_group_orders(bg_id)
    if not orders:
        await callback.answer("❌ Группа не найдена", show_alert=True)
        return
    if not all(o["user_id"] == callback.from_user.id for o in orders):
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    text = format_batch_group_status(orders)
    await callback.message.edit_text(
        text,
        reply_markup=batch_group_detail_kb(orders, bg_id, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_order_"))
async def view_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    text = format_order_status(order)
    doc_count = await get_order_doc_count(order_id)
    kb = order_detail_kb(order, doc_count=doc_count)
    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("complete_order_"))
async def complete_order_confirm(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ уже завершён", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, завершить", callback_data=f"confirm_complete_{order_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_order_{order_id}"),
        ]
    ])
    await callback.message.edit_text(
        f"⚠️ <b>Завершить заказ #{order_id}?</b>\n\n"
        f"После завершения вы не сможете получить оставшиеся подписи и документы.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_complete_"))
async def confirm_complete_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ уже завершён", show_alert=True)
        return
    await update_order_status(order_id, "completed")
    await callback.message.edit_text(
        f"✅ <b>Заказ #{order_id} завершён.</b>\n\n"
        f"Спасибо за использование нашего сервиса!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К заказам", callback_data="my_orders_list")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        bot = get_bot()
        from src.db.admins import get_admin_ids
        from src.db.settings import is_admin_notifications_enabled
        from src.handlers.sim_sign import get_target_operator_ids
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        cat_name = order.get("category_name", "—")
        cat_emoji = get_category_emoji(cat_name)
        cat_display = f"{cat_emoji} {cat_name}" if cat_emoji else cat_name
        custom_op = order.get("custom_operator_name")
        if custom_op:
            cat_display = f"{cat_display} ({custom_op})"
        claimed = order.get("signatures_claimed", 0)
        total = order.get("total_signatures", 1)
        notify_text = (
            f"📦 <b>Заказ #{order_id} завершён клиентом</b>\n\n"
            f"👤 Клиент: @{user_name}\n"
            f"📂 Категория: {cat_display}\n"
            f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n"
            f"📊 Подписей: {claimed}/{total}"
        )
        op_ids = await get_target_operator_ids(order.get("account_id"))
        for op_id in op_ids:
            try:
                await bot.send_message(op_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
        for admin_id in await get_admin_ids():
            notify_enabled = await is_admin_notifications_enabled(admin_id)
            if notify_enabled:
                try:
                    await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                except Exception:
                    pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("user_cancel_preorder_"))
async def user_cancel_preorder(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "preorder":
        await callback.answer("❌ Этот заказ не является предзаказом", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"confirm_cancel_preorder_{order_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_order_{order_id}"),
        ]
    ])
    category = await get_category(order["category_id"])
    cat_name = category["name"] if category else "—"
    await callback.message.edit_text(
        f"⚠️ <b>Отменить предзаказ #{order_id}?</b>\n\n"
        f"📂 Категория: {cat_name}\n"
        f"💰 Сумма: {order.get('price_paid', 0):.2f}$\n\n"
        f"Запрос на отмену будет отправлен администратору.\n"
        f"Средства будут возвращены после подтверждения.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel_preorder_"))
async def confirm_cancel_preorder(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "preorder":
        await callback.answer("❌ Этот заказ уже не является предзаказом", show_alert=True)
        return

    category = await get_category(order["category_id"])
    raw_cat_name = category["name"] if category else "—"
    cat_emoji = get_category_emoji(raw_cat_name)
    cat_name = f"{cat_emoji} {raw_cat_name}" if cat_emoji else raw_cat_name
    total_price = order.get("price_paid", 0)
    user = await get_user(callback.from_user.id)
    username = f"@{user['username']}" if user and user.get("username") else str(callback.from_user.id)

    await callback.message.edit_text(
        f"⏳ <b>Запрос на отмену предзаказа #{order_id} отправлен администратору.</b>\n\n"
        f"Ожидайте решения.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К заказам", callback_data="my_orders_list")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()

    bot = get_bot()
    admin_ids = await get_admin_ids()
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить отмену", callback_data=f"admin_approve_cancel_{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_cancel_{order_id}"),
        ]
    ])
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"🔔 <b>Запрос на отмену предзаказа</b>\n\n"
                f"📦 Заказ: #{order_id}\n"
                f"👤 Пользователь: {username} (ID: {callback.from_user.id})\n"
                f"📂 Категория: {cat_name}\n"
                f"💰 Сумма: {total_price:.2f}$\n\n"
                f"Подтвердить отмену и вернуть средства?",
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("admin_approve_cancel_"))
async def admin_approve_cancel(callback: CallbackQuery):
    from src.db.admins import is_admin
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "preorder":
        await callback.answer("❌ Заказ уже не является предзаказом", show_alert=True)
        return

    cancelled = await cancel_preorder(order_id)
    if not cancelled:
        await callback.answer("❌ Не удалось отменить", show_alert=True)
        return

    total_price = order.get("price_paid", 0)
    if total_price > 0:
        await update_balance(order["user_id"], total_price)

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ <b>Отменено</b> админом {callback.from_user.id}\n"
        f"💰 Возврат: {total_price:.2f}$",
        parse_mode="HTML",
    )
    await callback.answer("✅ Предзаказ отменён, средства возвращены")

    bot = get_bot()
    try:
        await bot.send_message(
            order["user_id"],
            f"✅ <b>Предзаказ #{order_id} отменён</b>\n\n"
            f"💰 На ваш баланс возвращено: <b>{total_price:.2f}$</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reject_cancel_"))
async def admin_reject_cancel(callback: CallbackQuery):
    from src.db.admins import is_admin
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "preorder":
        await callback.message.edit_text(
            callback.message.text + f"\n\nℹ️ Заказ уже не является предзаказом (статус: {order['status']})",
            parse_mode="HTML",
        )
        await callback.answer("ℹ️ Заказ уже обработан", show_alert=True)
        return

    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ <b>Отклонено</b> админом {callback.from_user.id}",
        parse_mode="HTML",
    )
    await callback.answer("❌ Запрос на отмену отклонён")

    bot = get_bot()
    try:
        await bot.send_message(
            order["user_id"],
            f"❌ <b>Запрос на отмену предзаказа #{order_id} отклонён</b>\n\n"
            f"Ваш предзаказ остаётся в очереди.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(F.text == "📁 Мои документы")
async def show_my_documents(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return
    orders_with_docs = await get_user_orders_with_documents(message.from_user.id)
    if not orders_with_docs:
        await message.answer(
            "📁 <b>Мои документы</b>\n\n"
            "📭 У вас пока нет документов.\n\n"
            "Документы появятся здесь после того, как администратор или оператор отправит их по вашему заказу.",
            parse_mode="HTML",
        )
        return
    buttons = []
    STATUS_EMOJI = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "expired": "⏰", "pending_review": "🟡", "pending_confirmation": "🟡"}
    for o in orders_with_docs:
        emoji = STATUS_EMOJI.get(o["status"], "📦")
        phone = o.get("phone") or "—"
        cat = o.get("category_name") or "—"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{o['order_id']} — {cat} ({o['doc_count']} док.)",
            callback_data=f"my_docs_{o['order_id']}"
        )])
    await message.answer(
        f"📁 <b>Мои документы</b>\n\n"
        f"Выберите заказ для просмотра документов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("my_docs_"))
async def show_order_documents(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    docs = await get_order_documents(order_id)
    if not docs:
        await callback.answer("📭 Документов нет", show_alert=True)
        return
    if docs[0]["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваши документы", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    total_docs = len(docs)
    if total_docs == 1:
        buttons = []
        buttons.append([InlineKeyboardButton(text="🔙 К документам", callback_data="my_documents_list")])
        try:
            await callback.message.delete()
        except Exception:
            pass
        bot = get_bot()
        await bot.send_photo(
            callback.from_user.id,
            docs[0]["file_id"],
            caption=(
                f"📄 <b>Документ по заказу #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>1x</b>"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML",
        )
    else:
        buttons = []
        row = []
        for i in range(1, total_docs + 1):
            row.append(InlineKeyboardButton(text=str(i), callback_data=f"view_doc_{order_id}_{i}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(
            text=f"📸 Показать все ({total_docs} шт)",
            callback_data=f"view_all_docs_{order_id}"
        )])
        buttons.append([InlineKeyboardButton(text="🔙 К документам", callback_data="my_documents_list")])
        try:
            await callback.message.edit_text(
                f"📁 <b>Документы заказа #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>{total_docs}x</b>\n\n"
                f"Выберите номер документа или посмотрите все:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML",
            )
        except Exception:
            await callback.message.answer(
                f"📁 <b>Документы заказа #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>{total_docs}x</b>\n\n"
                f"Выберите номер документа или посмотрите все:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(F.data.startswith("view_doc_"))
async def view_single_doc(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    doc_num = int(parts[3])
    docs = await get_order_documents(order_id)
    if not docs or doc_num < 1 or doc_num > len(docs):
        await callback.answer("❌ Документ не найден", show_alert=True)
        return
    if docs[0]["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваши документы", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    doc = docs[doc_num - 1]
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К списку", callback_data=f"my_docs_{order_id}")]
    ])
    try:
        await callback.message.delete()
    except Exception:
        pass
    bot = get_bot()
    await bot.send_photo(
        callback.from_user.id,
        doc["file_id"],
        caption=(
            f"📄 <b>Документ {doc_num}/{len(docs)}</b>\n"
            f"📦 Заказ: #{order_id}\n"
            f"📂 Категория: {cat_name}\n"
            f"📱 Телефон: <code>{phone}</code>"
        ),
        reply_markup=back_kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_all_docs_"))
async def view_all_docs(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    docs = await get_order_documents(order_id)
    if not docs:
        await callback.answer("📭 Документов нет", show_alert=True)
        return
    if docs[0]["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваши документы", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    bot = get_bot()
    from aiogram.types import InputMediaPhoto
    if len(docs) <= 10:
        media = []
        for i, doc in enumerate(docs):
            caption = (
                f"📄 <b>Документ {i+1}/{len(docs)}</b> — Заказ #{order_id}\n"
                f"📂 {cat_name} | 📱 <code>{phone}</code>"
            ) if i == 0 else None
            media.append(InputMediaPhoto(
                media=doc["file_id"],
                caption=caption,
                parse_mode="HTML" if caption else None,
            ))
        await bot.send_media_group(callback.from_user.id, media)
    else:
        for chunk_start in range(0, len(docs), 10):
            chunk = docs[chunk_start:chunk_start + 10]
            media = []
            for i, doc in enumerate(chunk):
                idx = chunk_start + i + 1
                caption = (
                    f"📄 <b>Документы {chunk_start+1}—{chunk_start+len(chunk)}/{len(docs)}</b> — Заказ #{order_id}\n"
                    f"📂 {cat_name} | 📱 <code>{phone}</code>"
                ) if i == 0 else None
                media.append(InputMediaPhoto(
                    media=doc["file_id"],
                    caption=caption,
                    parse_mode="HTML" if caption else None,
                ))
            await bot.send_media_group(callback.from_user.id, media)
    await callback.answer(f"📄 Отправлено {len(docs)} документ(ов)")


@router.callback_query(F.data == "my_documents_list")
async def back_to_documents_list(callback: CallbackQuery):
    orders_with_docs = await get_user_orders_with_documents(callback.from_user.id)
    if not orders_with_docs:
        try:
            await callback.message.delete()
        except Exception:
            pass
        bot = get_bot()
        await bot.send_message(
            callback.from_user.id,
            "📁 <b>Мои документы</b>\n\n"
            "📭 У вас пока нет документов.",
            parse_mode="HTML",
        )
        await callback.answer()
        return
    buttons = []
    STATUS_EMOJI = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "expired": "⏰", "pending_review": "🟡", "pending_confirmation": "🟡"}
    for o in orders_with_docs:
        emoji = STATUS_EMOJI.get(o["status"], "📦")
        cat = o.get("category_name") or "—"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{o['order_id']} — {cat} ({o['doc_count']} док.)",
            callback_data=f"my_docs_{o['order_id']}"
        )])
    try:
        await callback.message.delete()
    except Exception:
        pass
    bot = get_bot()
    await bot.send_message(
        callback.from_user.id,
        f"📁 <b>Мои документы</b>\n\n"
        f"Выберите заказ для просмотра документов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()
