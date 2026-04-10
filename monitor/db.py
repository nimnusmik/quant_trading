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
