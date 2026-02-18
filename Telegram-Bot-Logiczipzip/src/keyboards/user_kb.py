from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

PAGE_SIZE = 10


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Активировать SIM-Карту")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="📁 Мои документы"), KeyboardButton(text="⭐ Репутация")],
            [KeyboardButton(text="💬 Помощь"), KeyboardButton(text="💰 Пополнить баланс 💰")],
        ],
        resize_keyboard=True,
    )


CATEGORY_EMOJI = {
    "МТС'Физ": "🔴",
    "МТС'Есим": "🔴",
    "Билайн": "🟡",
    "Мегафон": "🟢",
    "Теле2": "⚫️",
    "Йота": "🔵",
    "Любой другой": "⚪️",
}

CATEGORY_ORDER = ["МТС'Физ", "МТС'Есим", "Билайн", "Мегафон", "Теле2", "Йота", "Любой другой"]


def buy_category_kb(categories: list[dict]) -> ReplyKeyboardMarkup:
    buttons = []
    cat_map = {c["name"]: c for c in categories}
    row = []
    shown = set()
    for name in CATEGORY_ORDER:
        if name == "Любой другой":
            continue
        cat = cat_map.get(name)
        if not cat:
            continue
        if not cat.get("is_active", 1):
            continue
        shown.add(name)
        price = cat.get("price", 0)
        row.append(KeyboardButton(text=f"{name} — {price:.2f}$"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    for cat in categories:
        name = cat["name"]
        if name in shown or name == "Любой другой":
            continue
        if not cat.get("is_active", 1):
            continue
        shown.add(name)
        price = cat.get("price", 0)
        row.append(KeyboardButton(text=f"{name} — {price:.2f}$"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    other_cat = cat_map.get("Любой другой")
    if other_cat and other_cat.get("is_active", 1):
        price = other_cat.get("price", 0)
        buttons.append([
            KeyboardButton(text=f"Любой другой — {price:.2f}$"),
            KeyboardButton(text="📦 Предзаказ"),
        ])
    else:
        buttons.append([KeyboardButton(text="📦 Предзаказ")])
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def confirm_buy_kb(category_id: int, total_price: float, batch_size: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💰 Оплатить с баланса ({total_price:.2f}$)",
            callback_data=f"confirm_buy_{category_id}"
        )],
        [InlineKeyboardButton(
            text=f"💳 Оплатить CryptoBot ({total_price:.2f}$)",
            callback_data=f"crypto_buy_{category_id}_{batch_size}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")],
    ])


def quantity_picker_kb(category_id: int, min_qty: int, max_qty: int, price_per_sig: float, bb_price=None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    step = min_qty if min_qty > 1 else 1
    display_max = min(max_qty, 10)
    i = min_qty
    while i <= display_max:
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"qty_select_{category_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
        i += step
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✏️ Своё количество", callback_data=f"custom_qty_{category_id}")])
    if bb_price is not None:
        buttons.append([InlineKeyboardButton(text="Тариф ББ🔥", callback_data=f"bb_select_{category_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def account_actions_kb(order_id: int, totp_refreshes: int, totp_shown: bool = False, signatures_claimed: int = 0, total_signatures: int = 1, totp_limit: int = 2) -> InlineKeyboardMarkup:
    buttons = []
    if not totp_shown:
        buttons.append([InlineKeyboardButton(
            text="🔐 Получить TOTP",
            callback_data=f"get_totp_{order_id}"
        )])
    elif totp_refreshes < totp_limit:
        buttons.append([InlineKeyboardButton(
            text="🔄 Обновить TOTP",
            callback_data=f"refresh_totp_{order_id}"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="📩 Обращение по TOTP",
            callback_data=f"totp_ticket_{order_id}"
        )])
    if totp_shown or totp_refreshes > 0:
        buttons.append([InlineKeyboardButton(
            text="✅ Подпись отправлена",
            callback_data=f"signature_sent_{order_id}"
        )])
    if signatures_claimed > 0:
        buttons.append([InlineKeyboardButton(
            text="📄 Получить документ",
            callback_data=f"request_doc_{order_id}"
        )])
    buttons.append([InlineKeyboardButton(
        text="🔙 К заказу",
        callback_data=f"view_order_{order_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _order_category_label(order: dict) -> str:
    cat = order.get('category_name', '')
    custom = order.get('custom_operator_name')
    if custom:
        return f"{cat} ({custom})"
    return cat


def _group_orders(orders: list[dict]) -> list[dict | list[dict]]:
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


def orders_list_kb(orders: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    STATUS_EMOJI = {"active": "🟢", "pending_confirmation": "🟡", "pending_review": "🟡", "completed": "✅", "rejected": "❌", "expired": "⏰", "preorder": "⏳"}
    buttons = []
    grouped = _group_orders(orders)
    total = len(grouped)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = grouped[start:end]
    for item in page_items:
        kind, bg_id, data = item
        if kind == "group":
            group_orders = data
            first = group_orders[0]
            total_sigs = sum(o.get("total_signatures", 1) for o in group_orders)
            claimed_sigs = sum(o.get("signatures_claimed", 0) for o in group_orders)
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
            cat_label = _order_category_label(first)
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {ids_str} — {cat_label} ({claimed_sigs}/{total_sigs})",
                callback_data=f"view_batch_{bg_id}"
            )])
        else:
            order = data
            emoji = STATUS_EMOJI.get(order["status"], "📦")
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} #{order['id']} — {_order_category_label(order)}",
                callback_data=f"view_order_{order['id']}"
            )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"orders_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"orders_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def batch_group_detail_kb(orders: list[dict], batch_group_id: str, page: int = 0) -> InlineKeyboardMarkup:
    STATUS_EMOJI = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "expired": "⏰", "pending_review": "🟡"}
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
            callback_data=f"view_order_{o['id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"batch_page_{batch_group_id}_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"batch_page_{batch_group_id}_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="my_orders_list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_detail_kb(order: dict, doc_count: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    if order["status"] == "active":
        claimed = order.get("signatures_claimed", 0)
        sent = order.get("signatures_sent", 0)
        total = order.get("total_signatures", 1)
        remaining = total - claimed
        if remaining > 0:
            buttons.append([InlineKeyboardButton(
                text=f"📝 Получить подпись ({remaining} осталось)",
                callback_data=f"claim_signature_{order['id']}"
            )])
        buttons.append([InlineKeyboardButton(
            text="📄 Получить документ",
            callback_data=f"request_doc_{order['id']}"
        )])
        if claimed <= sent:
            buttons.append([InlineKeyboardButton(
                text="✅ Завершить заказ",
                callback_data=f"complete_order_{order['id']}"
            )])
    if doc_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"📁 Посмотреть скрины ({doc_count} шт)",
            callback_data=f"my_docs_{order['id']}"
        )])
    if order["status"] == "preorder":
        buttons.append([InlineKeyboardButton(
            text="❌ Отменить предзаказ",
            callback_data=f"user_cancel_preorder_{order['id']}"
        )])
    bg_id = order.get("batch_group_id")
    if bg_id:
        buttons.append([InlineKeyboardButton(text="🔙 К группе заказов", callback_data=f"view_batch_{bg_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="my_orders_list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def claim_qty_kb(order_id: int, remaining: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, remaining + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"claim_qty_{order_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_order_{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def go_to_orders_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders_list")]
    ])


def help_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Помощь с заказом", callback_data="create_ticket")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="general_support")],
        [InlineKeyboardButton(text="📋 Мои обращения", callback_data="my_tickets")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="user_faq")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")],
    ])


