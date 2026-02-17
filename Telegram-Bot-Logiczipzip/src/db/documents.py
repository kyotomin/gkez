from src.db.database import get_pool


async def save_order_document(order_id: int, user_id: int, file_id: str, sender_type: str = "admin"):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO order_documents (order_id, user_id, file_id, sender_type) VALUES ($1, $2, $3, $4)",
            order_id, user_id, file_id, sender_type
        )


async def get_order_documents(order_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM order_documents WHERE order_id = $1 ORDER BY created_at ASC",
            order_id
        )
        return [dict(r) for r in rows]


async def get_order_doc_count(order_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM order_documents WHERE order_id = $1",
            order_id
        ) or 0


async def get_pending_doc_requests(order_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM doc_requests WHERE order_id = $1 AND status = 'pending'",
            order_id
        ) or 0


async def get_user_documents(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT od.*, o.status as order_status, c.name as category_name,
                      a.phone as phone
               FROM order_documents od
               JOIN orders o ON od.order_id = o.id
               LEFT JOIN categories c ON o.category_id = c.id
               LEFT JOIN accounts a ON o.account_id = a.id
               WHERE od.user_id = $1
               ORDER BY od.created_at DESC""",
            user_id
        )
        return [dict(r) for r in rows]


async def get_user_orders_with_documents(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT o.id as order_id, o.status, c.name as category_name,
                      a.phone as phone, COUNT(od.id) as doc_count,
                      MAX(od.created_at) as last_doc_at
               FROM order_documents od
               JOIN orders o ON od.order_id = o.id
               LEFT JOIN categories c ON o.category_id = c.id
               LEFT JOIN accounts a ON o.account_id = a.id
               WHERE od.user_id = $1
               GROUP BY o.id, o.status, c.name, a.phone
               ORDER BY last_doc_at DESC""",
            user_id
        )
        return [dict(r) for r in rows]
