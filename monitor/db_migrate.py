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
