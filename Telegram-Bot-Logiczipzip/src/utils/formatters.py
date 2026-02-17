from datetime import datetime
from src.utils.totp import generate_totp

CATEGORY_EMOJI_MAP = {
    "МТС'Физ": "🔴",
    "МТС'Есим": "🔴",
    "Билайн": "🟡",
    "Мегафон": "🟢",
    "Теле2": "⚫️",
    "Йота": "🔵",
}


def get_category_emoji(name: str) -> str:
    if not name or name == "—":
        return ""
    for key, emoji in CATEGORY_EMOJI_MAP.items():
        if key.lower() in name.lower():
            return emoji
    return "⚪️"


def _fmt_date(val) -> str:
    if not val:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val)[:10]


def _fmt_datetime(val) -> str:
    if not val:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    return str(val)[:16]


def _time_remaining(expires_at) -> str:
    if not expires_at:
        return "—"
    try:
        if isinstance(expires_at, datetime):
            exp = expires_at
        elif isinstance(expires_at, str):
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) if "+" in expires_at or "Z" in expires_at else datetime.strptime(expires_at[:19], "%Y-%m-%d %H:%M:%S")
        else:
            return "—"
        now = datetime.utcnow()
        delta = exp - now
        if delta.total_seconds() <= 0:
            return "⏰ Истекло"
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 0:
            return f"{hours}ч {minutes}мин"
        return f"{minutes}мин"
    except Exception:
        return "—"


def _category_display(order: dict) -> str:
    cat = order.get('category_name', '—')
    emoji = get_category_emoji(cat)
    custom = order.get('custom_operator_name')
    prefix = f"{emoji} " if emoji else ""
    if custom:
        return f"{prefix}{cat} ({custom})"
    return f"{prefix}{cat}"


def format_account_data_no_totp(order: dict, pending_qty: int = 0) -> str:
    claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)
    pending_line = f"\n📝 Текущий запрос: <b>{pending_qty} подп.</b>" if pending_qty > 0 else ""
    return (
        f"✅ <b>Данные для подписания:</b>\n\n"
        f"📂 Категория: {_category_display(order)}\n"
        f"📊 Подписей использовано: {claimed}/{total}"
        f"{pending_line}\n\n"
        f"📱 Аккаунт\n"
        f"├ Телефон: <code>{order['phone']}</code>\n"
        f"└ Пароль: <code>{order['password']}</code>\n\n"
        f"🔐 Нажмите «Получить TOTP» для генерации свежего кода.\n\n"
        f"⚠️ Нажмите «✅ Подпись отправлена» после отправки документов.\n"
        f"❗️ Эти данные конфиденциальны. Не передавайте их третьим лицам."
    )



def format_account_data(order: dict, totp_limit: int = 2, **kwargs) -> str:
    totp_code = generate_totp(order["totp_secret"])
    claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)
    totp_display = order.get("totp_refreshes", 0)
    return (
        f"✅ <b>Данные для подписания:</b>\n\n"
        f"📂 Категория: {_category_display(order)}\n"
        f"📊 Подписей: {claimed}/{total}\n\n"
        f"📱 Аккаунт\n"
        f"├ Телефон: <code>{order['phone']}</code>\n"
        f"├ Пароль: <code>{order['password']}</code>\n"
        f"├ TOTP: <code>{totp_code}</code>\n"
        f"└ Обновлений TOTP: {totp_display}/{totp_limit}\n\n"
        f"❗️ Эти данные конфиденциальны. Не передавайте их третьим лицам."
    )


def format_profile(user: dict, order_count: int, has_deposit: bool = False, deposit_required: bool = True) -> str:
    reg_date = _fmt_date(user.get("registered_at"))
    balance = user.get("balance", 0.0)
    if not deposit_required:
        deposit_status = "✅ Активен"
    elif has_deposit:
        deposit_status = "✅ Активен"
    else:
        deposit_status = "🔴 Неактивен (депозит не внесён)"
    return (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 Telegram ID: <code>{user['telegram_id']}</code>\n"
        f"💰 Баланс: <b>{balance:.2f}$</b>\n"
        f"📅 Дата регистрации: {reg_date}\n"
        f"📌 Статус: {deposit_status}\n\n"
        f"📊 Всего заказов: {order_count}"
    )


def format_order_status(order: dict) -> str:
    status_map = {
        "active": "🟢 Активен",
        "pending_confirmation": "🟡 Ожидает подтверждения",
        "pending_review": "🟡 На проверке",
        "completed": "✅ Завершён",
        "rejected": "❌ Отклонён",
        "expired": "⏰ Истёк",
        "preorder": "⏳ Предзаказ",
    }
    status = status_map.get(order["status"], order["status"])
    claimed = order.get("signatures_claimed", 0)
    confirmed = order.get("signatures_sent", 0)
    total = order.get("total_signatures", 1)
    if order["status"] == "preorder":
        return (
            f"⏳ <b>Предзаказ #{order['id']}</b>\n\n"
            f"📂 Категория: {_category_display(order)}\n"
            f"📊 Подписей: {total}\n"
            f"📌 Статус: {status}\n"
            f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
            f"📅 Создан: {_fmt_datetime(order.get('created_at'))}\n\n"
            f"⏰ Ожидает появления свободного аккаунта."
        )
    expires = order.get("expires_at")
    remaining = _time_remaining(expires) if expires else "—"
    expires_str = _fmt_datetime(expires) if expires else "—"
    phone = order.get("phone") or "—"
    remaining_unused = ""
    if order["status"] == "active" and claimed < total:
        remaining_unused = f"\n\n⏳ <b>Осталось времени: {remaining}</b>"
    return (
        f"📦 <b>Заказ #{order['id']}</b>\n\n"
        f"📂 Категория: {_category_display(order)}\n"
        f"📱 Телефон: <code>{phone}</code>\n"
        f"📊 Подписей получено: {claimed}/{total}\n"
        f"✅ Подтверждено: {confirmed}/{total}\n"
        f"📌 Статус: {status}\n"
        f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
        f"📅 Создан: {_fmt_datetime(order.get('created_at'))}\n"
        f"⏰ Действует до: {expires_str}"
        f"{remaining_unused}"
    )


