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
