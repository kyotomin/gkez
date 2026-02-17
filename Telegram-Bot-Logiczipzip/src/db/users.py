from src.db.database import get_pool


async def get_or_create_user(telegram_id: int, username: str = None, full_name: str = None) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO users (telegram_id, username, full_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (telegram_id) DO UPDATE
               SET username = EXCLUDED.username, full_name = EXCLUDED.full_name
               RETURNING *""",
            telegram_id, username, full_name
        )
        return dict(row)


async def get_user(telegram_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return dict(row) if row else None


async def get_user_order_count(telegram_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM orders WHERE user_id = $1", telegram_id)


async def update_balance(telegram_id: int, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = balance + $1 WHERE telegram_id = $2",
            amount, telegram_id
        )


async def set_balance(telegram_id: int, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = $1 WHERE telegram_id = $2",
            amount, telegram_id
        )


async def get_user_by_username(username: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username.lstrip("@"))
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users ORDER BY registered_at DESC")
        return [dict(r) for r in rows]


async def block_user(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked = 1 WHERE telegram_id = $1", telegram_id)


async def unblock_user(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked = 0 WHERE telegram_id = $1", telegram_id)


async def is_user_blocked(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_blocked FROM users WHERE telegram_id = $1", telegram_id)
        if not row:
            return False
        return bool(row["is_blocked"])


async def set_user_custom_deposit(telegram_id: int, amount: float | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET custom_deposit = $1 WHERE telegram_id = $2",
            amount, telegram_id
        )


async def get_user_deposit_required(telegram_id: int) -> float | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT custom_deposit FROM users WHERE telegram_id = $1", telegram_id)
        if row and row["custom_deposit"] is not None:
            return row["custom_deposit"]
        return None


async def get_user_totp_limit(telegram_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT totp_limit FROM users WHERE telegram_id = $1", telegram_id)
        if row and row["totp_limit"] is not None:
            return row["totp_limit"]
        return None


async def set_user_totp_limit(telegram_id: int, limit: int | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET totp_limit = $1 WHERE telegram_id = $2",
            limit, telegram_id
        )


async def get_total_spent(telegram_id: int) -> float:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COALESCE(SUM(price_paid), 0) FROM orders WHERE user_id = $1 AND status != 'rejected'",
            telegram_id
        )
        return float(val)


async def get_user_profile_data(telegram_id: int, username: str = None, full_name: str = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """WITH upserted AS (
                INSERT INTO users (telegram_id, username, full_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id) DO UPDATE
                SET username = EXCLUDED.username, full_name = EXCLUDED.full_name
                RETURNING *
            )
            SELECT u.*,
                   (SELECT COUNT(*) FROM orders WHERE user_id = $1) as order_count,
                   (SELECT id FROM deposits WHERE user_id = $1 LIMIT 1) IS NOT NULL as has_deposit,
                   COALESCE(
                       u.custom_deposit,
                       (SELECT value::float FROM settings WHERE key = 'deposit_amount')
                   ) as effective_deposit
            FROM upserted u""",
            telegram_id, username, full_name
        )
        return dict(row) if row else None


async def get_admin_user_profile_data(telegram_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.*,
                      (SELECT COUNT(*) FROM orders WHERE user_id = $1) as order_count,
                      (SELECT COALESCE(SUM(price_paid), 0) FROM orders WHERE user_id = $1 AND status != 'rejected') as total_spent,
                      (SELECT id FROM deposits WHERE user_id = $1 LIMIT 1) IS NOT NULL as has_deposit,
                      (SELECT COALESCE(amount, 0) FROM deposits WHERE user_id = $1) as deposit_paid,
                      COALESCE(u.custom_deposit, (SELECT value::float FROM settings WHERE key = 'deposit_amount')) as effective_deposit,
                      (SELECT value::int FROM settings WHERE key = 'totp_limit') as global_totp
               FROM users u WHERE u.telegram_id = $1""",
            telegram_id
        )
        return dict(row) if row else None
