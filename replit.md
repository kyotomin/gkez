# Telegram SIM Sign Bot

## Overview

A Telegram bot for a SIM card signing service built with Python. Users can browse categories of SIM cards (МТС, Билайн, Мегафон, Теле2, Йота, etc.), purchase signature slots, receive TOTP codes, and manage orders. The system supports CryptoBot (USDT) payments, operator/admin roles, preorder fulfillment, support tickets with file attachments, required channel subscriptions, reviews with bonuses, and Excel report generation.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Tech Stack
- **Language**: Python 3.12+
- **Bot Framework**: aiogram 3.x (async Telegram bot framework)
- **Database**: PostgreSQL via `asyncpg` (async connection pool, min 5 / max 40 connections)
- **FSM Storage**: In-memory (`MemoryStorage` from aiogram)
- **Payments**: CryptoBot API via `aiocryptopay` (USDT on mainnet)
- **TOTP**: `pyotp` for generating time-based one-time passwords
- **Excel**: `openpyxl` for availability and sales reports

### Project Structure
The entire bot lives under `Telegram-Bot-Logiczipzip/`. The root `main.py` is a placeholder; the real entry point is `Telegram-Bot-Logiczipzip/main.py`.

```
Telegram-Bot-Logiczipzip/
  main.py                    # Entry point: dispatcher setup, background tasks (expiry checker, preorder fulfiller, payment resume)
  src/
    config.py                # Environment variables: BOT_TOKEN, CRYPTO_BOT_TOKEN, DATABASE_URL, SEED_ADMIN_IDS
    bot/instance.py          # Bot singleton (global mutable `bot` variable)
    db/                      # Database layer (all async, uses asyncpg connection pool)
      database.py            # Pool init, schema creation (CREATE TABLE IF NOT EXISTS), default category seeding
      accounts.py            # Account CRUD, reservation with FOR UPDATE row locking
      categories.py          # Category management with live available_count computed via subquery
      orders.py              # Order lifecycle (active → pending_review → completed/expired), preorders
      payments.py            # Payment tracking (pending → paid)
      users.py               # User CRUD, balance management
      operators.py           # Operator role management
      admins.py              # Admin management (owner/admin roles)
      tickets.py             # Support tickets with daily limits and cooldowns
      settings.py            # Key-value settings store (deposit amounts, TOTP limits, FAQ text, etc.)
      reviews.py             # Review system with pagination
      channels.py            # Required channel subscriptions
      reputation.py          # Reputation links
      documents.py           # Order document attachments
    handlers/                # aiogram routers, one per feature domain
      start.py               # /start, main menu, subscription enforcement
      sim_sign.py            # SIM purchase flow (category selection → quantity → payment → order creation)
      payment.py             # CryptoBot invoice polling (5s interval, 30min timeout, semaphore-limited)
      profile.py             # User profile, deposit payment, balance top-up
      orders.py              # Order listing, signature claiming
      admin.py               # Admin panel (massive — categories, accounts, users, stats, broadcasts, channels, etc.)
      operator.py            # Operator order confirmation
      help.py                # FAQ display, support ticket creation
      review.py              # Review submission and paginated display
    keyboards/
      user_kb.py             # Reply keyboards + inline keyboards for users
      admin_kb.py            # Inline keyboards for admin panel
    states/
      user_states.py         # FSM states for user flows (tickets, orders, payments, reviews)
      admin_states.py        # FSM states for admin flows (many state groups for each admin feature)
    utils/
      cryptobot.py           # CryptoBot API wrapper (create invoice, check payment status)
      totp.py                # TOTP generation and validation using pyotp
      excel_export.py        # Excel report generation with styled headers
      formatters.py          # Text formatting helpers for profile, orders, accounts
      preorders.py           # Preorder fulfillment logic (runs as background task)
```

### Key Design Patterns

1. **Handler-per-feature routers**: Each feature (orders, admin, help, etc.) has its own `Router()` registered on the main dispatcher. This keeps the codebase modular.

2. **Database access via connection pool**: All DB functions acquire a connection from the asyncpg pool, execute queries with parameterized SQL (`$1`, `$2`), and return plain `dict` objects. No ORM is used — raw SQL throughout.

