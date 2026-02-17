from src.db.database import get_pool


async def create_review(user_id: int, order_id: int, text: str, bonus: float = 0.0) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO reviews (user_id, order_id, text, bonus) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, order_id, text, bonus
        )


async def get_all_reviews() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT r.*, u.username, u.full_name
               FROM reviews r
               JOIN users u ON r.user_id = u.telegram_id
               ORDER BY r.created_at DESC
               LIMIT 50"""
        )
        return [dict(r) for r in rows]


async def get_review(review_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT r.*, u.username, u.full_name
               FROM reviews r
               JOIN users u ON r.user_id = u.telegram_id
               WHERE r.id = $1""",
            review_id
        )
        return dict(row) if row else None


async def has_review_for_order(user_id: int, order_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM reviews WHERE user_id = $1 AND order_id = $2",
            user_id, order_id
        )
        return row is not None


async def get_reviews_page(offset: int = 0, limit: int = 5) -> tuple[list[dict], int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM reviews")
        rows = await conn.fetch(
            "SELECT text, bonus, created_at FROM reviews ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [dict(r) for r in rows], total


async def delete_review(review_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM reviews WHERE id = $1", review_id)
