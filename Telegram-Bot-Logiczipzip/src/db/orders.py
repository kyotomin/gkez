import uuid
from src.db.database import get_pool


def generate_batch_group_id() -> str:
    return str(uuid.uuid4())[:8]


async def create_order(user_id: int, account_id: int, category_id: int, price_paid: float = 0.0, total_signatures: int = 1, custom_operator_name: str = None, is_exclusive: bool = False, batch_group_id: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO orders (user_id, account_id, category_id, price_paid, total_signatures, signatures_claimed, expires_at, custom_operator_name, is_exclusive, batch_group_id)
               VALUES ($1, $2, $3, $4, $5, 0, NOW() + INTERVAL '3 days', $6, $7, $8) RETURNING id""",
            user_id, account_id, category_id, price_paid, total_signatures, custom_operator_name, 1 if is_exclusive else 0, batch_group_id
        )


async def create_preorder(user_id: int, category_id: int, price_paid: float, total_signatures: int, custom_operator_name: str = None, is_exclusive: bool = False, batch_group_id: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO orders (user_id, account_id, category_id, price_paid, total_signatures, signatures_claimed, status, custom_operator_name, is_exclusive, batch_group_id)
               VALUES ($1, NULL, $2, $3, $4, 0, 'preorder', $5, $6, $7) RETURNING id""",
            user_id, category_id, price_paid, total_signatures, custom_operator_name, 1 if is_exclusive else 0, batch_group_id
        )


async def get_pending_preorders() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.*, c.name as category_name
               FROM orders o
               JOIN categories c ON o.category_id = c.id
               WHERE o.status = 'preorder'
               ORDER BY o.created_at ASC"""
        )
        return [dict(r) for r in rows]


async def fulfill_preorder(order_id: int, account_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE orders SET status = 'active', account_id = $1, expires_at = NOW() + INTERVAL '3 days'
               WHERE id = $2 AND status = 'preorder'""",
            account_id, order_id
        )


async def fulfill_preorder_multi(preorder: dict, allocations: list[dict]) -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        order_ids = []
        category_id = preorder["category_id"]
        user_id = preorder["user_id"]
        custom_op = preorder.get("custom_operator_name")
        price_per_sig = preorder["price_paid"] / max(preorder["total_signatures"], 1)
        bg_id = generate_batch_group_id() if len(allocations) > 1 else preorder.get("batch_group_id")
        async with conn.transaction():
            for alloc in allocations:
                qty = alloc["batch_size"]
                alloc_price = price_per_sig * qty
                oid = await conn.fetchval(
                    """INSERT INTO orders (user_id, account_id, category_id, price_paid, total_signatures, signatures_claimed, status, expires_at, custom_operator_name, is_exclusive, batch_group_id)
                       VALUES ($1, $2, $3, $4, $5, 0, 'active', NOW() + INTERVAL '3 days', $6, 0, $7) RETURNING id""",
                    user_id, alloc["id"], category_id, alloc_price, qty, custom_op, bg_id
                )
                order_ids.append(oid)
            await conn.execute(
                "UPDATE orders SET status = 'fulfilled_split' WHERE id = $1 AND status = 'preorder'",
                preorder["id"]
            )
        return order_ids


async def get_user_orders(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.*, a.phone, a.password, a.totp_secret,
                      c.name as category_name
               FROM orders o
               LEFT JOIN accounts a ON o.account_id = a.id
               JOIN categories c ON o.category_id = c.id
               WHERE o.user_id = $1 AND o.status != 'fulfilled_split'
               ORDER BY o.created_at DESC""",
            user_id
        )
        return [dict(r) for r in rows]


async def get_batch_group_orders(batch_group_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.*, a.phone, a.password, a.totp_secret,
                      c.name as category_name
               FROM orders o
               LEFT JOIN accounts a ON o.account_id = a.id
               JOIN categories c ON o.category_id = c.id
               WHERE o.batch_group_id = $1 AND o.status != 'fulfilled_split'
               ORDER BY o.id ASC""",
            batch_group_id
        )
        return [dict(r) for r in rows]


async def set_batch_group_id(order_id: int, batch_group_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET batch_group_id = $1 WHERE id = $2",
            batch_group_id, order_id
        )


