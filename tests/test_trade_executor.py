import os
import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xrp_bot")


@pytest.fixture(autouse=True)
def setup_and_teardown():
    from monitor.db_migrate import migrate
    migrate(DATABASE_URL)

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

    assert "S1_EMA_Cross" in executor._open_positions

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

    closed = executor.check_exit(current_price=0.55)
    assert len(closed) == 1
    assert "TP" in closed[0][1]

    assert get_open_positions() == []

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
