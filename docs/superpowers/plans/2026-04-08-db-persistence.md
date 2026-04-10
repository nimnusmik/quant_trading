# DB Persistence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PostgreSQL persistence for positions, trade history, and signal logs so the monitoring bot survives restarts and retains full trade/signal history.

**Architecture:** Raw psycopg2 with SimpleConnectionPool, a migration script for schema creation, and DB-backed operations in trade_executor and signal_monitor. On restart, open positions are loaded from DB and TP/SL monitoring resumes automatically with a Telegram notification.

**Tech Stack:** psycopg2-binary, PostgreSQL (local), pytest, testing.postgresql or psycopg2 against a test DB

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `monitor/db.py` | Create | Connection pool + all DB CRUD operations |
| `monitor/db_migrate.py` | Create | Schema creation, version tracking |
| `monitor/trade_executor.py` | Modify | Write/delete positions in DB, write trade_history on close |
| `monitor/signal_monitor.py` | Modify | Log signals to signal_log table |
| `monitor/scheduler.py` | Modify | Load positions from DB on startup, send recovery notification |
| `.env.example` | Modify | Add DATABASE_URL |
| `requirements_monitor.txt` | Modify | Add psycopg2-binary, pytest |
| `tests/test_db.py` | Create | Tests for db.py operations |
| `tests/test_trade_executor.py` | Create | Tests for DB-backed trade_executor |
| `tests/test_signal_monitor.py` | Create | Tests for signal logging |

---

### Task 1: Dependencies and env setup

**Files:**
- Modify: `requirements_monitor.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add psycopg2-binary and pytest to requirements**

In `requirements_monitor.txt`, append:
```
psycopg2-binary>=2.9
pytest>=7.0
```

- [ ] **Step 2: Add DATABASE_URL to .env.example**

In `.env.example`, append:
```
# PostgreSQL 연결 (모니터링 봇 상태 저장)
DATABASE_URL=postgresql://xrp_bot:password@localhost:5432/xrp_bot
```

- [ ] **Step 3: Install dependencies**

Run: `pip install psycopg2-binary pytest`

- [ ] **Step 4: Create the test database**

Run:
```bash
createdb xrp_bot
```
If you need a user:
```bash
createuser -s xrp_bot
```

- [ ] **Step 5: Commit**

```bash
git add requirements_monitor.txt .env.example
git commit -m "feat: add psycopg2 and pytest dependencies for DB persistence"
```

---

### Task 2: Schema migration script

**Files:**
- Create: `monitor/db_migrate.py`
- Create: `tests/test_db_migrate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_migrate.py`:
```python
import os
import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    # Clean up tables after test
    with conn.cursor() as cur:
        for table in ["signal_log", "trade_history", "positions", "schema_version"]:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    conn.close()


def test_migrate_creates_all_tables(db_conn):
    from monitor.db_migrate import migrate

    migrate(DATABASE_URL)

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = [row[0] for row in cur.fetchall()]

    assert "positions" in tables
    assert "trade_history" in tables
    assert "signal_log" in tables
    assert "schema_version" in tables


def test_migrate_is_idempotent(db_conn):
    from monitor.db_migrate import migrate

    migrate(DATABASE_URL)
    migrate(DATABASE_URL)  # should not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM schema_version")
        count = cur.fetchone()[0]

    assert count == 1  # only one version row


def test_positions_strategy_unique(db_conn):
    from monitor.db_migrate import migrate

    migrate(DATABASE_URL)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO positions (strategy, symbol, side, entry_price, tp, sl, size) "
            "VALUES ('S1_EMA_Cross', 'XRPUSDT', 'long', 0.5, 0.55, 0.48, 100)"
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO positions (strategy, symbol, side, entry_price, tp, sl, size) "
                "VALUES ('S1_EMA_Cross', 'XRPUSDT', 'long', 0.6, 0.65, 0.55, 200)"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_migrate.py -v`
Expected: FAIL with "No module named 'monitor.db_migrate'"

- [ ] **Step 3: Write the migration script**

Create `monitor/db_migrate.py`:
```python
"""
Schema migration for the monitoring bot's PostgreSQL database.

Usage:
    python -m monitor.db_migrate              # uses DATABASE_URL from .env
    python -m monitor.db_migrate --url "..."  # explicit URL
"""

import os
import sys
import argparse
import psycopg2
from dotenv import load_dotenv

load_dotenv()

