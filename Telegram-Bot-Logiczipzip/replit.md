# Telegram SIM Sign Bot

## Overview
Telegram bot for SIM card signing service built with aiogram 3.x and PostgreSQL (asyncpg). Supports multi-signature batch ordering, CryptoBot payments (USDT), operator management, and admin panel.

## Project Architecture
```
main.py                          # Entry point, dispatcher setup, background tasks
src/
  config.py                      # BOT_TOKEN, SEED_ADMIN_IDS, CRYPTO_BOT_TOKEN, DATABASE_URL
  bot/instance.py                # Bot singleton
  db/
    database.py                  # PostgreSQL init via asyncpg, connection pool (min 2, max 20)
    accounts.py                  # Account CRUD, reservation logic with FOR UPDATE locking
    categories.py                # Category management
    orders.py                    # Order lifecycle, preorders
    payments.py                  # Payment tracking
    users.py                     # User management
    operators.py                 # Operator roles and notifications
    tickets.py                   # Support ticket system (with file attachments)
    settings.py                  # Key-value settings store
    reputation.py                # Reputation links
    reviews.py                   # Review system
    channels.py                  # Required channel subscriptions
    admins.py                    # Admin management (owner/admin roles)
  handlers/
    start.py                     # /start command, main menu, subscription check
    sim_sign.py                  # Signature ordering flow
    payment.py                   # CryptoBot payment + balance
    profile.py                   # User profile, deposit, balance
    orders.py                    # Order management, claim flow
    admin.py                     # Admin panel (categories, accounts, users, stats, channels)
    operator.py                  # Operator panel
    help.py                      # Help/FAQ, ticket creation with file attachments
    review.py                    # Review submission
  keyboards/
    user_kb.py                   # User ReplyKeyboard + InlineKeyboard
    admin_kb.py                  # Admin InlineKeyboards
  states/
    user_states.py               # User FSM states
    admin_states.py              # Admin FSM states
  utils/
    cryptobot.py                 # CryptoBot API wrapper
    excel_export.py              # Excel report generation (availability + sales)
    formatters.py                # Text formatting helpers
    totp.py                      # TOTP code generation
    preorders.py                 # Preorder fulfillment logic (reusable, no circular imports)
```

## Key Design Decisions
- **Database**: PostgreSQL via asyncpg with connection pool (min_size=2, max_size=20), comprehensive indexes on all key fields
- **Concurrency**: FOR UPDATE row locking in account reservation to prevent race conditions under high load
- **Connection pattern**: `pool = await get_pool()` then `async with pool.acquire() as conn:` for all DB operations
- **Payment**: CryptoBot USDT with 2s polling for 30 minutes
- **Ordering**: Batch purchase (e.g. 5 signatures), claim individually over 72h
- **Account allocation**: Priority DESC → reuse optimization → created_at ASC; disabled accounts (is_enabled=0) excluded
- **Deposit**: Fixed $30 from balance, withdrawal via support
- **Operators**: 3 roles (orders/support/preorders), individual notification toggles
- **BB tariff**: Exclusive account usage (Билайн $20, Теле2 $17), quantity picker for multiple packs (each pack = 1 exclusive account with full signatures)
- **Background tasks**: expiry_checker (5min), preorder_fulfiller (60s)
- **Admin management**: DB-backed admin list with owner/admin roles, owner-only management, self-removal/min-1 protection, admin stats (accounts loaded, signatures sold, revenue by period)
- **Account attribution**: added_by_admin_id tracks which admin loaded each account
- **Channel subscriptions**: Mandatory channel subscription check on /start, admins bypass
- **Ticket attachments**: file_id stored in ticket_messages, supports photos and documents
- **Account enable/disable**: is_enabled flag on accounts, toggled per-account, disabled accounts excluded from sales pool
- **Post-upload enable flow**: After bulk account upload, choose "Enable all", "Enable by phone list", or "Leave disabled"; phone normalization for flexible matching
- **Mass priority**: Set priority for all accounts assigned to a specific operator (human role)
- **Excel exports**: Availability + sales reports, custom date range support
- **Admin client management**: Admin can browse users, view profiles, see all orders with TOTP details
- **Order TOTP override**: totp_limit_override per order, admin can add TOTP attempts to specific orders via centralized compute_effective_totp_limit helper
- **TOTP tracking**: Global totp_refreshes counter per order (not per-batch), limit = base * pending_claim_qty, admin can reset via "Обнулить TOTP" button
- **Batch order grouping**: Multiple orders from one purchase share batch_group_id (uuid[:8]); "Мои заказы" and admin order lists group them as one entry with summary stats; detail view shows all accounts with claim buttons; single-order purchases have NULL batch_group_id for backward compat

## Database Indexes
- users: telegram_id
- orders: user_id, status, account_id, category_id, expires_at, created_at
- account_signatures: account_id, category_id, reserved_by
- accounts: is_enabled, operator_telegram_id, added_by_admin_id
- tickets: user_id, status, order_id
- ticket_messages: ticket_id
- payments: user_id, invoice_id, status
- deposits: user_id
- operators: telegram_id
- reviews: user_id, order_id

## Secrets Required
- `BOT_TOKEN` - Telegram Bot API token
- `CRYPTO_BOT_TOKEN` - CryptoBot API token for USDT payments
- `DATABASE_URL` - PostgreSQL connection string (auto-provided by Replit)

## User Preferences
- No comments in code
- Clean modular structure
- All bot messages in Russian
