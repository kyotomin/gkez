import logging

from src.db.database import get_pool

logger = logging.getLogger(__name__)


async def create_payment(user_id: int, invoice_id: int, amount: float, pay_url: str, purpose: str = "balance", payment_meta: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO payments (user_id, invoice_id, amount, pay_url, purpose, payment_meta) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            user_id, invoice_id, amount, pay_url, purpose, payment_meta
        )


async def get_payment_by_invoice(invoice_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM payments WHERE invoice_id = $1", invoice_id)
        return dict(row) if row else None


async def update_payment_status(invoice_id: int, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status == "paid":
            await conn.execute(
                "UPDATE payments SET status = $1, paid_at = NOW() WHERE invoice_id = $2",
                status, invoice_id
            )
        else:
            await conn.execute(
                "UPDATE payments SET status = $1 WHERE invoice_id = $2",
                status, invoice_id
            )


async def confirm_balance_payment(invoice_id: int, user_id: int, amount: float) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT status FROM payments WHERE invoice_id = $1 FOR UPDATE",
                invoice_id
            )
            if not row or row["status"] != "pending":
                logger.warning(f"BALANCE_PAY: invoice={invoice_id} skip — status={row['status'] if row else 'NOT_FOUND'}")
                return False
            await conn.execute(
                "UPDATE payments SET status = 'paid', paid_at = NOW() WHERE invoice_id = $1",
                invoice_id
            )
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE telegram_id = $2",
                amount, user_id
            )
            logger.info(f"BALANCE_PAY: invoice={invoice_id}, user={user_id}, amount={amount} — OK")
            return True


async def get_pending_payments() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY created_at"
        )
        return [dict(r) for r in rows]
