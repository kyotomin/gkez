from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PAGE_SIZE = 10


def admin_menu_kb(bot_paused: bool = False, show_admin_mgmt: bool = False) -> InlineKeyboardMarkup:
    pause_text = "▶️ Возобновить" if bot_paused else "⏸ Приостановить"
    buttons = [
        [
            InlineKeyboardButton(text="📂 Категории", callback_data="admin_categories"),
            InlineKeyboardButton(text="📦 Аккаунты", callback_data="admin_accounts"),
        ],
        [
            InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders"),
            InlineKeyboardButton(text="⏳ Предзаказы", callback_data="admin_preorders"),
        ],
        [
            InlineKeyboardButton(text="💬 Обращения", callback_data="admin_tickets"),
            InlineKeyboardButton(text="⭐ Отзывы", callback_data="admin_reviews"),
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton(text="💰 Баланс", callback_data="admin_topup_user"),
        ],
        [
            InlineKeyboardButton(text="🔒 Депозит", callback_data="admin_deposit"),
            InlineKeyboardButton(text="👷 Операторы", callback_data="admin_operators"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton(text="🔢 Лимит TOTP", callback_data="admin_totp_limit"),
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_toggle_notify"),
        ],
        [
            InlineKeyboardButton(text="⭐ Репутация", callback_data="admin_reputation"),
            InlineKeyboardButton(text="📖 Инструкция", callback_data="admin_faq"),
        ],
        [
            InlineKeyboardButton(text="📢 Подписки", callback_data="admin_channels"),
        ],
    ]
    if show_admin_mgmt:
        buttons.append([InlineKeyboardButton(text="👑 Админы", callback_data="admin_admins")])
    buttons.append([InlineKeyboardButton(text=pause_text, callback_data="admin_toggle_pause")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_categories_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        status = "✅" if cat.get("is_active", 1) else "❌"
        price = cat.get("price", 0)
        buttons.append([InlineKeyboardButton(
            text=f"{status} {cat['name']} — {price:.2f}$",
            callback_data=f"admin_cat_{cat['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_category")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_detail_kb(category_id: int, has_bb_price: bool = False) -> InlineKeyboardMarkup:
    bb_label = "💰 Изменить цену ББ" if has_bb_price else "💰 Установить цену ББ"
    rows = [
        [
            InlineKeyboardButton(text="💲 Изменить цену", callback_data=f"admin_set_price_{category_id}"),
            InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"admin_rename_cat_{category_id}"),
        ],
        [
            InlineKeyboardButton(text="📊 Лимит подписей", callback_data=f"admin_set_max_sigs_{category_id}"),
            InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"admin_toggle_cat_{category_id}"),
        ],
        [InlineKeyboardButton(text=bb_label, callback_data=f"admin_cat_bb_price_{category_id}")],
    ]
    rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_del_cat_{category_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_categories")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_accounts_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить аккаунты", callback_data="admin_add_accounts"),
            InlineKeyboardButton(text="📋 Все аккаунты", callback_data="admin_all_accounts"),
        ],
        [InlineKeyboardButton(text="🔍 Поиск по номеру", callback_data="admin_search_account")],
        [InlineKeyboardButton(text="📊 Наличие", callback_data="admin_availability")],
        [InlineKeyboardButton(text="🔄 Изменить лимиты всех", callback_data="admin_bulk_limits")],
        [
            InlineKeyboardButton(text="📱 Сбросить наличие аккаунта", callback_data="admin_reset_acc"),
            InlineKeyboardButton(text="🔄 Сбросить все", callback_data="admin_reset_all_accs"),
        ],
        [InlineKeyboardButton(text="👥 Массовое назначение", callback_data="admin_bulk_assign")],
        [InlineKeyboardButton(text="⭐ Массовый приоритет", callback_data="admin_mass_priority")],
        [InlineKeyboardButton(text="🗑 Массовое удаление", callback_data="admin_mass_delete")],
        [
            InlineKeyboardButton(text="✅ Массовое вкл.", callback_data="admin_mass_enable"),
            InlineKeyboardButton(text="❌ Массовое выкл.", callback_data="admin_mass_disable"),
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
    ])


def admin_accounts_list_kb(accounts: list[dict], page: int = 0, per_page: int = 20) -> InlineKeyboardMarkup:
    buttons = []
    start = page * per_page
    end = start + per_page
    page_accounts = accounts[start:end]
    for acc in page_accounts:
        star = "⭐ " if acc.get("priority", 0) > 0 else ""
        disabled = "🚫 " if not acc.get("is_enabled", 1) else ""
        buttons.append([InlineKeyboardButton(
            text=f"{disabled}{star}📱 {acc['phone']}",
            callback_data=f"admin_acc_{acc['id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_accs_page_{page - 1}"))
    if end < len(accounts):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_accs_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_account_detail_kb(account_id: int, operator_assigned: bool = False, is_enabled: bool = True) -> InlineKeyboardMarkup:
    op_text = "👷 Сменить оператора" if operator_assigned else "👷 Назначить оператора"
    enable_text = "🔴 Отключить" if is_enabled else "🟢 Включить"
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Изменить подписи", callback_data=f"admin_edit_sigs_{account_id}"),
            InlineKeyboardButton(text="⭐️ Приоритет", callback_data=f"admin_set_prio_{account_id}"),
        ],
        [InlineKeyboardButton(text=op_text, callback_data=f"admin_acc_assign_op_{account_id}")],
        [InlineKeyboardButton(text=enable_text, callback_data=f"admin_toggle_acc_{account_id}")],
    ]
    if operator_assigned:
        buttons.append([InlineKeyboardButton(text="❌ Снять оператора", callback_data=f"admin_acc_unassign_op_{account_id}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_del_acc_{account_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_account_sigs_kb(account_id: int, sigs: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in sigs:
        max_s = s.get("max_signatures") if s.get("max_signatures") is not None else s.get("cat_max_signatures", 5)
        remaining = max_s - s['used_signatures']
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {s['category_name']}: {s['used_signatures']}/{max_s} (ост. {remaining})",
                callback_data=f"admin_sig_{account_id}_{s['category_id']}"
            ),
            InlineKeyboardButton(
                text=f"📊",
                callback_data=f"admin_sig_used_{account_id}_{s['category_id']}"
            ),
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_acc_{account_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _admin_group_orders(orders: list[dict]) -> list[tuple]:
    seen_groups = {}
    result = []
    for order in orders:
        bg = order.get("batch_group_id")
        if bg:
            if bg not in seen_groups:
                seen_groups[bg] = []
                result.append(("group", bg, seen_groups[bg]))
            seen_groups[bg].append(order)
        else:
            result.append(("single", None, order))
    return result


def admin_orders_kb(orders: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    STATUS_EMOJI = {"active": "🟢", "pending_confirmation": "🟡", "pending_review": "🟡", "completed": "✅", "rejected": "❌", "preorder": "⏳", "expired": "⏰"}
    buttons = []
    grouped = _admin_group_orders(orders)
    total = len(grouped)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = grouped[start:end]
    for item in page_items:
        kind, bg_id, data = item
        if kind == "group":
            group_orders = data
            first = group_orders[0]
            user_name = first.get("username") or first.get("full_name") or str(first.get("telegram_id", ""))
            statuses = set(o["status"] for o in group_orders)
            if "active" in statuses:
                emoji = "🟢"
            elif "preorder" in statuses:
                emoji = "⏳"
            elif statuses == {"completed"}:
                emoji = "✅"
            elif "expired" in statuses:
                emoji = "⏰"
            else:
                emoji = STATUS_EMOJI.get(first["status"], "📦")
            ids_str = ", ".join(f"#{o['id']}" for o in group_orders)
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {ids_str} — {user_name} ({len(group_orders)} шт)",
                callback_data=f"admin_batch_{bg_id}"
            )])
        else:
            order = data
            emoji = STATUS_EMOJI.get(order["status"], "📦")
            user_name = order.get("username") or order.get("full_name") or str(order.get("telegram_id", ""))
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} #{order['id']} — {user_name}",
                callback_data=f"admin_order_{order['id']}"
            )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_orders_p_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_orders_p_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔍 Поиск заказа", callback_data="admin_global_search_order")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_batch_group_detail_kb(orders: list[dict], batch_group_id: str, page: int = 0) -> InlineKeyboardMarkup:
    STATUS_EMOJI = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "expired": "⏰", "pending_review": "🟡", "pending_confirmation": "🟡"}
    buttons = []
    total = len(orders)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_orders = orders[start:end]
    for o in page_orders:
        phone = o.get("phone", "—")
        emoji = STATUS_EMOJI.get(o["status"], "📦")
        claimed = o.get("signatures_claimed", 0)
        total_sigs = o.get("total_signatures", 1)
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{o['id']} — {phone} ({claimed}/{total_sigs})",
            callback_data=f"admin_order_{o['id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_batchp_{batch_group_id}_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_batchp_{batch_group_id}_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="admin_orders")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_order_detail_kb(order: dict, pending_docs: int = 0, doc_count: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    if pending_docs > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🔴 Клиент запросил документы x{pending_docs}",
            callback_data=f"admin_send_screenshot_{order['id']}"
        )])
    if order["status"] in ("pending_review", "pending_confirmation"):
        buttons.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_approve_{order['id']}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{order['id']}"),
        ])
    if order["status"] == "active":
        buttons.append([InlineKeyboardButton(text="📸 Отправить скриншот", callback_data=f"admin_send_screenshot_{order['id']}")])
        if order.get("totp_refreshes", 0) > 0:
            buttons.append([InlineKeyboardButton(text="🔄 Обнулить TOTP", callback_data=f"admin_reset_totp_{order['id']}")])
        total = order.get("total_signatures") or 1
        claimed = order.get("signatures_claimed") or 0
        unclaimed = total - claimed
        if unclaimed > 0:
            buttons.append([InlineKeyboardButton(text="➖ Уменьшить подписи", callback_data=f"admin_reduce_sigs_{order['id']}")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить заказ (возврат)", callback_data=f"admin_cancel_order_{order['id']}")])
        buttons.append([InlineKeyboardButton(text="⏹ Завершить досрочно", callback_data=f"admin_early_complete_{order['id']}")])
    if order["status"] == "completed":
        buttons.append([InlineKeyboardButton(text="📎 Прикрепить документ", callback_data=f"admin_send_screenshot_{order['id']}")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"admin_cancel_completed_{order['id']}")])
    if doc_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"📁 Посмотреть скрины ({doc_count} шт)",
            callback_data=f"admin_view_docs_{order['id']}"
        )])
    bg_id = order.get("batch_group_id")
    if bg_id:
        buttons.append([InlineKeyboardButton(text="🔙 К группе заказов", callback_data=f"admin_batch_{bg_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="admin_orders")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_tickets_kb(tickets: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for t in tickets:
        emoji = "🟢" if t["status"] == "open" else "🔴"
        user_name = t.get("username") or t.get("full_name") or "—"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{t['id']} — {user_name}: {t['subject'][:20]}",
            callback_data=f"admin_ticket_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔍 Поиск обращения", callback_data="admin_search_ticket")])
    buttons.append([InlineKeyboardButton(text="📝 Лимит обращений", callback_data="admin_ticket_limit")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_ticket_detail_kb(ticket: dict) -> InlineKeyboardMarkup:
    buttons = []
    if ticket["status"] == "open":
        buttons.append([
            InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin_ticket_reply_{ticket['id']}"),
            InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"admin_close_ticket_{ticket['id']}"),
        ])
    if ticket.get("order_id"):
        buttons.append([InlineKeyboardButton(text="📦 Перейти к заказу", callback_data=f"admin_order_{ticket['order_id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_tickets")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_confirm_delete_kb(entity: str, entity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_confirm_del_{entity}_{entity_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_categories" if entity == "cat" else "admin_accounts"),
        ],
    ])


def admin_operators_kb(operators: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for op in operators:
        name = f"@{op['username']}" if op.get("username") else str(op["telegram_id"])
        role = op.get("role", "orders")
        role_emoji = "📋" if role == "orders" else "🎫"
        buttons.append([InlineKeyboardButton(
            text=f"{role_emoji} {name}",
            callback_data=f"admin_op_{op['telegram_id']}"
        )])
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить оператора", callback_data="admin_add_operator"),
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_operator_detail_kb(telegram_id: int, role: str = "orders", notifications_enabled: bool = True) -> InlineKeyboardMarkup:
    buttons = []
    if role != "orders":
        buttons.append([InlineKeyboardButton(text="📋 Перевести на заказы", callback_data=f"admin_op_role_orders_{telegram_id}")])
    if role != "support":
        buttons.append([InlineKeyboardButton(text="🎫 Перевести на поддержку", callback_data=f"admin_op_role_support_{telegram_id}")])
    if role != "preorders":
        buttons.append([InlineKeyboardButton(text="⏳ Перевести на предзаказы", callback_data=f"admin_op_role_preorders_{telegram_id}")])
    notif_text = "🔔 Уведомления: ВКЛ" if notifications_enabled else "🔕 Уведомления: ВЫКЛ"
    buttons.append([InlineKeyboardButton(text=notif_text, callback_data=f"admin_op_toggle_notif_{telegram_id}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить оператора", callback_data=f"admin_del_op_{telegram_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_operators")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def operator_confirm_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data=f"op_done_{order_id}")],
    ])


def operator_confirm_sig_kb(order_id: int, sig_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подпись #{sig_num} готово", callback_data=f"op_sig_done_{order_id}_{sig_num}")],
    ])


