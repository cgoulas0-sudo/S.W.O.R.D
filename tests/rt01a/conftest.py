"""Real-PostgreSQL proof harness for the RT01-A published-runtime floor.

These tests require a real, disposable PostgreSQL instance (Supabase's Postgres
major line). They connect via ``RHC_RT01A_PG_DSN`` and are SKIPPED — never
silently downgraded to SQLite or string inspection — when no real Postgres is
reachable.

DSN resolution:
  * ``RHC_RT01A_PG_DSN`` if set, else
  * a local default of ``postgresql://postgres:rhc@localhost:55432/rhc``
    (the disposable ``postgres:15`` container used for local proof).
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 is required for the RT01-A real-Postgres proof"
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = Path(__file__).resolve().parent / "supabase_baseline_roles.sql"

DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"


def _dsn():
    return os.environ.get("RHC_RT01A_PG_DSN", DEFAULT_DSN)


def _connect():
    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    return conn


# RT01-A pins its own migration set explicitly rather than globbing
# supabase/migrations. Globbing would sweep in future RT01-B/C/D migrations and
# apply them inside the RT01-A phase proof, which could break RT01-A assertions
# even when RT01-A itself is correct. The proof must prove RT01-A and stop at
# the RT01-A boundary; later approved gates own their own proofs.
RT01A_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
)


def _migration_files():
    files = [MIGRATIONS / name for name in RT01A_MIGRATIONS]
    missing = [str(p) for p in files if not p.is_file()]
    assert not missing, f"missing RT01-A migration(s): {missing}"
    return files


def _apply_sql(cur, path: Path):
    cur.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pg_connection():
    """One superuser connection to the proof database, or SKIP if unreachable."""
    try:
        conn = _connect()
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(
            "RT01-A proof needs real PostgreSQL; none reachable at "
            f"{_dsn()!r} ({exc.__class__.__name__}). "
            "Start one (e.g. `docker run -e POSTGRES_PASSWORD=rhc -e POSTGRES_DB=rhc "
            "-p 55432:5432 postgres:15`) or set RHC_RT01A_PG_DSN."
        )
    yield conn
    conn.close()


@pytest.fixture()
def db(pg_connection):
    """A freshly-migrated schema for each test.

    Resets ``public``, provisions the Supabase baseline roles, grants baseline
    schema usage, then applies the RT01-A migrations in filename order.
    """
    with pg_connection.cursor() as cur:
        # Supabase baseline roles are cluster-level and persist across resets.
        _apply_sql(cur, BASELINE_ROLES_SQL)
        # Fresh schema every test for deterministic proof.
        cur.execute("drop schema if exists public cascade;")
        cur.execute("create schema public;")
        cur.execute(
            "grant usage on schema public to anon, authenticated, service_role;"
        )
        for path in _migration_files():
            _apply_sql(cur, path)
    return pg_connection
