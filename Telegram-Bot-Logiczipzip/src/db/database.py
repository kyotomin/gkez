import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None

DEFAULT_CATEGORIES = [
    ("МТС'Физ", 5.00, 2),
    ("МТС'Есим", 3.00, 2),
    ("Билайн", 4.00, 5),
    ("Мегафон", 4.50, 2),
    ("Теле2", 3.50, 5),
    ("Йота", 3.00, 2),
    ("Любой другой", 2.00, 3),
]


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=40,
        command_timeout=30,
    )
    return _pool


async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                balance DOUBLE PRECISION DEFAULT 0.0,
                is_blocked SMALLINT DEFAULT 0,
                custom_deposit DOUBLE PRECISION DEFAULT NULL,
                registered_at TIMESTAMP DEFAULT NOW(),
                is_active SMALLINT DEFAULT 1,
                last_support_at TIMESTAMP DEFAULT NULL,
                totp_limit INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                price DOUBLE PRECISION DEFAULT 0.0,
                max_signatures INTEGER DEFAULT 5,
                min_order INTEGER DEFAULT NULL,
                is_active SMALLINT DEFAULT 1,
                bb_price DOUBLE PRECISION DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                phone TEXT NOT NULL,
                password TEXT NOT NULL,
                totp_secret TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                is_enabled SMALLINT DEFAULT 1,
                operator_telegram_id BIGINT DEFAULT NULL,
                added_by_admin_id BIGINT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS account_signatures (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                max_signatures INTEGER DEFAULT NULL,
                used_signatures INTEGER DEFAULT 0,
                reserved_by BIGINT DEFAULT NULL,
                reserved_until TIMESTAMP DEFAULT NULL,
                last_issued_at TIMESTAMP,
                UNIQUE(account_id, category_id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                account_id INTEGER DEFAULT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                status TEXT DEFAULT 'active',
                totp_refreshes INTEGER DEFAULT 0,
                signatures_sent INTEGER DEFAULT 0,
                total_signatures INTEGER DEFAULT 1,
                signatures_claimed INTEGER DEFAULT 0,
                price_paid DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP DEFAULT NULL,
                completed_at TIMESTAMP,
                custom_operator_name TEXT DEFAULT NULL,
                is_exclusive SMALLINT DEFAULT 0,
                totp_limit_override INTEGER DEFAULT NULL,
                pending_claim_qty INTEGER DEFAULT 0,
                totp_at_claim_start INTEGER DEFAULT 0,
                batch_group_id TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                subject TEXT NOT NULL,
                order_id INTEGER DEFAULT NULL,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ticket_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                sender_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                file_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                paid_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS operators (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                role TEXT DEFAULT 'orders',
                notifications_enabled SMALLINT DEFAULT 1,
                added_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                invoice_id BIGINT,
                amount DOUBLE PRECISION NOT NULL,
                status TEXT DEFAULT 'pending',
                pay_url TEXT,
                purpose TEXT DEFAULT 'balance',
                payment_meta TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                paid_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS doc_requests (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                signature_num INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS order_documents (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                sender_type TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS reputation_links (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS admins (
                telegram_id BIGINT PRIMARY KEY,
                role TEXT DEFAULT 'admin',
                added_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                order_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                bonus DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, order_id)
            );

            CREATE TABLE IF NOT EXISTS required_channels (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_account_id ON orders(account_id);
            CREATE INDEX IF NOT EXISTS idx_orders_category_id ON orders(category_id);
            CREATE INDEX IF NOT EXISTS idx_orders_expires_at ON orders(expires_at);
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_account_signatures_account_id ON account_signatures(account_id);
            CREATE INDEX IF NOT EXISTS idx_account_signatures_category_id ON account_signatures(category_id);
            CREATE INDEX IF NOT EXISTS idx_account_signatures_reserved_by ON account_signatures(reserved_by);
            CREATE INDEX IF NOT EXISTS idx_accounts_is_enabled ON accounts(is_enabled);
            CREATE INDEX IF NOT EXISTS idx_accounts_operator ON accounts(operator_telegram_id);
            CREATE INDEX IF NOT EXISTS idx_accounts_added_by ON accounts(added_by_admin_id);
            CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone);
            CREATE INDEX IF NOT EXISTS idx_accounts_phone_trgm ON accounts USING gin (phone gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON tickets(user_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_order_id ON tickets(order_id);
            CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id);
            CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments(invoice_id);
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            CREATE INDEX IF NOT EXISTS idx_deposits_user_id ON deposits(user_id);
            CREATE INDEX IF NOT EXISTS idx_operators_telegram_id ON operators(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_order_id ON reviews(order_id);

            CREATE INDEX IF NOT EXISTS idx_orders_active ON orders(user_id, status) WHERE status IN ('active', 'preorder', 'pending_review');
            CREATE INDEX IF NOT EXISTS idx_orders_expiry ON orders(expires_at) WHERE status IN ('active', 'pending_review') AND expires_at IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_accounts_enabled ON accounts(id) WHERE is_enabled = 1;
            CREATE INDEX IF NOT EXISTS idx_signatures_available ON account_signatures(category_id, account_id) WHERE reserved_by IS NULL;
            CREATE INDEX IF NOT EXISTS idx_deposits_user ON deposits(user_id);
            CREATE INDEX IF NOT EXISTS idx_order_documents_order_id ON order_documents(order_id);
            CREATE INDEX IF NOT EXISTS idx_order_documents_user_id ON order_documents(user_id);
        """)

        col_exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='batch_group_id'"
        )
        if not col_exists:
            await conn.execute("ALTER TABLE orders ADD COLUMN batch_group_id TEXT DEFAULT NULL")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_batch_group ON orders(batch_group_id) WHERE batch_group_id IS NOT NULL")

        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
            "deposit_amount", "30"
        )

        cnt = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if cnt == 0:
            for name, price, max_sigs in DEFAULT_CATEGORIES:
                await conn.execute(
                    "INSERT INTO categories (name, price, max_signatures) VALUES ($1, $2, $3)",
                    name, price, max_sigs
                )

        from src.config import SEED_ADMIN_IDS
        for i, admin_id in enumerate(SEED_ADMIN_IDS):
            if i == 0:
                await conn.execute(
                    "INSERT INTO admins (telegram_id, role) VALUES ($1, 'owner') ON CONFLICT (telegram_id) DO NOTHING",
                    admin_id
                )
            else:
                await conn.execute(
                    "INSERT INTO admins (telegram_id) VALUES ($1) ON CONFLICT (telegram_id) DO NOTHING",
                    admin_id
                )

        rep_cnt = await conn.fetchval("SELECT COUNT(*) FROM reputation_links")
        if rep_cnt == 0:
            await conn.execute(
                "INSERT INTO reputation_links (name, url, sort_order) VALUES ($1, $2, $3)",
                "Continental", "https://t.me/CL_Inform/2707", 1
            )
            await conn.execute(
                "INSERT INTO reputation_links (name, url, sort_order) VALUES ($1, $2, $3)",
                "FRK", "https://t.me/FRKReputation_bot?start=p-31196", 2
            )
