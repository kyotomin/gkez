from src.db.database import get_pool


async def get_all_categories() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.*,
                      COALESCE(
                          (SELECT SUM(COALESCE(s.max_signatures, c.max_signatures) - s.used_signatures)
                           FROM account_signatures s
                           JOIN accounts a ON s.account_id = a.id
                           WHERE s.category_id = c.id
                             AND COALESCE(a.is_enabled, 1) = 1
                             AND s.used_signatures < COALESCE(s.max_signatures, c.max_signatures)
                             AND (s.reserved_by IS NULL OR s.reserved_until <= NOW())
                          ), 0
                      ) as available_count
               FROM categories c ORDER BY c.id"""
        )
        return [dict(r) for r in rows]


async def get_category(category_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", category_id)
        return dict(row) if row else None


async def create_category(name: str, price: float = 0.0, max_signatures: int = 5) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            cat_id = await conn.fetchval(
                "INSERT INTO categories (name, price, max_signatures) VALUES ($1, $2, $3) RETURNING id",
                name, price, max_signatures
            )
            await conn.execute(
                """INSERT INTO account_signatures (account_id, category_id, used_signatures)
                   SELECT id, $1, 0 FROM accounts
                   ON CONFLICT DO NOTHING""",
                cat_id
            )
        return cat_id


async def delete_category(category_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM categories WHERE id = $1", category_id)


async def rename_category(category_id: int, new_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE categories SET name = $1 WHERE id = $2", new_name, category_id)


async def update_category_price(category_id: int, price: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE categories SET price = $1 WHERE id = $2", price, category_id)


async def toggle_category_status(category_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM categories WHERE id = $1", category_id)
        new_status = 0 if row["is_active"] else 1
        await conn.execute("UPDATE categories SET is_active = $1 WHERE id = $2", new_status, category_id)
        return bool(new_status)


async def update_category_max_signatures(category_id: int, max_signatures: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE categories SET max_signatures = $1 WHERE id = $2", max_signatures, category_id)


async def get_active_categories() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.*,
                      COALESCE(
                          (SELECT SUM(COALESCE(s.max_signatures, c.max_signatures) - s.used_signatures)
                           FROM account_signatures s
                           JOIN accounts a ON s.account_id = a.id
                           WHERE s.category_id = c.id
                             AND COALESCE(a.is_enabled, 1) = 1
                             AND s.used_signatures < COALESCE(s.max_signatures, c.max_signatures)
                             AND (s.reserved_by IS NULL OR s.reserved_until <= NOW())
                          ), 0
                      ) as available_count
               FROM categories c
               WHERE c.is_active = 1
               ORDER BY c.id"""
        )
        return [dict(r) for r in rows]
