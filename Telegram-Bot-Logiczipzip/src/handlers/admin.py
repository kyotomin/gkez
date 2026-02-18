import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

from src.db.admins import get_admin_ids, add_admin, remove_admin, is_admin, is_owner, get_all_admins, get_admin_stats
from datetime import datetime, timedelta
import re
import asyncio
from src.states.admin_states import (
    AdminCategoryStates, AdminAccountStates, AdminTicketStates,
    AdminBalanceStates, AdminDepositStates, AdminOperatorStates,
    AdminUserStates, AdminBroadcastStates, AdminPreorderStates,
    AdminPauseStates, AdminReputationStates, AdminFaqStates,
    AdminTicketLimitStates, AdminReviewBonusStates, AdminStatsStates, AdminReferralStates,
    AdminWithdrawDepositStates, AdminMassDeleteStates, AdminBulkAssignStates,
    AdminChannelStates, AdminAdminStates, AdminOrderTotpStates,
    AdminEnableAccountsStates, AdminMassEnableStates, AdminMassDisableStates,
    AdminOrderSearchStates, AdminOrderScreenshotStates, AdminReduceSignaturesStates,
)
from src.db.categories import (
    get_all_categories, get_category, create_category, delete_category,
    rename_category, update_category_price, toggle_category_status,
    update_category_max_signatures,
)
from src.db.accounts import (
    get_all_accounts, get_account, delete_account, parse_accounts_text,
    bulk_add_accounts, search_accounts_by_phone, get_account_signatures,
    get_total_accounts_count, update_account_signature_max, set_account_priority,
    bulk_update_all_signature_max, reset_account_availability, reset_all_accounts_availability,
    assign_operator_to_account, bulk_assign_operator, get_accounts_availability, get_stats_by_date,
    get_accounts_availability_all, get_accounts_availability_by_date,
    find_accounts_by_phones, mass_delete_accounts, update_account_used_signatures,
    get_sales_stats_by_period, assign_operator_to_latest, set_mass_priority_by_operator,
    toggle_account_enabled, enable_accounts_by_ids, enable_accounts_by_phones,
    mass_enable_all_accounts, mass_disable_all_accounts,
    mass_enable_by_phones, mass_disable_by_phones, get_accounts_count_by_status,
    get_accounts_availability_by_phones, get_availability_summary,
    update_account_totp,
)
from src.db.orders import get_all_orders, get_order, update_order_status, get_preorders_with_users, cancel_preorder, get_user_orders, set_order_totp_limit, get_order_totp_limit, compute_effective_totp_limit, reduce_order_signatures, reset_totp_refreshes, search_orders
from src.db.tickets import get_all_tickets, get_ticket, get_ticket_messages, add_ticket_message, close_ticket, search_tickets
from src.db.users import (
    get_user, get_user_by_username, update_balance, get_all_users,
    block_user, unblock_user, set_user_custom_deposit, get_user_order_count,
    get_total_spent, get_user_totp_limit, set_user_totp_limit,
)
from src.db.settings import get_deposit_amount, set_deposit_amount, has_user_deposit, get_user_deposit_amount, is_bot_paused, set_bot_paused, get_totp_limit, set_totp_limit, get_ticket_limit, set_ticket_limit, get_review_bonus, set_review_bonus, delete_user_deposit, has_actual_deposit, is_deposit_required
from src.db.database import get_pool
from src.keyboards.admin_kb import (
    admin_menu_kb, admin_categories_kb, admin_category_detail_kb,
    admin_accounts_menu_kb, admin_accounts_list_kb, admin_account_detail_kb,
    admin_orders_kb, admin_order_detail_kb, admin_batch_group_detail_kb, admin_tickets_kb,
    admin_ticket_detail_kb, admin_confirm_delete_kb,
    admin_operators_kb, admin_operator_detail_kb, operator_tickets_kb,
    admin_account_sigs_kb, admin_users_menu_kb, admin_users_list_kb,
    admin_user_detail_kb, admin_preorders_kb, admin_preorder_detail_kb,
    admin_reputation_kb, admin_reputation_detail_kb,
    admin_reviews_kb, admin_review_detail_kb,
    admin_availability_kb, admin_stats_menu_kb, admin_stats_date_kb,
    admin_sales_period_kb, admin_channels_kb, admin_channel_detail_kb,
)
from src.db.operators import add_operator, remove_operator, get_all_operators, is_operator, update_operator_role, get_operator, toggle_operator_notifications
from src.db.reputation import get_all_reputation_links, get_reputation_link, add_reputation_link, update_reputation_link, delete_reputation_link
from src.db.reviews import get_all_reviews, get_review, delete_review
from src.db.settings import is_admin_notifications_enabled, set_admin_notifications, get_faq_text, set_faq_text
from src.db.documents import get_pending_doc_requests, get_order_doc_count, get_order_documents
from src.utils.formatters import format_order_status, get_category_emoji

router = Router()


async def _admin_order_kb(order: dict):
    pending = await get_pending_doc_requests(order["id"])
    doc_count = await get_order_doc_count(order["id"])
    return admin_order_detail_kb(order, pending_docs=pending, doc_count=doc_count)


