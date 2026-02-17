import math

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from src.states.user_states import ReviewStates
from src.db.reviews import create_review, has_review_for_order, get_reviews_page
from src.db.orders import get_order
from src.db.settings import get_review_bonus
from src.db.users import update_balance, is_user_blocked
from src.db.admins import get_admin_ids

router = Router()

REVIEWS_PER_PAGE = 5


def _reviews_page_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"reviews_page_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"reviews_page_{page + 1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 К репутации", callback_data="back_to_reputation")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_reviews_page(reviews: list[dict], page: int, total: int) -> str:
    lines = [f"⭐ <b>Отзывы клиентов</b> ({total} всего)\n"]
    for r in reviews:
        date = r["created_at"].strftime("%Y-%m-%d") if r["created_at"] else ""
        bonus_line = f"\n💰 Бонус: <b>{r['bonus']:.2f}$</b>" if r["bonus"] and r["bonus"] > 0 else ""
        lines.append(f"📅 {date}{bonus_line}\n💬 {r['text'][:300]}\n")
    return "\n".join(lines)


@router.callback_query(F.data == "show_reviews")
async def show_reviews(callback: CallbackQuery):
    reviews, total = await get_reviews_page(offset=0, limit=REVIEWS_PER_PAGE)
    if not reviews:
        await callback.message.edit_text("Пока нет отзывов", parse_mode="HTML")
        await callback.answer()
        return
    total_pages = math.ceil(total / REVIEWS_PER_PAGE)
    text = _format_reviews_page(reviews, 0, total)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_reviews_page_kb(0, total_pages))
    await callback.answer()


@router.callback_query(F.data.startswith("reviews_page_"))
async def reviews_pagination(callback: CallbackQuery):
    page = int(callback.data.split("reviews_page_")[1])
    offset = page * REVIEWS_PER_PAGE
    reviews, total = await get_reviews_page(offset=offset, limit=REVIEWS_PER_PAGE)
    total_pages = max(1, math.ceil(total / REVIEWS_PER_PAGE))
    if not reviews:
        await callback.message.edit_text("Пока нет отзывов", parse_mode="HTML")
        await callback.answer()
        return
    if page >= total_pages:
        page = max(0, total_pages - 1)
        offset = page * REVIEWS_PER_PAGE
        reviews, total = await get_reviews_page(offset=offset, limit=REVIEWS_PER_PAGE)
    text = _format_reviews_page(reviews, page, total)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_reviews_page_kb(page, total_pages))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("leave_review_"))
async def start_review(callback: CallbackQuery, state: FSMContext):
    blocked = await is_user_blocked(callback.from_user.id)
    if blocked:
        await callback.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
        return
    order_id = int(callback.data.split("leave_review_")[1])
    order = await get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        return
    if order["status"] != "completed":
        await callback.answer("❌ Заказ ещё не завершён", show_alert=True)
        return
    already = await has_review_for_order(callback.from_user.id, order_id)
    if already:
        await callback.answer("ℹ️ Вы уже оставили отзыв по этому заказу", show_alert=True)
        return
    bonus = await get_review_bonus()
    bonus_text = f"\n💰 За отзыв вы получите <b>{bonus:.2f}$</b> на баланс!" if bonus > 0 else ""
    await callback.message.edit_text(
        f"⭐ <b>Оставить отзыв по заказу #{order_id}</b>\n\n"
        f"Напишите ваш отзыв о сервисе:{bonus_text}",
        parse_mode="HTML",
    )
    await state.update_data(review_order_id=order_id)
    await state.set_state(ReviewStates.waiting_text)
    await callback.answer()


@router.message(ReviewStates.waiting_text)
async def process_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("review_order_id")
    if not order_id:
        await state.clear()
        return
    already = await has_review_for_order(message.from_user.id, order_id)
    if already:
        await message.answer("ℹ️ Вы уже оставили отзыв по этому заказу.")
        await state.clear()
        return
    bonus = await get_review_bonus()
    review_id = await create_review(message.from_user.id, order_id, message.text, bonus)
    if bonus > 0:
        await update_balance(message.from_user.id, bonus)
        await message.answer(
            f"⭐ <b>Спасибо за отзыв!</b>\n\n"
            f"💰 Вам начислен бонус <b>{bonus:.2f}$</b> на баланс.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "⭐ <b>Спасибо за отзыв!</b>",
            parse_mode="HTML",
        )
    await state.clear()
    try:
        from src.bot.instance import bot
        user_name = message.from_user.username or message.from_user.full_name or str(message.from_user.id)
        bonus_line = f"\n💰 Бонус: {bonus:.2f}$" if bonus > 0 else ""
        notify_text = (
            f"⭐ <b>Новый отзыв #{review_id}</b>\n\n"
            f"👤 Клиент: @{user_name}\n"
            f"📦 Заказ: #{order_id}{bonus_line}\n\n"
            f"💬 {message.text[:500]}"
        )
        for admin_id in await get_admin_ids():
            try:
                await bot.send_message(admin_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass
