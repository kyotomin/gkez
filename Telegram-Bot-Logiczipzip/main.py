import asyncio
import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import BOT_TOKEN
from src.bot.instance import create_bot
from src.db.database import init_db, close_db
from src.handlers import start, profile, sim_sign, orders, help, admin, operator, review
from src.handlers.payment import start_payment_check
from src.db.payments import get_pending_payments
from src.db.orders import expire_old_orders
from src.db.accounts import release_expired_reservations
from src.utils.preorders import run_preorder_fulfillment


async def resume_pending_payments():
    pending = await get_pending_payments()
    for p in pending:
        await start_payment_check(p["invoice_id"])
    if pending:
        logging.info(f"Resumed {len(pending)} pending payment checks")


async def expiry_checker(bot):
    while True:
        try:
            expired = await expire_old_orders()
            await release_expired_reservations()
            for order in expired:
                try:
                    await bot.send_message(
                        order["user_id"],
                        f"⏰ <b>Заказ #{order['id']} истёк</b>\n\n"
                        f"Срок действия заказа (72ч) закончился.\n"
                        f"Неиспользованные подписи аннулированы.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            if expired:
                logging.info(f"Expired {len(expired)} orders")
        except Exception as e:
            logging.error(f"Expiry checker error: {e}")
        await asyncio.sleep(300)


async def preorder_fulfiller(bot):
    while True:
        try:
            await run_preorder_fulfillment(bot)
        except Exception as e:
            logging.error(f"Preorder fulfiller error: {e}")
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    if not BOT_TOKEN:
        logging.error("BOT_TOKEN is not set. Please add it to secrets.")
        await asyncio.sleep(5)
        return

    bot = create_bot()
    await init_db()
    await resume_pending_payments()

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin.router)
    dp.include_router(operator.router)
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(sim_sign.router)
    dp.include_router(orders.router)
    dp.include_router(help.router)
    dp.include_router(review.router)

    asyncio.create_task(expiry_checker(bot))
    asyncio.create_task(preorder_fulfiller(bot))

    logging.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        from src.utils.cryptobot import close_crypto_session
        await close_crypto_session()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
