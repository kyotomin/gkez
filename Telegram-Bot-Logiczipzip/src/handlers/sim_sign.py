import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from src.db.admins import get_admin_ids, is_admin
from src.db.categories import get_all_categories, get_category, get_active_categories
from src.db.accounts import try_reserve_account, try_reserve_account_exclusive, try_reserve_accounts_multi, get_available_count, get_account_operator
from src.db.orders import create_order, create_preorder, get_order, increment_totp_refresh, update_order_status, claim_signature, is_order_expired, start_claim, clear_pending_claim
from src.db.users import get_user, update_balance, is_user_blocked, get_user_deposit_required, get_user_totp_limit
from src.db.settings import get_deposit_amount, has_user_deposit, is_bot_paused, is_admin_notifications_enabled, get_totp_limit, get_user_effective_deposit
from src.db.operators import get_order_operator_ids, is_operator_notifications_enabled, get_order_operators_with_notifications
from src.utils.formatters import format_account_data, format_account_data_no_totp, format_order_card_admin
from src.keyboards.user_kb import (
    buy_category_kb, account_actions_kb, go_to_orders_kb, confirm_buy_kb, main_menu_kb, order_detail_kb,
    quantity_picker_kb, claim_qty_kb, CATEGORY_EMOJI, CATEGORY_ORDER,
)
from src.states.user_states import OrderStates

router = Router()



async def get_target_operator_ids(account_id: int | None) -> list[int]:
    if account_id:
        assigned_op = await get_account_operator(account_id)
        if assigned_op:
            enabled = await is_operator_notifications_enabled(assigned_op)
            return [assigned_op] if enabled else []
    return await get_order_operators_with_notifications()




async def _get_effective_totp_limit(user_id: int, total_signatures: int = 1, order_id: int = None) -> int:
    if order_id:
        from src.db.orders import compute_effective_totp_limit
        return await compute_effective_totp_limit(order_id, user_id)
    custom = await get_user_totp_limit(user_id)
    base = custom if custom is not None else await get_totp_limit()
    return base * max(total_signatures, 1)


async def build_shop_text() -> str:
    categories = await get_active_categories()
    paused = await is_bot_paused()
    bot_status = "⏸ Приостановлено" if paused else "✅ В работе"
    text = f"🔹 Состояние бота: {bot_status}\n\n"
    cat_map = {c["name"]: c for c in categories}
    cat_texts = []
    shown = set()
    for name in CATEGORY_ORDER:
        cat = cat_map.get(name)
        if not cat:
            continue
        shown.add(name)
        emoji = CATEGORY_EMOJI.get(name, "⚪️")
        available = cat.get("available_count", 0)
        cat_texts.append(f"{emoji} <b>{name}</b> — {available}х")
    for cat in categories:
        name = cat["name"]
        if name in shown:
            continue
        emoji = CATEGORY_EMOJI.get(name, "⚪️")
        available = cat.get("available_count", 0)
        cat_texts.append(f"{emoji} <b>{name}</b> — {available}х")
    if not categories:
        text += "📭 Нет доступных категорий.\n"
    else:
        text += "\n\n".join(cat_texts)
    return text


@router.message(F.text == "📲 Активировать SIM-Карту")
async def show_shop(message: Message):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return

    categories = await get_active_categories()
    text = await build_shop_text()
    await message.answer(
        text,
        reply_markup=buy_category_kb(categories),
        parse_mode="HTML",
    )


@router.message(F.text == "🔙 Назад")
async def shop_back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.message(F.text == "📦 Предзаказ")
async def preorder_menu(message: Message):
    categories = await get_active_categories()
    if not categories:
        await message.answer("❌ Нет доступных категорий.")
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as IKB
    buttons = []
    for cat in categories:
        name = cat["name"]
        price = cat.get("price", 0)
        max_sigs = cat.get("max_signatures", 1)
        emoji = CATEGORY_EMOJI.get(name, "⚪️")
        avail = cat.get("available_count", 0)
        if name == "Любой другой":
            label = f"{emoji} {name} — {price:.2f}$ (от 1х)"
        else:
            label = f"{emoji} {name} — {price:.2f}$ (от {max_sigs}х)"
        buttons.append([IKB(
            text=label,
            callback_data=f"preorder_cat_{cat['id']}"
        )])
    buttons.append([IKB(text="🔙 Назад", callback_data="back_to_shop")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📦 <b>Предзаказ</b>\n\n"
        "Выберите категорию для предзаказа.\n"
        "Укажите любое количество (от минимума).\n"
        "Как только нужные аккаунты появятся — заказ выполнится автоматически.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("preorder_cat_"))
async def preorder_category_select(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    price = category.get("price", 0)
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")

    if category["name"] == "Любой другой":
        await callback.message.edit_text(
            f"📦 <b>Предзаказ — {emoji} {category['name']}</b>\n\n"
            f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
            f"📦 Минимальный заказ: <b>1 подп.</b>\n\n"
            f"✏️ Введите название оператора:",
            parse_mode="HTML",
        )
        await state.update_data(preorder_category_id=category_id)
        await state.set_state(OrderStates.waiting_preorder_operator)
    else:
        step = min_order if min_order > 1 else 1
        step_hint = f"\n📐 Шаг: кратно {step} ({step}, {step*2}, {step*3}...)" if step > 1 else ""
        await callback.message.edit_text(
            f"📦 <b>Предзаказ — {emoji} {category['name']}</b>\n\n"
            f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
            f"📦 Минимальный заказ: <b>{min_order} подп.</b>{step_hint}\n\n"
            f"✏️ Введите количество (от {min_order}):",
            parse_mode="HTML",
        )
        await state.update_data(preorder_category_id=category_id)
        await state.set_state(OrderStates.waiting_preorder_qty)
    await callback.answer()


@router.message(OrderStates.waiting_preorder_operator)
async def preorder_operator_name(message: Message, state: FSMContext):
    operator_name = message.text.strip() if message.text else ""
    if not operator_name or len(operator_name) > 50:
        await message.answer("❌ Введите корректное название оператора (до 50 символов).")
        return
    data = await state.get_data()
    category_id = data["preorder_category_id"]
    category = await get_category(category_id)
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    price = category.get("price", 0)
    await state.update_data(preorder_operator_name=operator_name)
    await message.answer(
        f"📦 <b>Предзаказ — Любой другой</b>\n"
        f"🏢 Оператор: <b>{operator_name}</b>\n\n"
        f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
        f"📦 Минимальный заказ: <b>{min_order} подп.</b>\n\n"
        f"✏️ Введите количество (от {min_order}):",
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.waiting_preorder_qty)


@router.message(OrderStates.waiting_preorder_qty)
async def preorder_quantity(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ Введите число.")
        return
    qty = int(text)
    data = await state.get_data()
    category_id = data["preorder_category_id"]
    category = await get_category(category_id)
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    step = min_order if min_order > 1 else 1
    if category["name"] == "Любой другой":
        if qty < 1:
            await message.answer("❌ Минимальное количество: 1.")
            return
    else:
        if qty < min_order:
            await message.answer(f"❌ Минимальное количество: {min_order}.")
            return
        if step > 1 and qty % step != 0:
            await message.answer(f"❌ Количество должно быть кратно {step} (например: {step}, {step*2}, {step*3}...)")
            return
    price = category.get("price", 0)
    total_price = price * qty
    custom_op = data.get("preorder_operator_name")
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    cat_label = category["name"]
    if custom_op:
        cat_label = f"{cat_label} ({custom_op})"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💰 Оплатить с баланса ({total_price:.2f}$)",
            callback_data=f"confirm_preorder_{category_id}_{qty}"
        )],
        [InlineKeyboardButton(
            text=f"💳 Оплатить CryptoBot ({total_price:.2f}$)",
            callback_data=f"crypto_preorder_{category_id}_{qty}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")],
    ])
    await message.answer(
        f"📦 <b>Подтверждение предзаказа</b>\n\n"
        f"📂 Категория: {emoji} {cat_label}\n"
        f"📊 Количество: <b>{qty} подп.</b>\n"
        f"💵 Итого: <b>{total_price:.2f}$</b>\n\n"
        f"⏰ Как только аккаунты появятся — заказ выполнится автоматически.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_preorder_"))