class AdminFilter:
    @staticmethod
    async def check(user_id: int) -> bool:
        return await is_admin(user_id)

    @staticmethod
    async def check_staff(user_id: int) -> bool:
        if await is_admin(user_id):
            return True
        return await is_operator(user_id)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    await state.clear()
    paused = await is_bot_paused()
    owner = await is_owner(message.from_user.id)
    status = "⏸ Приостановлен" if paused else "✅ В работе"
    await message.answer(
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"📌 Статус бота: {status}\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu_kb(paused, show_admin_mgmt=owner),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    paused = await is_bot_paused()
    owner = await is_owner(callback.from_user.id)
    status = "⏸ Приостановлен" if paused else "✅ В работе"
    try:
        await callback.message.edit_text(
            f"⚙️ <b>Панель администратора</b>\n\n"
            f"📌 Статус бота: {status}\n\n"
            "Выберите раздел:",
            reply_markup=admin_menu_kb(paused, show_admin_mgmt=owner),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_categories")
async def admin_categories(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    categories = await get_all_categories()
    await callback.message.edit_text(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_category")
async def admin_add_category(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📝 Введите название новой категории:",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_name)
    await callback.answer()


@router.message(AdminCategoryStates.waiting_name)
async def process_category_name(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    await state.update_data(cat_name=message.text.strip())
    await message.answer(
        "💲 Введите <b>цену за подпись</b> в USD (например: 3.50):",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_price)


@router.message(AdminCategoryStates.waiting_price)
async def process_category_price(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        price = float(message.text.strip().replace(",", "."))
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену (число >= 0).")
        return
    await state.update_data(cat_price=price)
    await message.answer(
        "📊 Введите <b>макс. подписей на аккаунт</b> для этой категории (число):",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_max_sigs)


@router.message(AdminCategoryStates.waiting_max_sigs)
async def process_category_max_sigs(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        max_sigs = int(message.text.strip())
        if max_sigs <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число > 0.")
        return
    data = await state.get_data()
    try:
        await create_category(data["cat_name"], data["cat_price"], max_sigs)
        await message.answer(
            f"✅ Категория «{data['cat_name']}» создана!\n"
            f"💲 Цена: {data['cat_price']:.2f}$\n"
            f"📊 Подписей/аккаунт: {max_sigs}",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer("❌ Категория с таким именем уже существует.", parse_mode="HTML")
    await state.clear()
    categories = await get_all_categories()
    await message.answer(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_cat_") & ~F.data.startswith("admin_cat_accounts_") & ~F.data.startswith("admin_cat_bb_price_"))
async def admin_category_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    status = "✅ Активна" if category.get("is_active", 1) else "❌ Отключена"
    bb_line = f"💰 Цена ББ: {category['bb_price']:.2f}$\n" if category.get("bb_price") else ""
    await callback.message.edit_text(
        f"📂 <b>{category['name']}</b>\n\n"
        f"💰 Цена: {category['price']:.2f}$\n"
        f"{bb_line}"
        f"📊 Подписей/аккаунт: {category.get('max_signatures', 5)}\n"
        f"📌 Статус: {status}",
        reply_markup=admin_category_detail_kb(category_id, has_bb_price=category.get("bb_price") is not None),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_price_"))
async def admin_set_price(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    await state.update_data(price_cat_id=category_id)
    await callback.message.edit_text(
        "💲 Введите новую <b>цену за подпись</b> в USD:",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_new_price)
    await callback.answer()


@router.message(AdminCategoryStates.waiting_new_price)
async def process_new_price(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        price = float(message.text.strip().replace(",", "."))
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену.")
        return
    data = await state.get_data()
    await update_category_price(data["price_cat_id"], price)
    await state.clear()
    await message.answer(f"✅ Цена обновлена: {price:.2f}$", parse_mode="HTML")
    categories = await get_all_categories()
    await message.answer(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_rename_cat_"))
async def admin_rename_cat(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    await state.update_data(rename_cat_id=category_id)
    await callback.message.edit_text(
        "✏️ Введите новое название категории:",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_rename)
    await callback.answer()


@router.message(AdminCategoryStates.waiting_rename)
async def process_rename_category(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    category_id = data["rename_cat_id"]
    await rename_category(category_id, message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ Категория переименована в «{message.text.strip()}»",
        parse_mode="HTML",
    )
    categories = await get_all_categories()
    await message.answer(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_toggle_cat_"))
async def admin_toggle_category(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    new_status = await toggle_category_status(category_id)
    status_text = "✅ включена" if new_status else "❌ отключена"
    await callback.answer(f"Категория {status_text}", show_alert=True)
    category = await get_category(category_id)
    status = "✅ Активна" if category.get("is_active", 1) else "❌ Отключена"
    bb_line = f"💰 Цена ББ: {category['bb_price']:.2f}$\n" if category.get("bb_price") else ""
    await callback.message.edit_text(
        f"📂 <b>{category['name']}</b>\n\n"
        f"💰 Цена: {category['price']:.2f}$\n"
        f"{bb_line}"
        f"📊 Подписей/аккаунт: {category.get('max_signatures', 5)}\n"
        f"📌 Статус: {status}",
        reply_markup=admin_category_detail_kb(category_id, has_bb_price=category.get("bb_price") is not None),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_set_max_sigs_"))
async def admin_set_max_sigs(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    await state.update_data(edit_cat_id=category_id)
    await callback.message.edit_text(
        f"📊 <b>Лимит подписей для: {category['name']}</b>\n\n"
        f"Текущий лимит: {category.get('max_signatures', 5)}\n\n"
        f"Введите новый лимит (1-100):",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_new_max_sigs)
    await callback.answer()


@router.message(AdminCategoryStates.waiting_new_max_sigs)
async def process_new_max_sigs(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) < 1 or int(text) > 100:
        await message.answer("❌ Введите число от 1 до 100.")
        return
    data = await state.get_data()
    cat_id = data["edit_cat_id"]
    new_max = int(text)
    await update_category_max_signatures(cat_id, new_max)
    await state.clear()
    category = await get_category(cat_id)
    status = "✅ Активна" if category.get("is_active", 1) else "❌ Отключена"
    await message.answer(
        f"✅ Лимит подписей обновлён: {new_max}\n\n"
        f"📂 <b>{category['name']}</b>\n\n"
        f"💰 Цена: {category['price']:.2f}$\n"
        f"📊 Подписей/аккаунт: {new_max}\n"
        f"📌 Статус: {status}",
        reply_markup=admin_category_detail_kb(cat_id, has_bb_price=category.get("bb_price") is not None),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_del_cat_"))
async def admin_delete_cat_confirm(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    await callback.message.edit_text(
        f"🗑 Вы уверены, что хотите удалить категорию «{category['name']}»?\n\n"
        f"⚠️ Все данные подписей по этой категории будут удалены!",
        reply_markup=admin_confirm_delete_kb("cat", category_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_del_cat_"))
async def admin_confirm_delete_cat(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    await delete_category(category_id)
    await callback.answer("✅ Категория удалена", show_alert=True)
    categories = await get_all_categories()
    await callback.message.edit_text(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_accounts")
async def admin_accounts_menu(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    total = await get_total_accounts_count()
    await callback.message.edit_text(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_accounts")
async def admin_add_accounts(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📝 <b>Добавление аккаунтов</b>\n\n"
        "Формат 1 (в строку):\n"
        "<code>1. 89567689900 qwerty124 TOTP_SECRET</code>\n"
        "<code>2. 89567689900 qwerty124 TOTP_SECRET</code>\n\n"
        "Формат 2 (из Excel):\n"
        "<code>1\n9053533283\nPompa65!\n3WU6ES3TYAU2YBK6GC2AJLR5A7MTQGT6</code>\n\n"
        "<code>2\n9053532725\nPompa65!\n46MTPWLJKDTKWVQ4BCDSHBISL5MEUOPC</code>\n\n"
        "Каждый аккаунт будет распределён на все категории.",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_bulk_data)
    await callback.answer()


@router.message(AdminAccountStates.waiting_bulk_data)
async def process_bulk_accounts(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    accounts_data = parse_accounts_text(message.text)
    if not accounts_data:
        await message.answer(
            "❌ Не удалось распознать ни одного аккаунта.\n\n"
            "Формат: <code>номер телефон пароль TOTP</code>",
            parse_mode="HTML",
        )
        return
    added, added_ids = await bulk_add_accounts(accounts_data, added_by_admin_id=message.from_user.id)
    await state.update_data(last_added_count=added, added_ids=added_ids)
    operators = await get_all_operators()
    order_ops = [op for op in operators if op.get("role") == "orders"]
    if order_ops:
        buttons = []
        for op in order_ops:
            name = op.get("username") or str(op["telegram_id"])
            buttons.append([InlineKeyboardButton(
                text=f"👷 {name}",
                callback_data=f"assign_after_add_{op['telegram_id']}",
            )])
        buttons.append([InlineKeyboardButton(text="⏩ Пропустить", callback_data="skip_assign_after_add")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(
            f"✅ Добавлено аккаунтов: <b>{added}</b> (выключены)\n\n"
            f"👷 Назначить оператора на добавленные аккаунты?",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await _show_enable_options(message, added, added_ids, state, use_answer=True)


async def _show_enable_options(target, added: int, added_ids: list[int], state: FSMContext, use_answer: bool = False):
    await state.update_data(added_ids=added_ids, last_added_count=added)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Включить все", callback_data="enable_all_added")],
        [InlineKeyboardButton(text="📋 Включить по списку", callback_data="enable_by_list_added")],
        [InlineKeyboardButton(text="⏩ Оставить выключенными", callback_data="skip_enable_added")],
    ])
    text = (
        f"✅ Добавлено аккаунтов: <b>{added}</b> (выключены)\n\n"
        f"Выберите, какие аккаунты включить:"
    )
    if use_answer:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("assign_after_add_"))
async def assign_after_add(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    op_id = int(callback.data.split("assign_after_add_")[1])
    data = await state.get_data()
    count = data.get("last_added_count", 0)
    added_ids = data.get("added_ids", [])
    if count > 0:
        assigned = await assign_operator_to_latest(op_id, count)
        op = await get_operator(op_id)
        op_name = op.get("username") or str(op_id) if op else str(op_id)
        await callback.message.edit_text(
            f"✅ Назначено <b>{assigned}</b> аккаунтов на оператора <b>{op_name}</b>",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text("❌ Нет аккаунтов для назначения.", parse_mode="HTML")
    await _show_enable_options(callback.message, count, added_ids, state, use_answer=True)
    await callback.answer()


@router.callback_query(F.data == "skip_assign_after_add")
async def skip_assign_after_add(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    count = data.get("last_added_count", 0)
    added_ids = data.get("added_ids", [])
    await _show_enable_options(callback.message, count, added_ids, state)
    await callback.answer()


@router.callback_query(F.data == "enable_all_added")
async def enable_all_added(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    added_ids = data.get("added_ids", [])
    if not added_ids:
        await state.clear()
        await callback.answer("❌ Данные о загруженных аккаунтах утеряны. Включите вручную в разделе аккаунтов.", show_alert=True)
        return
    await state.clear()
    enabled = await enable_accounts_by_ids(added_ids)
    await callback.message.edit_text(
        f"✅ Включено аккаунтов: <b>{enabled}</b>",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await callback.message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
    if enabled > 0:
        import asyncio
        from src.utils.preorders import run_preorder_fulfillment
        from src.bot.instance import get_bot
        asyncio.create_task(run_preorder_fulfillment(get_bot()))


@router.callback_query(F.data == "enable_by_list_added")
async def enable_by_list_added(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    if not data.get("added_ids"):
        await callback.answer("❌ Данные о загруженных аккаунтах утеряны. Включите вручную в разделе аккаунтов.", show_alert=True)
        return
    await state.set_state(AdminEnableAccountsStates.waiting_phone_list)
    await callback.message.edit_text(
        "📋 <b>Включение по списку</b>\n\n"
        "Отправьте номера телефонов для включения (каждый с новой строки):\n\n"
        "<code>89001234567\n89007654321\n89009876543</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminEnableAccountsStates.waiting_phone_list)
async def process_enable_phone_list(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    added_ids = data.get("added_ids", [])
    import re as _re
    raw_phones = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    phones = list(dict.fromkeys(_re.sub(r"[^\d]", "", p) for p in raw_phones if _re.sub(r"[^\d]", "", p)))
    if not phones:
        await message.answer("❌ Не удалось распознать номера. Отправьте каждый номер с новой строки.")
        return
    enabled, matched = await enable_accounts_by_phones(phones, added_ids)
    await state.clear()
    matched_norm = set(_re.sub(r"[^\d]", "", m) for m in matched)
    not_found = [p for p in phones if p not in matched_norm and not any(p.endswith(m) or m.endswith(p) for m in matched_norm)]
    text = f"✅ Включено аккаунтов: <b>{enabled}</b> из {len(phones)}"
    if not_found:
        text += f"\n\n❌ Не найдены среди загруженных:\n" + "\n".join(f"<code>{p}</code>" for p in not_found[:20])
    await message.answer(text, parse_mode="HTML")
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    if enabled > 0:
        import asyncio
        from src.utils.preorders import run_preorder_fulfillment
        from src.bot.instance import get_bot
        asyncio.create_task(run_preorder_fulfillment(get_bot()))


@router.callback_query(F.data == "skip_enable_added")
async def skip_enable_added(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    count = data.get("last_added_count", 0)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Добавлено аккаунтов: <b>{count}</b>\n\n"
        f"Все аккаунты добавлены выключенными.\n"
        f"Включить можно вручную в разделе аккаунтов.",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await callback.message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_mass_enable")
async def admin_mass_enable(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    counts = await get_accounts_count_by_status()
    await callback.message.edit_text(
        f"✅ <b>Массовое включение аккаунтов</b>\n\n"
        f"📊 Выключено: <b>{counts['disabled']}</b> | Включено: <b>{counts['enabled']}</b>\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Включить все выключенные", callback_data="mass_enable_all")],
            [InlineKeyboardButton(text="📋 Включить по списку номеров", callback_data="mass_enable_by_list")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "mass_enable_all")
async def mass_enable_all(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    enabled = await mass_enable_all_accounts()
    await callback.message.edit_text(
        f"✅ Включено аккаунтов: <b>{enabled}</b>",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await callback.message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
    if enabled > 0:
        import asyncio
        from src.utils.preorders import run_preorder_fulfillment
        from src.bot.instance import get_bot
        asyncio.create_task(run_preorder_fulfillment(get_bot()))


@router.callback_query(F.data == "mass_enable_by_list")
async def mass_enable_by_list(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminMassEnableStates.waiting_phone_list)
    await callback.message.edit_text(
        "📋 <b>Включение по списку</b>\n\n"
        "Отправьте номера телефонов для включения (каждый с новой строки):\n\n"
        "<code>89001234567\n89007654321\n89009876543</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminMassEnableStates.waiting_phone_list)
async def process_mass_enable_phone_list(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    raw_phones = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    phones = list(dict.fromkeys(re.sub(r"[^\d]", "", p) for p in raw_phones if re.sub(r"[^\d]", "", p)))
    if not phones:
        await message.answer("❌ Не удалось распознать номера. Отправьте каждый номер с новой строки.")
        return
    enabled, matched = await mass_enable_by_phones(phones)
    await state.clear()
    matched_norm = set(re.sub(r"[^\d]", "", m) for m in matched)
    not_found = [p for p in phones if p not in matched_norm and not any(p.endswith(m) or m.endswith(p) for m in matched_norm)]
    text = f"✅ Включено аккаунтов: <b>{enabled}</b> из {len(phones)}"
    if not_found:
        text += f"\n\n❌ Не найдены среди выключенных:\n" + "\n".join(f"<code>{p}</code>" for p in not_found[:20])
    await message.answer(text, parse_mode="HTML")
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    if enabled > 0:
        import asyncio
        from src.utils.preorders import run_preorder_fulfillment
        from src.bot.instance import get_bot
        asyncio.create_task(run_preorder_fulfillment(get_bot()))


@router.callback_query(F.data == "admin_mass_disable")
async def admin_mass_disable(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    counts = await get_accounts_count_by_status()
    await callback.message.edit_text(
        f"❌ <b>Массовое выключение аккаунтов</b>\n\n"
        f"📊 Включено: <b>{counts['enabled']}</b> | Выключено: <b>{counts['disabled']}</b>\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Выключить все включённые", callback_data="mass_disable_all")],
            [InlineKeyboardButton(text="📋 Выключить по списку номеров", callback_data="mass_disable_by_list")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "mass_disable_all")
async def mass_disable_all(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    disabled = await mass_disable_all_accounts()
    await callback.message.edit_text(
        f"❌ Выключено аккаунтов: <b>{disabled}</b>",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await callback.message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "mass_disable_by_list")
async def mass_disable_by_list(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminMassDisableStates.waiting_phone_list)
    await callback.message.edit_text(
        "📋 <b>Выключение по списку</b>\n\n"
        "Отправьте номера телефонов для выключения (каждый с новой строки):\n\n"
        "<code>89001234567\n89007654321\n89009876543</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminMassDisableStates.waiting_phone_list)
async def process_mass_disable_phone_list(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    raw_phones = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    phones = list(dict.fromkeys(re.sub(r"[^\d]", "", p) for p in raw_phones if re.sub(r"[^\d]", "", p)))
    if not phones:
        await message.answer("❌ Не удалось распознать номера. Отправьте каждый номер с новой строки.")
        return
    disabled, matched = await mass_disable_by_phones(phones)
    await state.clear()
    matched_norm = set(re.sub(r"[^\d]", "", m) for m in matched)
    not_found = [p for p in phones if p not in matched_norm and not any(p.endswith(m) or m.endswith(p) for m in matched_norm)]
    text = f"❌ Выключено аккаунтов: <b>{disabled}</b> из {len(phones)}"
    if not_found:
        text += f"\n\n❌ Не найдены среди включённых:\n" + "\n".join(f"<code>{p}</code>" for p in not_found[:20])
    await message.answer(text, parse_mode="HTML")
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_all_accounts")
async def admin_all_accounts(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await callback.message.edit_text(
            "📦 <b>Аккаунты</b>\n\n📭 Нет аккаунтов.",
            reply_markup=admin_accounts_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"📦 <b>Все аккаунты</b> ({len(accounts)}):",
        reply_markup=admin_accounts_list_kb(accounts),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_accs_page_"))
async def admin_accounts_page(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    page = int(callback.data.split("_")[-1])
    accounts = await get_all_accounts()
    await callback.message.edit_text(
        f"📦 <b>Все аккаунты</b> ({len(accounts)}):",
        reply_markup=admin_accounts_list_kb(accounts, page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_search_account")
async def admin_search_account(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🔍 Введите номер телефона (или часть) для поиска:",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_search_phone)
    await callback.answer()


@router.message(AdminAccountStates.waiting_search_phone)
async def process_search_account(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    phone = message.text.strip()
    accounts = await search_accounts_by_phone(phone)
    await state.clear()
    if not accounts:
        await message.answer(
            f"🔍 По запросу «{phone}» ничего не найдено.",
            parse_mode="HTML",
        )
        total = await get_total_accounts_count()
        await message.answer(
            f"📦 <b>Управление аккаунтами</b>\n\n📊 Всего аккаунтов: {total}",
            reply_markup=admin_accounts_menu_kb(),
            parse_mode="HTML",
        )
        return
    await message.answer(
        f"🔍 Найдено: {len(accounts)} аккаунт(ов)",
        reply_markup=admin_accounts_list_kb(accounts),
        parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^admin_acc_\d+$"))
async def admin_account_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    sigs = await get_account_signatures(account_id)
    sig_text = ""
    total_remaining = 0
    for s in sigs:
        max_s = s.get("max_signatures") if s.get("max_signatures") is not None else s.get("cat_max_signatures", 5)
        used = s["used_signatures"]
        remaining = max_s - used
        total_remaining += max(0, remaining)
        status = "🟢" if remaining > 0 else "🔴"
        sig_text += f"  {status} {s['category_name']}: {used}/{max_s}\n"

    pool_status = "🟢 В пуле" if total_remaining > 0 else "🔴 Исчерпан"
    is_enabled = bool(account.get("is_enabled", 1))
    enabled_status = "🟢 Включён" if is_enabled else "🔴 Отключён"
    prio = account.get("priority", 0) or 0
    op_id = account.get("operator_telegram_id")
    op_line = "├ Оператор: —\n"
    if op_id:
        op = await get_operator(op_id)
        op_name = op.get("username") or str(op_id) if op else str(op_id)
        op_line = f"├ Оператор: 👷 {op_name}\n"
    await callback.message.edit_text(
        f"📱 <b>Аккаунт #{account['id']}</b>\n\n"
        f"├ Телефон: <code>{account['phone']}</code>\n"
        f"├ Пароль: <code>{account['password']}</code>\n"
        f"├ TOTP: <code>{account['totp_secret'][:8]}...</code>\n"
        f"├ Приоритет: ⭐️ {prio}\n"
        f"{op_line}"
        f"├ Статус: {pool_status}\n"
        f"└ Доступность: {enabled_status}\n\n"
        f"📊 <b>Подписи:</b>\n{sig_text}",
        reply_markup=admin_account_detail_kb(account_id, operator_assigned=bool(op_id), is_enabled=is_enabled),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_toggle_acc_"))
async def admin_toggle_account(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("admin_toggle_acc_")[1])
    new_state = await toggle_account_enabled(account_id)
    status_text = "🟢 включён" if new_state else "🔴 отключён"
    await callback.answer(f"Аккаунт #{account_id} {status_text}", show_alert=True)
    account = await get_account(account_id)
    if not account:
        return
    sigs = await get_account_signatures(account_id)
    sig_text = ""
    total_remaining = 0
    for s in sigs:
        max_s = s.get("max_signatures") if s.get("max_signatures") is not None else s.get("cat_max_signatures", 5)
        used = s["used_signatures"]
        remaining = max_s - used
        total_remaining += max(0, remaining)
        status = "🟢" if remaining > 0 else "🔴"
        sig_text += f"  {status} {s['category_name']}: {used}/{max_s}\n"
    pool_status = "🟢 В пуле" if total_remaining > 0 else "🔴 Исчерпан"
    is_enabled = bool(account.get("is_enabled", 1))
    enabled_status = "🟢 Включён" if is_enabled else "🔴 Отключён"
    prio = account.get("priority", 0) or 0
    op_id = account.get("operator_telegram_id")
    op_line = "├ Оператор: —\n"
    if op_id:
        op = await get_operator(op_id)
        op_name = op.get("username") or str(op_id) if op else str(op_id)
        op_line = f"├ Оператор: 👷 {op_name}\n"
    await callback.message.edit_text(
        f"📱 <b>Аккаунт #{account['id']}</b>\n\n"
        f"├ Телефон: <code>{account['phone']}</code>\n"
        f"├ Пароль: <code>{account['password']}</code>\n"
        f"├ TOTP: <code>{account['totp_secret'][:8]}...</code>\n"
        f"├ Приоритет: ⭐️ {prio}\n"
        f"{op_line}"
        f"├ Статус: {pool_status}\n"
        f"└ Доступность: {enabled_status}\n\n"
        f"📊 <b>Подписи:</b>\n{sig_text}",
        reply_markup=admin_account_detail_kb(account_id, operator_assigned=bool(op_id), is_enabled=is_enabled),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_edit_totp_"))
async def admin_edit_totp_start(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("admin_edit_totp_")[1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    await state.set_state(AdminAccountStates.waiting_totp_edit)
    await state.update_data(totp_edit_account_id=account_id)
    try:
        await callback.message.edit_text(
            f"🔑 <b>Изменение TOTP для аккаунта #{account_id}</b>\n"
            f"📱 <code>{account['phone']}</code>\n\n"
            f"Текущий TOTP: <code>{account['totp_secret']}</code>\n\n"
            f"Отправьте новый TOTP-секрет:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_acc_{account_id}")],
            ]),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminAccountStates.waiting_totp_edit)
async def admin_edit_totp_process(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    account_id = data.get("totp_edit_account_id")
    if not account_id:
        await state.clear()
        return
    new_totp = message.text.strip()
    if not new_totp:
        await message.answer("❌ TOTP-секрет не может быть пустым.")
        return
    await update_account_totp(account_id, new_totp)
    await state.clear()
    await message.answer(
        f"✅ TOTP для аккаунта #{account_id} обновлён.",
        parse_mode="HTML",
    )
    account = await get_account(account_id)
    if not account:
        return
    sigs = await get_account_signatures(account_id)
    sig_text = ""
    total_remaining = 0
    for s in sigs:
        max_s = s.get("max_signatures") if s.get("max_signatures") is not None else s.get("cat_max_signatures", 5)
        used = s["used_signatures"]
        remaining = max_s - used
        total_remaining += max(0, remaining)
        status = "🟢" if remaining > 0 else "🔴"
        sig_text += f"  {status} {s['category_name']}: {used}/{max_s}\n"
    pool_status = "🟢 В пуле" if total_remaining > 0 else "🔴 Исчерпан"
    is_enabled = bool(account.get("is_enabled", 1))
    enabled_status = "🟢 Включён" if is_enabled else "🔴 Отключён"
    prio = account.get("priority", 0) or 0
    op_id = account.get("operator_telegram_id")
    op_line = "├ Оператор: —\n"
    if op_id:
        op = await get_operator(op_id)
        op_name = op.get("username") or str(op_id) if op else str(op_id)
        op_line = f"├ Оператор: 👷 {op_name}\n"
    await message.answer(
        f"📱 <b>Аккаунт #{account['id']}</b>\n\n"
        f"├ Телефон: <code>{account['phone']}</code>\n"
        f"├ Пароль: <code>{account['password']}</code>\n"
        f"├ TOTP: <code>{account['totp_secret'][:8]}...</code>\n"
        f"├ Приоритет: ⭐️ {prio}\n"
        f"{op_line}"
        f"├ Статус: {pool_status}\n"
        f"└ Доступность: {enabled_status}\n\n"
        f"📊 <b>Подписи:</b>\n{sig_text}",
        reply_markup=admin_account_detail_kb(account_id, operator_assigned=bool(op_id), is_enabled=is_enabled),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_edit_sigs_"))
async def admin_edit_sigs(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    sigs = await get_account_signatures(account_id)
    await callback.message.edit_text(
        f"✏️ <b>Изменение подписей для #{account_id}</b>\n"
        f"📱 {account['phone']}\n\n"
        f"✏️ — изменить лимит | 📊 — изменить наличие\n"
        f"Выберите категорию:",
        reply_markup=admin_account_sigs_kb(account_id, sigs),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_sig_used_"))
async def admin_sig_used_edit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    account_id = int(parts[3])
    category_id = int(parts[4])
    sigs = await get_account_signatures(account_id)
    current_sig = None
    for s in sigs:
        if s["category_id"] == category_id:
            current_sig = s
            break
    max_s = current_sig.get("max_signatures") if current_sig and current_sig.get("max_signatures") is not None else (current_sig.get("cat_max_signatures", 5) if current_sig else 5)
    used = current_sig["used_signatures"] if current_sig else 0
    remaining = max(max_s - used, 0)
    cat_name = current_sig["category_name"] if current_sig else "?"
    await state.update_data(sig_used_account_id=account_id, sig_used_category_id=category_id, sig_used_max=max_s)
    await callback.message.edit_text(
        f"📊 <b>Изменение наличия</b>\n\n"
        f"📂 Категория: <b>{cat_name}</b>\n"
        f"📊 Макс. подписей: {max_s}\n"
        f"📊 Использовано: {used}\n"
        f"📦 Доступно для продажи: {remaining}\n\n"
        f"Введите новое значение <b>использованных</b> подписей (от 0 до {max_s}):\n\n"
        f"💡 Если поставите меньше макс. — аккаунт станет доступен для покупки.",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_sig_used_value)
    await callback.answer()


@router.message(AdminAccountStates.waiting_sig_used_value)
async def process_sig_used_value(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    max_s = data.get("sig_used_max", 999)
    try:
        new_used = int(message.text.strip())
        if new_used < 0 or new_used > max_s:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ Введите число от 0 до {max_s}.")
        return
    account_id = data["sig_used_account_id"]
    category_id = data["sig_used_category_id"]
    await update_account_used_signatures(account_id, category_id, new_used)
    await state.clear()
    remaining_after = max(max_s - new_used, 0)
    await message.answer(
        f"✅ Использованных подписей обновлено: {new_used}\n"
        f"📦 Доступно для продажи: {remaining_after}",
        parse_mode="HTML",
    )
    sigs = await get_account_signatures(account_id)
    account = await get_account(account_id)
    await message.answer(
        f"✏️ <b>Изменение подписей для #{account_id}</b>\n"
        f"📱 {account['phone']}\n\n"
        f"✏️ — изменить лимит | 📊 — изменить наличие\n"
        f"Выберите категорию:",
        reply_markup=admin_account_sigs_kb(account_id, sigs),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_sig_"))
async def admin_sig_edit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    account_id = int(parts[2])
    category_id = int(parts[3])
    await state.update_data(sig_account_id=account_id, sig_category_id=category_id)
    await callback.message.edit_text(
        "✏️ Введите новое <b>макс. количество подписей</b> для этого аккаунта в этой категории:",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_sig_value)
    await callback.answer()


@router.message(AdminAccountStates.waiting_sig_value)
async def process_sig_value(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        new_max = int(message.text.strip())
        if new_max < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число >= 0.")
        return
    data = await state.get_data()
    account_id = data["sig_account_id"]
    category_id = data["sig_category_id"]
    await update_account_signature_max(account_id, category_id, new_max)
    await state.clear()
    sigs_check = await get_account_signatures(account_id)
    actual_used = 0
    for sc in sigs_check:
        if sc["category_id"] == category_id:
            actual_used = sc["used_signatures"]
            break
    remaining_after = max(new_max - actual_used, 0)
    await message.answer(
        f"✅ Макс. подписей обновлено: {new_max}\n"
        f"📊 Использовано: {actual_used}\n"
        f"📦 Доступно для продажи: {remaining_after}",
        parse_mode="HTML",
    )
    sigs = await get_account_signatures(account_id)
    account = await get_account(account_id)
    await message.answer(
        f"✏️ <b>Изменение подписей для #{account_id}</b>\n"
        f"📱 {account['phone']}\n\n"
        f"Выберите категорию для изменения:",
        reply_markup=admin_account_sigs_kb(account_id, sigs),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_set_prio_"))
async def admin_set_priority(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    current_prio = account.get("priority", 0) or 0
    await state.update_data(prio_account_id=account_id)
    await callback.message.edit_text(
        f"⭐️ <b>Приоритет аккаунта #{account_id}</b>\n"
        f"📱 {account['phone']}\n\n"
        f"Текущий приоритет: {current_prio}\n\n"
        f"Чем выше число — тем раньше аккаунт выдаётся.\n"
        f"Введите новый приоритет (0-100):",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_priority)
    await callback.answer()


@router.message(AdminAccountStates.waiting_priority)
async def process_priority(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) > 100:
        await message.answer("❌ Введите число от 0 до 100.")
        return
    data = await state.get_data()
    account_id = data["prio_account_id"]
    priority = int(text)
    await set_account_priority(account_id, priority)
    await state.clear()
    await message.answer(
        f"✅ Приоритет аккаунта #{account_id} установлен: {priority}",
        reply_markup=admin_account_detail_kb(account_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_del_acc_"))
async def admin_delete_account_confirm(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 Удалить аккаунт <code>{account['phone']}</code>?",
        reply_markup=admin_confirm_delete_kb("acc", account_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_del_acc_"))
async def admin_confirm_delete_account(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    try:
        await delete_account(account_id)
        await callback.answer("✅ Аккаунт удалён", show_alert=True)
    except Exception:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)
    total = await get_total_accounts_count()
    await callback.message.edit_text(
        f"📦 <b>Управление аккаунтами</b>\n\n📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_users")
async def admin_users_menu(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>",
        reply_markup=admin_users_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_all_users")
async def admin_all_users(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    users = await get_all_users()
    if not users:
        await callback.message.edit_text(
            "👥 <b>Пользователи</b>\n\n📭 Нет пользователей.",
            reply_markup=admin_users_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"👥 <b>Все пользователи</b> ({len(users)}):",
        reply_markup=admin_users_list_kb(users),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    page = int(callback.data.split("_")[-1])
    users = await get_all_users()
    await callback.message.edit_text(
        f"👥 <b>Все пользователи</b> ({len(users)}):",
        reply_markup=admin_users_list_kb(users, page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_search_user")
async def admin_search_user(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🔍 Введите Telegram ID или @username пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminUserStates.waiting_search)
    await callback.answer()


@router.message(AdminUserStates.waiting_search)
async def process_search_user(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip()
    user = None
    if text.startswith("@"):
        user = await get_user_by_username(text)
    else:
        try:
            tid = int(text)
            user = await get_user(tid)
        except ValueError:
            user = await get_user_by_username(text)
    await state.clear()
    if not user:
        await message.answer(
            "❌ Пользователь не найден.",
            parse_mode="HTML",
        )
        await message.answer(
            "👥 <b>Управление пользователями</b>",
            reply_markup=admin_users_menu_kb(),
            parse_mode="HTML",
        )
        return
    await _send_user_profile(message, user)


async def _send_user_profile(target, user: dict, edit: bool = False):
    from src.db.users import get_admin_user_profile_data
    data = await get_admin_user_profile_data(user["telegram_id"])
    if not data:
        return
    order_count = data["order_count"]
    total_spent = float(data["total_spent"])
    actual_dep = data["has_deposit"]
    dep_paid = float(data["deposit_paid"] or 0)
    dep_required = (data["effective_deposit"] or 0) > 0
    has_dep = not dep_required or actual_dep
    blocked_text = "🚫 Заблокирован" if data.get("is_blocked") else "✅ Активен"
    name = data.get("username") or data.get("full_name") or "—"
    custom_dep = data.get("custom_deposit")
    dep_text = f"{custom_dep:.2f}$" if custom_dep is not None else "по умолчанию"
    reg_date = data["registered_at"].strftime("%Y-%m-%d") if data.get("registered_at") else "—"
    user_totp = data.get("totp_limit")
    global_totp = data["global_totp"] or 2
    if user_totp is not None:
        totp_text = f"{user_totp}" if user_totp > 0 else "♾ Без лимита"
    else:
        totp_text = f"{global_totp} (глобальный)"

    if not dep_required:
        dep_status = "🔓 Не требуется"
    elif actual_dep:
        dep_status = f"✅ {dep_paid:.2f}$"
    else:
        dep_status = "❌ Нет"

    text = (
        f"👤 <b>Профиль пользователя</b>\n\n"
        f"🆔 ID: <code>{data['telegram_id']}</code>\n"
        f"👤 Имя: {name}\n"
        f"💰 Баланс: <b>{data.get('balance', 0):.2f}$</b>\n"
        f"📊 Статус: {blocked_text}\n"
        f"📅 Регистрация: {reg_date}\n\n"
        f"📦 Заказов: {order_count}\n"
        f"💵 Потрачено: {total_spent:.2f}$\n"
        f"🔒 Депозит оплачен: {dep_status}\n"
        f"🔒 Сумма депозита: {dep_text}\n"
        f"🔢 Лимит TOTP: {totp_text}"
    )
    if edit:
        await target.edit_text(text, reply_markup=admin_user_detail_kb(data, has_deposit=actual_dep, deposit_required=dep_required), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=admin_user_detail_kb(data, has_deposit=actual_dep, deposit_required=dep_required), parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^admin_user_\d+$"))
async def admin_user_detail(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_user_")[1])
    user = await get_user(telegram_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    await _send_user_profile(callback.message, user, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_block_user_"))
async def admin_block_user_handler(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_block_user_")[1])
    await block_user(telegram_id)
    await callback.answer("🚫 Пользователь заблокирован", show_alert=True)
    user = await get_user(telegram_id)
    await _send_user_profile(callback.message, user, edit=True)


@router.callback_query(F.data.startswith("admin_unblock_user_"))
async def admin_unblock_user_handler(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_unblock_user_")[1])
    await unblock_user(telegram_id)
    await callback.answer("✅ Пользователь разблокирован", show_alert=True)
    user = await get_user(telegram_id)
    await _send_user_profile(callback.message, user, edit=True)


@router.callback_query(F.data.startswith("admin_set_user_deposit_"))
async def admin_set_user_deposit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_set_user_deposit_")[1])
    await state.update_data(dep_user_id=telegram_id)
    await callback.message.edit_text(
        "💲 Введите сумму депозита для этого пользователя (0 = без депозита):",
        parse_mode="HTML",
    )
    await state.set_state(AdminUserStates.waiting_deposit_amount)
    await callback.answer()


@router.message(AdminUserStates.waiting_deposit_amount)
async def process_user_deposit_amount(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму >= 0.")
        return
    data = await state.get_data()
    telegram_id = data["dep_user_id"]
    await set_user_custom_deposit(telegram_id, amount)
    await state.clear()
    await message.answer(
        f"✅ Сумма депозита установлена: {amount:.2f}$",
        parse_mode="HTML",
    )
    user = await get_user(telegram_id)
    await _send_user_profile(message, user)


@router.callback_query(F.data.startswith("admin_topup_uid_"))
async def admin_topup_uid(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_topup_uid_")[1])
    await state.update_data(topup_uid=telegram_id)
    user = await get_user(telegram_id)
    name = user.get("username") or user.get("full_name") or str(telegram_id) if user else str(telegram_id)
    await callback.message.edit_text(
        f"💰 Изменение баланса для <b>{name}</b>\n"
        f"Текущий баланс: <b>{user.get('balance', 0):.2f}$</b>\n\n"
        f"Введите сумму:\n"
        f"<code>50</code> — начислить\n"
        f"<code>-50</code> — списать",
        parse_mode="HTML",
    )
    await state.set_state(AdminUserStates.waiting_topup_amount)
    await callback.answer()


@router.message(AdminUserStates.waiting_topup_amount)
async def process_user_topup_amount(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount == 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму (число != 0).")
        return
    data = await state.get_data()
    telegram_id = data["topup_uid"]
    user = await get_user(telegram_id)
    current_balance = user.get("balance", 0) if user else 0
    if amount < 0 and current_balance + amount < 0:
        await message.answer(
            f"❌ Недостаточно средств.\n"
            f"💰 Текущий баланс: {current_balance:.2f}$\n"
            f"Максимум для списания: {current_balance:.2f}$",
            parse_mode="HTML",
        )
        return
    await update_balance(telegram_id, amount)
    await state.clear()
    user = await get_user(telegram_id)
    sign = "+" if amount > 0 else ""
    action = "начислено" if amount > 0 else "списано"
    await message.answer(
        f"✅ {sign}{amount:.2f}$ {action}.\n"
        f"💰 Новый баланс: {user.get('balance', 0):.2f}$",
        parse_mode="HTML",
    )
    await _send_user_profile(message, user)
    try:
        from src.bot.instance import bot
        if amount > 0:
            notif_text = f"+{amount:.2f}$ — начислено администратором"
        else:
            notif_text = f"{amount:.2f}$ — списано администратором"
        await bot.send_message(
            telegram_id,
            f"💰 <b>Изменение баланса</b>\n\n"
            f"{notif_text}\n"
            f"Текущий баланс: {user.get('balance', 0):.2f}$",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    orders = await get_all_orders()
    if not orders:
        await callback.message.edit_text(
            "📦 <b>Заказы</b>\n\n📭 Нет заказов.",
            reply_markup=admin_orders_kb([]),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📦 <b>Заказы:</b>",
        reply_markup=admin_orders_kb(orders),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_orders_p_"))
async def admin_orders_page(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    page = int(callback.data.split("admin_orders_p_")[1])
    orders = await get_all_orders()
    if not orders:
        await callback.answer("📭 Нет заказов", show_alert=True)
        return
    await callback.message.edit_text(
        "📦 <b>Заказы:</b>",
        reply_markup=admin_orders_kb(orders, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_global_search_order")
async def admin_global_search_order(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.update_data(search_user_id=None)
    await state.set_state(AdminOrderSearchStates.waiting_order_id)
    await callback.message.edit_text(
        "🔍 <b>Поиск заказа</b>\n\n"
        "Введите:\n"
        "• <b>ID заказа</b> (например: 123 или #123)\n"
        "• <b>Telegram ID</b> пользователя\n"
        "• <b>Номер телефона</b> (полностью или часть)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_orders")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_batchp_"))
async def admin_batch_page(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    raw = callback.data.split("admin_batchp_")[1]
    bg_id, page_str = raw.rsplit("_", 1)
    page = int(page_str)
    from src.db.orders import get_batch_group_orders
    orders = await get_batch_group_orders(bg_id)
    if not orders:
        await callback.answer("❌ Группа не найдена", show_alert=True)
        return
    from src.utils.formatters import format_batch_group_status
    text = format_batch_group_status(orders)
    first = orders[0]
    user = await get_user(first["user_id"])
    user_name = ""
    if user:
        user_name = user.get("username") or user.get("full_name") or str(first["user_id"])
    text = f"👤 Пользователь: {user_name}\n\n{text}"
    await callback.message.edit_text(
        text,
        reply_markup=admin_batch_group_detail_kb(orders, bg_id, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_batch_"))
async def admin_batch_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    bg_id = callback.data.split("admin_batch_")[1]
    from src.db.orders import get_batch_group_orders
    orders = await get_batch_group_orders(bg_id)
    if not orders:
        await callback.answer("❌ Группа заказов не найдена", show_alert=True)
        return
    from src.utils.formatters import format_batch_group_status
    text = format_batch_group_status(orders)
    first = orders[0]
    user = await get_user(first["user_id"])
    user_name = ""
    if user:
        user_name = user.get("username") or user.get("full_name") or str(first["user_id"])
    text = f"👤 Пользователь: {user_name}\n\n{text}"
    await callback.message.edit_text(
        text,
        reply_markup=admin_batch_group_detail_kb(orders, bg_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order_"))
async def admin_order_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve_order(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await update_order_status(order_id, "completed")
    await callback.answer("✅ Заказ подтверждён", show_alert=True)
    order = await get_order(order_id)
    await callback.message.edit_text(
        format_order_status(order),
        reply_markup=await _admin_order_kb(order),
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import bot
        await bot.send_message(
            order["user_id"],
            f"✅ <b>Ваш заказ #{order_id} подтверждён!</b>\n\n"
            f"Спасибо за использование нашего сервиса.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_order(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await update_order_status(order_id, "rejected")
    await callback.answer("❌ Заказ отклонён", show_alert=True)
    order = await get_order(order_id)
    await callback.message.edit_text(
        format_order_status(order),
        reply_markup=await _admin_order_kb(order),
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import bot
        await bot.send_message(
            order["user_id"],
            f"❌ <b>Ваш заказ #{order_id} отклонён.</b>\n\n"
            f"Обратитесь в поддержку для уточнения причин.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reset_totp_"))
async def admin_reset_totp(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    old_val = order.get("totp_refreshes", 0)
    await reset_totp_refreshes(order_id)
    await callback.answer(f"✅ TOTP обнулён (было {old_val})", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import bot
        await bot.send_message(
            order["user_id"],
            f"🔄 <b>TOTP по заказу #{order_id} обнулён администратором.</b>\n"
            f"Вы можете снова запросить код.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_confirm_check_"))
async def admin_confirm_check(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    total = order.get("total_signatures") or 1
    current_sent = order.get("signatures_sent", 0)
    buttons = []
    row = []
    for i in range(1, total + 1):
        label = f"✅ {i}" if i <= current_sent else str(i)
        row.append(InlineKeyboardButton(text=label, callback_data=f"adm_chk_{order_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_order_{order_id}")])
    cat_name = order.get("category_name", "—")
    phone = order.get("phone", "—")
    confirmed_text = f"\n✅ Уже подтверждено: {current_sent}/{total}" if current_sent > 0 else ""
    await callback.message.edit_text(
        f"✅ <b>Подтверждение заказа #{order_id}</b>\n\n"
        f"📂 Категория: {cat_name}\n"
        f"📱 Телефон: <code>{phone}</code>{confirmed_text}\n\n"
        f"Сколько подписей подтверждено всего:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_chk_"))
async def admin_confirm_check_qty(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    parts = callback.data.split("_")
    order_id = int(parts[2])
    confirmed_qty = int(parts[3])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    total = order.get("total_signatures") or 1
    if confirmed_qty < 1 or confirmed_qty > total:
        await callback.answer("❌ Некорректное количество", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET signatures_sent = $1 WHERE id = $2",
            confirmed_qty, order_id
        )
    if confirmed_qty >= total:
        await update_order_status(order_id, "completed")
        from src.db.accounts import release_account_reservation
        account_id = order.get("account_id")
        if account_id:
            await release_account_reservation(account_id)
        await callback.answer("✅ Заказ полностью подтверждён!", show_alert=True)
        order = await get_order(order_id)
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
        try:
            from src.bot.instance import get_bot
            bot = get_bot()
            if bot:
                review_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"leave_review_{order_id}")]
                ])
                await bot.send_message(
                    order["user_id"],
                    f"✅ <b>Заказ #{order_id} полностью подтверждён!</b>\n\n"
                    f"Все {confirmed_qty} подписей проверены.\n"
                    f"Спасибо за использование нашего сервиса.",
                    reply_markup=review_kb,
                    parse_mode="HTML",
                )
        except Exception:
            pass
    else:
        await callback.answer(f"✅ Подтверждено {confirmed_qty}/{total}", show_alert=True)
        order = await get_order(order_id)
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin_early_complete_"))
async def admin_early_complete(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    await update_order_status(order_id, "completed")
    from src.db.accounts import release_account_reservation
    account_id = order.get("account_id")
    if account_id:
        await release_account_reservation(account_id)
    await callback.answer("✅ Заказ завершён досрочно", show_alert=True)
    order = await get_order(order_id)
    claimed = order.get("signatures_claimed", 0)
    total = order.get("total_signatures", 1)
    unused = total - claimed
    await callback.message.edit_text(
        format_order_status(order),
        reply_markup=await _admin_order_kb(order),
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            text = (
                f"⏹ <b>Заказ #{order_id} завершён досрочно администратором</b>\n\n"
                f"📊 Подписей использовано: {claimed}/{total}"
            )
            if unused > 0:
                text += f"\n⚠️ Неиспользованных подписей: {unused}"
            await bot.send_message(order["user_id"], text, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_cancel_order_"))
async def admin_cancel_order(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    total = order.get("total_signatures") or 1
    claimed = order.get("signatures_claimed") or 0
    unused = total - claimed
    full_refund = order.get("price_paid", 0)
    partial_refund = round(full_refund * unused / total, 2) if total > 0 else 0
    buttons = [
        [InlineKeyboardButton(text=f"💰 Полный возврат ({full_refund:.2f}$)", callback_data=f"admin_cc_full_{order_id}")],
    ]
    if partial_refund != full_refund and partial_refund > 0:
        buttons.append([InlineKeyboardButton(text=f"💸 Частичный возврат ({partial_refund:.2f}$)", callback_data=f"admin_cc_partial_{order_id}")])
    buttons.append([InlineKeyboardButton(text="🚫 Без возврата", callback_data=f"admin_cc_none_{order_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_order_{order_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text(
            f"⚠️ <b>Отмена заказа #{order_id}</b>\n\n"
            f"📊 Подписей: {total} (использовано: {claimed}, осталось: {unused})\n"
            f"💰 Полная сумма: <b>{full_refund:.2f}$</b>\n"
            f"💸 За неиспользованные: <b>{partial_refund:.2f}$</b>\n\n"
            f"Выберите тип возврата:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


async def _do_cancel_active_order(order_id: int, refund_amount: float):
    order = await get_order(order_id)
    if not order or order["status"] != "active":
        return None
    total = order.get("total_signatures") or 1
    claimed = order.get("signatures_claimed") or 0
    unused = total - claimed
    account_id = order.get("account_id")
    category_id = order.get("category_id")
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE orders SET status = 'rejected', completed_at = NOW() WHERE id = $1",
                order_id
            )
            if account_id and category_id and unused > 0:
                await conn.execute(
                    """UPDATE account_signatures 
                       SET used_signatures = GREATEST(used_signatures - $1, 0),
                           reserved_by = NULL,
                           reserved_until = NULL
                       WHERE account_id = $2 AND category_id = $3""",
                    unused, account_id, category_id
                )
            elif account_id:
                await conn.execute(
                    """UPDATE account_signatures 
                       SET reserved_by = NULL, reserved_until = NULL
                       WHERE account_id = $1""",
                    account_id
                )
            if refund_amount > 0:
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE telegram_id = $2",
                    refund_amount, order["user_id"]
                )
    return order


@router.callback_query(F.data.startswith("admin_confirm_cancel_"))
async def admin_confirm_cancel_legacy(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("❌ Заказ уже не активен", show_alert=True)
        return
    refund = order.get("price_paid", 0)
    result = await _do_cancel_active_order(order_id, refund)
    if not result:
        await callback.answer("❌ Не удалось отменить", show_alert=True)
        return
    await callback.answer("✅ Заказ отменён, средства возвращены", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("admin_cc_full_"))
async def admin_cancel_full_refund(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    refund = order.get("price_paid", 0)
    total = order.get("total_signatures") or 1
    claimed = order.get("signatures_claimed") or 0
    result = await _do_cancel_active_order(order_id, refund)
    if not result:
        await callback.answer("❌ Не удалось отменить заказ", show_alert=True)
        return
    await callback.answer("✅ Заказ отменён, полный возврат", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                result["user_id"],
                f"❌ <b>Заказ #{order_id} отменён администратором</b>\n\n"
                f"📊 Подписей было: {total} (использовано: {claimed})\n"
                f"💰 На ваш баланс возвращено: <b>{refund:.2f}$</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_cc_partial_"))
async def admin_cancel_partial_refund(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    total = order.get("total_signatures") or 1
    claimed = order.get("signatures_claimed") or 0
    unused = total - claimed
    full_price = order.get("price_paid", 0)
    partial_refund = round(full_price * unused / total, 2) if total > 0 else 0
    result = await _do_cancel_active_order(order_id, partial_refund)
    if not result:
        await callback.answer("❌ Не удалось отменить заказ", show_alert=True)
        return
    await callback.answer("✅ Заказ отменён, частичный возврат", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                result["user_id"],
                f"❌ <b>Заказ #{order_id} отменён администратором</b>\n\n"
                f"📊 Подписей было: {total} (использовано: {claimed}, неиспользовано: {unused})\n"
                f"💰 Частичный возврат: <b>{partial_refund:.2f}$</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_cc_none_"))
async def admin_cancel_no_refund(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    total = order.get("total_signatures") or 1
    claimed = order.get("signatures_claimed") or 0
    result = await _do_cancel_active_order(order_id, 0)
    if not result:
        await callback.answer("❌ Не удалось отменить заказ", show_alert=True)
        return
    await callback.answer("✅ Заказ отменён без возврата", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                result["user_id"],
                f"❌ <b>Заказ #{order_id} отменён администратором</b>\n\n"
                f"📊 Подписей было: {total} (использовано: {claimed})\n"
                f"💰 Возврат: <b>0.00$</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_cancel_completed_"))
async def admin_cancel_completed_order(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "completed":
        await callback.answer("❌ Заказ не завершён", show_alert=True)
        return
    refund = order.get("price_paid", 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 С возвратом ({refund:.2f}$)", callback_data=f"admin_cc_refund_{order_id}")],
        [InlineKeyboardButton(text="🚫 Без возврата", callback_data=f"admin_cc_norefund_{order_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_order_{order_id}")],
    ])
    try:
        await callback.message.edit_text(
            f"⚠️ <b>Отмена завершённого заказа #{order_id}</b>\n\n"
            f"💰 Сумма оплаты: <b>{refund:.2f}$</b>\n\n"
            f"Выберите вариант отмены:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cc_refund_"))
async def admin_cc_with_refund(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "completed":
        await callback.answer("❌ Заказ уже не завершён", show_alert=True)
        return
    refund = order.get("price_paid", 0)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE orders SET status = 'rejected', completed_at = NOW() WHERE id = $1 AND status = 'completed'",
                order_id
            )
            if result == "UPDATE 0":
                await callback.answer("❌ Заказ уже обработан", show_alert=True)
                return
            if refund > 0:
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE telegram_id = $2",
                    refund, order["user_id"]
                )
    await callback.answer("✅ Заказ отменён, средства возвращены", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                order["user_id"],
                f"❌ <b>Заказ #{order_id} отменён администратором</b>\n\n"
                f"💰 На ваш баланс возвращено: <b>{refund:.2f}$</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_cc_norefund_"))
async def admin_cc_without_refund(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] != "completed":
        await callback.answer("❌ Заказ уже не завершён", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE orders SET status = 'rejected', completed_at = NOW() WHERE id = $1 AND status = 'completed'",
            order_id
        )
        if result == "UPDATE 0":
            await callback.answer("❌ Заказ уже обработан", show_alert=True)
            return
    await callback.answer("✅ Заказ отменён без возврата", show_alert=True)
    order = await get_order(order_id)
    try:
        await callback.message.edit_text(
            format_order_status(order),
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                order["user_id"],
                f"❌ <b>Заказ #{order_id} отменён администратором</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reduce_sigs_"))
async def admin_reduce_sigs(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order or order["status"] != "active":
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    total = order.get("total_signatures", 1)
    claimed = order.get("signatures_claimed", 0)
    available = total - claimed
    if available <= 0:
        await callback.answer("❌ Все подписи уже использованы", show_alert=True)
        return
    price_per_sig = order["price_paid"] / max(total, 1)
    await state.set_state(AdminReduceSignaturesStates.waiting_count)
    await state.update_data(reduce_order_id=order_id, reduce_max=available, reduce_price_per_sig=price_per_sig)
    try:
        await callback.message.edit_text(
            f"➖ <b>Уменьшение подписей</b>\n\n"
            f"📦 Заказ #{order_id}\n"
            f"📊 Всего: {total} | Использовано: {claimed} | Доступно: {available}\n"
            f"💰 Цена за подпись: {price_per_sig:.2f}$\n\n"
            f"Введите количество подписей для возврата (1-{available}):",
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminReduceSignaturesStates.waiting_count)
async def process_reduce_sigs(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["reduce_order_id"]
    max_reduce = data["reduce_max"]
    price_per_sig = data["reduce_price_per_sig"]
    try:
        count = int(message.text.strip())
        if count < 1 or count > max_reduce:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(f"❌ Введите число от 1 до {max_reduce}.")
        return
    await state.clear()
    order = await get_order(order_id)
    if not order or order["status"] != "active":
        await message.answer("❌ Заказ больше не активен.")
        return
    total = order["total_signatures"]
    claimed = order.get("signatures_claimed", 0)
    available = total - claimed
    if count > available:
        await message.answer(f"❌ Доступно только {available} подписей для возврата.")
        return
    new_total = total - count
    if new_total < 1:
        await message.answer("❌ Нельзя уменьшить до 0. Используйте завершение заказа.")
        return
    actual_price_per_sig = order["price_paid"] / max(total, 1)
    refund = round(actual_price_per_sig * count, 2)
    new_price = round(order["price_paid"] - refund, 2)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET total_signatures = $1, price_paid = $2 WHERE id = $3",
            new_total, new_price, order_id
        )
    await update_balance(order["user_id"], refund)
    order = await get_order(order_id)
    await message.answer(
        f"✅ Подписи уменьшены\n\n"
        f"📦 Заказ #{order_id}: {total} → {new_total}\n"
        f"💰 Возврат: {refund:.2f}$ на баланс пользователя",
        parse_mode="HTML",
    )
    await message.answer(
        format_order_status(order),
        reply_markup=await _admin_order_kb(order),
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import get_bot
        bot = get_bot()
        if bot:
            await bot.send_message(
                order["user_id"],
                f"➖ <b>Изменение заказа #{order_id}</b>\n\n"
                f"Количество подписей уменьшено: {total} → {new_total}\n"
                f"💰 Возврат на баланс: <b>{refund:.2f}$</b>",
                parse_mode="HTML",
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_send_screenshot_"))
async def admin_send_screenshot(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["status"] not in ("active", "completed"):
        await callback.answer("❌ Заказ не активен", show_alert=True)
        return
    await state.update_data(screenshot_order_id=order_id)
    await state.set_state(AdminOrderScreenshotStates.waiting_qty)
    buttons = []
    row = []
    for i in range(1, 6):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"admin_scrn_qty_{order_id}_{i}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_order_{order_id}")])
    await callback.message.edit_text(
        f"📸 <b>Отправка скриншотов</b>\n\n"
        f"📦 Заказ: #{order_id}\n"
        f"👤 Клиент: {order.get('username') or order.get('user_id')}\n"
        f"📱 Телефон: <code>{order.get('phone', '—')}</code>\n\n"
        f"Выберите количество скриншотов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_scrn_qty_"))
async def admin_screenshot_qty(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    order_id = int(parts[3])
    qty = int(parts[4])
    await state.update_data(screenshot_order_id=order_id, scrn_qty=qty, scrn_current=0, scrn_photos=[])
    await state.set_state(AdminOrderScreenshotStates.waiting_screenshot)
    await callback.message.edit_text(
        f"📸 <b>Отправка скриншотов ({qty} шт)</b>\n\n"
        f"📦 Заказ: #{order_id}\n\n"
        f"Отправьте фото 1/{qty}:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminOrderScreenshotStates.waiting_screenshot, F.photo)
async def process_admin_screenshot(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data.get("screenshot_order_id")
    qty = data.get("scrn_qty", 1)
    photos = data.get("scrn_photos", [])
    current = data.get("scrn_current", 0)
    photo = message.photo[-1]
    photos.append(photo.file_id)
    current += 1
    if current < qty:
        await state.update_data(scrn_photos=photos, scrn_current=current)
        await message.answer(f"📸 Принято! Отправьте фото {current + 1}/{qty}:")
        return
    await state.clear()
    order = await get_order(order_id)
    if not order:
        await message.answer("❌ Заказ не найден.", parse_mode="HTML")
        return
    try:
        from src.bot.instance import bot
        from src.db.documents import save_order_document
        from src.db.database import get_pool
        pool = await get_pool()
        for file_id in photos:
            await save_order_document(order_id, order["user_id"], file_id, "admin")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE doc_requests SET status = 'sent' WHERE order_id = $1 AND status = 'pending'",
                order_id
            )
        cat_name = order.get('category_name', '—')
        phone = order.get('phone', '—')
        notify_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📁 Посмотреть скрины ({len(photos)} шт)",
                callback_data=f"my_docs_{order_id}"
            )],
        ])
        await bot.send_message(
            order["user_id"],
            f"📸 <b>Новые документы по заказу #{order_id}</b>\n\n"
            f"📂 Категория: {cat_name}\n"
            f"📱 Телефон: <code>{phone}</code>\n"
            f"📄 Загружено: <b>{len(photos)}x</b>\n\n"
            f"Перейдите в 📋 Мои заказы → 📁 Документы для просмотра.",
            reply_markup=notify_kb,
            parse_mode="HTML",
        )
        await message.answer(
            f"✅ {len(photos)} скриншот(ов) загружено для заказа #{order_id}.\n"
            f"Клиент получил уведомление.",
            reply_markup=await _admin_order_kb(order),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer("❌ Не удалось загрузить скриншоты.", parse_mode="HTML")


@router.message(AdminOrderScreenshotStates.waiting_screenshot)
async def process_admin_screenshot_not_photo(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте фото/скриншот.")


@router.callback_query(F.data.startswith("admin_view_docs_"))
async def admin_view_docs(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    docs = await get_order_documents(order_id)
    if not docs:
        await callback.answer("📭 Скриншотов нет", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    total_docs = len(docs)
    from src.bot.instance import get_bot
    _bot = get_bot()
    if total_docs == 1:
        try:
            await callback.message.delete()
        except Exception:
            pass
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К заказу", callback_data=f"admin_order_{order_id}")]
        ])
        await _bot.send_photo(
            callback.from_user.id,
            docs[0]["file_id"],
            caption=(
                f"📄 <b>Скриншот заказа #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>1x</b>"
            ),
            reply_markup=back_kb,
            parse_mode="HTML",
        )
    else:
        buttons = []
        row = []
        for i in range(1, total_docs + 1):
            row.append(InlineKeyboardButton(text=str(i), callback_data=f"adm_doc_{order_id}_{i}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(
            text=f"📸 Показать все ({total_docs} шт)",
            callback_data=f"adm_alldocs_{order_id}"
        )])
        buttons.append([InlineKeyboardButton(text="🔙 К заказу", callback_data=f"admin_order_{order_id}")])
        try:
            await callback.message.edit_text(
                f"📁 <b>Скриншоты заказа #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>{total_docs}x</b>\n\n"
                f"Выберите номер скриншота или посмотрите все:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML",
            )
        except Exception:
            await callback.message.answer(
                f"📁 <b>Скриншоты заказа #{order_id}</b>\n\n"
                f"📂 Категория: {cat_name}\n"
                f"📱 Телефон: <code>{phone}</code>\n"
                f"📄 Загружено: <b>{total_docs}x</b>\n\n"
                f"Выберите номер скриншота или посмотрите все:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_doc_"))
async def admin_view_single_doc(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    parts = callback.data.split("_")
    order_id = int(parts[2])
    doc_num = int(parts[3])
    docs = await get_order_documents(order_id)
    if not docs or doc_num < 1 or doc_num > len(docs):
        await callback.answer("❌ Скриншот не найден", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    doc = docs[doc_num - 1]
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К списку", callback_data=f"admin_view_docs_{order_id}")]
    ])
    try:
        await callback.message.delete()
    except Exception:
        pass
    from src.bot.instance import get_bot
    _bot = get_bot()
    await _bot.send_photo(
        callback.from_user.id,
        doc["file_id"],
        caption=(
            f"📄 <b>Скриншот {doc_num}/{len(docs)}</b>\n"
            f"📦 Заказ: #{order_id}\n"
            f"📂 Категория: {cat_name}\n"
            f"📱 Телефон: <code>{phone}</code>"
        ),
        reply_markup=back_kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_alldocs_"))
async def admin_view_all_docs(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    docs = await get_order_documents(order_id)
    if not docs:
        await callback.answer("📭 Скриншотов нет", show_alert=True)
        return
    order = await get_order(order_id)
    cat_name = order.get("category_name", "—") if order else "—"
    phone = order.get("phone", "—") if order else "—"
    from aiogram.types import InputMediaPhoto
    from src.bot.instance import get_bot
    _bot = get_bot()
    if len(docs) <= 10:
        media = []
        for i, doc in enumerate(docs):
            caption = (
                f"📄 <b>Скриншот {i+1}/{len(docs)}</b> — Заказ #{order_id}\n"
                f"📂 {cat_name} | 📱 <code>{phone}</code>"
            ) if i == 0 else None
            media.append(InputMediaPhoto(
                media=doc["file_id"],
                caption=caption,
                parse_mode="HTML" if caption else None,
            ))
        await _bot.send_media_group(callback.from_user.id, media)
    else:
        for chunk_start in range(0, len(docs), 10):
            chunk = docs[chunk_start:chunk_start + 10]
            media = []
            for i, doc in enumerate(chunk):
                caption = (
                    f"📄 <b>Скриншоты {chunk_start+1}—{chunk_start+len(chunk)}/{len(docs)}</b> — Заказ #{order_id}\n"
                    f"📂 {cat_name} | 📱 <code>{phone}</code>"
                ) if i == 0 else None
                media.append(InputMediaPhoto(
                    media=doc["file_id"],
                    caption=caption,
                    parse_mode="HTML" if caption else None,
                ))
            await _bot.send_media_group(callback.from_user.id, media)
    await callback.answer(f"📄 Отправлено {len(docs)} скриншот(ов)")


@router.callback_query(F.data == "admin_tickets")
async def admin_tickets(callback: CallbackQuery):
    await _show_tickets_page(callback, 0)


@router.callback_query(F.data.startswith("admin_tickets_page_"))
async def admin_tickets_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await _show_tickets_page(callback, page)


async def _show_tickets_page(callback: CallbackQuery, page: int):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    tickets = await get_all_tickets()
    user_is_admin = await AdminFilter.check(callback.from_user.id)
    if not tickets:
        kb = admin_tickets_kb([]) if user_is_admin else operator_tickets_kb([])
        try:
            await callback.message.edit_text(
                "🎫 <b>Тикеты</b>\n\n📭 Нет тикетов.",
                reply_markup=kb,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    total = len(tickets)
    kb = admin_tickets_kb(tickets, page=page) if user_is_admin else operator_tickets_kb(tickets, page=page)
    try:
        await callback.message.edit_text(
            f"🎫 <b>Тикеты</b> ({total}):",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_") & ~F.data.startswith("admin_ticket_reply_") & ~F.data.startswith("admin_ticket_limit") & ~F.data.startswith("admin_tickets_page_"))
async def admin_ticket_detail(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    ticket_id = int(callback.data.split("_")[-1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await callback.answer("❌ Тикет не найден", show_alert=True)
        return
    messages = await get_ticket_messages(ticket_id)
    order_text = f"\n📦 По заказу: #{ticket['order_id']}" if ticket.get("order_id") else ""
    text = (
        f"🎫 <b>Тикет #{ticket['id']}</b>\n\n"
        f"👤 Пользователь: {ticket['user_id']}\n"
        f"📋 Тема: {ticket['subject']}{order_text}\n"
        f"📊 Статус: {'🟢 Открыт' if ticket['status'] == 'open' else '🔴 Закрыт'}\n\n"
        f"💬 <b>Сообщения:</b>\n\n"
    )
    has_files = False
    for msg in messages:
        sender = "👤 Пользователь" if msg["sender_id"] == ticket["user_id"] else "👨‍💼 Поддержка"
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
        reply_markup=admin_ticket_detail_kb(ticket),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_reply_"))
async def admin_start_ticket_reply(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    ticket_id = int(callback.data.split("_")[-1])
    await state.update_data(admin_reply_ticket_id=ticket_id)
    await callback.message.edit_text(
        "💬 Введите ваш ответ:",
        parse_mode="HTML",
    )
    await state.set_state(AdminTicketStates.waiting_reply)
    await callback.answer()


@router.message(AdminTicketStates.waiting_reply)
async def admin_process_ticket_reply(message: Message, state: FSMContext):
    if not await AdminFilter.check_staff(message.from_user.id):
        return
    data = await state.get_data()
    ticket_id = data["admin_reply_ticket_id"]
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
    ticket = await get_ticket(ticket_id)
    await state.clear()
    file_mark = " 📎" if file_id else ""
    await message.answer(
        f"✅ Ответ отправлен в тикет #{ticket_id}.{file_mark}",
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import bot
        if file_id:
            try:
                await bot.send_photo(
                    ticket["user_id"], file_id,
                    caption=f"💬 <b>Новый ответ в тикете #{ticket_id}</b>\n\n👨‍💼 Поддержка: {text}",
                    parse_mode="HTML",
                )
            except Exception:
                await bot.send_document(
                    ticket["user_id"], file_id,
                    caption=f"💬 <b>Новый ответ в тикете #{ticket_id}</b>\n\n👨‍💼 Поддержка: {text}",
                    parse_mode="HTML",
                )
        else:
            await bot.send_message(
                ticket["user_id"],
                f"💬 <b>Новый ответ в тикете #{ticket_id}</b>\n\n"
                f"👨‍💼 Поддержка: {text}",
                parse_mode="HTML",
            )
    except Exception:
        pass
    tickets = await get_all_tickets()
    kb = admin_tickets_kb(tickets) if await AdminFilter.check(message.from_user.id) else operator_tickets_kb(tickets)
    await message.answer(
        "🎫 <b>Тикеты:</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_close_ticket_"))
async def admin_close_ticket(callback: CallbackQuery):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    ticket_id = int(callback.data.split("_")[-1])
    await close_ticket(ticket_id)
    await callback.answer("🔒 Тикет закрыт", show_alert=True)
    try:
        ticket = await get_ticket(ticket_id)
        from src.bot.instance import bot
        await bot.send_message(
            ticket["user_id"],
            f"🔒 <b>Тикет #{ticket_id} закрыт администратором.</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    tickets = await get_all_tickets()
    kb = admin_tickets_kb(tickets) if await AdminFilter.check(callback.from_user.id) else operator_tickets_kb(tickets)
    await callback.message.edit_text(
        "🎫 <b>Тикеты:</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_search_ticket")
async def admin_search_ticket(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check_staff(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🔍 <b>Поиск обращения</b>\n\n"
        "Введите ID тикета, ID пользователя, @username или ключевое слово из темы:",
        parse_mode="HTML",
    )
    await state.set_state(AdminTicketStates.waiting_search)
    await callback.answer()


@router.message(AdminTicketStates.waiting_search)
async def admin_process_ticket_search(message: Message, state: FSMContext):
    if not await AdminFilter.check_staff(message.from_user.id):
        return
    query = message.text.strip() if message.text else ""
    if not query:
        await message.answer("❌ Введите запрос для поиска.")
        return
    if query.startswith("@"):
        query = query[1:]
    results = await search_tickets(query)
    await state.clear()
    user_is_admin = await AdminFilter.check(message.from_user.id)
    if not results:
        kb = admin_tickets_kb([]) if user_is_admin else operator_tickets_kb([])
        await message.answer(
            f"🔍 По запросу «{query}» ничего не найдено.",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return
    kb = admin_tickets_kb(results) if user_is_admin else operator_tickets_kb(results)
    await message.answer(
        f"🔍 <b>Результаты поиска</b> ({len(results)}):",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_topup_user")
async def admin_topup_user(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "💰 <b>Изменение баланса</b>\n\n"
        "Введите Telegram ID или @username пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminBalanceStates.waiting_user_id)
    await callback.answer()


@router.message(AdminBalanceStates.waiting_user_id)
async def process_topup_user_id(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip()
    user = None
    if text.startswith("@"):
        user = await get_user_by_username(text)
    else:
        try:
            tid = int(text)
            user = await get_user(tid)
        except ValueError:
            user = await get_user_by_username(text)
    if not user:
        await message.answer(
            "❌ Пользователь не найден. Проверьте ID или username.",
            parse_mode="HTML",
        )
        return
    await state.update_data(bal_user_id=user["telegram_id"])
    name = user.get("username") or user.get("full_name") or str(user["telegram_id"])
    await message.answer(
        f"👤 Пользователь: <b>{name}</b>\n"
        f"💰 Текущий баланс: <b>{user.get('balance', 0):.2f}$</b>\n\n"
        f"Введите сумму:\n"
        f"<code>50</code> — начислить\n"
        f"<code>-50</code> — списать",
        parse_mode="HTML",
    )
    await state.set_state(AdminBalanceStates.waiting_amount)


@router.message(AdminBalanceStates.waiting_amount)
async def process_topup_amount(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount == 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму (число != 0).")
        return
    data = await state.get_data()
    telegram_id = data["bal_user_id"]
    user = await get_user(telegram_id)
    current_balance = user.get("balance", 0) if user else 0
    if amount < 0 and current_balance + amount < 0:
        await message.answer(
            f"❌ Недостаточно средств.\n"
            f"💰 Текущий баланс: {current_balance:.2f}$\n"
            f"Максимум для списания: {current_balance:.2f}$",
            parse_mode="HTML",
        )
        return
    await update_balance(telegram_id, amount)
    await state.clear()
    user = await get_user(telegram_id)
    sign = "+" if amount > 0 else ""
    action = "начислено" if amount > 0 else "списано"
    await message.answer(
        f"✅ {sign}{amount:.2f}$ {action}.\n"
        f"💰 Новый баланс: {user.get('balance', 0):.2f}$",
        parse_mode="HTML",
    )
    try:
        from src.bot.instance import bot
        if amount > 0:
            notif_text = f"+{amount:.2f}$ — начислено администратором"
        else:
            notif_text = f"{amount:.2f}$ — списано администратором"
        await bot.send_message(
            telegram_id,
            f"💰 <b>Изменение баланса</b>\n\n"
            f"{notif_text}\n"
            f"Текущий баланс: {user.get('balance', 0):.2f}$",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "admin_deposit")
async def admin_deposit(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    current = await get_deposit_amount()
    status = f"<b>{current:.2f}$</b>" if current > 0 else "отключён"
    await callback.message.edit_text(
        f"🔒 <b>Настройка депозита</b>\n\n"
        f"Текущий глобальный депозит: {status}\n\n"
        f"Депозит — сумма, которую пользователь должен внести перед покупкой.\n"
        f"Установите 0, чтобы отключить.\n\n"
        f"💡 Для отдельных пользователей депозит можно изменить в разделе «Пользователи».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="admin_set_deposit")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_deposit")
async def admin_set_deposit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "💲 Введите сумму депозита в USD (0 = отключить):",
        parse_mode="HTML",
    )
    await state.set_state(AdminDepositStates.waiting_amount)
    await callback.answer()


@router.message(AdminDepositStates.waiting_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму (число >= 0).")
        return
    await set_deposit_amount(amount)
    await state.clear()
    status = f"{amount:.2f}$" if amount > 0 else "отключён"
    await message.answer(
        f"✅ Глобальный депозит обновлён: {status}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    pool = await get_pool()
    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        orders_count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        total_accounts = await conn.fetchval("SELECT COUNT(*) FROM accounts")
        cats_count = await conn.fetchval("SELECT COUNT(*) FROM categories")
        open_tickets = await conn.fetchval("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
        total_revenue = await conn.fetchval("SELECT COALESCE(SUM(price_paid), 0) FROM orders WHERE status != 'rejected'")
    summary = await get_availability_summary()
    avail_lines = []
    total_remaining = 0
    total_loaded = 0
    if summary:
        from src.utils.formatters import get_category_emoji
        for s in summary:
            cat_name = s["category_name"]
            emoji = get_category_emoji(cat_name)
            prefix = f"{emoji} " if emoji else ""
            remaining = s["remaining_signatures"] or 0
            acc_count = s["accounts_count"] or 0
            total_remaining += remaining
            total_loaded += acc_count
            avail_lines.append(f"{prefix}{cat_name}: {acc_count} акк. / {remaining} подп.")
    avail_text = "\n".join(avail_lines) if avail_lines else "Нет данных"
    try:
        await callback.message.edit_text(
            "📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"📂 Категорий: {cats_count}\n"
            f"📦 Заказов: {orders_count}\n"
            f"📱 Всего аккаунтов: {total_accounts}\n"
            f"🎫 Открытых тикетов: {open_tickets}\n"
            f"💰 Общий доход: {total_revenue:.2f}$\n\n"
            f"📦 <b>Наличие (включённые)</b>\n"
            f"{avail_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📱 Всего акк.: {total_loaded} | 📝 Подп.: {total_remaining}",
            reply_markup=admin_stats_menu_kb(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_stats_by_date")
async def admin_stats_by_date_start(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminStatsStates.waiting_date)
    try:
        await callback.message.edit_text(
            "📅 <b>Введите дату</b>\n\n"
            "Формат: <code>ГГГГ-ММ-ДД</code>\n"
            "Например: <code>2026-02-13</code>",
            reply_markup=admin_stats_date_kb(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminStatsStates.waiting_date)
async def admin_stats_by_date_process(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    date_str = message.text.strip()
    import re as _re
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await message.answer(
            "❌ Неверный формат. Введите дату в формате <code>ГГГГ-ММ-ДД</code>",
            parse_mode="HTML",
        )
        return
    await state.clear()
    stats = await get_stats_by_date(date_str)
    if not stats:
        await message.answer(
            f"📊 <b>Статистика за {date_str}</b>\n\n"
            f"Нет данных за эту дату.",
            reply_markup=admin_stats_menu_kb(),
            parse_mode="HTML",
        )
        return
    lines = [f"📊 <b>Статистика за {date_str}</b>\n"]
    for s in stats:
        remaining = s["effective_max"] - s["used_signatures"]
        lines.append(
            f"📱 <code>{s['phone']}</code>\n"
            f"   📂 {s['category_name']}\n"
            f"   🛒 Продано: {s['sold_count']} подп.\n"
            f"   📊 Осталось: {remaining}/{s['effective_max']}\n"
        )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>...обрезано</i>"
    await message.answer(
        text,
        reply_markup=admin_stats_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_export_all")
async def admin_export_all(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    rows = await get_accounts_availability_all()
    if not rows:
        await callback.answer("❌ Нет данных для выгрузки", show_alert=True)
        return
    await callback.answer("⏳ Формируется файл...")
    import os
    from src.utils.excel_export import generate_availability_excel
    path = None
    try:
        path = generate_availability_excel(rows, title="Наличие (все)")
        from aiogram.types import FSInputFile
        doc = FSInputFile(path, filename="Наличие аккаунтов.xlsx")
        await callback.message.answer_document(doc, caption="📥 Выгрузка наличия (все аккаунты)")
    except Exception as e:
        logger.error(f"EXPORT_ALL: ошибка генерации/отправки файла: {e}", exc_info=True)
        try:
            await callback.message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data == "admin_export_date")
async def admin_export_date(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminStatsStates.waiting_export_date)
    try:
        await callback.message.edit_text(
            "📅 Введите дату для выгрузки в формате <code>ГГГГ-ММ-ДД</code>:",
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminStatsStates.waiting_export_date)
async def admin_export_date_process(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    date_str = message.text.strip()
    import re as _re
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await message.answer(
            "❌ Неверный формат. Введите дату в формате <code>ГГГГ-ММ-ДД</code>",
            parse_mode="HTML",
        )
        return
    await state.clear()
    rows = await get_accounts_availability_by_date(date_str)
    if not rows:
        await message.answer(
            f"📊 Нет данных за {date_str}.",
            reply_markup=admin_stats_menu_kb(),
            parse_mode="HTML",
        )
        return
    import os
    from src.utils.excel_export import generate_availability_excel
    path = None
    try:
        path = generate_availability_excel(rows, title=f"Наличие {date_str}")
        from aiogram.types import FSInputFile
        doc = FSInputFile(path, filename=f"Наличие аккаунтов {date_str}.xlsx")
        await message.answer_document(doc, caption=f"📥 Выгрузка наличия за {date_str}")
    except Exception as e:
        logger.error(f"EXPORT_DATE: ошибка генерации/отправки файла за {date_str}: {e}", exc_info=True)
        try:
            await message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data == "admin_export_today")
async def admin_export_today(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    from datetime import datetime as _dt, timezone, timedelta
    msk = timezone(timedelta(hours=3))
    today = str(_dt.now(msk).date())
    import os
    from src.utils.excel_export import generate_availability_excel
    path = None
    try:
        rows = await get_accounts_availability_by_date(today)
        if not rows:
            await callback.answer("❌ Нет данных за сегодня", show_alert=True)
            return
        await callback.answer("⏳ Формируется файл...")
        path = generate_availability_excel(rows, title=f"Наличие {today}")
        from aiogram.types import FSInputFile
        doc = FSInputFile(path, filename=f"Наличие аккаунтов {today}.xlsx")
        await callback.message.answer_document(doc, caption=f"📥 Выгрузка наличия за сегодня ({today})")
    except Exception as e:
        logger.error(f"EXPORT_TODAY: ошибка генерации/отправки файла за {today}: {e}", exc_info=True)
        try:
            await callback.message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data == "admin_export_phones")
async def admin_export_phones(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminStatsStates.waiting_export_phones)
    try:
        await callback.message.edit_text(
            "📱 <b>Выгрузка по номерам</b>\n\n"
            "Отправьте список номеров (каждый с новой строки):\n\n"
            "<code>+79001234567\n+79007654321\n89001112233</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_stats")],
            ]),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminStatsStates.waiting_export_phones)
async def admin_export_phones_process(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    await state.clear()
    lines = [l.strip() for l in message.text.strip().split("\n") if l.strip()]
    if not lines:
        await message.answer(
            "❌ Не удалось распознать номера.",
            reply_markup=admin_stats_menu_kb(),
        )
        return
    from src.db.accounts import normalize_phone
    unique_phones = list(set(normalize_phone(p) for p in lines))
    total_input = len(unique_phones)
    rows = await get_accounts_availability_by_phones(lines)
    if not rows:
        await message.answer(
            f"❌ Аккаунты по указанным номерам не найдены ({total_input} номеров).",
            reply_markup=admin_stats_menu_kb(),
        )
        return
    import os
    from src.utils.excel_export import generate_availability_excel
    path = None
    try:
        path = generate_availability_excel(rows, title="Наличие (по номерам)")
        from aiogram.types import FSInputFile
        found_phones = len(set(r["phone"] for r in rows))
        doc = FSInputFile(path, filename="Наличие по номерам.xlsx")
        await message.answer_document(
            doc,
            caption=f"📥 Выгрузка наличия по номерам\n📱 Найдено: {found_phones} из {total_input} номеров",
        )
    except Exception as e:
        logger.error(f"EXPORT_PHONES: ошибка генерации/отправки файла: {e}", exc_info=True)
        try:
            await message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data == "admin_sales_export")
async def admin_sales_export(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    try:
        await callback.message.edit_text(
            "📊 <b>Выгрузка продаж</b>\n\n"
            "Выберите период:",
            reply_markup=admin_sales_period_kb(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "sales_period_custom")
async def admin_sales_custom_period(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📆 <b>Свой период</b>\n\n"
        "Введите период в формате:\n"
        "<code>ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
        "Например: <code>2025-01-01 2025-01-31</code>",
        parse_mode="HTML",
    )
    await state.set_state(AdminStatsStates.waiting_custom_period)
    await callback.answer()


@router.message(AdminStatsStates.waiting_custom_period)
async def process_custom_period(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    import re as _re
    text = message.text.strip() if message.text else ""
    match = _re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})$", text)
    if not match:
        await message.answer(
            "❌ Неверный формат. Введите две даты через пробел:\n"
            "<code>ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>",
            parse_mode="HTML",
        )
        return
    date_from = match.group(1)
    date_to = match.group(2)
    if date_from > date_to:
        await message.answer(
            "❌ Дата начала должна быть раньше даты окончания.",
            parse_mode="HTML",
        )
        return
    await state.clear()
    rows = await get_sales_stats_by_period(date_from, date_to)
    if not rows:
        await message.answer(
            f"📊 Нет данных о продажах за период {date_from} — {date_to}.",
            reply_markup=admin_sales_period_kb(),
            parse_mode="HTML",
        )
        return
    import os
    from src.utils.excel_export import generate_sales_excel
    title = f"Продажи {date_from} — {date_to}"
    fname = f"Продажи за {date_from} — {date_to}.xlsx"
    path = None
    try:
        path = generate_sales_excel(rows, title=title)
        from aiogram.types import FSInputFile
        doc = FSInputFile(path, filename=fname)
        await message.answer_document(doc, caption=f"📥 {title}")
    except Exception as e:
        logger.error(f"SALES_CUSTOM: ошибка генерации/отправки файла: {e}", exc_info=True)
        try:
            await message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data.startswith("sales_period_"))
async def admin_sales_period(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    period = callback.data.replace("sales_period_", "")
    from datetime import datetime, timedelta, timezone
    msk = timezone(timedelta(hours=3))
    today = datetime.now(msk).date()
    date_from = None
    date_to = str(today)
    if period == "today":
        date_from = str(today)
        title = f"Продажи за {today}"
        fname = f"Продажи за {today}.xlsx"
    elif period == "week":
        date_from = str(today - timedelta(days=7))
        title = f"Продажи за неделю ({date_from} — {date_to})"
        fname = f"Продажи за неделю {date_from} — {date_to}.xlsx"
    elif period == "month":
        date_from = str(today - timedelta(days=30))
        title = f"Продажи за месяц ({date_from} — {date_to})"
        fname = f"Продажи за месяц {date_from} — {date_to}.xlsx"
    else:
        date_from = None
        date_to = None
        title = "Продажи за всё время"
        fname = "Продажи за всё время.xlsx"
    await callback.answer("⏳ Формируется файл...")
    rows = await get_sales_stats_by_period(date_from, date_to)
    if not rows:
        try:
            await callback.message.edit_text(
                "📊 Нет данных о продажах за выбранный период.",
                reply_markup=admin_sales_period_kb(),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        return
    import os
    from src.utils.excel_export import generate_sales_excel
    path = None
    try:
        path = generate_sales_excel(rows, title=title)
        from aiogram.types import FSInputFile
        doc = FSInputFile(path, filename=fname)
        await callback.message.answer_document(doc, caption=f"📥 {title}")
    except Exception as e:
        logger.error(f"SALES_PERIOD: ошибка генерации/отправки файла ({title}): {e}", exc_info=True)
        try:
            await callback.message.answer("❌ Ошибка при формировании файла.")
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.callback_query(F.data == "admin_availability")
async def admin_availability_view(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await _show_availability_page(callback, 0)


@router.callback_query(F.data.startswith("admin_avail_page_"))
async def admin_availability_page(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    page = int(callback.data.split("admin_avail_page_")[1])
    await _show_availability_page(callback, page)


async def _show_availability_page(callback: CallbackQuery, page: int):
    accounts = await get_accounts_availability()
    if not accounts:
        try:
            await callback.message.edit_text(
                "📊 <b>Наличие</b>\n\nНет аккаунтов с доступными подписями.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")]
                ]),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    if page < 0 or page >= len(accounts):
        page = 0
    acc = accounts[page]
    text = _build_avail_text(acc, page, len(accounts))
    try:
        await callback.message.edit_text(
            text,
            reply_markup=admin_availability_kb(accounts, page),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


def _build_avail_text(acc: dict, page: int, total: int) -> str:
    lines = [
        f"📊 <b>Наличие</b> ({page + 1}/{total})\n",
        f"📱 <b>{acc['phone']}</b>\n",
    ]
    total_remaining = 0
    for s in acc["sigs"]:
        lines.append(f"   📂 {s['category_name']}: <b>{s['remaining']}</b>/{s['effective_max']}")
        total_remaining += s["remaining"]
    lines.append(f"\n📊 Всего осталось: <b>{total_remaining}</b> подп.")
    return "\n".join(lines)


@router.callback_query(F.data == "admin_operators")
async def admin_operators_list(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    operators = await get_all_operators()
    await callback.message.edit_text(
        f"👷 <b>Операторы</b> ({len(operators)})\n\n"
        f"Операторы могут подтверждать заказы и отвечать на тикеты.",
        reply_markup=admin_operators_kb(operators),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_operator")
async def admin_add_operator_handler(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "👷 <b>Добавление оператора</b>\n\n"
        "Введите Telegram ID или @username:",
        parse_mode="HTML",
    )
    await state.set_state(AdminOperatorStates.waiting_id)
    await callback.answer()


@router.message(AdminOperatorStates.waiting_id)
async def process_add_operator(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip()
    username = None
    telegram_id = None
    if text.startswith("@"):
        user = await get_user_by_username(text)
        if user:
            telegram_id = user["telegram_id"]
            username = user.get("username")
        else:
            await message.answer(
                "❌ Пользователь не найден. Убедитесь, что он запускал бота.",
                parse_mode="HTML",
            )
            await state.clear()
            return
    else:
        try:
            telegram_id = int(text)
            user = await get_user(telegram_id)
            if user:
                username = user.get("username")
        except ValueError:
            await message.answer("❌ Введите корректный Telegram ID или @username.")
            await state.clear()
            return
    result = await add_operator(telegram_id, username)
    await state.clear()
    if result:
        await message.answer(
            f"✅ Оператор добавлен: <b>{username or telegram_id}</b>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Этот пользователь уже является оператором.",
            parse_mode="HTML",
        )
    operators = await get_all_operators()
    await message.answer(
        f"👷 <b>Операторы</b> ({len(operators)})",
        reply_markup=admin_operators_kb(operators),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_op_") & ~F.data.startswith("admin_op_role_") & ~F.data.startswith("admin_op_toggle_notif_"))
async def admin_operator_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_op_")[1])
    user = await get_user(telegram_id)
    name = "—"
    if user:
        name = user.get("username") or user.get("full_name") or str(telegram_id)
    op = await get_operator(telegram_id)
    role = op.get("role", "orders") if op else "orders"
    notif = bool(op.get("notifications_enabled", 1)) if op else True
    role_map = {"orders": "📋 Заказы", "support": "🎫 Поддержка", "preorders": "⏳ Предзаказы"}
    role_text = role_map.get(role, "📋 Заказы")
    notif_text = "🔔 ВКЛ" if notif else "🔕 ВЫКЛ"
    await callback.message.edit_text(
        f"👷 <b>Оператор</b>\n\n"
        f"🆔 ID: <code>{telegram_id}</code>\n"
        f"👤 Имя: {name}\n"
        f"📌 Роль: {role_text}\n"
        f"📢 Уведомления: {notif_text}",
        reply_markup=admin_operator_detail_kb(telegram_id, role, notif),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_del_op_"))
async def admin_delete_operator(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_del_op_")[1])
    await remove_operator(telegram_id)
    await callback.answer("✅ Оператор удалён", show_alert=True)
    operators = await get_all_operators()
    await callback.message.edit_text(
        f"👷 <b>Операторы</b> ({len(operators)})",
        reply_markup=admin_operators_kb(operators),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_toggle_pause")
async def admin_toggle_pause(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    paused = await is_bot_paused()
    if paused:
        await set_bot_paused(False)
        await callback.answer("▶️ Бот возобновлён. Покупки включены.", show_alert=True)
        users = await get_all_users()
        from src.bot.instance import bot
        for u in users:
            try:
                await bot.send_message(u["telegram_id"], "✅ Бот возобновил работу!", parse_mode="HTML")
            except Exception:
                pass
        owner = await is_owner(callback.from_user.id)
        try:
            await callback.message.edit_text(
                f"⚙️ <b>Панель администратора</b>\n\n"
                f"📌 Статус бота: ✅ В работе\n\n"
                "Выберите раздел:",
                reply_markup=admin_menu_kb(False, show_admin_mgmt=owner),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
    else:
        await callback.message.edit_text(
            "⏸ <b>Приостановка бота</b>\n\n"
            "Введите причину приостановки (или отправьте «-» без причины):",
            parse_mode="HTML",
        )
        await state.set_state(AdminPauseStates.waiting_reason)
        await callback.answer()


@router.message(AdminPauseStates.waiting_reason)
async def admin_pause_reason(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    reason = message.text.strip() if message.text else "-"
    await state.clear()
    await set_bot_paused(True)
    users = await get_all_users()
    from src.bot.instance import bot
    if reason == "-":
        broadcast_text = "❌ Бот приостановлен."
    else:
        broadcast_text = f"❌ Бот приостановлен. Причина: {reason}"
    sent = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass
    paused = await is_bot_paused()
    owner = await is_owner(message.from_user.id)
    await message.answer(
        f"⏸ <b>Бот приостановлен</b>\n\n"
        f"📢 Рассылка отправлена: {sent} пользователям\n"
        f"💬 Причина: {reason if reason != '-' else 'не указана'}",
        reply_markup=admin_menu_kb(paused, show_admin_mgmt=owner),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение, которое получат все пользователи бота.\n\n"
        "⚠️ Поддерживается текст с HTML-разметкой.",
        parse_mode="HTML",
    )
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    await state.update_data(broadcast_text=message.text)
    users = await get_all_users()
    await message.answer(
        f"📢 <b>Подтверждение рассылки</b>\n\n"
        f"👥 Получателей: {len(users)}\n\n"
        f"📝 Сообщение:\n{message.text}\n\n"
        f"Отправить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_menu"),
            ],
        ]),
        parse_mode="HTML",
    )
    await state.set_state(AdminBroadcastStates.waiting_confirm)


@router.callback_query(F.data == "broadcast_confirm", AdminBroadcastStates.waiting_confirm)
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    users = await get_all_users()
    from src.bot.instance import bot
    sent = 0
    failed = 0
    await callback.message.edit_text(
        "📢 <b>Рассылка...</b>\n\n⏳ Отправка сообщений...",
        parse_mode="HTML",
    )
    await callback.answer()
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    paused = await is_bot_paused()
    owner = await is_owner(callback.from_user.id)
    await callback.message.edit_text(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        reply_markup=admin_menu_kb(paused, show_admin_mgmt=owner),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_op_role_"))
async def admin_toggle_operator_role(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("admin_op_role_")[1]
    if parts.startswith("support_"):
        new_role = "support"
        telegram_id = int(parts.split("support_")[1])
    elif parts.startswith("preorders_"):
        new_role = "preorders"
        telegram_id = int(parts.split("preorders_")[1])
    else:
        new_role = "orders"
        telegram_id = int(parts.split("orders_")[1])
    await update_operator_role(telegram_id, new_role)
    role_map = {"orders": "📋 Заказы", "support": "🎫 Поддержка", "preorders": "⏳ Предзаказы"}
    role_text = role_map.get(new_role, "📋 Заказы")
    await callback.answer(f"✅ Роль изменена: {role_text}", show_alert=True)
    user = await get_user(telegram_id)
    name = "—"
    if user:
        name = user.get("username") or user.get("full_name") or str(telegram_id)
    op = await get_operator(telegram_id)
    notif = bool(op.get("notifications_enabled", 1)) if op else True
    notif_text = "🔔 ВКЛ" if notif else "🔕 ВЫКЛ"
    await callback.message.edit_text(
        f"👷 <b>Оператор</b>\n\n"
        f"🆔 ID: <code>{telegram_id}</code>\n"
        f"👤 Имя: {name}\n"
        f"📌 Роль: {role_text}\n"
        f"📢 Уведомления: {notif_text}",
        reply_markup=admin_operator_detail_kb(telegram_id, new_role, notif),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_op_toggle_notif_"))
async def admin_op_toggle_notifications(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_op_toggle_notif_")[1])
    new_state = await toggle_operator_notifications(telegram_id)
    status = "🔔 Включены" if new_state else "🔕 Отключены"
    await callback.answer(f"Уведомления: {status}", show_alert=True)
    user = await get_user(telegram_id)
    name = "—"
    if user:
        name = user.get("username") or user.get("full_name") or str(telegram_id)
    op = await get_operator(telegram_id)
    role = op.get("role", "orders") if op else "orders"
    role_map = {"orders": "📋 Заказы", "support": "🎫 Поддержка", "preorders": "⏳ Предзаказы"}
    role_text = role_map.get(role, "📋 Заказы")
    notif_text = "🔔 ВКЛ" if new_state else "🔕 ВЫКЛ"
    try:
        await callback.message.edit_text(
            f"👷 <b>Оператор</b>\n\n"
            f"🆔 ID: <code>{telegram_id}</code>\n"
            f"👤 Имя: {name}\n"
            f"📌 Роль: {role_text}\n"
            f"📢 Уведомления: {notif_text}",
            reply_markup=admin_operator_detail_kb(telegram_id, role, new_state),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "admin_toggle_notify")
async def admin_toggle_notify(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    current = await is_admin_notifications_enabled(callback.from_user.id)
    new_state = not current
    await set_admin_notifications(callback.from_user.id, new_state)
    status = "🔔 Включены" if new_state else "🔕 Отключены"
    await callback.answer(f"Уведомления: {status}", show_alert=True)
    paused = await is_bot_paused()
    owner = await is_owner(callback.from_user.id)
    try:
        await callback.message.edit_text(
            f"⚙️ <b>Панель администратора</b>\n\n"
            f"📌 Статус бота: {'⏸ Приостановлен' if paused else '✅ В работе'}\n"
            f"🔔 Уведомления: {status}\n\n"
            "Выберите раздел:",
            reply_markup=admin_menu_kb(paused, show_admin_mgmt=owner),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "admin_preorders")
async def admin_preorders(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    preorders = await get_preorders_with_users()
    if not preorders:
        await callback.message.edit_text(
            "⏳ <b>Предзаказы</b>\n\n📭 Нет активных предзаказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"⏳ <b>Предзаказы</b> ({len(preorders)})",
        reply_markup=admin_preorders_kb(preorders),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_preorder_") & ~F.data.startswith("admin_preorder_msg_") & ~F.data.startswith("admin_preorder_cancel_"))
async def admin_preorder_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Предзаказ не найден", show_alert=True)
        return
    user = await get_user(order["user_id"])
    user_name = "—"
    if user:
        user_name = f"@{user['username']}" if user.get("username") else (user.get("full_name") or str(user["telegram_id"]))
    raw_cat = order.get("category_name", "—")
    cat_emoji = get_category_emoji(raw_cat)
    cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
    custom = order.get("custom_operator_name")
    if custom:
        cat_name = f"{cat_name} ({custom})"
    total = order.get("total_signatures", 1)
    await callback.message.edit_text(
        f"⏳ <b>Предзаказ #{order_id}</b>\n\n"
        f"👤 Клиент: {user_name}\n"
        f"🆔 ID: <code>{order['user_id']}</code>\n"
        f"📂 Категория: {cat_name}\n"
        f"📊 Подписей: {total}\n"
        f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
        f"📅 Создан: {order['created_at'].strftime('%Y-%m-%d %H:%M') if order.get('created_at') else '—'}",
        reply_markup=admin_preorder_detail_kb(order_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_preorder_msg_"))
async def admin_preorder_msg(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await state.update_data(preorder_msg_order_id=order_id)
    await callback.message.edit_text(
        "💬 Введите сообщение для клиента:",
        parse_mode="HTML",
    )
    await state.set_state(AdminPreorderStates.waiting_message)
    await callback.answer()


@router.message(AdminPreorderStates.waiting_message)
async def admin_process_preorder_msg(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["preorder_msg_order_id"]
    order = await get_order(order_id)
    await state.clear()
    if not order:
        await message.answer("❌ Предзаказ не найден.")
        return
    try:
        from src.bot.instance import bot
        raw_cat = order.get("category_name", "—")
        cat_emoji = get_category_emoji(raw_cat)
        cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
        custom = order.get("custom_operator_name")
        if custom:
            cat_name = f"{cat_name} ({custom})"
        await bot.send_message(
            order["user_id"],
            f"📢 <b>Сообщение по предзаказу #{order_id}</b>\n\n"
            f"📂 Категория: {cat_name}\n\n"
            f"💬 {message.text}",
            parse_mode="HTML",
        )
        await message.answer("✅ Сообщение отправлено клиенту.", parse_mode="HTML")
    except Exception:
        await message.answer("❌ Не удалось отправить сообщение.", parse_mode="HTML")
    preorders = await get_preorders_with_users()
    if preorders:
        await message.answer(
            f"⏳ <b>Предзаказы</b> ({len(preorders)})",
            reply_markup=admin_preorders_kb(preorders),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "⏳ <b>Предзаказы</b>\n\n📭 Нет активных предзаказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
            ]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin_preorder_cancel_"))
async def admin_preorder_cancel(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    order = await cancel_preorder(order_id)
    if not order:
        await callback.answer("❌ Предзаказ не найден или уже выполнен", show_alert=True)
        return
    price = order.get("price_paid", 0)
    if price > 0:
        await update_balance(order["user_id"], price)
    await callback.answer("✅ Предзаказ отменён, средства возвращены", show_alert=True)
    try:
        from src.bot.instance import bot
        await bot.send_message(
            order["user_id"],
            f"❌ <b>Предзаказ #{order_id} отменён администратором.</b>\n\n"
            f"💰 Возвращено: {price:.2f}$",
            parse_mode="HTML",
        )
    except Exception:
        pass
    preorders = await get_preorders_with_users()
    if preorders:
        await callback.message.edit_text(
            f"⏳ <b>Предзаказы</b> ({len(preorders)})",
            reply_markup=admin_preorders_kb(preorders),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "⏳ <b>Предзаказы</b>\n\n📭 Нет активных предзаказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
            ]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin_cat_bb_price_"))
async def admin_cat_bb_price(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    current = category.get("bb_price")
    current_text = f"{current:.2f}$" if current else "не задана"
    await state.update_data(bb_price_cat_id=category_id)
    await callback.message.edit_text(
        f"💰 <b>Цена ББ для: {category['name']}</b>\n\n"
        f"Текущая цена ББ: {current_text}\n\n"
        f"Введите новую цену ББ в USD (0 = убрать):",
        parse_mode="HTML",
    )
    await state.set_state(AdminCategoryStates.waiting_bb_price)
    await callback.answer()


@router.message(AdminCategoryStates.waiting_bb_price)
async def process_bb_price(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        price = float(message.text.strip().replace(",", "."))
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену.")
        return
    data = await state.get_data()
    cat_id = data["bb_price_cat_id"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        if price == 0:
            await conn.execute("UPDATE categories SET bb_price = NULL WHERE id = $1", cat_id)
        else:
            await conn.execute("UPDATE categories SET bb_price = $1 WHERE id = $2", price, cat_id)
    await state.clear()
    result_text = f"{price:.2f}$" if price > 0 else "убрана"
    await message.answer(f"✅ Цена ББ обновлена: {result_text}", parse_mode="HTML")
    categories = await get_all_categories()
    await message.answer(
        "📂 <b>Управление категориями</b>",
        reply_markup=admin_categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_totp_limit")
async def admin_totp_limit_handler(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    current = await get_totp_limit()
    buttons = []
    row = []
    for i in range(1, 6):
        label = f"{'✅ ' if i == current else ''}{i}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"admin_set_totp_{i}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    await callback.message.edit_text(
        f"🔢 <b>Лимит обновлений TOTP</b>\n\n"
        f"Текущий лимит: <b>{current}</b>\n\n"
        f"Выберите новый лимит:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_totp_"))
async def admin_set_totp(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    value = int(callback.data.split("_")[-1])
    await set_totp_limit(value)
    await callback.answer(f"✅ Лимит TOTP установлен: {value}", show_alert=True)
    buttons = []
    row = []
    for i in range(1, 6):
        label = f"{'✅ ' if i == value else ''}{i}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"admin_set_totp_{i}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    await callback.message.edit_text(
        f"🔢 <b>Лимит обновлений TOTP</b>\n\n"
        f"Текущий лимит: <b>{value}</b>\n\n"
        f"Выберите новый лимит:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_reputation")
async def admin_reputation(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    links = await get_all_reputation_links()
    await callback.message.edit_text(
        f"⭐ <b>Управление репутацией</b>\n\n"
        f"📊 Всего ссылок: {len(links)}",
        reply_markup=admin_reputation_kb(links),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_rep_edit_name_"))
async def admin_rep_edit_name(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    link_id = int(callback.data.split("_")[-1])
    link = await get_reputation_link(link_id)
    if not link:
        await callback.answer("❌ Ссылка не найдена", show_alert=True)
        return
    await state.update_data(rep_edit_id=link_id)
    await callback.message.edit_text(
        f"✏️ <b>Изменение названия</b>\n\n"
        f"Текущее: {link['name']}\n\n"
        f"Введите новое название:",
        parse_mode="HTML",
    )
    await state.set_state(AdminReputationStates.waiting_edit_name)
    await callback.answer()


@router.message(AdminReputationStates.waiting_edit_name)
async def process_rep_edit_name(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    link_id = data["rep_edit_id"]
    link = await get_reputation_link(link_id)
    if not link:
        await message.answer("❌ Ссылка не найдена")
        await state.clear()
        return
    await update_reputation_link(link_id, message.text.strip(), link["url"])
    await state.clear()
    await message.answer(f"✅ Название обновлено: {message.text.strip()}", parse_mode="HTML")
    links = await get_all_reputation_links()
    await message.answer(
        f"⭐ <b>Управление репутацией</b>\n\n"
        f"📊 Всего ссылок: {len(links)}",
        reply_markup=admin_reputation_kb(links),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_rep_edit_url_"))
async def admin_rep_edit_url(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    link_id = int(callback.data.split("_")[-1])
    link = await get_reputation_link(link_id)
    if not link:
        await callback.answer("❌ Ссылка не найдена", show_alert=True)
        return
    await state.update_data(rep_edit_id=link_id)
    await callback.message.edit_text(
        f"🔗 <b>Изменение ссылки</b>\n\n"
        f"Текущая: {link['url']}\n\n"
        f"Введите новую ссылку:",
        parse_mode="HTML",
    )
    await state.set_state(AdminReputationStates.waiting_edit_url)
    await callback.answer()


@router.message(AdminReputationStates.waiting_edit_url)
async def process_rep_edit_url(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Введите корректную ссылку (начинается с http).")
        return
    data = await state.get_data()
    link_id = data["rep_edit_id"]
    link = await get_reputation_link(link_id)
    if not link:
        await message.answer("❌ Ссылка не найдена")
        await state.clear()
        return
    await update_reputation_link(link_id, link["name"], url)
    await state.clear()
    await message.answer(f"✅ Ссылка обновлена!", parse_mode="HTML")
    links = await get_all_reputation_links()
    await message.answer(
        f"⭐ <b>Управление репутацией</b>\n\n"
        f"📊 Всего ссылок: {len(links)}",
        reply_markup=admin_reputation_kb(links),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_rep_del_"))
async def admin_rep_delete(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    link_id = int(callback.data.split("_")[-1])
    link = await get_reputation_link(link_id)
    if not link:
        await callback.answer("❌ Ссылка не найдена", show_alert=True)
        return
    await delete_reputation_link(link_id)
    await callback.answer(f"✅ Ссылка «{link['name']}» удалена", show_alert=True)
    links = await get_all_reputation_links()
    await callback.message.edit_text(
        f"⭐ <b>Управление репутацией</b>\n\n"
        f"📊 Всего ссылок: {len(links)}",
        reply_markup=admin_reputation_kb(links),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_rep_") & ~F.data.startswith("admin_rep_edit_") & ~F.data.startswith("admin_rep_del_"))
async def admin_rep_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    link_id = int(callback.data.split("_")[-1])
    link = await get_reputation_link(link_id)
    if not link:
        await callback.answer("❌ Ссылка не найдена", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔗 <b>{link['name']}</b>\n\n"
        f"🌐 Ссылка: {link['url']}",
        reply_markup=admin_reputation_detail_kb(link_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_rep")
async def admin_add_rep(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📝 Введите <b>название</b> для новой ссылки на репутацию:",
        parse_mode="HTML",
    )
    await state.set_state(AdminReputationStates.waiting_name)
    await callback.answer()


@router.message(AdminReputationStates.waiting_name)
async def process_rep_name(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    await state.update_data(rep_name=message.text.strip())
    await message.answer(
        "🔗 Теперь введите <b>ссылку</b> (URL):",
        parse_mode="HTML",
    )
    await state.set_state(AdminReputationStates.waiting_url)


@router.message(AdminReputationStates.waiting_url)
async def process_rep_url(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Введите корректную ссылку (начинается с http).")
        return
    data = await state.get_data()
    name = data["rep_name"]
    await add_reputation_link(name, url)
    await state.clear()
    await message.answer(
        f"✅ Ссылка «{name}» добавлена!",
        parse_mode="HTML",
    )
    links = await get_all_reputation_links()
    await message.answer(
        f"⭐ <b>Управление репутацией</b>\n\n"
        f"📊 Всего ссылок: {len(links)}",
        reply_markup=admin_reputation_kb(links),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_bulk_limits")
async def admin_bulk_limits(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    categories = await get_all_categories()
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=f"📂 {cat['name']} (лимит: {cat.get('max_signatures', 1)})",
            callback_data=f"admin_bulk_lim_cat_{cat['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    await callback.message.edit_text(
        "🔄 <b>Изменить лимиты всех аккаунтов</b>\n\n"
        "Выберите категорию для массового изменения лимита:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bulk_lim_cat_"))
async def admin_bulk_lim_cat(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    category_id = int(callback.data.split("_")[-1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    await state.update_data(bulk_lim_cat_id=category_id)
    await callback.message.edit_text(
        f"🔄 <b>Массовое изменение лимита</b>\n\n"
        f"📂 Категория: {category['name']}\n"
        f"📊 Текущий лимит категории: {category.get('max_signatures', 1)}\n\n"
        f"Введите новый лимит подписей для ВСЕХ аккаунтов в этой категории:",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_bulk_limit_value)
    await callback.answer()


@router.message(AdminAccountStates.waiting_bulk_limit_value)
async def process_bulk_limit_value(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) < 1 or int(text) > 100:
        await message.answer("❌ Введите число от 1 до 100.")
        return
    new_max = int(text)
    data = await state.get_data()
    cat_id = data["bulk_lim_cat_id"]
    category = await get_category(cat_id)
    await bulk_update_all_signature_max(cat_id, new_max)
    await state.clear()
    await message.answer(
        f"✅ Лимит для всех аккаунтов в категории «{category['name']}» обновлён: <b>{new_max}</b>",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_reset_acc")
async def admin_reset_acc(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📱 <b>Сброс наличия аккаунта</b>\n\n"
        "Введите номер телефона (или часть) для поиска аккаунта:",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_reset_account_id)
    await callback.answer()


@router.message(AdminAccountStates.waiting_reset_account_id)
async def process_reset_account(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    phone = message.text.strip()
    accounts = await search_accounts_by_phone(phone)
    await state.clear()
    if not accounts:
        await message.answer(f"🔍 По запросу «{phone}» ничего не найдено.", parse_mode="HTML")
        total = await get_total_accounts_count()
        await message.answer(
            f"📦 <b>Управление аккаунтами</b>\n\n📊 Всего аккаунтов: {total}",
            reply_markup=admin_accounts_menu_kb(),
            parse_mode="HTML",
        )
        return
    buttons = []
    for acc in accounts[:20]:
        buttons.append([InlineKeyboardButton(
            text=f"📱 {acc['phone']}",
            callback_data=f"admin_do_reset_acc_{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    await message.answer(
        f"🔍 <b>Найдено: {len(accounts)}</b>\n\nВыберите аккаунт для сброса наличия:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_do_reset_acc_"))
async def admin_do_reset_acc(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("_")[-1])
    account = await get_account(account_id)
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    await reset_account_availability(account_id)
    await callback.answer(f"✅ Наличие аккаунта {account['phone']} сброшено", show_alert=True)
    total = await get_total_accounts_count()
    await callback.message.edit_text(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_reset_all_accs")
async def admin_reset_all_accs(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🔄 <b>Сброс наличия ВСЕХ аккаунтов</b>\n\n"
        "⚠️ Это обнулит использованные подписи и резервации у ВСЕХ аккаунтов!\n\n"
        "Вы уверены?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, сбросить всё", callback_data="admin_confirm_reset_all"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_accounts"),
            ],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_confirm_reset_all")
async def admin_confirm_reset_all(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await reset_all_accounts_availability()
    await callback.answer("✅ Наличие всех аккаунтов сброшено!", show_alert=True)
    total = await get_total_accounts_count()
    await callback.message.edit_text(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_mass_delete")
async def admin_mass_delete(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.set_state(AdminMassDeleteStates.waiting_phone_list)
    await callback.message.edit_text(
        "🗑 <b>Массовое удаление аккаунтов</b>\n\n"
        "📋 Отправьте список номеров телефонов для удаления.\n"
        "Каждый номер — с новой строки.\n\n"
        "📌 Пример:\n"
        "<code>+79991234567\n"
        "+79997654321\n"
        "89001112233</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_accounts")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminMassDeleteStates.waiting_phone_list)
async def admin_mass_delete_receive_phones(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    phones = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    if not phones:
        await message.answer(
            "❌ Список пуст. Отправьте номера, каждый с новой строки.",
            parse_mode="HTML",
        )
        return
    found, not_found = await find_accounts_by_phones(phones)
    if not found:
        await message.answer(
            "❌ <b>Ни один аккаунт не найден по указанным номерам.</b>\n\n"
            + (f"Не найдены:\n" + "\n".join(f"• {p}" for p in not_found) if not_found else ""),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")],
            ]),
            parse_mode="HTML",
        )
        await state.clear()
        return
    await state.update_data(mass_delete_ids=[a["id"] for a in found], mass_delete_phones=[a["phone"] for a in found])
    await state.set_state(AdminMassDeleteStates.waiting_confirm)
    found_lines = "\n".join(f"• <code>{a['phone']}</code>" for a in found)
    not_found_lines = "\n".join(f"• {p}" for p in not_found) if not_found else ""
    text = (
        f"🗑 <b>Подтверждение удаления</b>\n\n"
        f"✅ Найдено аккаунтов: <b>{len(found)}</b>\n"
        f"{found_lines}\n"
    )
    if not_found_lines:
        text += f"\n❌ Не найдены ({len(not_found)}):\n{not_found_lines}\n"
    text += (
        f"\n⚠️ <b>Будут удалены аккаунты и все связанные данные:</b>\n"
        f"подписи, заказы, тикеты, запросы документов.\n\n"
        f"Подтвердить удаление?"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data="admin_confirm_mass_delete"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_accounts"),
            ],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_confirm_mass_delete", AdminMassDeleteStates.waiting_confirm)
async def admin_confirm_mass_delete(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    data = await state.get_data()
    ids = data.get("mass_delete_ids", [])
    phones = data.get("mass_delete_phones", [])
    await state.clear()
    if not ids:
        await callback.answer("❌ Нет аккаунтов для удаления", show_alert=True)
        return
    deleted = await mass_delete_accounts(ids)
    total = await get_total_accounts_count()
    phones_text = "\n".join(f"• <code>{p}</code>" for p in phones)
    await callback.message.edit_text(
        f"✅ <b>Удалено аккаунтов: {deleted}</b>\n\n"
        f"{phones_text}\n\n"
        f"📊 Осталось аккаунтов: {total}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К аккаунтам", callback_data="admin_accounts")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_totp_"))
async def admin_user_totp(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_user_totp_")[1])
    user = await get_user(telegram_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    user_limit = await get_user_totp_limit(telegram_id)
    global_limit = await get_totp_limit()
    if user_limit is not None:
        current_text = f"{user_limit}" if user_limit > 0 else "♾ Без лимита"
    else:
        current_text = f"{global_limit} (глобальный)"
    await state.update_data(totp_user_id=telegram_id)
    await callback.message.edit_text(
        f"🔢 <b>Лимит TOTP для пользователя</b>\n\n"
        f"👤 {user.get('username') or user.get('full_name') or telegram_id}\n"
        f"📊 Текущий лимит: {current_text}\n"
        f"📊 Глобальный лимит: {global_limit}\n\n"
        f"Введите новый лимит (1-99) или 0 чтобы убрать лимит.\n"
        f"Отправьте «-» для возврата к глобальному.",
        parse_mode="HTML",
    )
    await state.set_state(AdminUserStates.waiting_totp_limit)
    await callback.answer()


@router.message(AdminUserStates.waiting_totp_limit)
async def process_user_totp_limit(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    data = await state.get_data()
    telegram_id = data["totp_user_id"]
    if text == "-":
        await set_user_totp_limit(telegram_id, None)
        await state.clear()
        await message.answer("✅ Лимит TOTP сброшен на глобальный.", parse_mode="HTML")
    else:
        try:
            value = int(text)
            if value < 0 or value > 99:
                raise ValueError
        except ValueError:
            await message.answer("❌ Введите число от 0 до 99 или «-».")
            return
        await set_user_totp_limit(telegram_id, value)
        await state.clear()
        if value == 0:
            await message.answer("✅ Лимит TOTP убран (без ограничений).", parse_mode="HTML")
        else:
            await message.answer(f"✅ Лимит TOTP установлен: {value}", parse_mode="HTML")
    user = await get_user(telegram_id)
    if user:
        await _send_user_profile(message, user)


@router.callback_query(F.data.startswith("admin_user_orders_"))
async def admin_user_orders(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_user_orders_")[1])
    orders = await get_user_orders(telegram_id)
    user = await get_user(telegram_id)
    name = "—"
    if user:
        name = user.get("username") or user.get("full_name") or str(telegram_id)
    if not orders:
        await callback.message.edit_text(
            f"📦 <b>Заказы пользователя {name}</b>\n\n"
            f"📭 Нет заказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_user_{telegram_id}")],
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    status_map = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "pending_review": "🔍", "expired": "⏰"}
    seen_groups = {}
    grouped = []
    for o in orders:
        bg = o.get("batch_group_id")
        if bg:
            if bg not in seen_groups:
                seen_groups[bg] = []
                grouped.append(("group", bg, seen_groups[bg]))
            seen_groups[bg].append(o)
        else:
            grouped.append(("single", None, o))
    buttons = []
    for item in grouped[:30]:
        kind, bg_id, data = item
        if kind == "group":
            group_orders = data
            first = group_orders[0]
            statuses = set(o["status"] for o in group_orders)
            if "active" in statuses:
                si = "🟢"
            elif "preorder" in statuses:
                si = "⏳"
            elif statuses == {"completed"}:
                si = "✅"
            else:
                si = status_map.get(first["status"], "⚪")
            ids_str = ", ".join(f"#{o['id']}" for o in group_orders)
            raw_cat = first.get("category_name", "—")
            cat_emoji = get_category_emoji(raw_cat)
            cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
            total_paid = sum(o.get("price_paid", 0) for o in group_orders)
            date = first["created_at"].strftime("%Y-%m-%d") if first.get("created_at") else "—"
            buttons.append([InlineKeyboardButton(
                text=f"{si} {ids_str} | {cat_name} | {total_paid:.2f}$ | {date}",
                callback_data=f"admin_ubatch_{telegram_id}_{bg_id}"
            )])
        else:
            o = data
            si = status_map.get(o["status"], "⚪")
            raw_cat = o.get("category_name", "—")
            cat_emoji = get_category_emoji(raw_cat)
            cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
            custom = o.get("custom_operator_name")
            if custom:
                cat_name = f"{cat_name} ({custom})"
            date = o["created_at"].strftime("%Y-%m-%d") if o.get("created_at") else "—"
            buttons.append([InlineKeyboardButton(
                text=f"{si} #{o['id']} | {cat_name} | {o.get('price_paid', 0):.2f}$ | {date}",
                callback_data=f"admin_uorder_{telegram_id}_{o['id']}"
            )])
    buttons.append([InlineKeyboardButton(text="🔍 Найти заказ по ID", callback_data=f"admin_search_order_{telegram_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_user_{telegram_id}")])
    await callback.message.edit_text(
        f"📦 <b>Заказы пользователя {name}</b>\n\n"
        f"📊 Всего заказов: {len(orders)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ubatch_"))
async def admin_ubatch(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("admin_ubatch_")[1]
    telegram_id_str, bg_id = parts.split("_", 1)
    telegram_id = int(telegram_id_str)
    from src.db.orders import get_batch_group_orders
    orders = await get_batch_group_orders(bg_id)
    if not orders:
        await callback.answer("❌ Группа заказов не найдена", show_alert=True)
        return
    from src.utils.formatters import format_batch_group_status
    text = format_batch_group_status(orders)
    buttons = []
    for o in orders:
        phone = o.get("phone", "—")
        buttons.append([InlineKeyboardButton(
            text=f"📋 #{o['id']} — {phone}",
            callback_data=f"admin_uorder_{telegram_id}_{o['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data=f"admin_user_orders_{telegram_id}")])
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_search_order_"))
async def admin_search_order(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("_")[-1])
    await state.update_data(search_user_id=telegram_id)
    await state.set_state(AdminOrderSearchStates.waiting_order_id)
    await callback.message.edit_text(
        "🔍 <b>Поиск заказа</b>\n\n"
        "Введите номер заказа (ID):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_user_orders_{telegram_id}")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminOrderSearchStates.waiting_order_id)
async def process_admin_order_search(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    telegram_id = data.get("search_user_id")
    query = (message.text or "").strip()
    if not query:
        back_cb = f"admin_user_orders_{telegram_id}" if telegram_id else "admin_orders"
        await message.answer(
            "❌ Введите запрос для поиска.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)],
            ]),
        )
        return
    await state.clear()
    if telegram_id:
        try:
            order_id = int(query.lstrip("#"))
        except (ValueError, AttributeError):
            await message.answer(
                "❌ Введите числовой ID заказа.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К заказам", callback_data=f"admin_user_orders_{telegram_id}")],
                ]),
            )
            return
        order = await get_order(order_id)
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К заказам", callback_data=f"admin_user_orders_{telegram_id}")],
                ]),
            )
            return
        await _show_search_order_detail(message, order, telegram_id)
        return
    results = await search_orders(query)
    if not results:
        await message.answer(
            f"❌ По запросу «{query}» ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin_global_search_order")],
                [InlineKeyboardButton(text="🔙 К заказам", callback_data="admin_orders")],
            ]),
        )
        return
    if len(results) == 1:
        await _show_search_order_detail(message, results[0], None)
        return
    STATUS_EMOJI = {"active": "🟢", "preorder": "⏳", "completed": "✅", "rejected": "❌", "expired": "⏰", "pending_review": "🟡", "pending_confirmation": "🟡"}
    buttons = []
    for o in results[:30]:
        emoji = STATUS_EMOJI.get(o["status"], "📦")
        user_name = o.get("username") or o.get("full_name") or str(o.get("user_id", ""))
        phone = o.get("phone", "")
        phone_part = f" {phone}" if phone else ""
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} #{o['id']} — {user_name}{phone_part}",
            callback_data=f"admin_order_{o['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin_global_search_order")])
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="admin_orders")])
    await message.answer(
        f"🔍 <b>Результаты поиска «{query}»</b>\n\n"
        f"Найдено: {len(results)} заказов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


async def _show_search_order_detail(message: Message, order: dict, telegram_id: int | None):
    order_id = order["id"]
    order_user_id = order["user_id"]
    status_map = {
        "active": "🟢 Активен", "preorder": "⏳ Предзаказ",
        "completed": "✅ Завершён", "rejected": "❌ Отклонён",
        "pending_review": "🔍 На проверке", "expired": "⏰ Истёк",
    }
    status_text = status_map.get(order["status"], order["status"])
    raw_cat = order.get("category_name", "—")
    cat_emoji = get_category_emoji(raw_cat)
    cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
    custom = order.get("custom_operator_name")
    if custom:
        cat_name = f"{cat_name} ({custom})"
    phone = order.get("phone", "—")
    created = order["created_at"].strftime("%Y-%m-%d %H:%M") if order.get("created_at") else "—"
    expires = order["expires_at"].strftime("%Y-%m-%d %H:%M") if order.get("expires_at") else "—"
    completed = order["completed_at"].strftime("%Y-%m-%d %H:%M") if order.get("completed_at") else "—"
    bb_line = f"🔥 Эксклюзив (ББ): ✅ Да\n" if order.get("is_exclusive") else ""
    totp_refreshes = order.get("totp_refreshes", 0)
    effective = await compute_effective_totp_limit(order_id, order_user_id)
    totp_override = order.get("totp_limit_override")
    totp_limit_text = f"{effective} (индивидуальный)" if totp_override is not None else str(effective)
    totp_remaining = max(0, effective - totp_refreshes)
    text = (
        f"📦 <b>Заказ #{order_id}</b>\n\n"
        f"👤 Пользователь: {order_user_id}\n"
        f"📊 Статус: {status_text}\n"
        f"📂 Категория: {cat_name}\n"
        f"📱 Телефон: <code>{phone}</code>\n"
        f"📊 Подписей: {order.get('signatures_claimed', 0)}/{order.get('total_signatures', 1)}\n"
        f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
        f"{bb_line}\n"
        f"🔢 TOTP: {totp_refreshes} использовано / {totp_limit_text} лимит\n"
        f"🔄 TOTP осталось: {totp_remaining}\n\n"
        f"📅 Создан: {created}\n"
        f"⏰ Истекает: {expires}\n"
        f"✅ Завершён: {completed}"
    )
    buttons = []
    if order["status"] in ("active", "pending_review"):
        buttons.append([
            InlineKeyboardButton(text="➕ TOTP", callback_data=f"admin_add_totp_{order_user_id}_{order_id}"),
            InlineKeyboardButton(text="➖ TOTP", callback_data=f"admin_sub_totp_{order_user_id}_{order_id}"),
        ])
    if order["status"] == "active":
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить (проверка)", callback_data=f"admin_confirm_check_{order_id}")])
        buttons.append([InlineKeyboardButton(text="⏹ Завершить досрочно", callback_data=f"admin_early_complete_{order_id}")])
    if telegram_id:
        buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data=f"admin_user_orders_{telegram_id}")])
        buttons.append([InlineKeyboardButton(text="🔙 К профилю", callback_data=f"admin_user_{telegram_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="👤 К профилю", callback_data=f"admin_user_{order_user_id}")])
        buttons.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin_global_search_order")])
        buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="admin_orders")])
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_uorder_"))
async def admin_user_order_detail(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    parts = callback.data.split("_")
    telegram_id = int(parts[2])
    order_id = int(parts[3])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    status_map = {
        "active": "🟢 Активен", "preorder": "⏳ Предзаказ",
        "completed": "✅ Завершён", "rejected": "❌ Отклонён",
        "pending_review": "🔍 На проверке", "expired": "⏰ Истёк",
    }
    status_text = status_map.get(order["status"], order["status"])
    raw_cat = order.get("category_name", "—")
    cat_emoji = get_category_emoji(raw_cat)
    cat_name = f"{cat_emoji} {raw_cat}" if cat_emoji else raw_cat
    custom = order.get("custom_operator_name")
    if custom:
        cat_name = f"{cat_name} ({custom})"
    phone = order.get("phone", "—")
    created = order["created_at"].strftime("%Y-%m-%d %H:%M") if order.get("created_at") else "—"
    expires = order["expires_at"].strftime("%Y-%m-%d %H:%M") if order.get("expires_at") else "—"
    completed = order["completed_at"].strftime("%Y-%m-%d %H:%M") if order.get("completed_at") else "—"
    bb_line = f"🔥 Эксклюзив (ББ): ✅ Да\n" if order.get("is_exclusive") else ""
    totp_refreshes = order.get("totp_refreshes", 0)
    effective = await compute_effective_totp_limit(order_id, telegram_id)
    totp_override = order.get("totp_limit_override")
    totp_limit_text = f"{effective} (индивидуальный)" if totp_override is not None else str(effective)
    totp_remaining = max(0, effective - totp_refreshes)
    text = (
        f"📦 <b>Заказ #{order_id}</b>\n\n"
        f"📊 Статус: {status_text}\n"
        f"📂 Категория: {cat_name}\n"
        f"📱 Телефон: <code>{phone}</code>\n"
        f"📊 Подписей: {order.get('signatures_claimed', 0)}/{order.get('total_signatures', 1)}\n"
        f"💰 Оплачено: {order.get('price_paid', 0):.2f}$\n"
        f"{bb_line}\n"
        f"🔢 TOTP: {totp_refreshes} использовано / {totp_limit_text} лимит\n"
        f"🔄 TOTP осталось: {totp_remaining}\n\n"
        f"📅 Создан: {created}\n"
        f"⏰ Истекает: {expires}\n"
        f"✅ Завершён: {completed}"
    )
    buttons = []
    if order["status"] in ("active", "pending_review"):
        buttons.append([
            InlineKeyboardButton(text="➕ TOTP", callback_data=f"admin_add_totp_{telegram_id}_{order_id}"),
            InlineKeyboardButton(text="➖ TOTP", callback_data=f"admin_sub_totp_{telegram_id}_{order_id}"),
        ])
    if order["status"] == "active":
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить (проверка)", callback_data=f"admin_confirm_check_{order_id}")])
        buttons.append([InlineKeyboardButton(text="⏹ Завершить досрочно", callback_data=f"admin_early_complete_{order_id}")])
    bg_id = order.get("batch_group_id")
    if bg_id:
        buttons.append([InlineKeyboardButton(text="🔙 К группе", callback_data=f"admin_ubatch_{telegram_id}_{bg_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К заказам", callback_data=f"admin_user_orders_{telegram_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К профилю", callback_data=f"admin_user_{telegram_id}")])
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_add_totp_"))
async def admin_add_totp(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    telegram_id = int(parts[3])
    order_id = int(parts[4])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    totp_refreshes = order.get("totp_refreshes", 0)
    current_limit = await compute_effective_totp_limit(order_id, telegram_id)
    remaining = max(0, current_limit - totp_refreshes)
    await state.update_data(order_id=order_id, telegram_id=telegram_id, current_limit=current_limit, totp_refreshes=totp_refreshes)
    await state.set_state(AdminOrderTotpStates.waiting_totp_amount)
    await callback.message.edit_text(
        f"🔢 <b>Добавить попытки TOTP</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"📊 Использовано: {totp_refreshes}\n"
        f"📊 Текущий лимит: {current_limit}\n"
        f"🔄 Осталось: {remaining}\n\n"
        f"Введите количество попыток для добавления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_uorder_{telegram_id}_{order_id}")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminOrderTotpStates.waiting_totp_amount)
async def process_admin_totp_amount(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["order_id"]
    telegram_id = data["telegram_id"]
    current_limit = data["current_limit"]
    totp_refreshes = data["totp_refreshes"]
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите положительное число.")
        return
    new_limit = current_limit + amount
    await set_order_totp_limit(order_id, new_limit)
    await state.clear()
    new_remaining = max(0, new_limit - totp_refreshes)
    await message.answer(
        f"✅ <b>Попытки TOTP обновлены</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"📊 Новый лимит: {new_limit}\n"
        f"🔄 Осталось попыток: {new_remaining}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 К заказу", callback_data=f"admin_uorder_{telegram_id}_{order_id}")],
            [InlineKeyboardButton(text="🔙 К профилю", callback_data=f"admin_user_{telegram_id}")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_sub_totp_"))
async def admin_sub_totp(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    telegram_id = int(parts[3])
    order_id = int(parts[4])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    totp_refreshes = order.get("totp_refreshes", 0)
    current_limit = await compute_effective_totp_limit(order_id, telegram_id)
    remaining = max(0, current_limit - totp_refreshes)
    await state.update_data(order_id=order_id, telegram_id=telegram_id, current_limit=current_limit, totp_refreshes=totp_refreshes)
    await state.set_state(AdminOrderTotpStates.waiting_totp_subtract)
    await callback.message.edit_text(
        f"🔢 <b>Убрать попытки TOTP</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"📊 Использовано: {totp_refreshes}\n"
        f"📊 Текущий лимит: {current_limit}\n"
        f"🔄 Осталось: {remaining}\n\n"
        f"Введите количество попыток для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_uorder_{telegram_id}_{order_id}")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminOrderTotpStates.waiting_totp_subtract)
async def process_admin_totp_subtract(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["order_id"]
    telegram_id = data["telegram_id"]
    current_limit = data["current_limit"]
    totp_refreshes = data["totp_refreshes"]
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите положительное число.")
        return
    new_limit = max(0, current_limit - amount)
    await set_order_totp_limit(order_id, new_limit)
    await state.clear()
    new_remaining = max(0, new_limit - totp_refreshes)
    await message.answer(
        f"✅ <b>Попытки TOTP обновлены</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"📊 Новый лимит: {new_limit}\n"
        f"🔄 Осталось попыток: {new_remaining}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 К заказу", callback_data=f"admin_uorder_{telegram_id}_{order_id}")],
            [InlineKeyboardButton(text="🔙 К профилю", callback_data=f"admin_user_{telegram_id}")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_faq")
async def admin_faq_menu(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    faq_text = await get_faq_text()
    preview = faq_text[:500] + "..." if len(faq_text) > 500 else faq_text
    await callback.message.edit_text(
        f"📖 <b>Текст инструкции</b>\n\n"
        f"Текущий текст:\n\n{preview}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin_faq_edit")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_faq_edit")
async def admin_faq_edit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📖 <b>Редактирование инструкции</b>\n\n"
        "Отправьте новый текст инструкции.\n"
        "Можно использовать HTML-разметку: <code>&lt;b&gt;жирный&lt;/b&gt;</code>, <code>&lt;i&gt;курсив&lt;/i&gt;</code>, <code>&lt;code&gt;код&lt;/code&gt;</code>\n\n"
        "Отправьте «-» для отмены.",
        parse_mode="HTML",
    )
    await state.set_state(AdminFaqStates.waiting_text)
    await callback.answer()


@router.message(AdminFaqStates.waiting_text)
async def process_faq_text(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if text == "-":
        await state.clear()
        await message.answer("❌ Отменено.", parse_mode="HTML")
        return
    if not text:
        await message.answer("❌ Текст не может быть пустым. Попробуйте ещё раз.")
        return
    await set_faq_text(text)
    await state.clear()
    await message.answer(
        "✅ Текст инструкции обновлён!",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_acc_assign_op_"))
async def admin_acc_assign_op(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("admin_acc_assign_op_")[1])
    operators = await get_all_operators()
    order_ops = [op for op in operators if op.get("role") == "orders"]
    if not order_ops:
        await callback.answer("❌ Нет операторов с ролью «заказы»", show_alert=True)
        return
    buttons = []
    for op in order_ops:
        name = op.get("username") or str(op["telegram_id"])
        buttons.append([InlineKeyboardButton(
            text=f"👷 {name}",
            callback_data=f"admin_acc_setop_{account_id}_{op['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_acc_{account_id}")])
    await callback.message.edit_text(
        f"👷 <b>Назначение оператора</b>\n\n"
        f"📱 Аккаунт #{account_id}\n\n"
        f"Выберите оператора:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_acc_setop_"))
async def admin_acc_setop(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    parts = callback.data.split("_")
    account_id = int(parts[3])
    op_telegram_id = int(parts[4])
    await assign_operator_to_account(account_id, op_telegram_id)
    op = await get_operator(op_telegram_id)
    op_name = op.get("username") or str(op_telegram_id) if op else str(op_telegram_id)
    await callback.answer(f"✅ Оператор {op_name} назначен", show_alert=True)
    account = await get_account(account_id)
    if account:
        callback.data = f"admin_acc_{account_id}"
        await admin_account_detail(callback)


@router.callback_query(F.data.startswith("admin_acc_unassign_op_"))
async def admin_acc_unassign_op(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    account_id = int(callback.data.split("admin_acc_unassign_op_")[1])
    await assign_operator_to_account(account_id, None)
    await callback.answer("✅ Оператор снят", show_alert=True)
    callback.data = f"admin_acc_{account_id}"
    await admin_account_detail(callback)


@router.callback_query(F.data == "admin_bulk_assign")
async def admin_bulk_assign(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    operators = await get_all_operators()
    order_ops = [op for op in operators if op.get("role") == "orders"]
    if not order_ops:
        await callback.answer("❌ Нет операторов с ролью «заказы»", show_alert=True)
        return
    buttons = []
    for op in order_ops:
        name = op.get("username") or str(op["telegram_id"])
        buttons.append([InlineKeyboardButton(
            text=f"👷 {name}",
            callback_data=f"admin_bulkassign_op_{op['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    await callback.message.edit_text(
        "👥 <b>Массовое назначение оператора</b>\n\n"
        "Выберите оператора для назначения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bulkassign_op_"))
async def admin_bulkassign_select_op(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    op_telegram_id = int(callback.data.split("admin_bulkassign_op_")[1])
    op = await get_operator(op_telegram_id)
    op_name = op.get("username") or str(op_telegram_id) if op else str(op_telegram_id)
    await state.update_data(bulk_assign_op_id=op_telegram_id, bulk_assign_op_name=op_name)
    pool = await get_pool()
    async with pool.acquire() as conn:
        unassigned = await conn.fetchval("SELECT COUNT(*) FROM accounts WHERE operator_telegram_id IS NULL")
    await callback.message.edit_text(
        f"👥 <b>Массовое назначение</b>\n\n"
        f"👷 Оператор: <b>{op_name}</b>\n"
        f"📦 Свободных аккаунтов: <b>{unassigned}</b>\n\n"
        f"Введите количество аккаунтов для назначения:",
        parse_mode="HTML",
    )
    await state.set_state(AdminBulkAssignStates.waiting_count)
    await callback.answer()


@router.message(AdminBulkAssignStates.waiting_count)
async def process_bulk_assign_count(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) < 1:
        await message.answer("❌ Введите корректное число (больше 0).")
        return
    count = int(text)
    data = await state.get_data()
    op_telegram_id = data["bulk_assign_op_id"]
    op_name = data["bulk_assign_op_name"]
    assigned = await bulk_assign_operator(op_telegram_id, count)
    await state.clear()
    if assigned == 0:
        await message.answer(
            "❌ Нет свободных (неназначенных) аккаунтов.",
            parse_mode="HTML",
        )
    elif assigned < count:
        await message.answer(
            f"⚠️ Назначено <b>{assigned}</b> из {count} аккаунтов на оператора <b>{op_name}</b>\n\n"
            f"Свободных аккаунтов было недостаточно.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"✅ Назначено {assigned} аккаунтов на оператора <b>{op_name}</b>",
            parse_mode="HTML",
        )
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_mass_priority")
async def admin_mass_priority(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    operators = await get_all_operators()
    if not operators:
        await callback.answer("❌ Нет операторов", show_alert=True)
        return
    buttons = []
    for op in operators:
        name = f"@{op['username']}" if op.get("username") else str(op["telegram_id"])
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"admin_massprio_op_{op['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_accounts")])
    await callback.message.edit_text(
        "⭐ <b>Массовый приоритет</b>\n\n"
        "Выберите оператора для установки приоритета всем его аккаунтам:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_massprio_op_"))
async def admin_massprio_select_op(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    op_id = int(callback.data.split("admin_massprio_op_")[1])
    op = await get_operator(op_id)
    if not op:
        await callback.answer("❌ Оператор не найден", show_alert=True)
        return
    op_name = f"@{op['username']}" if op.get("username") else str(op["telegram_id"])
    await state.update_data(mass_prio_op_id=op_id, mass_prio_op_name=op_name)
    await callback.message.edit_text(
        f"⭐ <b>Массовый приоритет — {op_name}</b>\n\n"
        f"Введите значение приоритета (число, 0 = обычный):",
        parse_mode="HTML",
    )
    await state.set_state(AdminAccountStates.waiting_mass_priority_value)
    await callback.answer()


@router.message(AdminAccountStates.waiting_mass_priority_value)
async def process_mass_priority(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    try:
        priority = int(text)
    except ValueError:
        await message.answer("❌ Введите числовое значение приоритета.")
        return
    data = await state.get_data()
    op_id = data["mass_prio_op_id"]
    op_name = data["mass_prio_op_name"]
    await state.clear()
    updated = await set_mass_priority_by_operator(op_id, priority)
    star = "⭐" if priority > 0 else ""
    await message.answer(
        f"✅ Приоритет {star} <b>{priority}</b> установлен для <b>{updated}</b> аккаунтов ({op_name})",
        parse_mode="HTML",
    )
    total = await get_total_accounts_count()
    await message.answer(
        f"📦 <b>Управление аккаунтами</b>\n\n"
        f"📊 Всего аккаунтов: {total}",
        reply_markup=admin_accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_ticket_limit")
async def admin_ticket_limit_view(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    current = await get_ticket_limit()
    await callback.message.edit_text(
        f"📝 <b>Лимит обращений</b>\n\n"
        f"Текущий лимит: <b>{current}</b> обращений в день\n\n"
        f"Введите новое значение (1-100):",
        parse_mode="HTML",
    )
    await state.set_state(AdminTicketLimitStates.waiting_value)
    await callback.answer()


@router.message(AdminTicketLimitStates.waiting_value)
async def process_ticket_limit(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        if val < 1 or val > 100:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 1 до 100.")
        return
    await set_ticket_limit(val)
    await state.clear()
    tickets = await get_all_tickets()
    await message.answer(
        f"✅ Лимит обращений установлен: <b>{val}</b> в день",
        reply_markup=admin_tickets_kb(tickets),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_reviews")
async def admin_reviews_list(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    reviews = await get_all_reviews()
    bonus = await get_review_bonus()
    if not reviews:
        await callback.message.edit_text(
            f"⭐ <b>Отзывы клиентов</b>\n\n"
            f"📭 Нет отзывов.\n\n"
            f"💰 Бонус за отзыв: <b>{bonus:.2f}$</b>",
            reply_markup=admin_reviews_kb([]),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"⭐ <b>Отзывы клиентов</b> ({len(reviews)})\n\n"
            f"💰 Бонус за отзыв: <b>{bonus:.2f}$</b>",
            reply_markup=admin_reviews_kb(reviews),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^admin_review_\d+$"))
async def admin_review_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    review_id = int(callback.data.split("admin_review_")[1])
    review = await get_review(review_id)
    if not review:
        await callback.answer("❌ Отзыв не найден", show_alert=True)
        return
    user_name = review.get("username") or review.get("full_name") or "—"
    date_str = review["created_at"].strftime("%Y-%m-%d %H:%M") if review.get("created_at") else "—"
    bonus_text = f"\n💰 Бонус: {review['bonus']:.2f}$" if review.get("bonus", 0) > 0 else ""
    await callback.message.edit_text(
        f"⭐ <b>Отзыв #{review['id']}</b>\n\n"
        f"👤 Клиент: @{user_name}\n"
        f"📦 Заказ: #{review['order_id']}\n"
        f"📅 Дата: {date_str}{bonus_text}\n\n"
        f"💬 {review['text']}",
        reply_markup=admin_review_detail_kb(review_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_del_review_"))
async def admin_delete_review(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    review_id = int(callback.data.split("admin_del_review_")[1])
    await delete_review(review_id)
    await callback.answer("✅ Отзыв удалён", show_alert=True)
    reviews = await get_all_reviews()
    bonus = await get_review_bonus()
    await callback.message.edit_text(
        f"⭐ <b>Отзывы клиентов</b> ({len(reviews)})\n\n"
        f"💰 Бонус за отзыв: <b>{bonus:.2f}$</b>",
        reply_markup=admin_reviews_kb(reviews),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_review_bonus")
async def admin_review_bonus_view(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    current = await get_review_bonus()
    await callback.message.edit_text(
        f"💰 <b>Бонус за отзыв</b>\n\n"
        f"Текущий бонус: <b>{current:.2f}$</b>\n\n"
        f"Введите новую сумму (0 = без бонуса):",
        parse_mode="HTML",
    )
    await state.set_state(AdminReviewBonusStates.waiting_value)
    await callback.answer()


@router.message(AdminReviewBonusStates.waiting_value)
async def process_review_bonus(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите корректную сумму (0 или больше).")
        return
    await set_review_bonus(val)
    await state.clear()
    reviews = await get_all_reviews()
    await message.answer(
        f"✅ Бонус за отзыв установлен: <b>{val:.2f}$</b>",
        reply_markup=admin_reviews_kb(reviews),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_referral")
async def admin_referral(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    from src.db.referrals import get_referral_percent
    current = await get_referral_percent()
    await callback.message.edit_text(
        f"👥 <b>Реферальная система</b>\n\n"
        f"Текущий процент: <b>{current:.1f}%</b>\n\n"
        f"Пользователи получают этот процент от каждой покупки приглашённого друга.\n"
        f"Установите 0, чтобы отключить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить процент", callback_data="admin_set_referral_percent")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_referral_percent")
async def admin_set_referral_percent(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📊 Введите процент реферального вознаграждения (0-100):",
        parse_mode="HTML",
    )
    await state.set_state(AdminReferralStates.waiting_percent)
    await callback.answer()


@router.message(AdminReferralStates.waiting_percent)
async def process_referral_percent(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 100:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0 до 100.")
        return
    from src.db.referrals import set_referral_percent
    await set_referral_percent(val)
    await state.clear()
    status = f"{val:.1f}%" if val > 0 else "отключена"
    await message.answer(
        f"✅ Реферальная система: {status}",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_withdraw_dep_"))
async def admin_withdraw_deposit(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    telegram_id = int(callback.data.split("admin_withdraw_dep_")[1])
    has_dep = await has_user_deposit(telegram_id)
    if not has_dep:
        await callback.answer("❌ У пользователя нет депозита", show_alert=True)
        return
    dep_amount = await get_user_deposit_amount(telegram_id)
    await state.set_state(AdminWithdrawDepositStates.waiting_check_link)
    await state.update_data(withdraw_uid=telegram_id, withdraw_amount=dep_amount)
    try:
        await callback.message.edit_text(
            f"💸 <b>Вывод депозита</b>\n\n"
            f"👤 ID: <code>{telegram_id}</code>\n"
            f"💰 Сумма: <b>{dep_amount:.2f}$</b>\n\n"
            f"📎 Отправьте ссылку на чек для пользователя:",
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(AdminWithdrawDepositStates.waiting_check_link)
async def process_withdraw_check_link(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await message.answer("❌ Отправьте ссылку на чек (текстом).")
        return
    check_link = message.text.strip()
    if not check_link.startswith("http"):
        await message.answer("❌ Ссылка должна начинаться с http:// или https://")
        return
    data = await state.get_data()
    telegram_id = data["withdraw_uid"]
    dep_amount = data["withdraw_amount"]
    await state.clear()
    await delete_user_deposit(telegram_id)
    try:
        from src.bot.instance import bot
        await bot.send_message(
            telegram_id,
            f"💸 <b>Возврат депозита</b>\n\n"
            f"Ваш депозит <b>{dep_amount:.2f}$</b> был возвращён.\n\n"
            f"🔗 Чек: {check_link}",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await message.answer(f"✅ Депозит {dep_amount:.2f}$ снят, ссылка отправлена пользователю.")
    user = await get_user(telegram_id)
    if user:
        await _send_user_profile(message, user, edit=False)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "admin_channels")
async def admin_channels(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await state.clear()
    from src.db.channels import get_required_channels
    channels = await get_required_channels()
    await callback.message.edit_text(
        f"📢 <b>Обязательные подписки</b>\n\n"
        f"Каналов: {len(channels)}\n\n"
        f"Пользователь не сможет пользоваться ботом,\n"
        f"пока не подпишется на все каналы из списка.",
        reply_markup=admin_channels_kb(channels),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_channel_"))
async def admin_channel_detail(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    ch_id = int(callback.data.split("admin_channel_")[1])
    from src.db.channels import get_required_channel
    ch = await get_required_channel(ch_id)
    if not ch:
        await callback.answer("❌ Канал не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"📢 <b>{ch['title']}</b>\n\n"
        f"🆔 ID канала: <code>{ch['channel_id']}</code>\n"
        f"🔗 Ссылка: {ch['url']}",
        reply_markup=admin_channel_detail_kb(ch_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_channel")
async def admin_add_channel(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📢 <b>Добавление канала</b>\n\n"
        "Введите ID канала (числовой, например -1001234567890).\n\n"
        "Бот должен быть администратором в этом канале/чате.",
        parse_mode="HTML",
    )
    await state.set_state(AdminChannelStates.waiting_channel_id)
    await callback.answer()


@router.message(AdminChannelStates.waiting_channel_id)
async def process_channel_id(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip()
    try:
        channel_id = int(text)
    except ValueError:
        await message.answer("❌ Введите числовой ID канала.")
        return
    await state.update_data(new_channel_id=channel_id)
    await message.answer(
        "📝 Введите название канала/чата (для отображения пользователю):",
        parse_mode="HTML",
    )
    await state.set_state(AdminChannelStates.waiting_channel_title)


@router.message(AdminChannelStates.waiting_channel_title)
async def process_channel_title(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    title = message.text.strip()
    await state.update_data(new_channel_title=title)
    await message.answer(
        "🔗 Введите ссылку на канал/чат (например, https://t.me/channel_name):",
        parse_mode="HTML",
    )
    await state.set_state(AdminChannelStates.waiting_channel_url)


@router.message(AdminChannelStates.waiting_channel_url)
async def process_channel_url(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    url = message.text.strip()
    data = await state.get_data()
    channel_id = data["new_channel_id"]
    title = data["new_channel_title"]
    await state.clear()
    from src.db.channels import add_required_channel
    await add_required_channel(channel_id, title, url)
    from src.db.channels import get_required_channels
    channels = await get_required_channels()
    await message.answer(
        f"✅ Канал «{title}» добавлен!\n\n"
        f"📢 <b>Обязательные подписки</b>\n"
        f"Каналов: {len(channels)}",
        reply_markup=admin_channels_kb(channels),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_del_channel_"))
async def admin_del_channel(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    ch_id = int(callback.data.split("admin_del_channel_")[1])
    from src.db.channels import delete_required_channel, get_required_channels
    await delete_required_channel(ch_id)
    channels = await get_required_channels()
    await callback.message.edit_text(
        f"✅ Канал удалён.\n\n"
        f"📢 <b>Обязательные подписки</b>\n"
        f"Каналов: {len(channels)}",
        reply_markup=admin_channels_kb(channels),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_admins")
async def admin_admins_list(callback: CallbackQuery):
    if not await is_owner(callback.from_user.id):
        return
    admins = await get_all_admins()
    lines = ["👑 <b>Управление админами</b>\n"]
    for adm in admins:
        role_label = "👑 Владелец" if adm["role"] == "owner" else "🔹 Админ"
        lines.append(f"{role_label}: <code>{adm['telegram_id']}</code>")
    text = "\n".join(lines)
    buttons = []
    for adm in admins:
        if adm["role"] != "owner":
            buttons.append([InlineKeyboardButton(
                text=f"❌ Удалить {adm['telegram_id']}",
                callback_data=f"admin_remove_admin_{adm['telegram_id']}",
            )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: CallbackQuery, state: FSMContext):
    if not await is_owner(callback.from_user.id):
        return
    await callback.message.edit_text(
        "👑 <b>Добавление админа</b>\n\n"
        "Введите Telegram ID нового админа:",
        parse_mode="HTML",
    )
    await state.set_state(AdminAdminStates.waiting_admin_id)
    await callback.answer()


@router.message(AdminAdminStates.waiting_admin_id)
async def admin_add_admin_process(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ Введите корректный Telegram ID (число).")
        return
    new_admin_id = int(text)
    await add_admin(new_admin_id)
    await state.clear()
    await message.answer(
        f"✅ Админ <code>{new_admin_id}</code> добавлен!",
        parse_mode="HTML",
    )
    admins = await get_all_admins()
    lines = ["👑 <b>Управление админами</b>\n"]
    for adm in admins:
        role_label = "👑 Владелец" if adm["role"] == "owner" else "🔹 Админ"
        lines.append(f"{role_label}: <code>{adm['telegram_id']}</code>")
    msg_text = "\n".join(lines)
    buttons = []
    for adm in admins:
        if adm["role"] != "owner":
            buttons.append([InlineKeyboardButton(
                text=f"❌ Удалить {adm['telegram_id']}",
                callback_data=f"admin_remove_admin_{adm['telegram_id']}",
            )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(msg_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_remove_admin_"))
async def admin_remove_admin_handler(callback: CallbackQuery):
    if not await is_owner(callback.from_user.id):
        return
    target_id = int(callback.data.split("admin_remove_admin_")[1])
    admins = await get_all_admins()
    target_admin = next((a for a in admins if a["telegram_id"] == target_id), None)
    if target_admin and target_admin["role"] == "owner":
        await callback.answer("❌ Нельзя удалить владельца!", show_alert=True)
        return
    admin_ids = await get_admin_ids()
    if len(admin_ids) <= 1:
        await callback.answer("❌ Должен остаться хотя бы один админ!", show_alert=True)
        return
    await remove_admin(target_id)
    admins = await get_all_admins()
    lines = ["👑 <b>Управление админами</b>\n"]
    for adm in admins:
        role_label = "👑 Владелец" if adm["role"] == "owner" else "🔹 Админ"
        lines.append(f"{role_label}: <code>{adm['telegram_id']}</code>")
    text = "\n".join(lines)
    buttons = []
    for adm in admins:
        if adm["role"] != "owner":
            buttons.append([InlineKeyboardButton(
                text=f"❌ Удалить {adm['telegram_id']}",
                callback_data=f"admin_remove_admin_{adm['telegram_id']}",
            )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"✅ Админ <code>{target_id}</code> удалён.\n\n{text}",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats_admins")
async def admin_stats_admins_list(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    admins = await get_all_admins()
    if not admins:
        await callback.answer("❌ Нет админов", show_alert=True)
        return
    buttons = []
    for adm in admins:
        role_label = "👑" if adm["role"] == "owner" else "🔹"
        buttons.append([InlineKeyboardButton(
            text=f"{role_label} {adm['telegram_id']}",
            callback_data=f"admin_stat_view_{adm['telegram_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_stats")])
    await callback.message.edit_text(
        "👑 <b>Статистика админов</b>\n\n"
        "Выберите админа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stat_view_"))
async def admin_stat_view(callback: CallbackQuery):
    if not await AdminFilter.check(callback.from_user.id):
        return
    target_id = int(callback.data.split("admin_stat_view_")[1])
    from datetime import timezone as _tz
    msk = _tz(timedelta(hours=3))
    today = str(datetime.now(msk).date())
    week_ago = str(datetime.now(msk).date() - timedelta(days=7))
    month_ago = str(datetime.now(msk).date() - timedelta(days=30))
    stats_today, stats_week, stats_month, stats_all = await asyncio.gather(
        get_admin_stats(target_id, date_from=today),
        get_admin_stats(target_id, date_from=week_ago, date_to=today),
        get_admin_stats(target_id, date_from=month_ago, date_to=today),
        get_admin_stats(target_id),
    )

    text = (
        f"👑 <b>Статистика админа</b> <code>{target_id}</code>\n\n"
        f"📅 <b>Сегодня:</b>\n"
        f"   📦 Загружено аккаунтов: {stats_today['accounts_added']}\n"
        f"   📝 Продано подписей: {stats_today['signatures_sold']}\n"
        f"   💰 Выручка: ${stats_today['revenue']:.2f}\n\n"
        f"📅 <b>За неделю:</b>\n"
        f"   📦 Загружено аккаунтов: {stats_week['accounts_added']}\n"
        f"   📝 Продано подписей: {stats_week['signatures_sold']}\n"
        f"   💰 Выручка: ${stats_week['revenue']:.2f}\n\n"
        f"📅 <b>За месяц:</b>\n"
        f"   📦 Загружено аккаунтов: {stats_month['accounts_added']}\n"
        f"   📝 Продано подписей: {stats_month['signatures_sold']}\n"
        f"   💰 Выручка: ${stats_month['revenue']:.2f}\n\n"
        f"📅 <b>За всё время:</b>\n"
        f"   📦 Загружено аккаунтов: {stats_all['accounts_added']}\n"
        f"   📝 Продано подписей: {stats_all['signatures_sold']}\n"
        f"   💰 Выручка: ${stats_all['revenue']:.2f}"
    )
    buttons = [
        [InlineKeyboardButton(text="📅 За конкретную дату", callback_data=f"admin_stat_date_{target_id}")],
        [InlineKeyboardButton(text="🔙 К списку админов", callback_data="admin_stats_admins")],
    ]
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stat_date_"))
async def admin_stat_date_start(callback: CallbackQuery, state: FSMContext):
    if not await AdminFilter.check(callback.from_user.id):
        return
    target_id = int(callback.data.split("admin_stat_date_")[1])
    await state.update_data(admin_stat_target_id=target_id)
    await callback.message.edit_text(
        "📅 Введите дату или период:\n\n"
        "Формат: <code>ГГГГ-ММ-ДД</code> (один день)\n"
        "или: <code>ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code> (период)",
        parse_mode="HTML",
    )
    await state.set_state(AdminStatsStates.waiting_admin_stats_date)
    await callback.answer()


@router.message(AdminStatsStates.waiting_admin_stats_date)
async def admin_stat_date_process(message: Message, state: FSMContext):
    if not await AdminFilter.check(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    data = await state.get_data()
    target_id = data["admin_stat_target_id"]

    single_match = re.match(r"^(\d{4}-\d{2}-\d{2})$", text)
    range_match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})$", text)

    if range_match:
        date_from = range_match.group(1)
        date_to = range_match.group(2)
        if date_from > date_to:
            await message.answer("❌ Дата начала должна быть раньше даты окончания.")
            return
        period_label = f"{date_from} — {date_to}"
    elif single_match:
        date_from = single_match.group(1)
        date_to = date_from
        period_label = date_from
    else:
        await message.answer("❌ Неверный формат. Используйте: <code>ГГГГ-ММ-ДД</code> или <code>ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>", parse_mode="HTML")
        return

    await state.clear()
    stats = await get_admin_stats(target_id, date_from=date_from, date_to=date_to)

    result_text = (
        f"👑 <b>Статистика админа</b> <code>{target_id}</code>\n"
        f"📅 Период: {period_label}\n\n"
        f"📦 Загружено аккаунтов: {stats['accounts_added']}\n"
        f"📝 Продано подписей: {stats['signatures_sold']}\n"
        f"💰 Выручка: ${stats['revenue']:.2f}"
    )
    buttons = [
        [InlineKeyboardButton(text="🔙 К статистике админа", callback_data=f"admin_stat_view_{target_id}")],
        [InlineKeyboardButton(text="🔙 К списку админов", callback_data="admin_stats_admins")],
    ]
    await message.answer(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
