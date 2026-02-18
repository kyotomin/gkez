from src.db.database import get_pool


async def set_referrer(user_telegram_id: int, referrer_telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET referred_by = $1 WHERE telegram_id = $2 AND referred_by IS NULL AND telegram_id != $1",
            referrer_telegram_id, user_telegram_id
        )


async def get_referrer(user_telegram_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT referred_by FROM users WHERE telegram_id = $1", user_telegram_id
        )


async def add_referral_earning(referrer_id: int, referral_id: int, order_id: int, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO referral_earnings (referrer_id, referral_id, order_id, amount) VALUES ($1, $2, $3, $4)",
            referrer_id, referral_id, order_id, amount
        )


async def get_referral_stats(user_telegram_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by = $1", user_telegram_id
        )
        earned = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM referral_earnings WHERE referrer_id = $1", user_telegram_id
        )
        return {"referral_count": count, "total_earned": float(earned)}


async def get_referral_percent() -> float:
    from src.db.settings import get_setting
    val = await get_setting("referral_percent")
    return float(val) if val else 5.0


async def set_referral_percent(percent: float):
    from src.db.settings import set_setting
    await set_setting("referral_percent", str(percent))


async def process_referral_reward(buyer_telegram_id: int, order_id: int, purchase_amount: float):
    referrer_id = await get_referrer(buyer_telegram_id)
    if not referrer_id:
        return None
    percent = await get_referral_percent()
    if percent <= 0:
        return None
    reward = round(purchase_amount * percent / 100, 2)
    if reward <= 0:
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        already = await conn.fetchval(
            "SELECT 1 FROM referral_earnings WHERE order_id = $1", order_id
        )
        if already:
            return None
    from src.db.users import update_balance
    await update_balance(referrer_id, reward)
    await add_referral_earning(referrer_id, buyer_telegram_id, order_id, reward)
    return {"referrer_id": referrer_id, "reward": reward}
