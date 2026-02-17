from src.db.database import get_pool


async def get_all_reputation_links() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reputation_links ORDER BY sort_order ASC, id ASC")
        return [dict(r) for r in rows]


async def get_reputation_link(link_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM reputation_links WHERE id = $1", link_id)
        return dict(row) if row else None


async def add_reputation_link(name: str, url: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        next_order = await conn.fetchval("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM reputation_links")
        return await conn.fetchval(
            "INSERT INTO reputation_links (name, url, sort_order) VALUES ($1, $2, $3) RETURNING id",
            name, url, next_order
        )


async def update_reputation_link(link_id: int, name: str, url: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reputation_links SET name = $1, url = $2 WHERE id = $3",
            name, url, link_id
        )


async def delete_reputation_link(link_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM reputation_links WHERE id = $1", link_id)
