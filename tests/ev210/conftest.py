"""Real-PostgreSQL proof harness for the EV2-10 inventory-ownership tests.

The proof chain is the entire forward migration set in `supabase/migrations`,
applied in filename order; EV2-10 is simply the newest link on top of the
RT01/RT02/RT03/RT04/HWB-02 runtime spine. A real server is required — the proof
skips rather than mocking when one is not reachable. No live Supabase is touched.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="the EV2-10 inventory proof runs against a real PostgreSQL server"
)

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _ROOT / "supabase" / "migrations"
_BASELINE_ROLES = _ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"

# Filename order IS migration order for this repository's forward-only chain.
_CHAIN = tuple(sorted(path.name for path in _MIGRATIONS_DIR.glob("*.sql")))


def _target_dsn():
    for variable in ("RHC_EV210_PG_DSN", "RHC_HWB02_PG_DSN", "RHC_RT04_PG_DSN"):
        value = os.environ.get(variable)
        if value:
            return value
    return _FALLBACK_DSN


@pytest.fixture(scope="session")
def _server():
    try:
        connection = psycopg2.connect(_target_dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"the EV2-10 proof needs a real PostgreSQL server: {exc}")
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def db(_server):
    """Install the baseline roles and the full migration chain into a fresh schema."""
    with _server.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES.read_text(encoding="utf-8"))
        cursor.execute("drop schema if exists public cascade;")
        cursor.execute("create schema public;")
        cursor.execute("grant usage on schema public to anon, authenticated, service_role;")
        for name in _CHAIN:
            cursor.execute((_MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    return _server
