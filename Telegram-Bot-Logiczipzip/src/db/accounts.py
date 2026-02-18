import re
import logging
from src.db.database import get_pool

logger = logging.getLogger(__name__)


async def get_all_accounts() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM accounts ORDER BY created_at DESC")
        return [dict(r) for r in rows]


async def get_account(account_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
        return dict(row) if row else None


async def search_accounts_by_phone(phone: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM accounts WHERE phone LIKE $1 ORDER BY created_at DESC",
            f"%{phone}%"
        )
        return [dict(r) for r in rows]


async def get_account_signatures(account_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.*, c.name as category_name, c.max_signatures as cat_max_signatures
               FROM account_signatures s
               JOIN categories c ON s.category_id = c.id
               WHERE s.account_id = $1
               ORDER BY c.name""",
            account_id
        )
        return [dict(r) for r in rows]


async def get_effective_max_signatures(sig: dict) -> int:
    if sig.get("max_signatures") is not None:
        return sig["max_signatures"]
    return sig.get("cat_max_signatures", 5)


async def is_account_exhausted(account_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            """SELECT COUNT(*) FROM account_signatures s
               JOIN categories c ON s.category_id = c.id
               WHERE s.account_id = $1
                 AND s.used_signatures < COALESCE(s.max_signatures, c.max_signatures)""",
            account_id
        )
        return cnt == 0


async def update_account_totp(account_id: int, new_totp: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET totp_secret = $1 WHERE id = $2",
            new_totp, account_id
        )


def parse_accounts_text(text: str) -> list[dict]:
    results = []
    lines = [l.strip() for l in text.strip().split("\n")]
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
        parts = cleaned.split()
        if len(parts) >= 3:
            results.append({
                "phone": parts[0],
                "password": parts[1],
                "totp_secret": parts[2],
            })
            i += 1
            continue
        if re.match(r"^\d+$", cleaned) and len(cleaned) <= 5:
            if i + 3 < len(lines):
                phone = lines[i + 1].strip()
                password = lines[i + 2].strip()
                totp_secret = lines[i + 3].strip()
                if phone and password and totp_secret:
                    results.append({
                        "phone": phone,
                        "password": password,
                        "totp_secret": totp_secret,
                    })
                    i += 4
                    continue
        if len(parts) == 1 and len(cleaned) >= 7:
            if i + 2 < len(lines):
                password = lines[i + 1].strip()
                totp_secret = lines[i + 2].strip()
                if password and totp_secret:
                    results.append({
                        "phone": cleaned,
                        "password": password,
                        "totp_secret": totp_secret,
                    })
                    i += 3
                    continue
        i += 1
    return results


async def bulk_add_accounts(accounts_data: list[dict], added_by_admin_id: int = None) -> tuple[int, list[int]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, max_signatures FROM categories")
        categories = [dict(c) for c in categories]

        added = 0
        added_ids = []
        async with conn.transaction():
            for acc in accounts_data:
                account_id = await conn.fetchval(
                    "INSERT INTO accounts (phone, password, totp_secret, added_by_admin_id, is_enabled) VALUES ($1, $2, $3, $4, 0) RETURNING id",
                    acc["phone"], acc["password"], acc["totp_secret"], added_by_admin_id
                )
                added_ids.append(account_id)
                for cat in categories:
                    await conn.execute(
                        "INSERT INTO account_signatures (account_id, category_id, used_signatures) VALUES ($1, $2, 0)",
                        account_id, cat["id"]
                    )
                added += 1
        return added, added_ids


async def enable_accounts_by_ids(account_ids: list[int]) -> int:
    if not account_ids:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET is_enabled = 1 WHERE id = ANY($1)",
            account_ids
        )
        return len(account_ids)


def _normalize_phone(phone: str) -> str:
    return re.sub(r"[^\d]", "", phone)


async def enable_accounts_by_phones(phones: list[str], account_ids: list[int]) -> tuple[int, list[str]]:
    if not phones or not account_ids:
        return 0, []
    normalized = list(set(_normalize_phone(p) for p in phones if _normalize_phone(p)))
    if not normalized:
        return 0, []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, phone FROM accounts WHERE id = ANY($1)",
            account_ids
        )
        if not rows:
            return 0, []
        matched_ids = []
        matched_phones = []
        for r in rows:
            db_phone_norm = _normalize_phone(r["phone"])
            if db_phone_norm in normalized or any(db_phone_norm.endswith(n) or n.endswith(db_phone_norm) for n in normalized):
                matched_ids.append(r["id"])
                matched_phones.append(r["phone"])
        if not matched_ids:
            return 0, []
        await conn.execute(
            "UPDATE accounts SET is_enabled = 1 WHERE id = ANY($1)",
            matched_ids
        )
        return len(matched_ids), matched_phones


async def mass_enable_all_accounts() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE accounts SET is_enabled = 1 WHERE is_enabled = 0")
        return int(result.split()[-1])


async def mass_disable_all_accounts() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE accounts SET is_enabled = 0 WHERE is_enabled = 1")
        return int(result.split()[-1])


async def mass_enable_by_phones(phones: list[str]) -> tuple[int, list[str]]:
    if not phones:
        return 0, []
    normalized = list(set(_normalize_phone(p) for p in phones if _normalize_phone(p)))
    if not normalized:
        return 0, []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, phone FROM accounts WHERE is_enabled = 0")
        if not rows:
            return 0, []
        matched_ids = []
        matched_phones = []
        for r in rows:
            db_phone_norm = _normalize_phone(r["phone"])
            if db_phone_norm in normalized or any(db_phone_norm.endswith(n) or n.endswith(db_phone_norm) for n in normalized):
                matched_ids.append(r["id"])
                matched_phones.append(r["phone"])
        if not matched_ids:
            return 0, []
        await conn.execute("UPDATE accounts SET is_enabled = 1 WHERE id = ANY($1)", matched_ids)
        return len(matched_ids), matched_phones


async def mass_disable_by_phones(phones: list[str]) -> tuple[int, list[str]]:
    if not phones:
        return 0, []
    normalized = list(set(_normalize_phone(p) for p in phones if _normalize_phone(p)))
    if not normalized:
        return 0, []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, phone FROM accounts WHERE is_enabled = 1")
        if not rows:
            return 0, []
        matched_ids = []
        matched_phones = []
        for r in rows:
            db_phone_norm = _normalize_phone(r["phone"])
            if db_phone_norm in normalized or any(db_phone_norm.endswith(n) or n.endswith(db_phone_norm) for n in normalized):
                matched_ids.append(r["id"])
                matched_phones.append(r["phone"])
        if not matched_ids:
            return 0, []
        await conn.execute("UPDATE accounts SET is_enabled = 0 WHERE id = ANY($1)", matched_ids)
        return len(matched_ids), matched_phones


async def get_accounts_count_by_status() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT is_enabled, COUNT(*) as cnt FROM accounts GROUP BY is_enabled")
        result = {"enabled": 0, "disabled": 0}
        for r in rows:
            if r["is_enabled"] == 1:
                result["enabled"] = r["cnt"]
            else:
                result["disabled"] = r["cnt"]
        return result


async def delete_account(account_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM account_signatures WHERE account_id = $1", account_id)
            order_ids = await conn.fetch("SELECT id FROM orders WHERE account_id = $1", account_id)
            for row in order_ids:
                oid = row["id"]
                await conn.execute("DELETE FROM reviews WHERE order_id = $1", oid)
                await conn.execute("DELETE FROM ticket_messages WHERE ticket_id IN (SELECT id FROM tickets WHERE order_id = $1)", oid)
                await conn.execute("DELETE FROM tickets WHERE order_id = $1", oid)
                await conn.execute("DELETE FROM doc_requests WHERE order_id = $1", oid)
            await conn.execute("DELETE FROM orders WHERE account_id = $1", account_id)
            await conn.execute("DELETE FROM accounts WHERE id = $1", account_id)


async def find_accounts_by_phones(phones: list[str]) -> tuple[list[dict], list[str]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cleaned_map = {}
        not_found = []
        for phone in phones:
            cleaned = phone.strip().replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            if not cleaned or len(cleaned) < 6:
                if phone.strip():
                    not_found.append(phone.strip())
                continue
            cleaned_map[cleaned] = phone.strip()
        if not cleaned_map:
            return [], not_found
        cleaned_list = list(cleaned_map.keys())
        rows = await conn.fetch(
            """SELECT id, phone,
                      REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', ''), '(', ''), ')', '') as cleaned_phone
               FROM accounts
               WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', ''), '(', ''), ')', '') = ANY($1)""",
            cleaned_list
        )
        found = []
        found_cleaned = set()
        for row in rows:
            if not any(f["id"] == row["id"] for f in found):
                found.append({"id": row["id"], "phone": row["phone"]})
            found_cleaned.add(row["cleaned_phone"])
        for cleaned, original in cleaned_map.items():
            if cleaned not in found_cleaned:
                not_found.append(original)
        return found, not_found


async def mass_delete_accounts(account_ids: list[int]) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted = 0
            await conn.execute("DELETE FROM account_signatures WHERE account_id = ANY($1)", account_ids)
            order_ids_rows = await conn.fetch("SELECT id FROM orders WHERE account_id = ANY($1)", account_ids)
            if order_ids_rows:
                oids = [r["id"] for r in order_ids_rows]
                await conn.execute("DELETE FROM reviews WHERE order_id = ANY($1)", oids)
                await conn.execute("DELETE FROM ticket_messages WHERE ticket_id IN (SELECT id FROM tickets WHERE order_id = ANY($1))", oids)
                await conn.execute("DELETE FROM tickets WHERE order_id = ANY($1)", oids)
                await conn.execute("DELETE FROM doc_requests WHERE order_id = ANY($1)", oids)
            await conn.execute("DELETE FROM orders WHERE account_id = ANY($1)", account_ids)
            result = await conn.execute("DELETE FROM accounts WHERE id = ANY($1)", account_ids)
            deleted = int(result.split(" ")[-1]) if result else 0
            return deleted


async def try_reserve_account(category_id: int, user_id: int, quantity: int = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                min_remaining = quantity if quantity else 1
                row = await conn.fetchrow(
                    """SELECT a.id, a.phone, a.password, a.totp_secret,
                              COALESCE(a.priority, 0) as prio,
                              (COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $1)) - s.used_signatures) as remaining
                       FROM accounts a
                       JOIN account_signatures s ON a.id = s.account_id
                       WHERE s.category_id = $2
                         AND COALESCE(a.is_enabled, 1) = 1
                         AND (COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $3)) - s.used_signatures) >= $4
                         AND (s.reserved_by IS NULL OR s.reserved_by = $5 OR s.reserved_until <= NOW())
                       ORDER BY CASE WHEN s.reserved_by = $6 THEN 0 ELSE 1 END, prio DESC, remaining ASC, a.created_at ASC
                       LIMIT 1
                       FOR UPDATE OF s""",
                    category_id, category_id, category_id, min_remaining, user_id, user_id
                )
                if not row:
                    return None
                account_id = row["id"]
                cat_row = await conn.fetchrow(
                    "SELECT max_signatures FROM categories WHERE id = $1",
                    category_id
                )
                batch_size = cat_row["max_signatures"] if cat_row else 1
                sig_row = await conn.fetchrow(
                    "SELECT COALESCE(s.max_signatures, $1) as effective_max, s.used_signatures FROM account_signatures s WHERE s.account_id = $2 AND s.category_id = $3",
                    batch_size, account_id, category_id
                )
                effective_max = sig_row["effective_max"] if sig_row else batch_size
                current_used = sig_row["used_signatures"] if sig_row else 0
                remaining_capacity = effective_max - current_used
                if quantity is not None:
                    if quantity > remaining_capacity:
                        return None
                    new_used = current_used + quantity
                    actual_qty = quantity
                else:
                    new_used = effective_max
                    actual_qty = remaining_capacity
                fully_used = new_used >= effective_max
                if fully_used:
                    await conn.execute(
                        """UPDATE account_signatures 
                           SET used_signatures = $1,
                               reserved_by = $2,
                               reserved_until = NOW() + INTERVAL '3 days'
                           WHERE account_id = $3 AND category_id = $4""",
                        new_used, user_id, account_id, category_id
                    )
                else:
                    await conn.execute(
                        """UPDATE account_signatures 
                           SET used_signatures = $1,
                               reserved_by = NULL,
                               reserved_until = NULL
                           WHERE account_id = $2 AND category_id = $3""",
                        new_used, account_id, category_id
                    )
                logger.info(f"reserve_account: account={account_id}, cat={category_id}, user={user_id}, qty={actual_qty}, new_used={new_used}, fully={fully_used}")
                return {
                    "id": row["id"],
                    "phone": row["phone"],
                    "password": row["password"],
                    "totp_secret": row["totp_secret"],
                    "batch_size": actual_qty,
                }
        except Exception as e:
            logger.error(f"try_reserve_account error: {e}", exc_info=True)
            return None


async def try_reserve_accounts_multi(category_id: int, user_id: int, total_quantity: int) -> list[dict]:
    single = await try_reserve_account(category_id, user_id, quantity=total_quantity)
    if single:
        return [single]

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                rows = await conn.fetch(
                    """SELECT a.id, a.phone, a.password, a.totp_secret,
                              COALESCE(a.priority, 0) as prio,
                              (COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $1)) - s.used_signatures) as remaining
                       FROM accounts a
                       JOIN account_signatures s ON a.id = s.account_id
                       WHERE s.category_id = $2
                         AND COALESCE(a.is_enabled, 1) = 1
                         AND (COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $3)) - s.used_signatures) >= 1
                         AND (s.reserved_by IS NULL OR s.reserved_by = $4 OR s.reserved_until <= NOW())
                       ORDER BY CASE WHEN s.reserved_by = $5 THEN 0 ELSE 1 END, prio DESC, remaining ASC, a.created_at ASC
                       FOR UPDATE OF s""",
                    category_id, category_id, category_id, user_id, user_id
                )
                if not rows:
                    return []

                allocations = []
                left = total_quantity
                for row in rows:
                    if left <= 0:
                        break
                    avail = row["remaining"]
                    take = min(avail, left)
                    account_id = row["id"]

                    cat_row = await conn.fetchrow(
                        "SELECT max_signatures FROM categories WHERE id = $1",
                        category_id
                    )
                    batch_size = cat_row["max_signatures"] if cat_row else 1

                    sig_row = await conn.fetchrow(
                        "SELECT COALESCE(s.max_signatures, $1) as effective_max, s.used_signatures FROM account_signatures s WHERE s.account_id = $2 AND s.category_id = $3",
                        batch_size, account_id, category_id
                    )
                    effective_max = sig_row["effective_max"] if sig_row else batch_size
                    current_used = sig_row["used_signatures"] if sig_row else 0
                    new_used = current_used + take
                    fully_used = new_used >= effective_max

                    if fully_used:
                        await conn.execute(
                            """UPDATE account_signatures 
                               SET used_signatures = $1,
                                   reserved_by = $2,
                                   reserved_until = NOW() + INTERVAL '3 days'
                               WHERE account_id = $3 AND category_id = $4""",
                            new_used, user_id, account_id, category_id
                        )
                    else:
                        await conn.execute(
                            """UPDATE account_signatures 
                               SET used_signatures = $1,
                                   reserved_by = NULL,
                                   reserved_until = NULL
                               WHERE account_id = $2 AND category_id = $3""",
                            new_used, account_id, category_id
                        )
                    logger.info(f"reserve_multi: account={account_id}, cat={category_id}, user={user_id}, take={take}, new_used={new_used}, fully={fully_used}")
                    allocations.append({
                        "id": row["id"],
                        "phone": row["phone"],
                        "password": row["password"],
                        "totp_secret": row["totp_secret"],
                        "batch_size": take,
                    })
                    left -= take

                if left > 0:
                    raise Exception("Not enough accounts")

                return allocations
        except Exception as e:
            logger.error(f"try_reserve_accounts_multi error: {e}", exc_info=True)
            return []


async def try_reserve_account_exclusive(category_id: int, user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT a.id, a.phone, a.password, a.totp_secret,
                              COALESCE(a.priority, 0) as prio,
                              (COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $1)) - s.used_signatures) as remaining
                       FROM accounts a
                       JOIN account_signatures s ON a.id = s.account_id
                       WHERE s.category_id = $2
                         AND COALESCE(a.is_enabled, 1) = 1
                         AND s.used_signatures = 0
                         AND (s.reserved_by IS NULL OR s.reserved_until <= NOW())
                       ORDER BY prio DESC, a.created_at ASC
                       LIMIT 1
                       FOR UPDATE OF s""",
                    category_id, category_id
                )
                if not row:
                    return None
                account_id = row["id"]
                cat_row = await conn.fetchrow(
                    "SELECT max_signatures FROM categories WHERE id = $1",
                    category_id
                )
                batch_size = cat_row["max_signatures"] if cat_row else 1
                sig_row = await conn.fetchrow(
                    "SELECT COALESCE(s.max_signatures, $1) as effective_max FROM account_signatures s WHERE s.account_id = $2 AND s.category_id = $3",
                    batch_size, account_id, category_id
                )
                effective_max = sig_row["effective_max"] if sig_row else batch_size
                await conn.execute(
                    """UPDATE account_signatures 
                       SET used_signatures = $1,
                           reserved_by = $2,
                           reserved_until = NOW() + INTERVAL '3 days'
                       WHERE account_id = $3 AND category_id = $4""",
                    effective_max, user_id, account_id, category_id
                )
                return {
                    "id": row["id"],
                    "phone": row["phone"],
                    "password": row["password"],
                    "totp_secret": row["totp_secret"],
                    "batch_size": effective_max,
                }
        except Exception as e:
            logger.error(f"try_reserve_account_exclusive error: {e}", exc_info=True)
            return None


async def try_issue_account(category_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT a.id, a.phone, a.password, a.totp_secret,
                              COALESCE(a.priority, 0) as prio,
                              (SELECT COALESCE(SUM(s2.used_signatures), 0) FROM account_signatures s2 WHERE s2.account_id = a.id AND s2.category_id != $1) as other_used
                       FROM accounts a
                       JOIN account_signatures s ON a.id = s.account_id
                       WHERE s.category_id = $2
                         AND s.used_signatures < COALESCE(s.max_signatures, (SELECT max_signatures FROM categories WHERE id = $3))
                         AND (s.reserved_by IS NULL OR s.reserved_until <= NOW())
                       ORDER BY prio DESC, other_used DESC, a.created_at ASC
                       LIMIT 1
                       FOR UPDATE OF s""",
                    category_id, category_id, category_id
                )
                if not row:
                    return None
                account_id = row["id"]
                await conn.execute(
                    """UPDATE account_signatures 
                       SET used_signatures = used_signatures + 1
                       WHERE account_id = $1 AND category_id = $2""",
                    account_id, category_id
                )
                return {
                    "id": row["id"],
                    "phone": row["phone"],
                    "password": row["password"],
                    "totp_secret": row["totp_secret"],
                }
        except Exception as e:
            logger.error(f"try_issue_account error: {e}", exc_info=True)
            return None


