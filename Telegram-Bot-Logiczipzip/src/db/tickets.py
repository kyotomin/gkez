from src.db.database import get_pool


async def can_create_general_support(user_id: int) -> bool:
    from src.db.settings import get_ticket_limit
    limit = await get_ticket_limit()
    pool = await get_pool()
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            """SELECT COUNT(*) FROM tickets
               WHERE user_id = $1 AND order_id IS NULL
               AND created_at::date = CURRENT_DATE""",
            user_id
        )
        return cnt < limit


async def check_daily_ticket_limit(user_id: int) -> bool:
    from src.db.settings import get_ticket_limit
    limit = await get_ticket_limit()
    pool = await get_pool()
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            """SELECT COUNT(*) FROM tickets
               WHERE user_id = $1 AND created_at::date = CURRENT_DATE""",
            user_id
        )
        return cnt < limit


async def get_support_cooldown_remaining(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT created_at FROM tickets
               WHERE user_id = $1 AND order_id IS NULL
               AND created_at::date = CURRENT_DATE
               ORDER BY created_at DESC LIMIT 1""",
            user_id
        )
        if not row:
            return None
        from datetime import datetime, timedelta, timezone
        created = row["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        end_of_day = created.replace(hour=23, minute=59, second=59) + timedelta(seconds=1)
        now = datetime.now(timezone.utc)
        remaining = (end_of_day - now).total_seconds()
        if remaining <= 0:
            return None
        return int(remaining)


async def can_create_ticket_for_order(user_id: int, order_id: int, tag: str = None) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if tag:
            cnt = await conn.fetchval(
                """SELECT COUNT(*) FROM tickets
                   WHERE user_id = $1 AND order_id = $2
                   AND status = 'open'
                   AND subject LIKE '%TOTP%'""",
                user_id, order_id
            )
        else:
            cnt = await conn.fetchval(
                """SELECT COUNT(*) FROM tickets
                   WHERE user_id = $1 AND order_id = $2
                   AND status = 'open'""",
                user_id, order_id
            )
        return cnt == 0


async def create_ticket(user_id: int, subject: str, order_id: int = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO tickets (user_id, subject, order_id) VALUES ($1, $2, $3) RETURNING id",
            user_id, subject, order_id
        )


async def add_ticket_message(ticket_id: int, sender_id: int, message: str, file_id: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ticket_messages (ticket_id, sender_id, message, file_id) VALUES ($1, $2, $3, $4)",
            ticket_id, sender_id, message, file_id
        )


async def get_user_tickets(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tickets WHERE user_id = $1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(r) for r in rows]


async def get_ticket(ticket_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tickets WHERE id = $1", ticket_id)
        return dict(row) if row else None


async def get_ticket_messages(ticket_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM ticket_messages WHERE ticket_id = $1 ORDER BY created_at",
            ticket_id
        )
        return [dict(r) for r in rows]


async def close_ticket(ticket_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = NOW() WHERE id = $1",
            ticket_id
        )


async def get_open_tickets() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.*, u.username, u.full_name
               FROM tickets t
               JOIN users u ON t.user_id = u.telegram_id
               WHERE t.status = 'open'
               ORDER BY t.created_at DESC"""
        )
        return [dict(r) for r in rows]


async def get_all_tickets() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.*, u.username, u.full_name
               FROM tickets t
               JOIN users u ON t.user_id = u.telegram_id
               ORDER BY t.created_at DESC
               LIMIT 50"""
        )
        return [dict(r) for r in rows]


async def search_tickets(query: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if query.isdigit():
            qval = int(query)
            rows = await conn.fetch(
                """SELECT t.*, u.username, u.full_name
                   FROM tickets t
                   JOIN users u ON t.user_id = u.telegram_id
                   WHERE t.id = $1 OR t.user_id = $2 OR t.order_id = $3
                   ORDER BY t.created_at DESC
                   LIMIT 50""",
                qval, qval, qval
            )
        else:
            pat = f"%{query}%"
            rows = await conn.fetch(
                """SELECT t.*, u.username, u.full_name
                   FROM tickets t
                   JOIN users u ON t.user_id = u.telegram_id
                   WHERE u.username LIKE $1 OR u.full_name LIKE $2 OR t.subject LIKE $3
                   ORDER BY t.created_at DESC
                   LIMIT 50""",
                pat, pat, pat
            )
        return [dict(r) for r in rows]
