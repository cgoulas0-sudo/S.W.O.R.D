"""EV2-13.420 Temporal Core — real-PostgreSQL proof harness.

The temporal-core contract is pure SQL, so the proof only runs against a live
PostgreSQL server; when none is reachable the module set is skipped rather than
mocked. A disposable schema is rebuilt from the complete forward migration chain
before every test. PG15 and PG17 coverage both use the existing runtime CI
services; no Supabase project or live database is ever contacted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="EV2-13.420 temporal core needs a real PostgreSQL server"
)

_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_ROLES = (
    _ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
).read_text(encoding="utf-8")
FORWARD_MIGRATIONS = tuple(
    sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
)
TEMPORAL_MIGRATION = _ROOT / "supabase" / "migrations" / (
    "20260920000001_ev213420_temporal_core.sql"
)
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)

# PostgreSQL 15 service is the primary proof target (the runtime workflow maps
# both services to localhost:55432 / 55433). PG17 is proven separately.
_DSN_PRECEDENCE = (
    "RHC_EV213420_PG_DSN",
    "RHC_EV213_PG_DSN",
    "RHC_EV2121_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"

_PG17_DSN_PRECEDENCE = (
    "RHC_EV213420_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55433/rhc"


def _first_dsn(variables, fallback: str) -> str:
    for variable in variables:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return fallback


def install_chain(connection, migrations=FORWARD_MIGRATIONS) -> None:
    """Install the baseline roles plus the given forward migration chain."""
    with connection.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES)
        for statement in _SCHEMA_RESET:
            cursor.execute(statement)
        for migration in migrations:
            cursor.execute(migration.read_text(encoding="utf-8"))


def install_forward_chain(connection) -> None:
    install_chain(connection)


@pytest.fixture(scope="session")
def database_server():
    try:
        connection = psycopg2.connect(_first_dsn(_DSN_PRECEDENCE, _FALLBACK_DSN))
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"EV2-13.420 temporal core proof skipped (no server): {exc}")
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    install_forward_chain(database_server)
    return database_server


@pytest.fixture(scope="session")
def database_server_pg17():
    try:
        connection = psycopg2.connect(
            _first_dsn(_PG17_DSN_PRECEDENCE, _PG17_FALLBACK_DSN)
        )
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"EV2-13.420 PostgreSQL 17 proof skipped (no server): {exc}")
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def db_pg17(database_server_pg17):
    install_forward_chain(database_server_pg17)
    return database_server_pg17