def operator_send_doc_kb(order_id: int, sig_num: int, qty: int = 1) -> InlineKeyboardMarkup:
    label = f"📸 Отправить {qty} документ(ов)" if qty > 1 else "📸 Отправить документ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"op_send_doc_{order_id}_{sig_num}_{qty}")],
    ])


def operator_tickets_kb(tickets: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for t in tickets:
        emoji = "🟢" if t["status"] == "open" else "🔴"
        user_name = t.get("username") or t.get("full_name") or "—"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{t['id']} — {user_name}: {t['subject'][:20]}",
            callback_data=f"admin_ticket_{t['id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_preorders_kb(preorders: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for po in preorders:
        cat_name = po.get("category_name", "—")
        custom = po.get("custom_operator_name")
        if custom:
            cat_name = f"{cat_name} ({custom})"
        user_name = po.get("username") or po.get("full_name") or str(po.get("user_id", ""))
        buttons.append([InlineKeyboardButton(
            text=f"⏳ #{po['id']} — {user_name} | {cat_name}",
            callback_data=f"admin_preorder_{po['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_preorder_detail_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"admin_preorder_msg_{order_id}")],
        [InlineKeyboardButton(text="❌ Отменить предзаказ", callback_data=f"admin_preorder_cancel_{order_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_preorders")],
    ])


def admin_reputation_kb(links: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for link in links:
        buttons.append([InlineKeyboardButton(
            text=f"🔗 {link['name']}",
            callback_data=f"admin_rep_{link['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить ссылку", callback_data="admin_add_rep")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_reputation_detail_kb(link_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin_rep_edit_name_{link_id}"),
            InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data=f"admin_rep_edit_url_{link_id}"),
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_rep_del_{link_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_reputation")],
    ])


def admin_users_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Все пользователи", callback_data="admin_all_users"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="admin_search_user"),
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
    ])


def admin_users_list_kb(users: list[dict], page: int = 0, per_page: int = 20) -> InlineKeyboardMarkup:
    buttons = []
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    for u in page_users:
        name = f"@{u['username']}" if u.get("username") else (u.get("full_name") or str(u["telegram_id"]))
        blocked = "🚫 " if u.get("is_blocked") else ""
        buttons.append([InlineKeyboardButton(
            text=f"{blocked}👤 {name}",
            callback_data=f"admin_user_{u['telegram_id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_page_{page - 1}"))
    if end < len(users):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_detail_kb(user: dict, has_deposit: bool = False, deposit_required: bool = True) -> InlineKeyboardMarkup:
    is_blocked = user.get("is_blocked", 0)
    block_text = "🔓 Разблокировать" if is_blocked else "🚫 Заблокировать"
    block_data = f"admin_unblock_user_{user['telegram_id']}" if is_blocked else f"admin_block_user_{user['telegram_id']}"
    rows = [
        [
            InlineKeyboardButton(text=block_text, callback_data=block_data),
            InlineKeyboardButton(text="💲 Депозит", callback_data=f"admin_set_user_deposit_{user['telegram_id']}"),
        ],
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"admin_topup_uid_{user['telegram_id']}")],
        [InlineKeyboardButton(text="🔢 Лимит TOTP", callback_data=f"admin_user_totp_{user['telegram_id']}")],
        [InlineKeyboardButton(text="📦 Заказы", callback_data=f"admin_user_orders_{user['telegram_id']}")],
    ]
    if deposit_required and has_deposit:
        rows.append([InlineKeyboardButton(text="💸 Вывести депозит", callback_data=f"admin_withdraw_dep_{user['telegram_id']}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_reviews_kb(reviews: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for r in reviews:
        user_name = r.get("username") or r.get("full_name") or "—"
        date_str = r["created_at"].strftime("%Y-%m-%d") if r.get("created_at") else ""
        buttons.append([InlineKeyboardButton(
            text=f"💬 #{r['id']} — {user_name} ({date_str})",
            callback_data=f"admin_review_{r['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="💰 Бонус за отзыв", callback_data="admin_review_bonus")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_review_detail_kb(review_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_del_review_{review_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_reviews")],
    ])


def admin_availability_kb(accounts: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    total = len(accounts)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_avail_page_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_avail_page_{page + 1}"))
    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_stats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Статистика за дату", callback_data="admin_stats_by_date")],
        [
            InlineKeyboardButton(text="📥 Выгрузка (все)", callback_data="admin_export_all"),
            InlineKeyboardButton(text="📥 Выгрузка (дата)", callback_data="admin_export_date"),
        ],
        [InlineKeyboardButton(text="📥 Выгрузка (сегодня)", callback_data="admin_export_today")],
        [InlineKeyboardButton(text="📱 Выгрузка по номерам", callback_data="admin_export_phones")],
        [InlineKeyboardButton(text="📊 Выгрузка продаж", callback_data="admin_sales_export")],
        [InlineKeyboardButton(text="👑 Статистика админов", callback_data="admin_stats_admins")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
    ])


def admin_sales_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 За сегодня", callback_data="sales_period_today")],
        [InlineKeyboardButton(text="📆 За неделю", callback_data="sales_period_week")],
        [InlineKeyboardButton(text="🗓 За месяц", callback_data="sales_period_month")],
        [InlineKeyboardButton(text="📋 За всё время", callback_data="sales_period_all")],
        [InlineKeyboardButton(text="📆 Свой период", callback_data="sales_period_custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_stats")],
    ])


def admin_stats_date_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_stats")],
    ])


def admin_channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['title']}",
            callback_data=f"admin_channel_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_channel_detail_kb(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_del_channel_{channel_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_channels")],
    ])
