from src.db.database import get_pool


async def get_required_channels() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM required_channels ORDER BY id ASC")
        return [dict(r) for r in rows]


async def add_required_channel(channel_id: int, title: str, url: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO required_channels (channel_id, title, url) VALUES ($1, $2, $3) RETURNING id",
            channel_id, title, url
        )


async def delete_required_channel(rec_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM required_channels WHERE id = $1", rec_id)


async def get_required_channel(rec_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM required_channels WHERE id = $1", rec_id)
        return dict(row) if row else None
