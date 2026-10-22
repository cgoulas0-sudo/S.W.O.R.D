"""Real-PostgreSQL proof harness for RT04 Safe Run Reconciliation."""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 is required for the RT04 real-Postgres proof"
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
RT04_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
    "20260908000004_rt01c_runtime_published_git_handshake.sql",
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    "20260908000006_rt01d_dm_read_engineering_release.sql",
    "20260911000001_rt02_campaign_clock.sql",
    "20260911000002_rt03_canonical_run_runtime_read.sql",
    "20260912000001_rt04_safe_run_reconciliation.sql",
)


def _dsn():
    return (
        os.environ.get("RHC_RT04_PG_DSN")
        or os.environ.get("RHC_RT03_PG_DSN")
        or os.environ.get("RHC_RT02_PG_DSN")
        or os.environ.get("RHC_RT01D_PG_DSN")
        or os.environ.get("RHC_RT01C_PG_DSN")
        or os.environ.get("RHC_RT01B_PG_DSN")
        or os.environ.get("RHC_RT01A_PG_DSN")
        or DEFAULT_DSN
    )


def _apply_sql(cur, path: Path):
    cur.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pg_dsn():
    return _dsn()


@pytest.fixture(scope="session")
def pg_connection(pg_dsn):
    try:
        conn = psycopg2.connect(pg_dsn)
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"RT04 proof needs real PostgreSQL at {pg_dsn!r}: {exc}")
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture()
def db(pg_connection):
    with pg_connection.cursor() as cur:
        _apply_sql(cur, BASELINE_ROLES_SQL)
        cur.execute("drop schema if exists public cascade;")
        cur.execute("create schema public;")
        cur.execute("grant usage on schema public to anon, authenticated, service_role;")
        for name in RT04_MIGRATIONS:
            _apply_sql(cur, MIGRATIONS / name)
    return pg_connection


@pytest.fixture()
def txn(db):
    """A fresh non-autocommit connection for all-or-nothing proofs.

    Depends on `db` so the RT04 migration chain is already installed on the
    shared server before the transaction-scoped connection is opened.
    """
    conn = psycopg2.connect(_dsn())
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()