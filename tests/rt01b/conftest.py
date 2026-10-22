"""Real-PostgreSQL proof harness for the RT01-B Save Gateway + Mutation Boundary.

These tests require a real, disposable PostgreSQL instance (Supabase's Postgres
major line). They connect via ``RHC_RT01B_PG_DSN`` (falling back to the shared
RT01-A DSN, then a local default) and are SKIPPED — never silently downgraded to
SQLite, string inspection, or mocked transaction behavior — when no real Postgres
is reachable. The gateway's guarantees (advisory locking, row locks, SECURITY
DEFINER guard triggers, exactly-once generation advance under concurrency) only
exist in a real transactional engine.

Phase isolation: this harness pins the migration set through the RT01-B boundary
explicitly rather than globbing ``supabase/migrations``. Globbing would sweep in
future RT01-C/D migrations and contaminate the RT01-B phase proof.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 is required for the RT01-B real-Postgres proof"
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
# The Supabase baseline roles (anon/authenticated/service_role) are shared proof
# scaffolding owned by the RT01-A harness; reuse it rather than forking a copy.
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"

DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"

# Migrations through the RT01-B boundary, in apply order. RT01-C/D are NOT here.
RT01B_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
)


def _dsn():
    return (
        os.environ.get("RHC_RT01B_PG_DSN")
        or os.environ.get("RHC_RT01A_PG_DSN")
        or DEFAULT_DSN
    )


def _connect():
    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    return conn


def _migration_files():
    files = [MIGRATIONS / name for name in RT01B_MIGRATIONS]
    missing = [str(p) for p in files if not p.is_file()]
    assert not missing, f"missing RT01-B migration(s): {missing}"
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
            "RT01-B proof needs real PostgreSQL; none reachable at "
            f"{_dsn()!r} ({exc.__class__.__name__}). "
            "Start one (e.g. `docker run -e POSTGRES_PASSWORD=rhc -e POSTGRES_DB=rhc "
            "-p 55432:5432 postgres:15`) or set RHC_RT01B_PG_DSN."
        )
    yield conn
    conn.close()


def _reset_and_migrate(cur):
    # Supabase baseline roles are cluster-level and persist across resets.
    _apply_sql(cur, BASELINE_ROLES_SQL)
    cur.execute("drop schema if exists public cascade;")
    cur.execute("create schema public;")
    cur.execute("grant usage on schema public to anon, authenticated, service_role;")
    for path in _migration_files():
        _apply_sql(cur, path)


@pytest.fixture()
def db(pg_connection):
    """A freshly-migrated schema (RT01-A floor + RT01-B gateway) for each test."""
    with pg_connection.cursor() as cur:
        _reset_and_migrate(cur)
    return pg_connection


@pytest.fixture()
def new_connection(db):
    """Factory for additional real connections to the SAME migrated database.

    Concurrency proof needs genuinely separate sessions (separate advisory-lock
    holders and transactions). Connections are tracked and closed at teardown.
    ``autocommit`` defaults to True; pass ``autocommit=False`` for tests that must
    hold a transaction (and its locks) open across a race.
    """
    conns = []

    def _make(autocommit=True):
        conn = psycopg2.connect(_dsn())
        conn.autocommit = autocommit
        conns.append(conn)
        return conn

    yield _make

    for conn in conns:
        try:
            conn.close()
        except Exception:  # pragma: no cover - best-effort teardown
            pass
