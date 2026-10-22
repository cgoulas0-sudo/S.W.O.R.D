"""EV2-11 item-custody runtime proof harness.

A real PostgreSQL server is required; the proof skips (never mocks) when none is
reachable. Before each test the complete forward migration chain in
`supabase/migrations` is applied in filename order into a freshly reset schema,
so EV2-11 is always graded on top of the whole RT01/RT02/RT03/RT04/HWB-02/EV2-10
spine. No live Supabase project is touched.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2", reason="EV2-11 requires a live PostgreSQL server")

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_MIGRATIONS = sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
_ROLES_SQL = (_ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql").read_text(
    encoding="utf-8"
)
_DSN_VARS = ("RHC_EV211_PG_DSN", "RHC_EV210_PG_DSN", "RHC_HWB02_PG_DSN", "RHC_RT04_PG_DSN")
_DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"


def _dsn():
    return next((os.environ[name] for name in _DSN_VARS if os.environ.get(name)), _DEFAULT_DSN)


@pytest.fixture(scope="session")
def pg_server():
    try:
        server = psycopg2.connect(_dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"EV2-11 proof needs a real PostgreSQL server: {exc}")
    server.autocommit = True
    yield server
    server.close()


@pytest.fixture()
def db(pg_server):
    reset = (
        _ROLES_SQL,
        "drop schema if exists public cascade;",
        "create schema public;",
        "grant usage on schema public to anon, authenticated, service_role;",
    )
    with pg_server.cursor() as cursor:
        for statement in reset:
            cursor.execute(statement)
        for migration in _MIGRATIONS:
            cursor.execute(migration.read_text(encoding="utf-8"))
    return pg_server
