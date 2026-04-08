"""
End-to-end integration tests for the full signal → trade → exit lifecycle
and restart recovery.
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
    """signal -> trade -> TP exit -> verify DB state"""
    from monitor import trade_executor
    from monitor.db import (
        insert_signal,
        update_signal_acted,
        get_open_positions,
        insert_trade,
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

    # 4. TP hit -> close
    closed = trade_executor.check_exit(current_price=0.55)
    assert len(closed) == 1

    # 5. Position gone, trade in history
    assert get_open_positions() == []

    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pnl_pct, exit_reason FROM trade_history "
            "WHERE strategy = 'S1_EMA_Cross'"
        )
        row = cur.fetchone()
        assert row is not None
        assert float(row[0]) > 0  # positive PnL
        # exit_reason is reason[:20], e.g. "TP 도달 +5.77%"
        assert row[1].startswith("TP")

        cur.execute(
            "SELECT acted FROM signal_log WHERE id = %s", (signal_id,)
        )
        assert cur.fetchone()[0] is True
    conn.close()


def test_restart_recovery():
    """Positions from a previous run are recovered and TP/SL monitoring works."""
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
    trade_executor.load_positions_from_db()
    assert "S2_VWAP_Bounce" in trade_executor._open_positions

    # TP/SL monitoring works on recovered position
    closed = trade_executor.check_exit(current_price=0.53)
    assert len(closed) == 1
    assert closed[0][1].startswith("TP")
