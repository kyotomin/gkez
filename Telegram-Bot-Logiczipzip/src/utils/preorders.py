import asyncio
import logging

from src.db.orders import get_pending_preorders, fulfill_preorder, fulfill_preorder_multi, create_order, get_order
from src.db.accounts import try_reserve_account_exclusive, try_reserve_accounts_multi

logger = logging.getLogger(__name__)

_fulfillment_lock = asyncio.Lock()


async def _notify_fulfillment(bot, po, accounts_info: list[dict], order_ids: list[int]):
    cat_name = po.get("category_name", "—")
    custom_op = po.get("custom_operator_name")
    is_exclusive = po.get("is_exclusive", 0)
    if custom_op:
        cat_name = f"{cat_name} ({custom_op})"
    if is_exclusive:
        cat_name = f"{cat_name} (ББ)"

    phones_text = "\n".join(f"📱 <code>{a['phone']}</code>" for a in accounts_info)
    orders_text = ", ".join(f"#{oid}" for oid in order_ids)

    try:
        await bot.send_message(
            po["user_id"],
            f"✅ <b>Предзаказ #{po['id']} выполнен!</b>\n\n"
            f"📂 Категория: {cat_name}\n"
            f"{phones_text}\n"
            f"📋 Заказы: {orders_text}\n\n"
            f"Аккаунты закреплены за вами на 72ч.\n"
            f"Нажмите «Получить подпись» в заказе.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        from src.db.admins import get_admin_ids
        from src.db.operators import get_preorder_operator_ids
        admin_ids = await get_admin_ids()
        notify_text = (
            f"📦 <b>Предзаказ #{po['id']} выполнен</b>\n\n"
            f"👤 Пользователь: {po['user_id']}\n"
            f"📂 Категория: {cat_name}\n"
            f"{phones_text}\n"
            f"📋 Заказы: {orders_text}"
        )
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
        op_ids = await get_preorder_operator_ids()
        for op_id in op_ids:
            try:
                await bot.send_message(op_id, notify_text, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass


async def _fulfill_exclusive(bot, po) -> bool:
    account = await try_reserve_account_exclusive(po["category_id"], po["user_id"])
    if not account:
        return False
    await fulfill_preorder(po["id"], account["id"])
    await _notify_fulfillment(bot, po, [account], [po["id"]])
    return True


async def _fulfill_regular(bot, po) -> bool:
    qty = po.get("total_signatures", 1)
    allocations = await try_reserve_accounts_multi(po["category_id"], po["user_id"], qty)
    if not allocations:
        return False

    if len(allocations) == 1:
        await fulfill_preorder(po["id"], allocations[0]["id"])
        await _notify_fulfillment(bot, po, allocations, [po["id"]])
    else:
        order_ids = await fulfill_preorder_multi(po, allocations)
        await _notify_fulfillment(bot, po, allocations, order_ids)

    return True


async def run_preorder_fulfillment(bot):
    if not bot:
        logger.warning("run_preorder_fulfillment: bot is None, skipping")
        return 0

    if _fulfillment_lock.locked():
        return 0

    async with _fulfillment_lock:
        preorders = await get_pending_preorders()
        fulfilled = 0
        for po in preorders:
            try:
                is_exclusive = po.get("is_exclusive", 0)
                if is_exclusive:
                    success = await _fulfill_exclusive(bot, po)
                else:
                    success = await _fulfill_regular(bot, po)

                if success:
                    fulfilled += 1
                    logger.info(f"Fulfilled preorder #{po['id']} (exclusive={is_exclusive})")
            except Exception as e:
                logger.error(f"Preorder fulfill error #{po['id']}: {e}")
        return fulfilled