def ticket_menu_kb() -> InlineKeyboardMarkup:
    return help_menu_kb()


def select_order_for_ticket_kb(orders: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for order in orders:
        buttons.append([InlineKeyboardButton(
            text=f"📦 #{order['id']} — {_order_category_label(order)}",
            callback_data=f"ticket_order_{order['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="help_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_tickets_kb(tickets: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for t in tickets:
        emoji = "🟢" if t["status"] == "open" else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{t['id']} — {t['subject'][:30]}",
            callback_data=f"view_ticket_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="help_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def ticket_detail_kb(ticket: dict) -> InlineKeyboardMarkup:
    buttons = []
    if ticket["status"] == "open":
        buttons.append([InlineKeyboardButton(
            text="💬 Написать сообщение",
            callback_data=f"ticket_reply_{ticket['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К обращениям", callback_data="my_tickets")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def reputation_kb(links: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for link in links:
        row.append(InlineKeyboardButton(text=link["name"], url=link["url"]))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⭐ Отзывы", callback_data="show_reviews")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def profile_kb(has_deposit: bool = False, deposit_required: bool = True) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="topup_balance")])
    if deposit_required:
        if not has_deposit:
            buttons.append([InlineKeyboardButton(text="🔒 Пополнить депозит", callback_data="pay_deposit")])
        else:
            buttons.append([InlineKeyboardButton(text="💸 Вывести депозит", callback_data="withdraw_deposit")])
    buttons.append([InlineKeyboardButton(text="👥 Рефералы", callback_data="my_referrals")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topup_amounts_kb() -> InlineKeyboardMarkup:
    amounts = [1, 5, 10, 25, 50, 100]
    buttons = []
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(text=f"{amt}$", callback_data=f"topup_{amt}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="topup_custom")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_check_kb(invoice_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_menu")],
    ])


def attach_file_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Прикрепить файл", callback_data="ticket_attach_file")],
        [InlineKeyboardButton(text="✅ Отправить без файла", callback_data="ticket_skip_file")],
    ])


def subscription_required_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["url"])])
    buttons.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