def format_order_card_admin(order: dict, user_name: str) -> str:
    status_map = {
        "active": "🟢 Активен",
        "pending_confirmation": "🟡 Ожидает подтверждения",
        "pending_review": "🟡 На проверке",
        "completed": "✅ Завершён",
    }
    status = status_map.get(order["status"], order["status"])
    total = order.get("total_signatures", 1)
    claimed = order.get("signatures_claimed", 0)
    custom = order.get('custom_operator_name')
    custom_line = f"🏢 Оператор: {custom}\n" if custom else ""
    return (
        f"🛒 <b>Новый заказ #{order['id']}</b>\n\n"
        f"👤 Клиент: @{user_name}\n"
        f"📂 Категория: {_category_display(order)}\n"
        f"{custom_line}"
        f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n"
        f"📊 Подписей: {claimed}/{total}\n"
        f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
        f"📌 Статус: {status}"
    )


def format_batch_group_status(orders: list[dict]) -> str:
    if not orders:
        return ""
    first = orders[0]
    status_map = {
        "active": "🟢 Активен",
        "pending_confirmation": "🟡 Ожидает подтверждения",
        "pending_review": "🟡 На проверке",
        "completed": "✅ Завершён",
        "rejected": "❌ Отклонён",
        "expired": "⏰ Истёк",
        "preorder": "⏳ Предзаказ",
    }
    total_sigs = sum(o.get("total_signatures", 1) for o in orders)
    claimed_sigs = sum(o.get("signatures_claimed", 0) for o in orders)
    confirmed_sigs = sum(o.get("signatures_sent", 0) for o in orders)
    total_paid = sum(o.get("price_paid", 0) for o in orders)
    statuses = set(o["status"] for o in orders)
    if "active" in statuses:
        status_text = "🟢 Активен"
    elif "preorder" in statuses:
        status_text = "⏳ Предзаказ"
    elif statuses == {"completed"}:
        status_text = "✅ Завершён"
    elif "expired" in statuses:
        status_text = "⏰ Истёк"
    else:
        status_text = status_map.get(first["status"], first["status"])
    ids_str = ", ".join(f"#{o['id']}" for o in orders)
    is_bb = any(o.get("is_exclusive") for o in orders)
    bb_label = " (ББ🔥)" if is_bb else ""
    lines = [
        f"📦 <b>Заказ {ids_str}</b>{bb_label}\n",
        f"📂 Категория: {_category_display(first)}",
        f"📊 Подписей: {claimed_sigs}/{total_sigs}",
        f"✅ Подтверждено: {confirmed_sigs}/{total_sigs}",
        f"💰 Оплачено: {total_paid:.2f}$",
        f"📌 Статус: {status_text}\n",
        f"📱 <b>Аккаунты ({len(orders)}):</b>",
    ]
    for i, o in enumerate(orders, 1):
        phone = o.get("phone") or "—"
        o_claimed = o.get("signatures_claimed", 0)
        o_total = o.get("total_signatures", 1)
        o_status = status_map.get(o["status"], o["status"])
        lines.append(f"\n{i}. <code>{phone}</code> — {o_claimed}/{o_total} подп. — {o_status}")
    active_orders = [o for o in orders if o["status"] == "active"]
    if active_orders:
        earliest_exp = min((o.get("expires_at") for o in active_orders if o.get("expires_at")), default=None)
        if earliest_exp:
            lines.append(f"\n⏳ <b>Осталось: {_time_remaining(earliest_exp)}</b>")
    return "\n".join(lines)


def format_bb_batch_card_admin(orders: list[dict], user_name: str) -> str:
    if not orders:
        return ""
    first = orders[0]
    status_map = {
        "active": "🟢 Активен",
        "pending_confirmation": "🟡 Ожидает подтверждения",
        "pending_review": "🟡 На проверке",
        "completed": "✅ Завершён",
    }
    total_sigs = sum(o.get("total_signatures", 1) for o in orders)
    claimed_sigs = sum(o.get("signatures_claimed", 0) for o in orders)
    total_paid = sum(o.get("price_paid", 0) for o in orders)
    phones = "\n".join(f"<code>{o.get('phone', '—')}</code>" for o in orders)
    ids_str = ", ".join(f"#{o['id']}" for o in orders)
    status = status_map.get(first["status"], first["status"])
    is_bb = any(o.get("is_exclusive") for o in orders)
    bb_label = " (ББ🔥)" if is_bb else ""
    return (
        f"🛒 <b>Новый заказ {ids_str}</b>\n\n"
        f"👤 Клиент: @{user_name}\n"
        f"📂 Категория: {_category_display(first)}{bb_label}\n"
        f"📱 Телефоны:\n\n"
        f"{phones}\n\n"
        f"📊 Подписей: {claimed_sigs}/{total_sigs}\n"
        f"💰 Оплачено: {total_paid:.2f}$\n"
        f"📌 Статус: {status}"
    )


def format_ticket(ticket: dict) -> str:
    status = "🟢 Открыто" if ticket["status"] == "open" else "🔴 Закрыто"
    return (
        f"📋 Обращение #{ticket['id']}\n\n"
        f"📋 Тема: {ticket['subject']}\n"
        f"📊 Статус: {status}\n"
        f"📅 Создан: {_fmt_datetime(ticket.get('created_at'))}"
    )
