"""EV2-12.1 generalized item identity admission — real-PostgreSQL test harness.

Skip-not-mock: the runtime tests run only against a live PostgreSQL server, and a
fresh schema is rebuilt from the complete forward migration chain for every test.
No live Supabase project is ever contacted.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2", reason="EV2-12.1 needs real PostgreSQL")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = ROOT / "supabase" / "migrations"
BASELINE = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DSN_ENV_ORDER = (
    "RHC_EV2121_PG_DSN",
    "RHC_EV212_PG_DSN",
    "RHC_EV211_PG_DSN",
    "RHC_EV210_PG_DSN",
    "RHC_RT04_PG_DSN",
)
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"


def connection_string():
    for variable in DSN_ENV_ORDER:
        value = os.environ.get(variable)
        if value:
            return value
    return DEFAULT_DSN


def migration_bodies():
    ordered = sorted(MIGRATION_DIR.glob("*.sql"))
    return [path.read_text(encoding="utf-8") for path in ordered]


@pytest.fixture(scope="session")
def pg():
    try:
        connection = psycopg2.connect(connection_string())
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"EV2-12.1 admission proof skipped (no server): {exc}")
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def db(pg):
    reset_statements = (
        BASELINE.read_text(encoding="utf-8"),
        "drop schema if exists public cascade;",
        "create schema public;",
        "grant usage on schema public to anon, authenticated, service_role;",
    )
    with pg.cursor() as cursor:
        for statement in reset_statements:
            cursor.execute(statement)
        for body in migration_bodies():
            cursor.execute(body)
    return pg
