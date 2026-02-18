import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.db.users import get_or_create_user, is_user_blocked
from src.keyboards.user_kb import main_menu_kb, subscription_required_kb
from src.db.admins import is_admin

router = Router()


async def check_user_subscriptions(bot, user_id: int) -> list[dict]:
    from src.db.channels import get_required_channels
    channels = await get_required_channels()
    if not channels:
        return []
    if await is_admin(user_id):
        return []

    async def _check_one(ch):
        try:
            member = await bot.get_chat_member(ch["channel_id"], user_id)
            return None if member.status not in ("left", "kicked") else ch
        except Exception:
            return ch

    results = await asyncio.gather(*[_check_one(ch) for ch in channels])
    return [ch for ch in results if ch is not None]


async def send_subscription_required(message_or_callback, not_subscribed: list[dict]):
    text = (
        "📢 <b>Для использования бота необходимо подписаться на каналы:</b>\n\n"
        "После подписки нажмите «Проверить подписку»."
    )
    kb = subscription_required_kb(not_subscribed)
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    args = message.text.split(maxsplit=1)
    referral_arg = args[1] if len(args) > 1 else None

    await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if referral_arg and referral_arg.startswith("ref_"):
        try:
            referrer_id = int(referral_arg[4:])
            from src.db.referrals import set_referrer
            await set_referrer(message.from_user.id, referrer_id)
        except (ValueError, Exception):
            pass

    blocked = await is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer(
            "🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.",
            parse_mode="HTML",
        )
        return
    from src.bot.instance import bot
    not_subscribed = await check_user_subscriptions(bot, message.from_user.id)
    if not_subscribed:
        await send_subscription_required(message, not_subscribed)
        return
    wave_msg = await message.answer("👋")
    await asyncio.sleep(1)
    await wave_msg.delete()
    await message.answer(
        f"Добро пожаловать, <b>{message.from_user.first_name}</b>!\n\n"
        f"🏪 Это бот-магазин для подписания SIM-карт.\n"
        f"Выберите нужный раздел в меню ниже.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "check_subscription")
async def check_subscription_cb(callback: CallbackQuery):
    from src.bot.instance import bot
    not_subscribed = await check_user_subscriptions(bot, callback.from_user.id)
    if not_subscribed:
        await callback.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
        await send_subscription_required(callback, not_subscribed)
        return
    await callback.message.edit_text(
        "✅ <b>Подписка подтверждена!</b>\n\n"
        "Добро пожаловать!",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "user_back_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
