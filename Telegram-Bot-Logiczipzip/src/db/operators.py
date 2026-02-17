from src.db.database import get_pool


async def add_operator(telegram_id: int, username: str = None, role: str = "orders") -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "INSERT INTO operators (telegram_id, username, role) VALUES ($1, $2, $3) ON CONFLICT (telegram_id) DO NOTHING",
            telegram_id, username, role
        )
        return result.split()[-1] != "0"


async def remove_operator(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM operators WHERE telegram_id = $1",
            telegram_id
        )
        return int(result.split()[-1]) > 0


async def get_all_operators() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM operators ORDER BY added_at DESC")
        return [dict(r) for r in rows]


async def is_operator(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM operators WHERE telegram_id = $1",
            telegram_id
        )
        return row is not None


async def get_operator_ids(role: str = None) -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if role:
            rows = await conn.fetch(
                "SELECT telegram_id FROM operators WHERE role = $1",
                role
            )
        else:
            rows = await conn.fetch("SELECT telegram_id FROM operators")
        return [r["telegram_id"] for r in rows]


async def get_order_operator_ids() -> list[int]:
    return await get_operator_ids("orders")


async def get_ticket_operator_ids() -> list[int]:
    return await get_operator_ids("support")


async def get_preorder_operator_ids() -> list[int]:
    return await get_operator_ids("preorders")


async def update_operator_role(telegram_id: int, role: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE operators SET role = $1 WHERE telegram_id = $2",
            role, telegram_id
        )


async def get_operator(telegram_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM operators WHERE telegram_id = $1",
            telegram_id
        )
        return dict(row) if row else None


async def toggle_operator_notifications(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT notifications_enabled FROM operators WHERE telegram_id = $1",
            telegram_id
        )
        if not row:
            return False
        new_val = 0 if row["notifications_enabled"] else 1
        await conn.execute(
            "UPDATE operators SET notifications_enabled = $1 WHERE telegram_id = $2",
            new_val, telegram_id
        )
        return bool(new_val)


async def is_operator_notifications_enabled(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT notifications_enabled FROM operators WHERE telegram_id = $1",
            telegram_id
        )
        return bool(row["notifications_enabled"]) if row else True


async def get_order_operators_with_notifications() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT telegram_id FROM operators WHERE role = 'orders' AND notifications_enabled = 1"
        )
        return [r["telegram_id"] for r in rows]