3. **Row-level locking for reservations**: Account reservation uses `FOR UPDATE` to prevent race conditions when multiple users try to reserve the same SIM account simultaneously.

4. **Background async tasks**: Three long-running tasks started at boot:
   - **Expiry checker** (every 5 min): Expires old orders (72h), releases expired reservations, notifies users.
   - **Preorder fulfiller** (periodic): Matches pending preorders to newly available accounts.
   - **Payment resume**: On startup, resumes polling for any payments left in `pending` state.

5. **Payment polling**: Instead of webhooks, payments are checked by polling CryptoBot API every 5 seconds for up to 30 minutes per invoice. A semaphore limits concurrent checks to 30.

6. **Admin/Operator role hierarchy**: Three levels — owner (from SEED_ADMIN_IDS), admin (stored in DB), operator (stored in DB with role like "orders"/"tickets"). Permissions are checked in handlers.

7. **FSM (Finite State Machine)**: aiogram's FSM with in-memory storage manages multi-step flows (ordering, ticket creation, admin operations). State is lost on restart.

8. **Schema auto-migration**: `init_db()` creates all tables with `CREATE TABLE IF NOT EXISTS`. New columns must be added via `ALTER TABLE` statements to handle existing databases (the error log shows a missing `is_exclusive` column issue — this pattern needs careful migration handling).

### Database Schema (PostgreSQL)
Key tables (created in `database.py`):
- `users` — telegram_id, username, balance, is_blocked
- `admins` — telegram_id, role (owner/admin)
- `operators` — telegram_id, username, role
- `categories` — name, price, max_signatures, is_active
- `accounts` — phone, login, password, totp_secret, is_enabled, priority
- `account_signatures` — account_id, category_id, used_signatures, max_signatures, reserved_by, reserved_until
- `orders` — user_id, account_id, category_id, status, price_paid, total_signatures, signatures_claimed, expires_at, is_exclusive, batch_group_id, custom_operator_name
- `payments` — user_id, invoice_id, amount, status, purpose, payment_meta
- `deposits` — user_id tracking
- `tickets` — user_id, order_id, subject, status
- `ticket_messages` — ticket_id, sender_type, text, file_id
- `reviews` — user_id, order_id, text, bonus
- `settings` — key/value store
- `required_channels` — channel_id, title, url
- `reputation_links` — name, url, sort_order
- `order_documents` — order_id, file_id, sender_type
- `doc_requests` — order_id, status

### Configuration
All config is via environment variables:
- `BOT_TOKEN` — Telegram bot token
- `CRYPTO_BOT_TOKEN` — CryptoBot API token
- `DATABASE_URL` — PostgreSQL connection string

Seed admin IDs are hardcoded in `config.py`: `[8181792806, 1083294848, 7699005037]`

## External Dependencies

### Services
- **Telegram Bot API** — via aiogram 3.x for all bot interactions
- **CryptoBot (Crypto Pay API)** — via `aiocryptopay` for USDT payment invoices and status checking. Uses mainnet.
- **PostgreSQL** — primary data store. Connection string from `DATABASE_URL` env var. Uses `asyncpg` with connection pooling.

### Python Packages
- `aiogram>=3.25.0` — Telegram bot framework
- `asyncpg` — Async PostgreSQL driver
- `aiocryptopay>=0.4.8` — CryptoBot payment API client
- `pyotp>=2.9.0` — TOTP code generation
- `openpyxl>=3.1.5` — Excel file generation
- `aiosqlite>=0.22.1` — Listed in requirements but NOT actively used (project uses asyncpg/PostgreSQL)

### Important Notes for Development
- The working directory for the bot is `Telegram-Bot-Logiczipzip/`, not the repo root.
- PostgreSQL must be available and `DATABASE_URL` must be set before the bot starts.
- The bot uses Russian language throughout for all user-facing text.
- FSM storage is in-memory — state is lost on restart. Consider this when testing multi-step flows.
- The `pg_trgm` PostgreSQL extension is required (created in `init_db`).