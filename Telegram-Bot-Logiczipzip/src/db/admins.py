from src.db.database import get_pool


async def get_admin_ids() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM admins")
        return [row["telegram_id"] for row in rows]


async def add_admin(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(
                "INSERT INTO admins (telegram_id) VALUES ($1) ON CONFLICT (telegram_id) DO NOTHING",
                telegram_id
            )
            return result.split()[-1] != "0"
        except Exception:
            return False


async def remove_admin(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM admins WHERE telegram_id = $1",
            telegram_id
        )
        return int(result.split()[-1]) > 0


async def is_admin(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM admins WHERE telegram_id = $1",
            telegram_id
        )
        return row is not None


async def is_owner(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM admins WHERE telegram_id = $1 AND role = 'owner'",
            telegram_id
        )
        return row is not None


async def get_all_admins() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id, role, added_at FROM admins ORDER BY added_at ASC")
        return [dict(row) for row in rows]


async def get_admin_stats(admin_telegram_id: int, date_from: str = None, date_to: str = None) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if date_from and date_to:
            accounts_added = await conn.fetchval(
                "SELECT COUNT(*) FROM accounts a WHERE a.added_by_admin_id = $1 AND (a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date BETWEEN $2::date AND $3::date",
                admin_telegram_id, date_from, date_to
            )
            row = await conn.fetchrow(
                """SELECT COUNT(*) as cnt, COALESCE(SUM(o.total_signatures), 0) as sigs,
                           COALESCE(SUM(o.price_paid), 0) as revenue
                    FROM orders o
                    JOIN accounts a ON o.account_id = a.id
                    WHERE a.added_by_admin_id = $1 AND o.status IN ('active', 'completed')
                    AND (o.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date BETWEEN $2::date AND $3::date""",
                admin_telegram_id, date_from, date_to
            )
        elif date_from:
            accounts_added = await conn.fetchval(
                "SELECT COUNT(*) FROM accounts a WHERE a.added_by_admin_id = $1 AND (a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = $2::date",
                admin_telegram_id, date_from
            )
            row = await conn.fetchrow(
                """SELECT COUNT(*) as cnt, COALESCE(SUM(o.total_signatures), 0) as sigs,
                           COALESCE(SUM(o.price_paid), 0) as revenue
                    FROM orders o
                    JOIN accounts a ON o.account_id = a.id
                    WHERE a.added_by_admin_id = $1 AND o.status IN ('active', 'completed')
                    AND (o.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = $2::date""",
                admin_telegram_id, date_from
            )
        else:
            accounts_added = await conn.fetchval(
                "SELECT COUNT(*) FROM accounts a WHERE a.added_by_admin_id = $1",
                admin_telegram_id
            )
            row = await conn.fetchrow(
                """SELECT COUNT(*) as cnt, COALESCE(SUM(o.total_signatures), 0) as sigs,
                           COALESCE(SUM(o.price_paid), 0) as revenue
                    FROM orders o
                    JOIN accounts a ON o.account_id = a.id
                    WHERE a.added_by_admin_id = $1 AND o.status IN ('active', 'completed')""",
                admin_telegram_id
            )

        return {
            "accounts_added": accounts_added,
            "orders_count": row["cnt"],
            "signatures_sold": int(row["sigs"]),
            "revenue": float(row["revenue"]),
        }
