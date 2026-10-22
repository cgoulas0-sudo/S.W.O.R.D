"""Real-PostgreSQL harness for the EV2-12 first-real-item canary admission proof.

Every runtime test in this directory is graded against a freshly rebuilt schema
that carries the whole forward migration chain (RT01-A/B/C/D, RT02, RT03, RT04,
HWB-02, EV2-10, EV2-11). The harness is skip-not-mock: if the target server
cannot be reached the runtime tests are skipped, and no live Supabase project is
ever contacted.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="EV2-12 runtime proof needs a real PostgreSQL server"
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHAIN = [
    migration
    for migration in sorted((_REPO_ROOT / "supabase" / "migrations").glob("*.sql"))
]
_BASELINE = (_REPO_ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql").read_text(
    encoding="utf-8"
)
_DSN_ENV = (
    "RHC_EV212_PG_DSN",
    "RHC_EV211_PG_DSN",
    "RHC_EV210_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"


def dsn():
    return next((os.environ[key] for key in _DSN_ENV if os.environ.get(key)), _FALLBACK_DSN)


@pytest.fixture(scope="session")
def server():
    connection = None
    try:
        connection = psycopg2.connect(dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"EV2-12 admission runtime proof skipped (no server): {exc}")
    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def db(server):
    statements = (
        _BASELINE,
        "drop schema if exists public cascade;",
        "create schema public;",
        "grant usage on schema public to anon, authenticated, service_role;",
    )
    with server.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        for migration in _CHAIN:
            cursor.execute(migration.read_text(encoding="utf-8"))
    return server
