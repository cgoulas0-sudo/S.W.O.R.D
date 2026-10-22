"""Real-PostgreSQL proof harness for RT01-C runtime-published Git handshake."""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 is required for the RT01-C real-Postgres proof"
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
RT01C_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
    "20260908000004_rt01c_runtime_published_git_handshake.sql",
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
)


def _dsn():
    return (
        os.environ.get("RHC_RT01C_PG_DSN")
        or os.environ.get("RHC_RT01B_PG_DSN")
        or os.environ.get("RHC_RT01A_PG_DSN")
        or DEFAULT_DSN
    )


def _connect():
    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    return conn


def _apply_sql(cur, path: Path):
    cur.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pg_connection():
    try:
        conn = _connect()
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"RT01-C proof needs real PostgreSQL at {_dsn()!r}: {exc}")
    yield conn
    conn.close()


@pytest.fixture()
def db(pg_connection):
    with pg_connection.cursor() as cur:
        _apply_sql(cur, BASELINE_ROLES_SQL)
        cur.execute("drop schema if exists public cascade;")
        cur.execute("create schema public;")
        cur.execute("grant usage on schema public to anon, authenticated, service_role;")
        for name in RT01C_MIGRATIONS:
            _apply_sql(cur, MIGRATIONS / name)
    return pg_connection
