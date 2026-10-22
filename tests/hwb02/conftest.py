"""Real-PostgreSQL proof harness for HWB-02 SAVE runtime authority.

Chain: the full RT01-A/B/C/D + RT02 + RT03 + RT04 spine, then the forward-only
HWB-02 `20260914000001_hwb02_save_runtime_authority.sql` migration. Proved on
real PostgreSQL 15 and 17 (skipped, never downgraded to mocks, when a real
server is not reachable). No live Supabase is touched.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 is required for the HWB-02 real-Postgres proof"
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
DEFAULT_DSN17 = "postgresql://postgres:rhc@localhost:55433/rhc"

RT_SPINE = (
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
HWB02 = "20260914000001_hwb02_save_runtime_authority.sql"

# The exact server-owned ordinary `campaign_save` allowlist (Architecture Pin 2).
CAMPAIGN_SAVE_ALLOWED_KEYS = (
    "daily_recap",
    "day_resolution",
    "live_status",
    "dm_meta",
    "narrative_hooks",
    "runs",
)


def _apply_sql(cur, path: Path):
    cur.execute(path.read_text(encoding="utf-8"))


def _apply_chain(cur, include_hwb02: bool = True):
    _apply_sql(cur, BASELINE_ROLES_SQL)
    cur.execute("drop schema if exists public cascade;")
    cur.execute("create schema public;")
    cur.execute("grant usage on schema public to anon, authenticated, service_role;")
    chain = RT_SPINE + ((HWB02,) if include_hwb02 else ())
    for name in chain:
        _apply_sql(cur, MIGRATIONS / name)


def _pg15_dsn():
    return (
        os.environ.get("RHC_HWB02_PG_DSN")
        or os.environ.get("RHC_RT04_PG_DSN")
        or DEFAULT_DSN
    )


def _pg17_dsn():
    return os.environ.get("RHC_HWB02_PG17_DSN") or DEFAULT_DSN17


@pytest.fixture(scope="session")
def pg15_dsn():
    return _pg15_dsn()


@pytest.fixture(scope="session")
def pg17_dsn():
    return _pg17_dsn()


@pytest.fixture(scope="session")
def pg15_connection(pg15_dsn):
    try:
        conn = psycopg2.connect(pg15_dsn)
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"HWB-02 proof needs real PostgreSQL at {pg15_dsn!r}: {exc}")
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg17_connection(pg17_dsn):
    try:
        conn = psycopg2.connect(pg17_dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("show server_version_num")
            version = int(cur.fetchone()[0])
        if version < 170000:
            conn.close()
            pytest.skip(f"PG17 proof target at {pg17_dsn!r} is not PostgreSQL 17+")
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PG17 proof skipped: no PostgreSQL 17 reachable at {pg17_dsn!r}: {exc}")
    yield conn
    conn.close()


@pytest.fixture()
def db(pg15_connection):
    with pg15_connection.cursor() as cur:
        _apply_chain(cur)
    return pg15_connection


@pytest.fixture()
def db_pre_hwb02(pg15_connection):
    """PG15 with the RT spine installed but NOT the HWB-02 migration.

    Used to prove the forward-only install check: refusal while a save is active,
    and that the install takes the authoritative singleton lock so a concurrent
    `begin_campaign_save` cannot race the check.
    """
    with pg15_connection.cursor() as cur:
        _apply_chain(cur, include_hwb02=False)
    return pg15_connection


@pytest.fixture()
def db17(pg17_connection):
    with pg17_connection.cursor() as cur:
        _apply_chain(cur)
    return pg17_connection


@pytest.fixture()
def db17_pre_hwb02(pg17_connection):
    with pg17_connection.cursor() as cur:
        _apply_chain(cur, include_hwb02=False)
    return pg17_connection


@pytest.fixture()
def both_dbs(db, db17):
    """Parametrize a policy proof over real PostgreSQL 15 and 17."""
    return [db, db17]


@pytest.fixture()
def both_dbs_pre_hwb02(db_pre_hwb02, db17_pre_hwb02):
    """Parametrize an install-check proof over PG15 and PG17 (pre-HWB-02 chain)."""
    return [db_pre_hwb02, db17_pre_hwb02]
