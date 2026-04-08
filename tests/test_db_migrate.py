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