CURRENT_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER       NOT NULL,
    applied_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
    id           SERIAL          PRIMARY KEY,
    strategy     VARCHAR(30)     NOT NULL UNIQUE,
    symbol       VARCHAR(20)     NOT NULL,
    side         VARCHAR(5)      NOT NULL,
    entry_price  NUMERIC(18,8)   NOT NULL,
    tp           NUMERIC(18,8)   NOT NULL,
    sl           NUMERIC(18,8)   NOT NULL,
    size         NUMERIC(18,8)   NOT NULL,
    opened_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trade_history (
    id           SERIAL          PRIMARY KEY,
    strategy     VARCHAR(30)     NOT NULL,
    symbol       VARCHAR(20)     NOT NULL,
    side         VARCHAR(5)      NOT NULL,
    entry_price  NUMERIC(18,8)   NOT NULL,
    exit_price   NUMERIC(18,8)   NOT NULL,
    size         NUMERIC(18,8)   NOT NULL,
    pnl_pct      NUMERIC(8,4),
    exit_reason  VARCHAR(20),
    opened_at    TIMESTAMPTZ     NOT NULL,
    closed_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_log (
    id              SERIAL          PRIMARY KEY,
    strategy        VARCHAR(30)     NOT NULL,
    symbol          VARCHAR(20)     NOT NULL,
    side            VARCHAR(5)      NOT NULL,
    interval        VARCHAR(5)      NOT NULL,
    price           NUMERIC(18,8)   NOT NULL,
    rsi             NUMERIC(6,2),
    vwap            NUMERIC(18,8),
    acted           BOOLEAN         NOT NULL DEFAULT FALSE,
    reason_skipped  VARCHAR(100),
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
"""


def migrate(database_url: str = None) -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        print("[db_migrate] DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            # Check current version
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = 'public' AND table_name = 'schema_version'"
                ")"
            )
            has_version_table = cur.fetchone()[0]

            if has_version_table:
                cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
                current = cur.fetchone()[0]
                if current >= CURRENT_VERSION:
                    print(f"[db_migrate] Schema already at v{current}, nothing to do")
                    return

            # Apply schema
            cur.execute(_SCHEMA_V1)
            if not has_version_table:
                cur.execute(
                    "INSERT INTO schema_version (version) VALUES (%s)",
                    (CURRENT_VERSION,),
                )
            print(f"[db_migrate] Schema migrated to v{CURRENT_VERSION}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DB migrations")
    parser.add_argument("--url", help="PostgreSQL connection URL")
    args = parser.parse_args()
    migrate(args.url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_migrate.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add monitor/db_migrate.py tests/test_db_migrate.py
git commit -m "feat: add schema migration script with positions, trade_history, signal_log tables"
```

---

### Task 3: Database operations module (db.py)

**Files:**
- Create: `monitor/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:
```python
import os
from datetime import datetime, timezone
import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Run migration before each test, clean tables after."""
    from monitor.db_migrate import migrate
    migrate(DATABASE_URL)

    yield

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM signal_log")
        cur.execute("DELETE FROM trade_history")
        cur.execute("DELETE FROM positions")
    conn.close()


@pytest.fixture
def db():
    from monitor.db import init_pool, close_pool
    pool = init_pool(DATABASE_URL)
    yield pool
    close_pool()


def test_insert_and_get_position(db):
    from monitor.db import insert_position, get_open_positions

    pos = {
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "entry_price": 0.52,
        "tp": 0.546,
        "sl": 0.494,
        "size": 192.3077,
    }
    insert_position(pos)

    positions = get_open_positions()
    assert len(positions) == 1
    assert positions[0]["strategy"] == "S1_EMA_Cross"
    assert float(positions[0]["entry_price"]) == 0.52


def test_delete_position(db):
    from monitor.db import insert_position, delete_position, get_open_positions

    insert_position({
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "entry_price": 0.52,
        "tp": 0.546,
        "sl": 0.494,
        "size": 192.3077,
    })
    deleted = delete_position("S1_EMA_Cross")
    assert deleted is not None
    assert deleted["strategy"] == "S1_EMA_Cross"
    assert get_open_positions() == []


def test_delete_nonexistent_position(db):
    from monitor.db import delete_position

    result = delete_position("S99_Nonexistent")
    assert result is None


def test_insert_trade(db):
    from monitor.db import insert_trade

    trade = {
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "entry_price": 0.52,
        "exit_price": 0.546,
        "size": 192.3077,
        "pnl_pct": 5.0,
        "exit_reason": "TP",
        "opened_at": datetime.now(timezone.utc),
    }
    trade_id = insert_trade(trade)
    assert trade_id > 0


def test_insert_signal(db):
    from monitor.db import insert_signal

    signal = {
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "interval": "1h",
        "price": 0.52,
        "rsi": 45.3,
        "vwap": 0.518,
        "acted": False,
        "reason_skipped": None,
    }
    signal_id = insert_signal(signal)
    assert signal_id > 0


def test_update_signal_acted(db):
    from monitor.db import insert_signal, update_signal_acted

    signal_id = insert_signal({
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "interval": "1h",
        "price": 0.52,
        "rsi": 45.3,
        "vwap": 0.518,
        "acted": False,
        "reason_skipped": None,
    })
    update_signal_acted(signal_id)

    # Verify via direct query
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT acted FROM signal_log WHERE id = %s", (signal_id,))
        assert cur.fetchone()[0] is True
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with "No module named 'monitor.db'"

- [ ] **Step 3: Write db.py**

Create `monitor/db.py`:
```python
"""
Database operations for the monitoring bot.

All DB access goes through this module. Uses a connection pool
for efficient connection reuse in the single-process bot.
"""

import os
from datetime import datetime, timezone
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

_pool = None


def init_pool(database_url: str = None) -> pool.SimpleConnectionPool:
    """Initialize the connection pool. Call once at startup."""
    global _pool
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    _pool = pool.SimpleConnectionPool(minconn=1, maxconn=3, dsn=url)
    return _pool


def close_pool() -> None:
    """Close all connections in the pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


def _get_conn():
    """Get a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized — call init_pool() first")
    return _pool.getconn()


def _put_conn(conn):
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


# ── Positions ───────────────────────────────────────


def insert_position(pos: dict) -> int:
    """Insert an open position. Returns the row ID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO positions "
                "(strategy, symbol, side, entry_price, tp, sl, size) "
                "VALUES (%(strategy)s, %(symbol)s, %(side)s, "
                "%(entry_price)s, %(tp)s, %(sl)s, %(size)s) "
                "RETURNING id",
                pos,
            )
            row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def get_open_positions() -> list:
    """Return all open positions as a list of dicts."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM positions ORDER BY opened_at")
            return [dict(row) for row in cur.fetchall()]
    finally:
        _put_conn(conn)


def delete_position(strategy: str) -> dict | None:
    """Delete a position by strategy name. Returns the deleted row or None."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "DELETE FROM positions WHERE strategy = %s "
                "RETURNING *",
                (strategy,),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


# ── Trade History ───────────────────────────────────


def insert_trade(trade: dict) -> int:
    """Insert a completed trade. Returns the row ID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trade_history "
                "(strategy, symbol, side, entry_price, exit_price, size, "
                " pnl_pct, exit_reason, opened_at) "
                "VALUES (%(strategy)s, %(symbol)s, %(side)s, "
                "%(entry_price)s, %(exit_price)s, %(size)s, "
                "%(pnl_pct)s, %(exit_reason)s, %(opened_at)s) "
                "RETURNING id",
                trade,
            )
            row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


# ── Signal Log ──────────────────────────────────────


def insert_signal(signal: dict) -> int:
    """Insert a signal log entry. Returns the row ID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO signal_log "
                "(strategy, symbol, side, interval, price, rsi, vwap, "
                " acted, reason_skipped) "
                "VALUES (%(strategy)s, %(symbol)s, %(side)s, %(interval)s, "
                "%(price)s, %(rsi)s, %(vwap)s, %(acted)s, %(reason_skipped)s) "
                "RETURNING id",
                signal,
            )
            row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def update_signal_acted(signal_id: int) -> None:
    """Mark a signal as acted upon."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE signal_log SET acted = TRUE WHERE id = %s",
                (signal_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add monitor/db.py tests/test_db.py
git commit -m "feat: add DB operations module with connection pool and CRUD for positions, trades, signals"
```

---

### Task 4: Integrate DB into trade_executor.py

**Files:**
- Modify: `monitor/trade_executor.py`
- Create: `tests/test_trade_executor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trade_executor.py`:
```python
import os
import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture(autouse=True)
def setup_and_teardown():
    from monitor.db_migrate import migrate
    migrate(DATABASE_URL)

    # Force paper mode and init pool
    os.environ["TRADE_MODE"] = "paper"
    from monitor import db
    db.init_pool(DATABASE_URL)

    yield

    db.close_pool()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM signal_log")
        cur.execute("DELETE FROM trade_history")
        cur.execute("DELETE FROM positions")
    conn.close()


@pytest.fixture
def executor():
    """Fresh trade_executor with cleared in-memory state."""
    from monitor import trade_executor
    trade_executor._open_positions.clear()
    return trade_executor


def test_execute_signal_persists_position(executor):
    from monitor.db import get_open_positions

    executor.execute_signal(
        symbol="XRPUSDT",
        side="long",
        price=0.52,
        strategy="S1_EMA_Cross",
        tp_pct=0.05,
        sl_pct=0.01,
    )

    # Check in-memory
    assert "S1_EMA_Cross" in executor._open_positions

    # Check DB
    positions = get_open_positions()
    assert len(positions) == 1
    assert positions[0]["strategy"] == "S1_EMA_Cross"
    assert float(positions[0]["entry_price"]) == 0.52


def test_check_exit_persists_trade_history(executor):
    from monitor.db import get_open_positions

    executor.execute_signal(
        symbol="XRPUSDT",
        side="long",
        price=0.52,
        strategy="S1_EMA_Cross",
        tp_pct=0.05,
        sl_pct=0.01,
    )

    # TP hit
    closed = executor.check_exit(current_price=0.55)
    assert len(closed) == 1
    assert "TP" in closed[0][1]

    # Position gone from DB
    assert get_open_positions() == []

    # Trade in history
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM trade_history WHERE strategy = 'S1_EMA_Cross'")
        assert cur.fetchone()[0] == 1
    conn.close()


def test_duplicate_position_blocked(executor):
    executor.execute_signal(
        symbol="XRPUSDT", side="long", price=0.52,
        strategy="S1_EMA_Cross", tp_pct=0.05, sl_pct=0.01,
    )
    result = executor.execute_signal(
        symbol="XRPUSDT", side="long", price=0.53,
        strategy="S1_EMA_Cross", tp_pct=0.05, sl_pct=0.01,
    )
    assert result == {}


def test_load_positions_from_db(executor):
    from monitor.db import insert_position

    # Simulate a position saved from a previous run
    insert_position({
        "strategy": "S6_MACD_Volume",
        "symbol": "XRPUSDT",
        "side": "long",
        "entry_price": 0.50,
        "tp": 0.525,
        "sl": 0.495,
        "size": 200.0,
    })

    executor.load_positions_from_db()
    assert "S6_MACD_Volume" in executor._open_positions
    assert executor._open_positions["S6_MACD_Volume"]["entry_price"] == 0.50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trade_executor.py -v`
Expected: FAIL (db calls not yet wired in, `load_positions_from_db` not defined)

- [ ] **Step 3: Modify trade_executor.py**

Replace the entire content of `monitor/trade_executor.py` with:
```python
"""
Trade executor with PostgreSQL persistence.

TRADE_MODE=paper  : no real orders, log only (default)
TRADE_MODE=live   : real market orders via ccxt

Positions are persisted to DB and cached in memory.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

_TRADE_MODE = os.getenv("TRADE_MODE", "paper").lower()

_exchange = None
if _TRADE_MODE == "live":
    try:
        import ccxt
        _exchange = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_SECRET", ""),
        })
    except ImportError:
        print("[trade_executor] ccxt not installed — pip install ccxt")

# In-memory cache of open positions (backed by DB)
_open_positions = {}


def load_positions_from_db() -> list:
    """Load open positions from DB into in-memory cache. Returns the list."""
    try:
        from monitor.db import get_open_positions
        rows = get_open_positions()
        for row in rows:
            _open_positions[row["strategy"]] = {
                "symbol":      row["symbol"],
                "side":        row["side"],
                "entry_price": float(row["entry_price"]),
                "tp":          float(row["tp"]),
                "sl":          float(row["sl"]),
                "size":        float(row["size"]),
                "strategy":    row["strategy"],
            }
        return rows
    except Exception as e:
        print(f"[trade_executor] Failed to load positions from DB: {e}")
        return []


def get_position(strategy: str = None) -> dict | None:
    if strategy is None:
        return _open_positions if _open_positions else None
    return _open_positions.get(strategy)


def get_all_positions() -> dict:
    return dict(_open_positions)


def execute_signal(
    symbol: str,
    side: str,
    price: float,
    strategy: str = "unknown",
    tp_pct: float = 0.012,
    sl_pct: float = 0.005,
    size_usdt: float = 100.0,
    bot_send=None,
) -> dict:
    if strategy in _open_positions:
        print(f"[trade] {strategy} position already open — skipping")
        return {}

    tp = price * (1 + tp_pct) if side == "long" else price * (1 - tp_pct)
    sl = price * (1 - sl_pct) if side == "long" else price * (1 + sl_pct)
    amount = size_usdt / price

    position = {
        "symbol":      symbol,
        "side":        side,
        "entry_price": price,
        "tp":          tp,
        "sl":          sl,
        "size":        amount,
        "strategy":    strategy,
    }

    coin = symbol.replace("USDT", "")
    side_kr = "롱" if side == "long" else "숏"
    n_active = len(_open_positions) + 1

    if _TRADE_MODE == "paper":
        _open_positions[strategy] = position
        _persist_position(position)

        msg = (
            f"📋 [PAPER] {side_kr} 진입 — {strategy}\n"
            f"{coin} @ ${price:,.4f}\n"
            f"TP: ${tp:,.4f} (+{tp_pct*100:.1f}%) | SL: ${sl:,.4f} (-{sl_pct*100:.1f}%)\n"
            f"수량: {amount:.4f} {coin}\n"
            f"활성 포지션: {n_active}개"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return position

    # live mode
    try:
        binance_side = "buy" if side == "long" else "sell"
        order = _exchange.create_market_order(symbol, binance_side, amount)
        filled_price = order.get("average", price)
        position["entry_price"] = filled_price
        _open_positions[strategy] = position
        _persist_position(position)

        msg = (
            f"✅ [LIVE] {side_kr} 진입 완료 — {strategy}\n"
            f"{coin} @ ${filled_price:,.4f}\n"
            f"TP: ${tp:,.4f} | SL: ${sl:,.4f}\n"
            f"주문ID: {order.get('id', 'N/A')}\n"
            f"활성 포지션: {n_active}개"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return order

    except Exception as e:
        err = f"[trade] {strategy} order failed: {e}"
        print(err)
        if bot_send:
            bot_send(f"⚠️ {strategy} 주문 실패: {e}")
        return {}


def check_exit(current_price: float, bot_send=None) -> list:
    closed = []
    to_close = []

    for strategy, p in _open_positions.items():
        reason = None

        if p["side"] == "long":
            if current_price >= p["tp"]:
                pnl_pct = (current_price / p["entry_price"] - 1) * 100
                reason = f"TP 도달 +{pnl_pct:.2f}%"
            elif current_price <= p["sl"]:
                pnl_pct = (current_price / p["entry_price"] - 1) * 100
                reason = f"SL 도달 {pnl_pct:.2f}%"
        else:
            if current_price <= p["tp"]:
                pnl_pct = (p["entry_price"] / current_price - 1) * 100
                reason = f"TP 도달 +{pnl_pct:.2f}%"
            elif current_price >= p["sl"]:
                pnl_pct = (p["entry_price"] / current_price - 1) * 100
                reason = f"SL 도달 {pnl_pct:.2f}%"

        if reason:
            coin = p["symbol"].replace("USDT", "")
            side_kr = "롱" if p["side"] == "long" else "숏"
            emoji = "💰" if "TP" in reason else "🛑"
            msg = (
                f"{emoji} [{side_kr} 청산] {coin} — {strategy}\n"
                f"진입: ${p['entry_price']:,.4f} → 현재: ${current_price:,.4f}\n"
                f"결과: {reason}"
            )
            print(msg)
            if bot_send:
                bot_send(msg)
            to_close.append((strategy, p, current_price, reason))
            closed.append((strategy, reason))

    for strategy, p, exit_price, reason in to_close:
        del _open_positions[strategy]
        _persist_close(strategy, p, exit_price, reason)

    return closed


def _persist_position(position: dict) -> None:
    """Write position to DB. Logs warning on failure but doesn't crash."""
    try:
        from monitor.db import insert_position
        insert_position({
            "strategy":    position["strategy"],
            "symbol":      position["symbol"],
            "side":        position["side"],
            "entry_price": position["entry_price"],
            "tp":          position["tp"],
            "sl":          position["sl"],
            "size":        position["size"],
        })
    except Exception as e:
        print(f"[trade_executor] DB write failed (position): {e}")


def _persist_close(strategy: str, position: dict, exit_price: float, reason: str) -> None:
    """Delete position from DB and write trade history. Logs warning on failure."""
    try:
        from monitor.db import delete_position, insert_trade
        deleted = delete_position(strategy)
        opened_at = deleted["opened_at"] if deleted else datetime.now(timezone.utc)

        exit_reason = "TP" if "TP" in reason else "SL"
        if position["side"] == "long":
            pnl_pct = (exit_price / position["entry_price"] - 1) * 100
        else:
            pnl_pct = (position["entry_price"] / exit_price - 1) * 100

        insert_trade({
            "strategy":    strategy,
            "symbol":      position["symbol"],
            "side":        position["side"],
            "entry_price": position["entry_price"],
            "exit_price":  exit_price,
            "size":        position["size"],
            "pnl_pct":     round(pnl_pct, 4),
            "exit_reason":  exit_reason,
            "opened_at":   opened_at,
        })
    except Exception as e:
        print(f"[trade_executor] DB write failed (trade history): {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trade_executor.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add monitor/trade_executor.py tests/test_trade_executor.py
git commit -m "feat: integrate DB persistence into trade_executor for positions and trade history"
```

---

### Task 5: Integrate signal logging into signal_monitor.py

**Files:**
- Modify: `monitor/signal_monitor.py`
- Create: `tests/test_signal_monitor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_signal_monitor.py`:
```python
import os
import psycopg2
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture(autouse=True)
def setup_and_teardown():
    from monitor.db_migrate import migrate
    migrate(DATABASE_URL)
    from monitor import db
    db.init_pool(DATABASE_URL)

    yield

    db.close_pool()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM signal_log")
        cur.execute("DELETE FROM trade_history")
        cur.execute("DELETE FROM positions")
    conn.close()


def _make_fake_df(n=150, trigger_signal=True):
    """Create a minimal DataFrame with columns signal_monitor expects."""
    dates = pd.date_range("2026-01-01", periods=n, freq="1h")
    close = np.random.uniform(0.5, 0.6, n)
    df = pd.DataFrame({
        "datetime": dates,
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.uniform(1000, 5000, n),
        "ema_fast": close * 0.999,
        "ema_slow": close * 1.001,
        "ema_trend": close * 1.002,
        "ema_cross_up": [False] * n,
        "ema_cross_down": [False] * n,
        "ema_bullish": [False] * n,
        "ema_bearish": [False] * n,
        "rsi": [50.0] * n,
        "vwap": close,
        "price_vs_vwap": [0.0] * n,
        "vol_ratio": [1.5] * n,
        "bb_mid": close,
        "bb_upper": close * 1.02,
        "bb_lower": close * 0.98,
        "bb_squeeze": [False] * n,
        "macd_cross_up": [False] * n,
        "macd_cross_down": [False] * n,
    })
    if trigger_signal:
        # Trigger S1_EMA_Cross long signal at index -2 (the candle we check)
        df.loc[df.index[-2], "ema_cross_up"] = True
        df.loc[df.index[-2], "rsi"] = 45.0
    return df


def test_signal_logged_to_db():
    from monitor.signal_monitor import check_signals, _last_signal_candle
    _last_signal_candle.clear()

    fake_df = _make_fake_df(trigger_signal=True)

    sent_messages = []
    def fake_send(msg):
        sent_messages.append(msg)

    with patch("monitor.signal_monitor._fetch_latest_candles", return_value=fake_df), \
         patch("monitor.signal_monitor.compute_all", return_value=fake_df):

        fired = check_signals(fake_send, interval="1h")

    # Signal was detected
    assert len(fired) > 0

    # Signal was logged to DB
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM signal_log")
        count = cur.fetchone()[0]
    conn.close()
    assert count > 0


def test_no_signal_not_logged():
    from monitor.signal_monitor import check_signals, _last_signal_candle
    _last_signal_candle.clear()

    fake_df = _make_fake_df(trigger_signal=False)

    with patch("monitor.signal_monitor._fetch_latest_candles", return_value=fake_df), \
         patch("monitor.signal_monitor.compute_all", return_value=fake_df):

        fired = check_signals(lambda msg: None, interval="1h")

    assert len(fired) == 0

    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM signal_log")
        count = cur.fetchone()[0]
    conn.close()
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signal_monitor.py -v`
Expected: FAIL (signal_monitor doesn't log to DB yet)

- [ ] **Step 3: Modify signal_monitor.py**

Add signal logging to `check_signals()`. In `monitor/signal_monitor.py`, add this import near the top (after existing imports):

```python
from monitor.db import insert_signal, update_signal_acted
```

Then, inside the `check_signals` function, replace the inner loop body (the `for side, sig_series in ...` block starting at line 125) with:

```python
                for side, sig_series in [("long", long_sig)]:
                    if not sig_series.iloc[-2]:
                        continue

                    # Log signal to DB
                    signal_id = None
                    try:
                        signal_id = insert_signal({
                            "strategy": strat_name,
                            "symbol": symbol,
                            "side": side,
                            "interval": interval,
                            "price": float(last_candle["close"]),
                            "rsi": float(last_candle.get("rsi", 0)),
                            "vwap": float(last_candle.get("vwap", 0)),
                            "acted": False,
                            "reason_skipped": None,
                        })
                    except Exception as e:
                        print(f"[signal_monitor] DB signal log failed: {e}")

                    # Duplicate alert prevention
                    key = (symbol, strat_name, side, interval)
                    if _last_signal_candle.get(key) == last_candle_time:
                        if signal_id:
                            try:
                                from monitor.db import update_signal_acted
                                # Already alerted — mark reason
                            except Exception:
                                pass
                        continue
                    _last_signal_candle[key] = last_candle_time

                    label = STRATEGY_LABELS[strat_name]
                    emoji = "🟢" if side == "long" else "🔴"
                    side_kr = "롱" if side == "long" else "숏"

                    price_vs_vwap_pct = last_candle.get("price_vs_vwap", 0) * 100

                    msg = (
                        f"{emoji} [{label}] {side_kr} 신호\n"
                        f"코인: {coin}/USDT | {interval}\n"
                        f"가격: ${last_candle['close']:,.4f}\n"
                        f"RSI: {last_candle['rsi']:.1f} | "
                        f"VWAP: ${last_candle['vwap']:,.4f} "
                        f"({price_vs_vwap_pct:+.2f}%)\n"
                        f"─────────────────\n"
                        f"EMA: {params.get('ema_fast', '?')}/{params.get('ema_slow', '?')} | "
                        f"TP: {params.get('tp_pct', 0):.1%} | "
                        f"SL: {params.get('sl_pct', 0):.1%}"
                    )
                    bot_send(msg)
                    fired.append((symbol, strat_name, side, params, signal_id))
```

Note: `fired` now includes `signal_id` as the 5th element. Update the return type accordingly.

- [ ] **Step 4: Update scheduler.py to pass signal_id**

In `monitor/scheduler.py`, update `_execute_signals` to handle the new tuple format and mark signals as acted:

```python
def _execute_signals(fired: list):
    """Execute trades for fired signals and mark them as acted in DB."""
    for item in fired:
        symbol, strat_name, side, params = item[0], item[1], item[2], item[3]
        signal_id = item[4] if len(item) > 4 else None

        price = _last_prices.get(symbol, 0)
        if price <= 0:
            continue

        tp_pct = params.get("tp_pct", 0.012)
        sl_pct = params.get("sl_pct", 0.005)

        result = trade_executor.execute_signal(
            symbol=symbol,
            side=side,
            price=price,
            strategy=strat_name,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            bot_send=send,
        )

        if result and signal_id:
            try:
                from monitor.db import update_signal_acted
                update_signal_acted(signal_id)
            except Exception as e:
                print(f"[scheduler] Failed to mark signal as acted: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_signal_monitor.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add monitor/signal_monitor.py monitor/scheduler.py tests/test_signal_monitor.py
git commit -m "feat: log all detected signals to signal_log table with acted tracking"
```

---

### Task 6: Startup recovery in scheduler.py

**Files:**
- Modify: `monitor/scheduler.py`
- Modify: `monitor/run_monitor.py` (the project root `run_monitor.py`)

- [ ] **Step 1: Modify scheduler.py to add recovery logic**

In `monitor/scheduler.py`, add a `startup_recovery` function and call DB init + migration at scheduler creation. Replace `create_scheduler` with:

```python
def startup_recovery(bot_send) -> None:
    """Load positions from DB and notify via Telegram."""
    positions = trade_executor.load_positions_from_db()
    if positions:
        lines = []
        for p in positions:
            side_kr = "롱" if p["side"] == "long" else "숏"
            lines.append(
                f"  {p['strategy']} {side_kr} @ ${float(p['entry_price']):,.4f}"
            )
        msg = (
            f"🔄 봇 재시작 — 포지션 {len(positions)}개 복구됨\n"
            + "\n".join(lines)
        )
    else:
        msg = "🔄 봇 재시작 — 오픈 포지션 없음"
    print(msg)
    bot_send(msg)


def create_scheduler() -> BackgroundScheduler:
    """Create scheduler and register all jobs."""
    # Initialize DB
    from monitor.db import init_pool
    from monitor.db_migrate import migrate
    import os

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[scheduler] DATABASE_URL not set — DB persistence disabled")
    else:
        migrate(db_url)
        init_pool(db_url)
        startup_recovery(send)

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        _job_price_check,
        "interval",
        minutes=1,
        id="price_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job_signal_1h,
        "interval",
        hours=1,
        id="signal_1h",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job_daily_briefing,
        CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="daily_briefing",
        max_instances=1,
    )

    return scheduler
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add monitor/scheduler.py
git commit -m "feat: add startup recovery — load positions from DB and notify via Telegram on restart"
```

---

### Task 7: Final integration test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write an end-to-end test**

Create `tests/test_integration.py`:
```python
"""
End-to-end test: signal → trade → exit → verify DB state.
"""

import os
import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture(autouse=True)
def setup_and_teardown():
    os.environ["TRADE_MODE"] = "paper"
    from monitor.db_migrate import migrate
    from monitor import db
    migrate(DATABASE_URL)
    db.init_pool(DATABASE_URL)

    yield

    db.close_pool()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM signal_log")
        cur.execute("DELETE FROM trade_history")
        cur.execute("DELETE FROM positions")
    conn.close()


def test_full_lifecycle():
    from monitor import trade_executor
    from monitor.db import (
        insert_signal, update_signal_acted,
        get_open_positions, insert_trade,
    )

    trade_executor._open_positions.clear()

    # 1. Log a signal
    signal_id = insert_signal({
        "strategy": "S1_EMA_Cross",
        "symbol": "XRPUSDT",
        "side": "long",
        "interval": "1h",
        "price": 0.52,
        "rsi": 45.0,
        "vwap": 0.518,
        "acted": False,
        "reason_skipped": None,
    })
    assert signal_id > 0

    # 2. Execute trade
    result = trade_executor.execute_signal(
        symbol="XRPUSDT",
        side="long",
        price=0.52,
        strategy="S1_EMA_Cross",
        tp_pct=0.05,
        sl_pct=0.01,
    )
    assert result != {}
    update_signal_acted(signal_id)

    # 3. Verify position in DB
    positions = get_open_positions()
    assert len(positions) == 1

    # 4. TP hit → close
    closed = trade_executor.check_exit(current_price=0.55)
    assert len(closed) == 1

    # 5. Position gone, trade in history
    assert get_open_positions() == []

    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT pnl_pct, exit_reason FROM trade_history WHERE strategy = 'S1_EMA_Cross'")
        row = cur.fetchone()
        assert row is not None
        assert float(row[0]) > 0  # positive PnL
        assert row[1] == "TP"

        cur.execute("SELECT acted FROM signal_log WHERE id = %s", (signal_id,))
        assert cur.fetchone()[0] is True
    conn.close()


def test_restart_recovery():
    from monitor import trade_executor
    from monitor.db import insert_position

    trade_executor._open_positions.clear()

    # Simulate position from previous run
    insert_position({
        "strategy": "S2_VWAP_Bounce",
        "symbol": "XRPUSDT",
        "side": "long",
        "entry_price": 0.50,
        "tp": 0.525,
        "sl": 0.495,
        "size": 200.0,
    })

    # Recover
    recovered = trade_executor.load_positions_from_db()
    assert len(recovered) == 1
    assert "S2_VWAP_Bounce" in trade_executor._open_positions

    # TP/SL monitoring works on recovered position
    closed = trade_executor.check_exit(current_price=0.53)
    assert len(closed) == 1
    assert "TP" in closed[0][1]
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests for DB persistence lifecycle"
```

---

### Task 8: Create tests/__init__.py and final cleanup

**Files:**
- Create: `tests/__init__.py`

- [ ] **Step 1: Create empty init**

Create `tests/__init__.py` (empty file) so pytest discovers the test package.

- [ ] **Step 2: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS (approximately 13 tests across 4 files)

- [ ] **Step 3: Commit**

```bash
git add tests/__init__.py
git commit -m "chore: add tests package init"
```
