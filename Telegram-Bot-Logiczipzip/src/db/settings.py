from src.db.database import get_pool


async def get_setting(key: str) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row["value"] if row else None


async def set_setting(key: str, value: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
            key, value
        )


async def get_deposit_amount() -> float:
    val = await get_setting("deposit_amount")
    return float(val) if val else 30.0


async def set_deposit_amount(amount: float):
    await set_setting("deposit_amount", str(amount))


async def get_user_effective_deposit(user_id: int) -> float:
    from src.db.users import get_user_deposit_required
    custom = await get_user_deposit_required(user_id)
    if custom is not None:
        return custom
    return await get_deposit_amount()


async def has_user_deposit(user_id: int) -> bool:
    eff = await get_user_effective_deposit(user_id)
    if eff == 0:
        return True
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM deposits WHERE user_id = $1", user_id)
        return row is not None


async def has_actual_deposit(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM deposits WHERE user_id = $1", user_id)
        return row is not None


async def is_deposit_required(user_id: int) -> bool:
    eff = await get_user_effective_deposit(user_id)
    return eff > 0


async def get_user_deposit_amount(user_id: int) -> float:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT amount FROM deposits WHERE user_id = $1", user_id)
        return row["amount"] if row else 0.0


async def create_user_deposit(user_id: int, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO deposits (user_id, amount) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET amount = $2, paid_at = NOW()",
            user_id, amount
        )


async def is_bot_paused() -> bool:
    val = await get_setting("bot_paused")
    return val == "1"


async def set_bot_paused(paused: bool):
    await set_setting("bot_paused", "1" if paused else "0")


async def is_admin_notifications_enabled(admin_id: int) -> bool:
    val = await get_setting(f"admin_notify_{admin_id}")
    if val is None:
        return True
    return val == "1"


async def set_admin_notifications(admin_id: int, enabled: bool):
    await set_setting(f"admin_notify_{admin_id}", "1" if enabled else "0")


async def get_totp_limit() -> int:
    val = await get_setting("totp_limit")
    return int(val) if val else 2


async def set_totp_limit(limit: int):
    await set_setting("totp_limit", str(limit))


async def get_faq_text() -> str:
    val = await get_setting("faq_text")
    return val if val else "ℹ️ Раздел в разработке. Скоро здесь появится подробная инструкция."


async def set_faq_text(text: str):
    await set_setting("faq_text", text)


async def get_ticket_limit() -> int:
    val = await get_setting("ticket_limit")
    return int(val) if val else 1


async def set_ticket_limit(limit: int):
    await set_setting("ticket_limit", str(limit))


async def get_review_bonus() -> float:
    val = await get_setting("review_bonus")
    return float(val) if val else 0.0


async def set_review_bonus(amount: float):
    await set_setting("review_bonus", str(amount))


async def delete_user_deposit(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM deposits WHERE user_id = $1", user_id)