async def confirm_preorder(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    category_id = int(parts[2])
    qty = int(parts[3])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    price = category.get("price", 0)
    total_price = price * qty

    if not await is_admin(callback.from_user.id):
        paused = await is_bot_paused()
        if paused:
            await callback.answer("⏸ Бот приостановлен. Покупки временно отключены.", show_alert=True)
            return
        blocked = await is_user_blocked(callback.from_user.id)
        if blocked:
            await callback.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
            return
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer(
                    "🔒 Для продолжения необходимо пополнить депозит.",
                    show_alert=True,
                )
                return

    if total_price > 0:
        user = await get_user(callback.from_user.id)
        if not user or user.get("balance", 0) < total_price:
            await callback.answer(
                f"❌ Недостаточно средств. Нужно: {total_price:.2f}$.",
                show_alert=True,
            )
            return
        await update_balance(callback.from_user.id, -total_price)

    data = await state.get_data()
    custom_op = data.get("preorder_operator_name")
    order_id = await create_preorder(callback.from_user.id, category_id, total_price, qty, custom_op)
    await state.clear()
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    cat_label = category["name"]
    if custom_op:
        cat_label = f"{cat_label} ({custom_op})"
    await callback.message.edit_text(
        f"⏳ <b>Предзаказ #{order_id} оформлен!</b>\n\n"
        f"📂 Категория: {emoji} {cat_label}\n"
        f"📊 Подписей: {qty}\n"
        f"💰 Сумма: {total_price:.2f}$\n\n"
        f"⏰ Как только аккаунты появятся — заказ выполнится автоматически и вы получите уведомление.",
        reply_markup=go_to_orders_kb(),
        parse_mode="HTML",
    )
    await callback.answer()

    from src.db.operators import get_preorder_operator_ids
    from src.bot.instance import bot
    try:
        op_ids = await get_preorder_operator_ids()
        for op_id in op_ids:
            try:
                await bot.send_message(
                    op_id,
                    f"📦 <b>Новый предзаказ #{order_id}</b>\n\n"
                    f"👤 ID: <code>{callback.from_user.id}</code>\n"
                    f"📂 Категория: {emoji} {cat_label}\n"
                    f"📊 Подписей: {qty}\n"
                    f"💰 Сумма: {total_price:.2f}$",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass


@router.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    categories = await get_active_categories()
    text = await build_shop_text()
    await callback.message.answer(
        text,
        reply_markup=buy_category_kb(categories),
        parse_mode="HTML",
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("buy_cat_"))
async def select_category_inline(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    if not category.get("is_active", 1):
        await callback.answer("❌ Категория отключена", show_alert=True)
        return
    count = await get_available_count(category_id)
    await _show_category_detail(callback.message, state, category, count, edit=True)
    await callback.answer()


async def _find_category_by_text(text: str) -> dict | None:
    categories = await get_active_categories()
    for cat in categories:
        name = cat["name"]
        price = cat.get("price", 0)
        if text == f"{name} — {price:.2f}$":
            return cat
    return None


@router.message(lambda m: m.text and " — " in m.text and m.text.endswith("$"))
async def select_category_text(message: Message, state: FSMContext):
    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer("🚫 Ваш аккаунт заблокирован.", parse_mode="HTML")
        return

    category = await _find_category_by_text(message.text)
    if not category:
        await message.answer("❌ Категория не найдена или отключена.")
        return
    if not category.get("is_active", 1):
        await message.answer("❌ Категория отключена.")
        return
    count = await get_available_count(category["id"])
    await _show_category_detail(message, state, category, count, edit=False)


async def _show_category_detail(target, state: FSMContext, category: dict, count: int, edit: bool = False):
    category_id = category["id"]
    if category["name"] == "Любой другой":
        price = category.get("price", 0)
        max_sigs = category.get("max_signatures", 1)
        text = (
            f"📝 <b>Выбран оператор: Любой другой — {max_sigs}х</b>\n\n"
            f"📊 Наличие: {count}х\n\n"
            f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
            f"*Минимальная покупка от 1х\n\n"
            f"✏️ Введите название оператора:"
        )
        if edit:
            await target.edit_text(text, parse_mode="HTML")
        else:
            await target.answer(text, parse_mode="HTML")
        await state.set_state(OrderStates.waiting_operator_name)
        await state.update_data(category_id=category_id, available_count=count)
        return

    price = category.get("price", 0)
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    bb_price = category.get("bb_price")
    max_available = count

    if max_available == 0:
        text = (
            f"{emoji} <b>{category['name']}</b>\n\n"
            f"📊 Доступно: 0 подп.\n"
            f"💰 Цена за подпись: <b>{price:.2f}$</b>\n\n"
            f"❌ Сейчас нет в наличии.\n"
            f"Вы можете оформить предзаказ — мы уведомим вас, когда появятся подписи."
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        buttons = [
            [InlineKeyboardButton(text="📦 Оформить предзаказ", callback_data=f"preorder_cat_{category_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")],
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        if edit:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    elif max_available <= min_order:
        total_price = price * min_order
        text = (
            f"{emoji} <b>{category['name']}</b>\n\n"
            f"📊 Доступно: {count} подп.\n"
            f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
            f"📦 Минимальный заказ: <b>{min_order} подп.</b>\n"
            f"💵 Итого: <b>{total_price:.2f}$</b>\n\n"
            f"⚠️ Аккаунт будет закреплён за вами на 72ч.\n\n"
            f"Подтвердите покупку:"
        )
        await state.update_data(buy_qty=min_order)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        buttons = [
            [InlineKeyboardButton(
                text=f"💰 Оплатить с баланса ({total_price:.2f}$)",
                callback_data=f"confirm_buy_{category_id}"
            )],
            [InlineKeyboardButton(
                text=f"💳 Оплатить CryptoBot ({total_price:.2f}$)",
                callback_data=f"crypto_buy_{category_id}_{min_order}"
            )],
        ]
        if bb_price is not None:
            buttons.append([InlineKeyboardButton(text="Тариф ББ🔥", callback_data=f"bb_select_{category_id}")])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        if edit:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        text = (
            f"{emoji} <b>{category['name']}</b>\n\n"
            f"📊 Доступно: {count} подп.\n"
            f"💰 Цена за подпись: {price:.2f}$\n"
            f"📦 Минимальный заказ: {min_order} подп.\n\n"
            f"Выберите количество:"
        )
        kb = quantity_picker_kb(category_id, min_order, max_available, price, bb_price=bb_price)
        if edit:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(OrderStates.waiting_operator_name)
async def process_operator_name(message: Message, state: FSMContext):
    operator_name = message.text.strip() if message.text else ""
    if not operator_name or len(operator_name) > 100:
        await message.answer("❌ Введите корректное название оператора (до 100 символов).")
        return
    data = await state.get_data()
    category_id = data["category_id"]
    category = await get_category(category_id)
    price = category.get("price", 0)
    max_sigs = category.get("max_signatures", 1)
    available = data.get("available_count", 0)
    await state.update_data(custom_operator_name=operator_name)
    await message.answer(
        f"📝 <b>Оператор: {operator_name}</b>\n\n"
        f"📊 Доступно: {available}х\n"
        f"💰 Цена за подпись: <b>{price:.2f}$</b>\n"
        f"*Минимальная покупка от 1х\n\n"
        f"✏️ Введите необходимое количество:",
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.waiting_quantity)


@router.message(OrderStates.waiting_quantity)
async def process_quantity(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ Введите число.")
        return
    qty = int(text)
    data = await state.get_data()
    category_id = data["category_id"]
    category = await get_category(category_id)
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    step = min_order if min_order > 1 else 1
    if qty < 1:
        await message.answer("❌ Минимальное количество: 1.")
        return
    if step > 1 and qty % step != 0:
        await message.answer(f"❌ Количество должно быть кратно {step} (например: {step}, {step*2}, {step*3}...)")
        return
    price = category.get("price", 0)
    total_price = price * qty
    operator_name = data.get("custom_operator_name", "")
    await state.update_data(custom_quantity=qty)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💰 Оплатить с баланса ({total_price:.2f}$)",
            callback_data=f"confirm_custom_buy_{category_id}"
        )],
        [InlineKeyboardButton(
            text=f"💳 Оплатить CryptoBot ({total_price:.2f}$)",
            callback_data=f"crypto_custom_buy_{category_id}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")],
    ])
    await message.answer(
        f"📝 <b>Подтверждение заказа</b>\n\n"
        f"📂 Категория: Любой другой\n"
        f"🏢 Оператор: <b>{operator_name}</b>\n"
        f"📊 Количество: <b>{qty} подп.</b>\n"
        f"💵 Итого: <b>{total_price:.2f}$</b>\n\n"
        f"⚠️ Аккаунт будет закреплён за вами на 72ч.\n"
        f"Вы сможете использовать подписи по одной.\n\n"
        f"Подтвердите покупку:",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_custom_buy_"))
async def confirm_custom_buy(callback: CallbackQuery, state: FSMContext):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен. Покупки временно недоступны.", show_alert=True)
        return

    data = await state.get_data()
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return

    custom_operator_name = data.get("custom_operator_name", "")
    qty = data.get("custom_quantity", 1)

    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer(
                    "🔒 Для продолжения необходимо пополнить депозит.\n"
                    "Вы можете это сделать в разделе «Профиль».",
                    show_alert=True,
                )
                return

    price = category.get("price", 0)
    total_price = price * qty

    if total_price > 0:
        user = await get_user(callback.from_user.id)
        if not user or user.get("balance", 0) < total_price:
            await callback.answer(
                f"❌ Недостаточно средств. Нужно: {total_price:.2f}$. Пополните баланс.",
                show_alert=True,
            )
            return
        await update_balance(callback.from_user.id, -total_price)

    allocations = await try_reserve_accounts_multi(category_id, callback.from_user.id, qty)
    if not allocations:
        order_id = await create_preorder(callback.from_user.id, category_id, total_price, qty, custom_operator_name)
        await state.clear()
        await callback.message.edit_text(
            f"⏳ <b>Предзаказ #{order_id} оформлен!</b>\n\n"
            f"📂 Категория: Любой другой\n"
            f"🏢 Оператор: <b>{custom_operator_name}</b>\n"
            f"📊 Подписей: {qty}\n"
            f"💰 Сумма: {total_price:.2f}$\n\n"
            f"⏰ Сейчас нет свободных аккаунтов.\n"
            f"Как только аккаунт появится — заказ будет выполнен автоматически и вы получите уведомление.",
            reply_markup=go_to_orders_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    orders_created = []
    for alloc in allocations:
        alloc_qty = alloc["batch_size"]
        alloc_price = price * alloc_qty
        oid = await create_order(callback.from_user.id, alloc["id"], category_id, alloc_price, alloc_qty, custom_operator_name)
        o = await get_order(oid)
        orders_created.append((o, alloc))

    await state.clear()

    if len(orders_created) == 1:
        order, account = orders_created[0]
        await callback.message.edit_text(
            f"✅ <b>Заказ #{order['id']} оформлен!</b>\n\n"
            f"📂 Категория: Любой другой\n"
            f"🏢 Оператор: <b>{custom_operator_name}</b>\n"
            f"📊 Оплачено подписей: {account['batch_size']}\n"
            f"💰 Сумма: {total_price:.2f}$\n\n"
            f"📱 Телефон: <code>{account['phone']}</code>\n\n"
            f"Аккаунт закреплён за вами на 72ч.\n"
            f"Вы можете использовать подписи по одной.\n\n"
            f"📝 Нажмите «Получить подпись» в заказе, чтобы начать.",
            reply_markup=order_detail_kb(order),
            parse_mode="HTML",
        )
    else:
        lines = [f"✅ <b>Оформлено {len(orders_created)} заказов!</b>\n"]
        lines.append(f"📂 Категория: Любой другой")
        lines.append(f"🏢 Оператор: <b>{custom_operator_name}</b>")
        lines.append(f"📊 Всего подписей: {qty}")
        lines.append(f"💰 Сумма: {total_price:.2f}$\n")
        lines.append("📋 <b>Ваши заказы:</b>\n")
        for order, alloc in orders_created:
            lines.append(
                f"📦 Заказ #{order['id']} — {alloc['batch_size']} подп. — "
                f"<code>{alloc['phone']}</code>"
            )
        lines.append(
            "\n⚠️ Подписи распределены по нескольким аккаунтам.\n"
            "Работайте с каждым заказом по очереди.\n"
            "Откройте заказ в разделе «📋 Мои заказы»."
        )
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=go_to_orders_kb(),
            parse_mode="HTML",
        )
    await callback.answer()

    try:
        from src.bot.instance import bot
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        for order, alloc in orders_created:
            notify_text = format_order_card_admin(order, user_name)
            for admin_id in await get_admin_ids():
                notify_enabled = await is_admin_notifications_enabled(admin_id)
                if notify_enabled:
                    try:
                        await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
            op_ids = await get_target_operator_ids(order.get("account_id"))
            for op_id in op_ids:
                try:
                    await bot.send_message(op_id, notify_text, parse_mode="HTML")
                except Exception:
                    pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("qty_select_"))
async def qty_select(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    category_id = int(parts[2])
    qty = int(parts[3])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    if qty < min_order:
        await callback.answer(f"❌ Минимальное количество: {min_order}", show_alert=True)
        return
    count = await get_available_count(category_id)
    if count < qty:
        await callback.answer(f"❌ Недостаточно подписей. Доступно: {count}", show_alert=True)
        return
    price = category.get("price", 0)
    total = price * qty
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    multi_text = "Вы сможете использовать подписи по одной.\n\n" if qty > 1 else ""
    text = (
        f"{emoji} <b>{category['name']}</b>\n\n"
        f"📊 Количество: {qty} подп.\n"
        f"💰 Цена за подпись: {price:.2f}$\n"
        f"💵 Итого: {total:.2f}$\n\n"
        f"⚠️ Аккаунт будет закреплён за вами на 72ч.\n"
        f"{multi_text}"
        f"Подтвердите покупку:"
    )
    await state.update_data(buy_qty=qty)
    await callback.message.edit_text(
        text,
        reply_markup=confirm_buy_kb(category_id, total, qty),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("custom_qty_"))
async def custom_qty_start(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    count = await get_available_count(category_id)
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    price = category.get("price", 0)
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    step = min_order if min_order > 1 else 1
    step_hint = f"\n📐 Шаг: кратно {step} ({step}, {step*2}, {step*3}...)" if step > 1 else ""
    await state.update_data(category_id=category_id)
    await state.set_state(OrderStates.waiting_custom_qty)
    await callback.message.edit_text(
        f"{emoji} <b>{category['name']}</b>\n\n"
        f"📊 Доступно: {count} подп.\n"
        f"💰 Цена за подпись: {price:.2f}$\n"
        f"📦 Минимум: {min_order} подп.{step_hint}\n\n"
        f"✏️ Введите нужное количество подписей:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(OrderStates.waiting_custom_qty)
async def process_custom_qty(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ Введите число.")
        return
    qty = int(text)
    data = await state.get_data()
    category_id = data["category_id"]
    category = await get_category(category_id)
    if not category:
        await message.answer("❌ Категория не найдена.")
        await state.clear()
        return
    max_sigs = category.get("max_signatures", 1)
    min_order = category.get("min_order") or max_sigs
    step = min_order if min_order > 1 else 1
    if qty < min_order:
        await message.answer(f"❌ Минимальное количество: {min_order}")
        return
    if step > 1 and qty % step != 0:
        await message.answer(f"❌ Количество должно быть кратно {step} (например: {step}, {step*2}, {step*3}...)")
        return
    count = await get_available_count(category_id)
    if count < qty:
        await message.answer(f"❌ Недостаточно подписей. Доступно: {count}")
        return
    price = category.get("price", 0)
    total = price * qty
    emoji = CATEGORY_EMOJI.get(category["name"], "⚪️")
    multi_text = "Вы сможете использовать подписи по одной.\n\n" if qty > 1 else ""
    await state.update_data(buy_qty=qty)
    await state.set_state(None)
    await message.answer(
        f"{emoji} <b>{category['name']}</b>\n\n"
        f"📊 Количество: {qty} подп.\n"
        f"💰 Цена за подпись: {price:.2f}$\n"
        f"💵 Итого: {total:.2f}$\n\n"
        f"⚠️ Аккаунт будет закреплён за вами на 72ч.\n"
        f"{multi_text}"
        f"Подтвердите покупку:",
        reply_markup=confirm_buy_kb(category_id, total, qty),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bb_select_"))
async def bb_select(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    available = await get_available_count(category_id)
    if available < 1:
        await callback.answer("❌ Нет доступных аккаунтов", show_alert=True)
        return
    bb_price = category.get("bb_price")
    if not bb_price:
        await callback.answer("❌ Тариф ББ недоступен", show_alert=True)
        return
    max_sigs = category.get("max_signatures", 1)
    name = category["name"]
    emoji = CATEGORY_EMOJI.get(name, "⚪️")
    max_packs = min(available, 10)
    text = (
        f"<b>ТАРИФ БЕЗ БЛОКИРОВОК🔥</b>\n\n"
        f"{emoji} {name} {bb_price:.2f}$ за пачку\n\n"
        f"1 пачка = 1 аккаунт с полным набором ({max_sigs}х) подписей.\n\n"
        f"Тем самым вы можете подписать нужное себе количество от 2х до {max_sigs}х, "
        f"рекомендуем до 3х, во избежание Блокировок🔥\n\n"
        f"За собой мы оставляем гарантию, что оставшиеся подписи не будут проданы, "
        f"и ваши Сим-карты проживут намного дольше - чем обычно ✅\n\n"
        f"Выберите количество пачек:"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    row = []
    for i in range(1, max_packs + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"bb_qty_{category_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✏️ Своё количество", callback_data=f"bb_custom_qty_{category_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("bb_custom_qty_"))
async def bb_custom_qty_start(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    available = await get_available_count(category_id)
    await state.update_data(bb_custom_cat_id=category_id)
    await state.set_state(OrderStates.waiting_bb_custom_qty)
    await callback.message.edit_text(
        f"✏️ <b>Введите количество пачек</b>\n\n"
        f"Доступно аккаунтов: <b>{available}</b>\n"
        f"Введите число от 1 до {available}:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(OrderStates.waiting_bb_custom_qty)
async def bb_custom_qty_process(message: Message, state: FSMContext):
    data = await state.get_data()
    category_id = data.get("bb_custom_cat_id")
    if not category_id:
        await state.clear()
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) < 1:
        await message.answer("❌ Введите положительное число.")
        return
    qty = int(text)
    category = await get_category(category_id)
    if not category:
        await message.answer("❌ Категория не найдена.")
        await state.clear()
        return
    available = await get_available_count(category_id)
    if qty > available:
        await message.answer(f"❌ Доступно только {available} аккаунтов. Введите число от 1 до {available}.")
        return
    bb_price = category.get("bb_price")
    if not bb_price:
        await message.answer("❌ Тариф ББ недоступен.")
        await state.clear()
        return
    await state.clear()
    total_price = bb_price * qty
    max_sigs = category.get("max_signatures", 1)
    name = category["name"]
    emoji = CATEGORY_EMOJI.get(name, "⚪️")
    qty_label = f"{qty} пачк{'а' if qty == 1 else 'и' if 2 <= qty <= 4 else 'ек'}"
    text_msg = (
        f"<b>ТАРИФ БЕЗ БЛОКИРОВОК🔥</b>\n\n"
        f"{emoji} {name}\n"
        f"📦 {qty_label} × {bb_price:.2f}$ = <b>{total_price:.2f}$</b>\n"
        f"Каждая пачка = 1 аккаунт с {max_sigs} подписями.\n\n"
        f"Выберите способ оплаты:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Оплата с баланса", callback_data=f"confirm_bb_{category_id}_{qty}")],
        [InlineKeyboardButton(text="💎 Оплата CryptoBot", callback_data=f"crypto_bb_{category_id}_{qty}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"bb_select_{category_id}")],
    ])
    await message.answer(text_msg, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("bb_qty_"))
async def bb_qty_select(callback: CallbackQuery):
    parts = callback.data.split("_")
    category_id = int(parts[2])
    qty = int(parts[3])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    bb_price = category.get("bb_price")
    if not bb_price:
        await callback.answer("❌ Тариф ББ недоступен", show_alert=True)
        return
    total_price = bb_price * qty
    max_sigs = category.get("max_signatures", 1)
    name = category["name"]
    emoji = CATEGORY_EMOJI.get(name, "⚪️")
    qty_label = f"{qty} пачк{'а' if qty == 1 else 'и' if 2 <= qty <= 4 else 'ек'}"
    text = (
        f"<b>ТАРИФ БЕЗ БЛОКИРОВОК🔥</b>\n\n"
        f"{emoji} {name}\n\n"
        f"📦 {qty_label} × {bb_price:.2f}$ = <b>{total_price:.2f}$</b>\n"
        f"📊 {qty} аккаунт{'а' if 2 <= qty <= 4 else 'ов' if qty > 4 else ''} по {max_sigs} подписей\n\n"
        f"Выберите способ оплаты:"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💰 Оплатить с баланса ({total_price:.2f}$)",
            callback_data=f"confirm_bb_{category_id}_{qty}"
        )],
        [InlineKeyboardButton(
            text=f"💳 Оплатить CryptoBot ({total_price:.2f}$)",
            callback_data=f"crypto_bb_{category_id}_{qty}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"bb_select_{category_id}")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_bb_"))
async def confirm_bb(callback: CallbackQuery):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен. Покупки временно недоступны.", show_alert=True)
        return
    parts = callback.data.split("_")
    category_id = int(parts[2])
    pack_qty = int(parts[3]) if len(parts) > 3 else 1
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    bb_price = category.get("bb_price")
    if not bb_price:
        await callback.answer("❌ Тариф ББ недоступен", show_alert=True)
        return
    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer(
                    "🔒 Для продолжения необходимо пополнить депозит.\n"
                    "Вы можете это сделать в разделе «Профиль».",
                    show_alert=True,
                )
                return
    total_price = bb_price * pack_qty
    max_sigs = category.get("max_signatures", 1)
    if total_price > 0:
        user = await get_user(callback.from_user.id)
        if not user or user.get("balance", 0) < total_price:
            await callback.answer(
                f"❌ Недостаточно средств. Нужно: {total_price:.2f}$. Пополните баланс.",
                show_alert=True,
            )
            return
        await update_balance(callback.from_user.id, -total_price)
    from src.db.orders import generate_batch_group_id
    bg_id = generate_batch_group_id() if pack_qty > 1 else None
    order_ids = []
    preorder_ids = []
    try:
        for _ in range(pack_qty):
            account = await try_reserve_account_exclusive(category_id, callback.from_user.id)
            if not account:
                oid = await create_preorder(callback.from_user.id, category_id, bb_price, max_sigs, is_exclusive=True, batch_group_id=bg_id)
                preorder_ids.append(oid)
            else:
                batch_size = account.get("batch_size", max_sigs)
                oid = await create_order(
                    callback.from_user.id, account["id"], category_id,
                    bb_price, batch_size, is_exclusive=True, batch_group_id=bg_id,
                )
                order_ids.append(oid)
    except Exception:
        created_count = len(order_ids) + len(preorder_ids)
        refund = bb_price * (pack_qty - created_count)
        if refund > 0:
            await update_balance(callback.from_user.id, refund)
        if created_count == 0:
            await callback.answer("❌ Ошибка при создании заказов. Средства возвращены.", show_alert=True)
            return
    lines = []
    if order_ids:
        ids_str = ", ".join(f"#{oid}" for oid in order_ids)
        lines.append(f"✅ <b>Заказы {ids_str} оформлены! (Тариф ББ🔥)</b>")
    if preorder_ids:
        ids_str = ", ".join(f"#{oid}" for oid in preorder_ids)
        lines.append(f"⏳ <b>Предзаказы {ids_str} оформлены!</b>")
    lines.append(f"\n📂 Категория: {category['name']} (ББ)")
    lines.append(f"📦 Пачек: {pack_qty}")
    lines.append(f"💰 Сумма: {total_price:.2f}$")
    if preorder_ids:
        lines.append(f"\n⏰ Для предзаказов ожидайте — заказы будут выполнены автоматически.")
    if order_ids:
        lines.append(f"\n📝 Нажмите «📋 Мои заказы» чтобы начать работу.")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=go_to_orders_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        from src.bot.instance import bot
        from src.utils.formatters import format_bb_batch_card_admin
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        bb_orders = []
        for oid in order_ids:
            order = await get_order(oid)
            if order:
                bb_orders.append(order)
        if bb_orders:
            notify_text = format_bb_batch_card_admin(bb_orders, user_name)
            for admin_id in await get_admin_ids():
                notify_enabled = await is_admin_notifications_enabled(admin_id)
                if notify_enabled:
                    try:
                        await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
            notified_ops = set()
            for order in bb_orders:
                op_ids = await get_target_operator_ids(order.get("account_id"))
                notified_ops.update(op_ids)
            for op_id in notified_ops:
                try:
                    await bot.send_message(op_id, notify_text, parse_mode="HTML")
                except Exception:
                    pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy(callback: CallbackQuery, state: FSMContext):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен. Покупки временно недоступны.", show_alert=True)
        return

    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return

    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer(
                    "🔒 Для продолжения необходимо пополнить депозит.\n"
                    "Вы можете это сделать в разделе «Профиль».",
                    show_alert=True,
                )
                return

    price = category.get("price", 0)
    max_sigs = category.get("max_signatures", 1)
    data = await state.get_data()
    qty = data.get("buy_qty", max_sigs)
    total_price = price * qty

    if total_price > 0:
        user = await get_user(callback.from_user.id)
        if not user or user.get("balance", 0) < total_price:
            await callback.answer(
                f"❌ Недостаточно средств. Нужно: {total_price:.2f}$. Пополните баланс.",
                show_alert=True,
            )
            return
        await update_balance(callback.from_user.id, -total_price)

    allocations = await try_reserve_accounts_multi(category_id, callback.from_user.id, qty)
    if not allocations:
        order_id = await create_preorder(callback.from_user.id, category_id, total_price, qty)
        await state.clear()
        await callback.message.edit_text(
            f"⏳ <b>Предзаказ #{order_id} оформлен!</b>\n\n"
            f"📂 Категория: {category['name']}\n"
            f"📊 Подписей: {qty}\n"
            f"💰 Сумма: {total_price:.2f}$\n\n"
            f"⏰ Сейчас нет свободных аккаунтов.\n"
            f"Как только аккаунт появится — заказ будет выполнен автоматически и вы получите уведомление.",
            reply_markup=go_to_orders_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    from src.db.orders import generate_batch_group_id
    bg_id = generate_batch_group_id() if len(allocations) > 1 else None
    orders_created = []
    for alloc in allocations:
        alloc_qty = alloc["batch_size"]
        alloc_price = price * alloc_qty
        oid = await create_order(callback.from_user.id, alloc["id"], category_id, alloc_price, alloc_qty, batch_group_id=bg_id)
        o = await get_order(oid)
        orders_created.append((o, alloc))

    await state.clear()

    if len(orders_created) == 1:
        order, account = orders_created[0]
        batch_size = account["batch_size"]
        await callback.message.edit_text(
            f"✅ <b>Заказ #{order['id']} оформлен!</b>\n\n"
            f"📂 Категория: {category['name']}\n"
            f"📊 Оплачено подписей: {batch_size}\n"
            f"💰 Сумма: {total_price:.2f}$\n\n"
            f"📱 Телефон: <code>{account['phone']}</code>\n\n"
            f"Аккаунт закреплён за вами на 72ч.\n"
            f"Вы можете использовать подписи по одной.\n\n"
            f"📝 Нажмите «Получить подпись» в заказе, чтобы начать.",
            reply_markup=order_detail_kb(order),
            parse_mode="HTML",
        )
    else:
        all_orders = [o for o, _ in orders_created]
        phones_list = "\n".join(f"<code>{alloc['phone']}</code>" for _, alloc in orders_created)
        ids_str = ", ".join(f"#{o['id']}" for o in all_orders)
        lines = [
            f"✅ <b>Заказ {ids_str} оформлен!</b>\n",
            f"📂 Категория: {category['name']}",
            f"📊 Всего подписей: {qty}",
            f"💰 Сумма: {total_price:.2f}$\n",
            f"📱 Телефоны:\n{phones_list}\n",
            "Аккаунты закреплены за вами на 72ч.\n"
            "📝 Откройте заказ в «📋 Мои заказы» чтобы начать."
        ]
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=go_to_orders_kb(),
            parse_mode="HTML",
        )
    await callback.answer()

    try:
        from src.bot.instance import bot
        from src.utils.formatters import format_bb_batch_card_admin
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        all_orders = [o for o, _ in orders_created]
        if len(all_orders) > 1:
            notify_text = format_bb_batch_card_admin(all_orders, user_name)
            for admin_id in await get_admin_ids():
                notify_enabled = await is_admin_notifications_enabled(admin_id)
                if notify_enabled:
                    try:
                        await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
            notified_ops = set()
            for order in all_orders:
                op_ids = await get_target_operator_ids(order.get("account_id"))
                notified_ops.update(op_ids)
            for op_id in notified_ops:
                try:
                    await bot.send_message(op_id, notify_text, parse_mode="HTML")
                except Exception:
                    pass
        else:
            for order in all_orders:
                notify_text = format_order_card_admin(order, user_name)
                for admin_id in await get_admin_ids():
                    notify_enabled = await is_admin_notifications_enabled(admin_id)
                    if notify_enabled:
                        try:
                            await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                        except Exception:
                            pass
                op_ids = await get_target_operator_ids(order.get("account_id"))
                for op_id in op_ids:
                    try:
                        await bot.send_message(op_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
    except Exception:
        pass


async def _create_order_invoice(callback: CallbackQuery, amount: float, meta: dict):
    import json
    from src.utils.cryptobot import create_invoice
    from src.db.payments import create_payment
    from src.handlers.payment import start_payment_check

    invoice = await create_invoice(amount, f"Оплата заказа — {amount:.2f}$ USDT")
    if not invoice:
        await callback.answer("❌ Не удалось создать счёт. Попробуйте позже.", show_alert=True)
        return
    await create_payment(
        callback.from_user.id, invoice["invoice_id"], amount,
        invoice.get("bot_invoice_url", ""), purpose="order",
        payment_meta=json.dumps(meta, ensure_ascii=False),
    )
    await start_payment_check(invoice["invoice_id"])
    pay_url = invoice.get("bot_invoice_url", "")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")],
    ])
    await callback.message.edit_text(
        f"💳 <b>Счёт на оплату заказа</b>\n\n"
        f"💵 Сумма: <b>{amount:.2f} USDT</b>\n"
        f"⏰ Счёт действителен 30 минут\n\n"
        f"Нажмите кнопку ниже для оплаты.\n"
        f"После оплаты заказ оформится автоматически.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("crypto_buy_"))
async def crypto_buy(callback: CallbackQuery, state: FSMContext):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен.", show_alert=True)
        return
    parts = callback.data.split("_")
    category_id = int(parts[2])
    qty = int(parts[3])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer("🔒 Сначала пополните депозит в разделе «Профиль».", show_alert=True)
                return
    price = category.get("price", 0)
    data = await state.get_data()
    buy_qty = data.get("buy_qty", qty)
    total = price * buy_qty
    meta = {"type": "regular", "category_id": category_id, "qty": buy_qty}
    await _create_order_invoice(callback, total, meta)


@router.callback_query(F.data.startswith("crypto_custom_buy_"))
async def crypto_custom_buy(callback: CallbackQuery, state: FSMContext):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен.", show_alert=True)
        return
    data = await state.get_data()
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer("🔒 Сначала пополните депозит в разделе «Профиль».", show_alert=True)
                return
    qty = data.get("custom_quantity", 1)
    custom_op = data.get("custom_operator_name", "")
    price = category.get("price", 0)
    total = price * qty
    meta = {"type": "custom", "category_id": category_id, "qty": qty, "custom_operator_name": custom_op}
    await _create_order_invoice(callback, total, meta)


@router.callback_query(F.data.startswith("crypto_bb_"))
async def crypto_bb(callback: CallbackQuery):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен.", show_alert=True)
        return
    parts = callback.data.split("_")
    category_id = int(parts[2])
    pack_qty = int(parts[3]) if len(parts) > 3 else 1
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    bb_price = category.get("bb_price")
    if not bb_price:
        await callback.answer("❌ Тариф ББ недоступен", show_alert=True)
        return
    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer("🔒 Сначала пополните депозит в разделе «Профиль».", show_alert=True)
                return
    total_price = bb_price * pack_qty
    meta = {"type": "regular", "category_id": category_id, "qty": category.get("max_signatures", 1), "is_bb": True, "bb_pack_qty": pack_qty}
    await _create_order_invoice(callback, total_price, meta)


@router.callback_query(F.data.startswith("crypto_preorder_"))
async def crypto_preorder(callback: CallbackQuery, state: FSMContext):
    paused = await is_bot_paused()
    if paused:
        await callback.answer("⏸ Бот приостановлен.", show_alert=True)
        return
    parts = callback.data.split("_")
    category_id = int(parts[2])
    qty = int(parts[3])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    if not await is_admin(callback.from_user.id):
        deposit_needed = await get_user_effective_deposit(callback.from_user.id)
        if deposit_needed > 0:
            has_dep = await has_user_deposit(callback.from_user.id)
            if not has_dep:
                await callback.answer("🔒 Сначала пополните депозит в разделе «Профиль».", show_alert=True)
                return
    price = category.get("price", 0)
    total = price * qty
    data = await state.get_data()
    custom_op = data.get("preorder_operator_name")
    meta = {"type": "regular", "category_id": category_id, "qty": qty}
    if custom_op:
        meta["custom_operator_name"] = custom_op
        meta["type"] = "custom"
    await _create_order_invoice(callback, total, meta)


@router.callback_query(F.data.startswith("claim_signature_"))
async def claim_signature_handler(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] == "preorder":
        await callback.answer("⏳ Предзаказ ещё не выполнен. Ожидайте.", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ неактивен", show_alert=True)
        return
    expired = await is_order_expired(order_id)
    if expired:
        await callback.answer("❌ Срок заказа истёк. Подписи больше недоступны.", show_alert=True)
        return
    claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)
    remaining = total - claimed
    if remaining <= 0:
        await callback.answer("❌ Все подписи уже использованы", show_alert=True)
        return
    if remaining == 1:
        await _do_claim(callback, order_id, 1, state)
        return
    cat_name = order.get("category_name", "—")
    custom_op = order.get("custom_operator_name")
    if custom_op:
        cat_name = f"{cat_name} ({custom_op})"
    await callback.message.edit_text(
        f"📝 <b>Получение подписей</b>\n\n"
        f"📦 Заказ: #{order_id}\n"
        f"📂 Категория: {cat_name}\n"
        f"📊 Осталось подписей: <b>{remaining}</b>\n\n"
        f"Выберите, сколько подписей запросить:",
        reply_markup=claim_qty_kb(order_id, remaining),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("claim_qty_"))
async def claim_qty_handler(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    qty = int(parts[3])
    if qty < 1:
        await callback.answer("❌ Некорректное количество", show_alert=True)
        return
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ неактивен", show_alert=True)
        return
    expired = await is_order_expired(order_id)
    if expired:
        await callback.answer("❌ Срок заказа истёк.", show_alert=True)
        return
    remaining = order["total_signatures"] - order["signatures_claimed"]
    if qty > remaining:
        await callback.answer(f"❌ Доступно только {remaining} подписей", show_alert=True)
        return
    if qty == remaining:
        await callback.answer("📌 Вы запросили максимальное количество", show_alert=True)
    await _do_claim(callback, order_id, qty, state)


async def _do_claim(callback: CallbackQuery, order_id: int, qty: int, state: FSMContext):
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    await start_claim(order_id, qty)
    order = await get_order(order_id)
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, qty, order_id)
    totp_used = order.get("totp_refreshes", 0)
    await callback.message.edit_text(
        format_account_data_no_totp(order, pending_qty=qty),
        reply_markup=account_actions_kb(order_id, totp_used, totp_shown=False, signatures_claimed=order.get("signatures_claimed", 0), total_signatures=order.get("total_signatures", 1), totp_limit=totp_lim),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("get_totp_"))
async def get_totp(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] == "preorder" or not order.get("totp_secret"):
        await callback.answer("❌ TOTP недоступен для этого заказа", show_alert=True)
        return
    pending_qty = order.get("pending_claim_qty") or 0
    if pending_qty <= 0:
        await callback.answer("❌ Сначала нажмите «Получить подпись»", show_alert=True)
        return
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, pending_qty, order_id)
    totp_used = order["totp_refreshes"]
    if totp_used >= totp_lim:
        total_remaining = order["total_signatures"] - order.get("signatures_claimed", 0)
        if pending_qty < total_remaining:
            await callback.answer(
                f"❌ Лимит TOTP исчерпан.\n\nПолучите оставшиеся подписи ({total_remaining}), чтобы получить дополнительные попытки TOTP.",
                show_alert=True,
            )
        else:
            await callback.answer("❌ Лимит TOTP исчерпан.", show_alert=True)
        return
    await increment_totp_refresh(order_id)
    await callback.answer()
    order = await get_order(order_id)
    totp_used = order["totp_refreshes"]
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, pending_qty, order_id)
    kb = account_actions_kb(
        order_id, totp_used, totp_shown=True,
        signatures_claimed=order.get("signatures_claimed", 0),
        total_signatures=order.get("total_signatures", 1),
        totp_limit=totp_lim,
    )
    try:
        await callback.message.edit_text(
            format_account_data(order, totp_limit=totp_lim),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("refresh_totp_"))
async def refresh_totp(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    pending_qty = order.get("pending_claim_qty") or 0
    if pending_qty <= 0:
        await callback.answer("❌ Сначала нажмите «Получить подпись»", show_alert=True)
        return
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, pending_qty, order_id)
    totp_used = order["totp_refreshes"]
    if totp_used >= totp_lim:
        total_remaining = order["total_signatures"] - order.get("signatures_claimed", 0)
        if pending_qty < total_remaining:
            await callback.answer(
                f"❌ Лимит TOTP исчерпан.\n\nПолучите оставшиеся подписи ({total_remaining}), чтобы получить дополнительные попытки TOTP.",
                show_alert=True,
            )
        else:
            await callback.answer("❌ Лимит обновлений TOTP исчерпан.", show_alert=True)
        return
    await increment_totp_refresh(order_id)
    await callback.answer()
    order = await get_order(order_id)
    totp_used = order["totp_refreshes"]
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, pending_qty, order_id)
    kb = account_actions_kb(
        order_id, totp_used, totp_shown=True,
        signatures_claimed=order.get("signatures_claimed", 0),
        total_signatures=order.get("total_signatures", 1),
        totp_limit=totp_lim,
    )
    try:
        await callback.message.edit_text(
            format_account_data(order, totp_limit=totp_lim),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("signature_sent_"))
async def signature_sent(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    pending_qty = order.get("pending_claim_qty") or 0
    if pending_qty <= 0:
        await callback.answer("❌ Сначала нажмите «Получить подпись»", show_alert=True)
        return
    if order["totp_refreshes"] <= 0:
        await callback.answer("❌ Сначала получите TOTP код", show_alert=True)
        return
    qty_text = f"{pending_qty} подп." if pending_qty > 1 else "подпись"
    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы точно воспользовались TOTP и отправили {qty_text}?\n\n"
        f"❗ Подтверждая, вы принимаете, что если подпись фактически "
        f"не была отправлена — возврат невозможен.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, подтверждаю", callback_data=f"confirm_sig_sent_{order_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"cancel_sig_sent_{order_id}")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_sig_sent_"))
async def cancel_sig_sent(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    pending_qty = order.get("pending_claim_qty") or 0
    totp_used = order["totp_refreshes"]
    totp_lim = await _get_effective_totp_limit(callback.from_user.id, pending_qty, order_id)
    kb = account_actions_kb(
        order_id, totp_used, totp_shown=True,
        signatures_claimed=order.get("signatures_claimed", 0),
        total_signatures=order.get("total_signatures", 1),
        totp_limit=totp_lim,
    )
    try:
        await callback.message.edit_text(
            format_account_data(order, totp_limit=totp_lim),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_sig_sent_"))
async def confirm_signature_sent(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return

    pending_qty = order.get("pending_claim_qty") or 0
    if pending_qty <= 0:
        await callback.answer("❌ Сначала нажмите «Получить подпись»", show_alert=True)
        return

    if order["totp_refreshes"] <= 0:
        await callback.answer("❌ Сначала получите TOTP код", show_alert=True)
        return

    result = await claim_signature(order_id, pending_qty)
    if not result:
        await callback.answer("❌ Не удалось засчитать подпись. Попробуйте ещё раз.", show_alert=True)
        return

    await clear_pending_claim(order_id)

    order = await get_order(order_id)
    new_claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)

    qty_text = f"{pending_qty} подп." if pending_qty > 1 else ""
    claim_range_start = new_claimed - pending_qty + 1
    claim_range = f"#{claim_range_start}—#{new_claimed}" if pending_qty > 1 else f"#{new_claimed}"

    await callback.message.edit_text(
        f"✅ <b>Подпись {claim_range} отправлена!</b>\n\n"
        f"⏰ Ожидайте подтверждения оператором.\n\n"
        f"📊 Подписей использовано: {new_claimed}/{total}\n"
        f"Статус заказа можно посмотреть в разделе «📋 Мои заказы».",
        reply_markup=order_detail_kb(order),
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        from src.bot.instance import bot
        from src.keyboards.admin_kb import operator_confirm_sig_kb
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        custom_op = order.get('custom_operator_name')
        custom_line = f"🏢 Оператор: {custom_op}\n" if custom_op else ""
        cat_name = order.get('category_name', '—')
        if custom_op:
            cat_name = f"{cat_name} ({custom_op})"
        qty_line = f"🔢 Кол-во: <b>{pending_qty}</b>\n" if pending_qty > 1 else ""
        notify_text = (
            f"📝 <b>Подпись {claim_range}/{total} ожидает подтверждения</b>\n\n"
            f"👤 Клиент: @{user_name}\n"
            f"📦 Заказ: #{order_id}\n"
            f"📂 Категория: {cat_name}\n"
            f"{custom_line}"
            f"{qty_line}"
            f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n\n"
            f"Нажмите «Готово» после проверки."
        )
        kb = operator_confirm_sig_kb(order_id, new_claimed)
        for admin_id in await get_admin_ids():
            notify_enabled = await is_admin_notifications_enabled(admin_id)
            if notify_enabled:
                try:
                    await bot.send_message(admin_id, notify_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
        op_ids = await get_target_operator_ids(order.get("account_id"))
        for op_id in op_ids:
            try:
                await bot.send_message(op_id, notify_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("request_doc_"))
async def request_doc(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    claimed = order.get("signatures_claimed", 0)
    if claimed == 0:
        await callback.answer("❌ Сначала получите подпись", show_alert=True)
        return
    from src.db.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing_count = await conn.fetchval(
            "SELECT COUNT(*) FROM doc_requests WHERE order_id = $1",
            order_id
        )
    available = claimed - existing_count
    if available <= 0:
        await callback.answer(
            f"❌ Лимит запросов документов исчерпан ({claimed} из {claimed}). "
            f"По 1 документу на каждую подпись.",
            show_alert=True,
        )
        return
    if available == 1:
        await _send_doc_request(callback, order, order_id, existing_count + 1, 1, claimed)
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    row = []
    for i in range(1, available + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"doc_qty_{order_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_order_{order_id}")])
    await callback.message.edit_text(
        f"📄 <b>Запрос документов</b>\n\n"
        f"📦 Заказ: #{order_id}\n"
        f"📊 Доступно: {available} из {claimed}\n\n"
        f"Выберите количество документов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("doc_qty_"))
async def doc_qty_handler(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    qty = int(parts[3])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    claimed = order.get("signatures_claimed", 0)
    from src.db.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing_count = await conn.fetchval(
            "SELECT COUNT(*) FROM doc_requests WHERE order_id = $1",
            order_id
        )
    available = claimed - existing_count
    if qty > available:
        await callback.answer(f"❌ Доступно только {available} документов", show_alert=True)
        return
    await _send_doc_request(callback, order, order_id, existing_count + 1, qty, claimed)


async def _send_doc_request(callback, order, order_id, start_num, qty, claimed):
    from src.db.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        for i in range(qty):
            await conn.execute(
                "INSERT INTO doc_requests (order_id, signature_num) VALUES ($1, $2)",
                order_id, start_num + i
            )
    end_num = start_num + qty - 1
    if qty == 1:
        range_text = f"#{start_num}"
    else:
        range_text = f"#{start_num}—#{end_num}"
    await callback.answer(f"📄 Запрос на документы {range_text} отправлен! ({end_num}/{claimed})", show_alert=True)
    try:
        from src.bot.instance import bot
        from src.keyboards.admin_kb import operator_send_doc_kb
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        custom_op = order.get('custom_operator_name')
        custom_line = f"🏢 Оператор: {custom_op}\n" if custom_op else ""
        cat_name = order.get('category_name', '—')
        if custom_op:
            cat_name = f"{cat_name} ({custom_op})"
        qty_line = f"🔢 Кол-во: <b>{qty}</b>\n" if qty > 1 else ""
        notify_text = (
            f"📄 <b>Запрос документов</b>\n\n"
            f"👤 Клиент: @{user_name}\n"
            f"📦 Заказ: #{order_id}\n"
            f"📂 Категория: {cat_name}\n"
            f"{custom_line}"
            f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n"
            f"{qty_line}"
            f"📊 Документы: {range_text} из {claimed}\n\n"
            f"Отправьте {qty} скриншот(ов) подтверждения."
        )
        kb = operator_send_doc_kb(order_id, start_num, qty)
        op_ids = await get_target_operator_ids(order.get("account_id"))
        for op_id in op_ids:
            try:
                await bot.send_message(op_id, notify_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
        for admin_id in await get_admin_ids():
            notify_enabled = await is_admin_notifications_enabled(admin_id)
            if notify_enabled:
                try:
                    await bot.send_message(admin_id, notify_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
    except Exception:
        pass


@router.callback_query(F.data.startswith("totp_ticket_"))
async def totp_ticket_handler(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    from src.db.tickets import create_ticket, can_create_ticket_for_order, check_daily_ticket_limit
    daily_ok = await check_daily_ticket_limit(callback.from_user.id)
    if not daily_ok:
        await callback.answer(
            "❌ Вы достигли дневного лимита обращений. Попробуйте завтра.",
            show_alert=True,
        )
        return
    can_create = await can_create_ticket_for_order(callback.from_user.id, order_id, "totp_limit")
    if not can_create:
        await callback.answer(
            "📩 Вы уже отправляли обращение по TOTP для этого заказа. Ожидайте ответа.",
            show_alert=True,
        )
        return
    cat_name = order.get("category_name", "—")
    custom_op = order.get("custom_operator_name")
    if custom_op:
        cat_name = f"{cat_name} ({custom_op})"
    subject = f"TOTP лимит — Заказ #{order_id} ({cat_name})"
    ticket_id = await create_ticket(callback.from_user.id, subject, order_id)
    await callback.message.edit_text(
        f"📩 <b>Обращение #{ticket_id} создано!</b>\n\n"
        f"📦 Заказ: #{order_id}\n"
        f"📂 Категория: {cat_name}\n"
        f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n\n"
        f"Лимит TOTP исчерпан. Администратор получил ваше обращение "
        f"и свяжется с вами в ближайшее время.\n\n"
        f"Статус обращения можно отслеживать в разделе «❓ Помощь».",
        reply_markup=order_detail_kb(order),
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        from src.bot.instance import bot
        user_name = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)
        notify_text = (
            f"📩 <b>Обращение #{ticket_id} — TOTP лимит</b>\n\n"
            f"👤 Клиент: @{user_name}\n"
            f"📦 Заказ: #{order_id}\n"
            f"📂 Категория: {cat_name}\n"
            f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n\n"
            f"Клиент исчерпал лимит TOTP и просит помощь."
        )
        for admin_id in await get_admin_ids():
            try:
                await bot.send_message(admin_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
        op_ids = await get_target_operator_ids(order.get("account_id"))
        for op_id in op_ids:
            try:
                await bot.send_message(op_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass
