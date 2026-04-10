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

    assert len(fired) > 0

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