async def get_available_count(category_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            """SELECT COALESCE(SUM(COALESCE(s.max_signatures, c.max_signatures) - s.used_signatures), 0)
               FROM account_signatures s
               JOIN categories c ON s.category_id = c.id
               JOIN accounts a ON s.account_id = a.id
               WHERE s.category_id = $1
                 AND COALESCE(a.is_enabled, 1) = 1
                 AND s.used_signatures < COALESCE(s.max_signatures, c.max_signatures)
                 AND (s.reserved_by IS NULL OR s.reserved_until <= NOW())""",
            category_id
        )
        return val


async def get_total_accounts_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM accounts")


async def sync_account_signatures(account_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        categories = await conn.fetch("SELECT id FROM categories")
        for cat in categories:
            await conn.execute(
                "INSERT INTO account_signatures (account_id, category_id, used_signatures) VALUES ($1, $2, 0) ON CONFLICT DO NOTHING",
                account_id, cat["id"]
            )


async def sync_all_signatures():
    pool = await get_pool()
    async with pool.acquire() as conn:
        accounts = await conn.fetch("SELECT id FROM accounts")
        categories = await conn.fetch("SELECT id FROM categories")
        for acc in accounts:
            for cat in categories:
                await conn.execute(
                    "INSERT INTO account_signatures (account_id, category_id, used_signatures) VALUES ($1, $2, 0) ON CONFLICT DO NOTHING",
                    acc["id"], cat["id"]
                )


async def update_account_signature_max(account_id: int, category_id: int, new_max: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT used_signatures FROM account_signatures WHERE account_id = $1 AND category_id = $2",
            account_id, category_id
        )
        current_used = row["used_signatures"] if row else 0
        clamped_used = min(current_used, new_max)
        await conn.execute(
            "UPDATE account_signatures SET max_signatures = $1, used_signatures = $2, reserved_by = NULL, reserved_until = NULL WHERE account_id = $3 AND category_id = $4",
            new_max, clamped_used, account_id, category_id
        )


async def update_account_used_signatures(account_id: int, category_id: int, new_used: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE account_signatures SET used_signatures = $1, reserved_by = NULL, reserved_until = NULL WHERE account_id = $2 AND category_id = $3",
            new_used, account_id, category_id
        )


async def set_account_priority(account_id: int, priority: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE accounts SET priority = $1 WHERE id = $2", priority, account_id)


async def toggle_account_enabled(account_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_enabled FROM accounts WHERE id = $1", account_id)
        if not row:
            return False
        new_val = 0 if row["is_enabled"] else 1
        await conn.execute("UPDATE accounts SET is_enabled = $1 WHERE id = $2", new_val, account_id)
        return bool(new_val)


async def set_mass_priority_by_operator(operator_telegram_id: int, priority: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE accounts SET priority = $1 WHERE operator_telegram_id = $2",
            priority, operator_telegram_id
        )
        return int(result.split()[-1])


async def bulk_update_all_signature_max(category_id: int, new_max: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE account_signatures SET max_signatures = $1 WHERE category_id = $2",
            new_max, category_id
        )


async def reset_account_availability(account_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE account_signatures SET used_signatures = 0, reserved_by = NULL, reserved_until = NULL WHERE account_id = $1",
            account_id
        )


async def reset_all_accounts_availability():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE account_signatures SET used_signatures = 0, reserved_by = NULL, reserved_until = NULL"
        )


async def assign_operator_to_account(account_id: int, operator_telegram_id: int | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET operator_telegram_id = $1 WHERE id = $2",
            operator_telegram_id, account_id
        )


async def bulk_assign_operator(operator_telegram_id: int, count: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM accounts WHERE operator_telegram_id IS NULL ORDER BY created_at ASC LIMIT $1",
            count
        )
        if not rows:
            return 0
        ids = [row["id"] for row in rows]
        await conn.execute(
            "UPDATE accounts SET operator_telegram_id = $1 WHERE id = ANY($2)",
            operator_telegram_id, ids
        )
        return len(ids)


async def assign_operator_to_latest(operator_telegram_id: int, count: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM accounts WHERE operator_telegram_id IS NULL ORDER BY created_at DESC LIMIT $1",
            count
        )
        if not rows:
            return 0
        ids = [row["id"] for row in rows]
        await conn.execute(
            "UPDATE accounts SET operator_telegram_id = $1 WHERE id = ANY($2)",
            operator_telegram_id, ids
        )
        return len(ids)


async def get_account_operator(account_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT operator_telegram_id FROM accounts WHERE id = $1",
            account_id
        )
        return row["operator_telegram_id"] if row else None


async def get_accounts_availability() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.id, a.phone,
                      s.category_id,
                      c.name as category_name,
                      s.used_signatures,
                      COALESCE(s.max_signatures, c.max_signatures) as effective_max
               FROM accounts a
               JOIN account_signatures s ON a.id = s.account_id
               JOIN categories c ON s.category_id = c.id
               ORDER BY a.phone, c.name"""
        )
        accounts = {}
        for r in rows:
            r = dict(r)
            aid = r["id"]
            if aid not in accounts:
                accounts[aid] = {"id": aid, "phone": r["phone"], "sigs": []}
            remaining = r["effective_max"] - r["used_signatures"]
            if remaining > 0:
                accounts[aid]["sigs"].append({
                    "category_name": r["category_name"],
                    "remaining": remaining,
                    "effective_max": r["effective_max"],
                    "used": r["used_signatures"],
                })
        result = [v for v in accounts.values() if v["sigs"]]
        return result


async def get_accounts_availability_all() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.id, a.phone, a.password, a.created_at,
                      c.name as category_name,
                      c.price as category_price,
                      s.used_signatures,
                      COALESCE(s.max_signatures, c.max_signatures) as effective_max
               FROM accounts a
               JOIN account_signatures s ON a.id = s.account_id
               JOIN categories c ON s.category_id = c.id
               ORDER BY a.phone, c.name"""
        )
        return [dict(r) for r in rows]


async def get_accounts_availability_by_date(date_str: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.id, a.phone, a.created_at,
                      c.name as category_name,
                      s.used_signatures,
                      COALESCE(s.max_signatures, c.max_signatures) as effective_max
               FROM accounts a
               JOIN account_signatures s ON a.id = s.account_id
               JOIN categories c ON s.category_id = c.id
               WHERE (a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = $1::date
               ORDER BY a.phone, c.name""",
            date_str
        )
        return [dict(r) for r in rows]


async def get_stats_by_date(date_str: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.id as account_id, a.phone,
                      c.name as category_name,
                      COUNT(o.id) as sold_count,
                      COALESCE(s.max_signatures, c.max_signatures) as effective_max,
                      s.used_signatures
               FROM orders o
               JOIN accounts a ON o.account_id = a.id
               JOIN categories c ON o.category_id = c.id
               JOIN account_signatures s ON s.account_id = a.id AND s.category_id = c.id
               WHERE (o.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = $1::date
                 AND o.status != 'rejected'
               GROUP BY a.id, a.phone, c.name, s.max_signatures, c.max_signatures, s.used_signatures
               ORDER BY a.phone, c.name""",
            date_str
        )
        return [dict(r) for r in rows]


async def get_sales_stats_by_period(date_from: str = None, date_to: str = None) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["o.status != 'rejected'"]
        params = []
        idx = 1
        if date_from:
            conditions.append(f"(o.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date >= ${idx}::date")
            params.append(date_from)
            idx += 1
        if date_to:
            conditions.append(f"(o.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date <= ${idx}::date")
            params.append(date_to)
            idx += 1
        where = " AND ".join(conditions)
        rows = await conn.fetch(
            f"""SELECT a.id as account_id, a.phone, a.password,
                       c.name as category_name,
                       c.price as category_price,
                       COUNT(o.id) as sold_count,
                       SUM(o.total_signatures) as total_sigs_sold,
                       SUM(o.price_paid) as revenue,
                       COALESCE(s.max_signatures, c.max_signatures) as effective_max,
                       s.used_signatures
                FROM orders o
                JOIN accounts a ON o.account_id = a.id
                JOIN categories c ON o.category_id = c.id
                JOIN account_signatures s ON s.account_id = a.id AND s.category_id = c.id
                WHERE {where}
                GROUP BY a.id, a.phone, a.password, c.name, c.price, s.max_signatures, c.max_signatures, s.used_signatures
                ORDER BY a.phone, c.name""",
            *params
        )
        return [dict(r) for r in rows]


async def release_expired_reservations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE account_signatures 
               SET reserved_by = NULL, reserved_until = NULL
               WHERE reserved_until IS NOT NULL AND reserved_until <= NOW()"""
        )


async def release_account_reservation(account_id: int | None):
    if not account_id:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE account_signatures 
               SET reserved_by = NULL, reserved_until = NULL
               WHERE account_id = $1""",
            account_id
        )


async def restore_account_signatures(account_id: int, category_id: int, count: int):
    if not account_id or count <= 0:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE account_signatures 
               SET used_signatures = GREATEST(used_signatures - $1, 0),
                   reserved_by = NULL,
                   reserved_until = NULL
               WHERE account_id = $2 AND category_id = $3""",
            count, account_id, category_id
        )


def normalize_phone(p: str) -> str:
    p = p.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if p.startswith("+7") and len(p) == 12:
        p = p[2:]
    elif p.startswith("8") and len(p) == 11:
        p = p[1:]
    elif p.startswith("7") and len(p) == 11:
        p = p[1:]
    return p


async def get_accounts_availability_by_phones(phones: list[str]) -> list[dict]:
    if not phones:
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        normalized = list(set(normalize_phone(p) for p in phones if p.strip()))
        rows = await conn.fetch(
            """SELECT a.id, a.phone, a.password, a.created_at,
                      c.name as category_name,
                      c.price as category_price,
                      s.used_signatures,
                      COALESCE(s.max_signatures, c.max_signatures) as effective_max
               FROM accounts a
               JOIN account_signatures s ON a.id = s.account_id
               JOIN categories c ON s.category_id = c.id
               WHERE a.phone = ANY($1)
               ORDER BY a.phone, c.name""",
            normalized
        )
        return [dict(r) for r in rows]


async def get_availability_summary() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.name as category_name,
                      COUNT(DISTINCT a.id) as accounts_count,
                      SUM(COALESCE(s.max_signatures, c.max_signatures) - s.used_signatures) as remaining_signatures,
                      SUM(COALESCE(s.max_signatures, c.max_signatures)) as total_signatures
               FROM accounts a
               JOIN account_signatures s ON a.id = s.account_id
               JOIN categories c ON s.category_id = c.id
               WHERE a.is_enabled = 1
               GROUP BY c.id, c.name
               ORDER BY c.name"""
        )
        return [dict(r) for r in rows]