async def get_order(order_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT o.*, a.phone, a.password, a.totp_secret,
                      c.name as category_name
               FROM orders o
               LEFT JOIN accounts a ON o.account_id = a.id
               JOIN categories c ON o.category_id = c.id
               WHERE o.id = $1""",
            order_id
        )
        return dict(row) if row else None


async def update_order_status(order_id: int, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status in ("completed", "rejected"):
            await conn.execute(
                "UPDATE orders SET status = $1, completed_at = NOW() WHERE id = $2",
                status, order_id
            )
        else:
            await conn.execute(
                "UPDATE orders SET status = $1 WHERE id = $2",
                status, order_id
            )


async def increment_totp_refresh(order_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET totp_refreshes = totp_refreshes + 1 WHERE id = $1",
            order_id
        )


async def reset_totp_refreshes(order_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET totp_refreshes = 0 WHERE id = $1",
            order_id
        )


async def increment_signatures_sent(order_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET signatures_sent = signatures_sent + 1 WHERE id = $1",
            order_id
        )


async def start_claim(order_id: int, qty: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET pending_claim_qty = $1 WHERE id = $2",
            qty, order_id
        )


async def clear_pending_claim(order_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET pending_claim_qty = 0 WHERE id = $1",
            order_id
        )


async def claim_signature(order_id: int, count: int = 1) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT signatures_claimed, total_signatures, expires_at FROM orders WHERE id = $1",
            order_id
        )
        if not row:
            return False
        remaining = row["total_signatures"] - row["signatures_claimed"]
        if remaining < count:
            return False
        await conn.execute(
            "UPDATE orders SET signatures_claimed = signatures_claimed + $1 WHERE id = $2",
            count, order_id
        )
        return True


async def is_order_expired(order_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT expires_at FROM orders WHERE id = $1",
            order_id
        )
        if not row or not row["expires_at"]:
            return False
        expired = await conn.fetchval(
            "SELECT $1 <= NOW()",
            row["expires_at"]
        )
        return bool(expired)


async def expire_old_orders() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.id, o.user_id, c.name as category_name
               FROM orders o
               JOIN categories c ON o.category_id = c.id
               WHERE o.status IN ('active', 'pending_review')
                 AND o.expires_at IS NOT NULL
                 AND o.expires_at <= NOW()"""
        )
        expired = [dict(r) for r in rows]
        if expired:
            await conn.execute(
                """UPDATE orders SET status = 'expired'
                   WHERE status IN ('active', 'pending_review')
                     AND expires_at IS NOT NULL
                     AND expires_at <= NOW()"""
            )
        return expired


async def get_preorders_with_users() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.*, c.name as category_name,
                      u.username, u.full_name
               FROM orders o
               JOIN categories c ON o.category_id = c.id
               JOIN users u ON o.user_id = u.telegram_id
               WHERE o.status = 'preorder'
               ORDER BY o.created_at ASC"""
        )
        return [dict(r) for r in rows]


async def cancel_preorder(order_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1 AND status = 'preorder'",
            order_id
        )
        if not row:
            return None
        order = dict(row)
        await conn.execute(
            "UPDATE orders SET status = 'rejected' WHERE id = $1",
            order_id
        )
        return order


async def set_order_totp_limit(order_id: int, limit: int | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET totp_limit_override = $1 WHERE id = $2",
            limit, order_id
        )


async def get_order_totp_limit(order_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT totp_limit_override FROM orders WHERE id = $1", order_id)
        if row and row["totp_limit_override"] is not None:
            return row["totp_limit_override"]
        return None


async def compute_effective_totp_limit(order_id: int, user_id: int) -> int:
    from src.db.users import get_user_totp_limit
    from src.db.settings import get_totp_limit
    order = await get_order(order_id)
    if not order:
        return 0
    override = order.get("totp_limit_override")
    if override is not None:
        return override
    user_custom = await get_user_totp_limit(user_id)
    base = user_custom if user_custom is not None else await get_totp_limit()
    pending = order.get("pending_claim_qty") or 0
    qty = pending if pending > 0 else max(order.get("total_signatures", 1), 1)
    return base * qty


async def get_all_orders() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.*, a.phone, c.name as category_name,
                      u.username, u.full_name, u.telegram_id
               FROM orders o
               LEFT JOIN accounts a ON o.account_id = a.id
               JOIN categories c ON o.category_id = c.id
               JOIN users u ON o.user_id = u.telegram_id
               WHERE o.status != 'fulfilled_split'
               ORDER BY o.created_at DESC
               LIMIT 50"""
        )
        return [dict(r) for r in rows]


async def reduce_order_signatures(order_id: int, new_total: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET total_signatures = $1 WHERE id = $2",
            new_total, order_id
        )


async def search_orders(query: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cleaned = query.strip().lstrip("#")
        if cleaned.isdigit():
            order_id = int(cleaned)
            rows = await conn.fetch(
                """SELECT o.*, c.name as category_name,
                          a.phone as phone,
                          u.username, u.full_name, u.telegram_id
                   FROM orders o
                   LEFT JOIN categories c ON o.category_id = c.id
                   LEFT JOIN accounts a ON o.account_id = a.id
                   LEFT JOIN users u ON o.user_id = u.telegram_id
                   WHERE o.id = $1 OR o.user_id = $1
                   ORDER BY o.created_at DESC
                   LIMIT 50""",
                order_id
            )
        else:
            phone = cleaned.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            rows = await conn.fetch(
                """SELECT o.*, c.name as category_name,
                          a.phone as phone,
                          u.username, u.full_name, u.telegram_id
                   FROM orders o
                   LEFT JOIN categories c ON o.category_id = c.id
                   LEFT JOIN accounts a ON o.account_id = a.id
                   LEFT JOIN users u ON o.user_id = u.telegram_id
                   WHERE regexp_replace(a.phone, '[^0-9]', '', 'g') LIKE '%' || $1 || '%'
                   ORDER BY o.created_at DESC
                   LIMIT 50""",
                phone
            )
        return [dict(r) for r in rows]
