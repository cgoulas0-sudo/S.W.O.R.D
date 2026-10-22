"""EV2-13 mutable entity state — real-PostgreSQL proof harness.

The runtime proof only runs against a live PostgreSQL server; when none is
reachable the whole module set is skipped rather than mocked. A disposable
schema is rebuilt from the complete forward migration chain before every test.
No Supabase project or live database is ever contacted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="EV2-13 mutable entity state needs a real PostgreSQL server"
)

_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_ROLES = (
    _ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
).read_text(encoding="utf-8")
_FORWARD_MIGRATIONS = tuple(
    sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
)
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)
_DSN_PRECEDENCE = (
    "RHC_EV213_PG_DSN",
    "RHC_EV2121_PG_DSN",
    "RHC_EV212_PG_DSN",
    "RHC_EV211_PG_DSN",
    "RHC_EV210_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"


def _target_dsn() -> str:
    for variable in _DSN_PRECEDENCE:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return _FALLBACK_DSN


def _install_forward_chain(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES)
        for statement in _SCHEMA_RESET:
            cursor.execute(statement)
        for migration in _FORWARD_MIGRATIONS:
            cursor.execute(migration.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def database_server():
    try:
        connection = psycopg2.connect(_target_dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(
            f"EV2-13 mutable entity state proof skipped (no server): {exc}"
        )
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    _install_forward_chain(database_server)
    return database_server
