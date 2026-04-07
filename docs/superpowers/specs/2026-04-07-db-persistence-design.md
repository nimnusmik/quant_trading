# DB Persistence Layer for Monitor/Trading System

**Date:** 2026-04-07
**Status:** Approved
**Branch:** regime-holdout-enhancement

## Problem

The monitoring bot stores all state (open positions, trade results, signal history) in memory. On restart, open positions are lost, trade history disappears, and there's no data for post-hoc analysis.

## Decision

Add PostgreSQL persistence using raw `psycopg2` with a simple migration script. No ORM.

**Why psycopg2 + migration script (not SQLAlchemy):**
- Only 3 simple, stable tables
- Keeps the stack lean — no ORM layer to learn/debug
- Migration script gives just enough structure to evolve the schema
- Fits the project's direct, minimal style

## Schema

### `positions` — currently open (rows deleted on close)

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| strategy | VARCHAR(30) | NOT NULL, UNIQUE |
| symbol | VARCHAR(20) | NOT NULL |
| side | VARCHAR(5) | NOT NULL |
| entry_price | NUMERIC(18,8) | NOT NULL |
| tp | NUMERIC(18,8) | NOT NULL |
| sl | NUMERIC(18,8) | NOT NULL |
| size | NUMERIC(18,8) | NOT NULL |
| opened_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |

### `trade_history` — every completed trade

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| strategy | VARCHAR(30) | NOT NULL |
| symbol | VARCHAR(20) | NOT NULL |
| side | VARCHAR(5) | NOT NULL |
| entry_price | NUMERIC(18,8) | NOT NULL |
| exit_price | NUMERIC(18,8) | NOT NULL |
| size | NUMERIC(18,8) | NOT NULL |
| pnl_pct | NUMERIC(8,4) | |
| exit_reason | VARCHAR(20) | |
| opened_at | TIMESTAMPTZ | NOT NULL |
| closed_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |

### `signal_log` — every signal detected

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| strategy | VARCHAR(30) | NOT NULL |
| symbol | VARCHAR(20) | NOT NULL |
| side | VARCHAR(5) | NOT NULL |
| interval | VARCHAR(5) | NOT NULL |
| price | NUMERIC(18,8) | NOT NULL |
| rsi | NUMERIC(6,2) | |
| vwap | NUMERIC(18,8) | |
| acted | BOOLEAN | NOT NULL, DEFAULT FALSE |
| reason_skipped | VARCHAR(100) | |
| detected_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |

### `schema_version` — migration tracking

| Column | Type | Constraints |
|--------|------|-------------|
| version | INTEGER | NOT NULL |
| applied_at | TIMESTAMPTZ | DEFAULT NOW() |

## Architecture

### New files

- **`monitor/db.py`** — Connection pool + all DB operations
  - `init_pool()` — create `SimpleConnectionPool(min=1, max=3)` from `DATABASE_URL`
  - `insert_position(position: dict)` — INSERT into positions
  - `delete_position(strategy: str)` — DELETE from positions
  - `get_open_positions() -> list[dict]` — SELECT all from positions
  - `insert_trade(trade: dict)` — INSERT into trade_history
  - `insert_signal(signal: dict)` — INSERT into signal_log
  - `update_signal_acted(signal_id: int)` — UPDATE acted=TRUE

- **`monitor/db_migrate.py`** — Schema creation and versioning
  - `CREATE TABLE IF NOT EXISTS` for all tables
  - `schema_version` table tracks current version
  - Safe to run repeatedly (idempotent)

### Modified files

- **`monitor/trade_executor.py`**
  - `execute_signal()`: write to `positions` table after successful entry
  - `check_exit()`: delete from `positions`, write to `trade_history` with PnL
  - `get_position()` / `get_all_positions()`: read from DB, keep in-memory dict as cache

- **`monitor/scheduler.py`**
  - On startup: call `db.get_open_positions()` -> load into trade_executor's in-memory dict
  - Send Telegram notification listing recovered positions (or "no open positions")

- **`monitor/signal_monitor.py`**
  - `check_signals()`: log every detected signal to `signal_log` table
  - Set `acted=true` when a trade is opened from that signal

- **`.env.example`**
  - Add `DATABASE_URL=postgresql://user:pass@localhost:5432/xrp_bot`

## Data Flow

```
Signal detected
  -> signal_monitor writes to signal_log (acted=false)
  -> if trade opened:
      trade_executor writes to positions table
      signal_monitor updates signal_log (acted=true)

TP/SL hit
  -> trade_executor deletes from positions
  -> trade_executor writes to trade_history (with PnL)

Bot restart
  -> scheduler loads positions from DB
  -> resumes TP/SL monitoring
  -> sends Telegram notification listing recovered positions
```

## Error Handling

- **DB unreachable at startup:** log error and exit. No point running without persistence.
- **DB fails mid-operation:** log error + Telegram warning. Don't crash — the in-flight trade still needs TP/SL monitoring via the in-memory cache until next successful DB write.
- **Duplicate prevention:** `positions.strategy` UNIQUE constraint enforces one position per strategy (same as current in-memory logic).
- **Signal log:** no uniqueness constraint. All signals logged; duplicates are fine for analysis.
- **Migration safety:** `CREATE TABLE IF NOT EXISTS` + `schema_version` tracking. Safe to run repeatedly. Future migrations can alter tables without breaking.

## Connection Management

- `psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=3)`
- Connection URL from `DATABASE_URL` env var
- Single-process bot, so simple pool is sufficient

## Restart Recovery

1. `scheduler.py` startup calls `db.get_open_positions()`
2. Loads results into `trade_executor`'s in-memory dict
3. Starts TP/SL monitoring immediately
4. Sends Telegram message:
   - If positions found: "Bot restarted. Recovered N open positions: [S1_EMA_Cross LONG @ $0.52, ...]"
   - If none: "Bot restarted. No open positions."
