import asyncio
import json
import logging

from src.utils.cryptobot import check_invoice_paid
from src.db.payments import get_payment_by_invoice, update_payment_status
from src.db.users import update_balance

logger = logging.getLogger(__name__)

_active_checks: dict[int, asyncio.Task] = {}
_payment_semaphore = asyncio.Semaphore(30)


async def start_payment_check(invoice_id: int):
    if invoice_id in _active_checks:
        return
    task = asyncio.create_task(_poll_payment(invoice_id))
    _active_checks[invoice_id] = task


async def _poll_payment(invoice_id: int):
    async with _payment_semaphore:
        await _poll_payment_inner(invoice_id)


async def _poll_payment_inner(invoice_id: int):
    try:
        for _ in range(360):
            await asyncio.sleep(5)
            is_paid = await check_invoice_paid(invoice_id)
            if is_paid:
                payment = await get_payment_by_invoice(invoice_id)
                if payment and payment["status"] == "pending":
                    await update_payment_status(invoice_id, "paid")
                    purpose = payment.get("purpose", "balance")
                    if purpose == "order":
                        await _process_order_payment(payment)
                    else:
                        await update_balance(payment["user_id"], payment["amount"])
                        try:
                            from src.bot.instance import bot
                            await bot.send_message(
                                payment["user_id"],
                                f"✅ <b>Баланс пополнен!</b>\n\n"
                                f"💵 Сумма: {payment['amount']:.2f} USDT\n\n"
                                f"Средства зачислены на ваш баланс.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                break
        else:
            payment = await get_payment_by_invoice(invoice_id)
            if payment and payment["status"] == "pending":
                await update_payment_status(invoice_id, "expired")
                if payment.get("purpose") == "order":
                    try:
                        from src.bot.instance import bot
                        await bot.send_message(
                            payment["user_id"],
                            "⏰ <b>Время оплаты истекло.</b>\n\n"
                            "Счёт на оплату заказа больше не действителен.\n"
                            "Вы можете оформить заказ заново.",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Payment check error for invoice {invoice_id}: {e}")
    finally:
        _active_checks.pop(invoice_id, None)


async def _process_order_payment(payment: dict):
    try:
        meta = json.loads(payment.get("payment_meta", "{}"))
    except (json.JSONDecodeError, TypeError):
        await update_balance(payment["user_id"], payment["amount"])
        return

    order_type = meta.get("type", "regular")
    category_id = meta.get("category_id")
    qty = meta.get("qty", 1)
    custom_op = meta.get("custom_operator_name")
    is_bb = meta.get("is_bb", False)

    from src.bot.instance import bot
    from src.db.categories import get_category
    from src.db.accounts import try_reserve_account, try_reserve_account_exclusive, try_reserve_accounts_multi
    from src.db.orders import create_order, create_preorder, get_order
    from src.db.settings import is_admin_notifications_enabled
    from src.db.operators import get_order_operator_ids
    from src.db.admins import get_admin_ids
    from src.utils.formatters import format_order_card_admin
    from src.keyboards.user_kb import order_detail_kb, go_to_orders_kb

    category = await get_category(category_id)
    if not category:
        await update_balance(payment["user_id"], payment["amount"])
        try:
            await bot.send_message(
                payment["user_id"],
                "❌ Категория не найдена. Средства зачислены на баланс.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    user_id = payment["user_id"]
    total_price = payment["amount"]
    order_id = None
    orders_created = []

    if is_bb:
        from src.db.orders import generate_batch_group_id
        bb_pack_qty = meta.get("bb_pack_qty", 1)
        bb_price = category.get("bb_price", total_price / bb_pack_qty if bb_pack_qty > 0 else total_price)
        max_sigs = category.get("max_signatures", 1)
        bg_id = generate_batch_group_id() if bb_pack_qty > 1 else None
        bb_order_ids = []
        bb_preorder_ids = []
        try:
            for _ in range(bb_pack_qty):
                account = await try_reserve_account_exclusive(category_id, user_id)
                if not account:
                    oid = await create_preorder(user_id, category_id, bb_price, max_sigs, is_exclusive=True, batch_group_id=bg_id)
                    bb_preorder_ids.append(oid)
                else:
                    batch_size = account.get("batch_size", max_sigs)
                    oid = await create_order(user_id, account["id"], category_id, bb_price, batch_size, is_exclusive=True, batch_group_id=bg_id)
                    bb_order_ids.append(oid)
        except Exception:
            created_count = len(bb_order_ids) + len(bb_preorder_ids)
            refund = bb_price * (bb_pack_qty - created_count)
            if refund > 0:
                await update_balance(user_id, refund)
        lines = [f"✅ <b>Оплата получена!</b>\n"]
        if bb_order_ids:
            ids_str = ", ".join(f"#{oid}" for oid in bb_order_ids)
            lines.append(f"✅ <b>Заказы {ids_str} оформлены! (Тариф ББ🔥)</b>")
        if bb_preorder_ids:
            ids_str = ", ".join(f"#{oid}" for oid in bb_preorder_ids)
            lines.append(f"⏳ <b>Предзаказы {ids_str} оформлены!</b>")
        lines.append(f"\n📂 Категория: {category['name']} (ББ)")
        lines.append(f"📦 Пачек: {bb_pack_qty}")
        lines.append(f"💰 Сумма: {total_price:.2f}$")
        if bb_preorder_ids:
            lines.append(f"\n⏰ Для предзаказов ожидайте — заказы будут выполнены автоматически.")
        if bb_order_ids:
            lines.append(f"\n📝 Нажмите «📋 Мои заказы» чтобы начать работу.")
        try:
            await bot.send_message(user_id, "\n".join(lines), reply_markup=go_to_orders_kb(), parse_mode="HTML")
        except Exception:
            pass
        for oid in bb_order_ids:
            o = await get_order(oid)
            if o:
                orders_created.append((o, None))
    elif order_type == "custom":
        allocations = await try_reserve_accounts_multi(category_id, user_id, qty)
        if not allocations:
            order_id = await create_preorder(user_id, category_id, total_price, qty, custom_op)
            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>Оплата получена!</b>\n\n"
                    f"⏳ <b>Предзаказ #{order_id} оформлен!</b>\n\n"
                    f"📂 Категория: Любой другой\n"
                    f"🏢 Оператор: <b>{custom_op}</b>\n"
                    f"📊 Подписей: {qty}\n"
                    f"💰 Сумма: {total_price:.2f}$\n\n"
                    f"⏰ Как только аккаунт появится — заказ будет выполнен автоматически.",
                    reply_markup=go_to_orders_kb(),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        from src.db.orders import generate_batch_group_id
        bg_id = generate_batch_group_id() if len(allocations) > 1 else None
        price_per = category.get("price", 0)
        orders_created = []
        for alloc in allocations:
            aq = alloc["batch_size"]
            ap = price_per * aq
            oid = await create_order(user_id, alloc["id"], category_id, ap, aq, custom_op, batch_group_id=bg_id)
            o = await get_order(oid)
            orders_created.append((o, alloc))
        await _send_multi_order_message(bot, user_id, orders_created, category, total_price, qty, custom_op=custom_op)
    else:
        allocations = await try_reserve_accounts_multi(category_id, user_id, qty)
        if not allocations:
            order_id = await create_preorder(user_id, category_id, total_price, qty)
            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>Оплата получена!</b>\n\n"
                    f"⏳ <b>Предзаказ #{order_id} оформлен!</b>\n\n"
                    f"📂 Категория: {category['name']}\n"
                    f"📊 Подписей: {qty}\n"
                    f"💰 Сумма: {total_price:.2f}$\n\n"
                    f"⏰ Как только аккаунт появится — заказ будет выполнен автоматически.",
                    reply_markup=go_to_orders_kb(),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        from src.db.orders import generate_batch_group_id
        bg_id = generate_batch_group_id() if len(allocations) > 1 else None
        price_per = category.get("price", 0)
        orders_created = []
        for alloc in allocations:
            aq = alloc["batch_size"]
            ap = price_per * aq
            oid = await create_order(user_id, alloc["id"], category_id, ap, aq, batch_group_id=bg_id)
            o = await get_order(oid)
            orders_created.append((o, alloc))
        await _send_multi_order_message(bot, user_id, orders_created, category, total_price, qty)

    all_orders = []
    if orders_created:
        all_orders = [o for o, _ in orders_created]

    if all_orders:
        try:
            user_obj = await bot.get_chat(user_id)
            user_name = user_obj.username or user_obj.full_name or str(user_id)
            if is_bb and len(all_orders) >= 1:
                from src.utils.formatters import format_bb_batch_card_admin
                notify_text = format_bb_batch_card_admin(all_orders, user_name)
                for admin_id in await get_admin_ids():
                    notify_enabled = await is_admin_notifications_enabled(admin_id)
                    if notify_enabled:
                        try:
                            await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                        except Exception:
                            pass
                op_ids = await get_order_operator_ids()
                for op_id in op_ids:
                    try:
                        await bot.send_message(op_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
            else:
                from src.utils.formatters import format_batch_card_admin
                notify_text = format_batch_card_admin(all_orders, user_name)
                for admin_id in await get_admin_ids():
                    notify_enabled = await is_admin_notifications_enabled(admin_id)
                    if notify_enabled:
                        try:
                            await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                        except Exception:
                            pass
                op_ids = await get_order_operator_ids()
                for op_id in op_ids:
                    try:
                        await bot.send_message(op_id, notify_text, parse_mode="HTML")
                    except Exception:
                        pass
        except Exception:
            pass


async def _send_multi_order_message(bot, user_id, orders_created, category, total_price, qty, custom_op=None):
    from src.keyboards.user_kb import order_detail_kb, go_to_orders_kb
    if len(orders_created) == 1:
        order, alloc = orders_created[0]
        cat_label = f"Любой другой" if custom_op else category['name']
        custom_line = f"🏢 Оператор: <b>{custom_op}</b>\n" if custom_op else ""
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Оплата получена! Заказ #{order['id']} оформлен!</b>\n\n"
                f"📂 Категория: {cat_label}\n"
                f"{custom_line}"
                f"📊 Оплачено подписей: {alloc['batch_size']}\n"
                f"💰 Сумма: {total_price:.2f}$\n\n"
                f"📱 Телефон: <code>{alloc['phone']}</code>\n\n"
                f"Аккаунт закреплён за вами на 72ч.\n"
                f"📝 Нажмите «Получить подпись» в заказе, чтобы начать.",
                reply_markup=order_detail_kb(order),
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        cat_label = f"Любой другой" if custom_op else category['name']
        custom_line = f"🏢 Оператор: <b>{custom_op}</b>\n" if custom_op else ""
        lines = [f"✅ <b>Оплата получена! Оформлено {len(orders_created)} заказов!</b>\n"]
        lines.append(f"📂 Категория: {cat_label}")
        if custom_op:
            lines.append(f"🏢 Оператор: <b>{custom_op}</b>")
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
        try:
            await bot.send_message(
                user_id,
                "\n".join(lines),
                reply_markup=go_to_orders_kb(),
                parse_mode="HTML",
            )
        except Exception:
            pass
