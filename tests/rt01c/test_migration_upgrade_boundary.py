"""RT01-C upgrade-boundary proof (Codex P1 #1).

These tests reproduce the RT01-B -> RT01-C *upgrade boundary*, not the
already-migrated schema. The danger is a live RT01-B save that is already active
over an already-published generation N at the instant RT01-C is applied: that
save's lock token predates the migration and would still satisfy the replacement
publish_campaign_save(). If RT01-C minted N's mirror token and let that in-flight
save publish N+1, generation N would advance to N+1 without ever being mirrored.

We therefore apply migrations up to RT01-B only, drive real RT01-B lifecycle
state, THEN apply the RT01-C migration file and assert it fails closed.
"""

import os
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"

RT01A_B_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
)
RT01C_MIGRATION = "20260908000004_rt01c_runtime_published_git_handshake.sql"
RT01C_BASE_BINDING_MIGRATION = "20260908000005_rt01c_bind_runtime_mirror_base.sql"


def _dsn():
    return (
        os.environ.get("RHC_RT01C_PG_DSN")
        or os.environ.get("RHC_RT01B_PG_DSN")
        or os.environ.get("RHC_RT01A_PG_DSN")
        or DEFAULT_DSN
    )


def _apply(cur, name: str):
    cur.execute((MIGRATIONS / name).read_text(encoding="utf-8"))


@pytest.fixture()
def rt01b_db():
    """A schema migrated through RT01-B only (RT01-C deliberately NOT applied)."""
    try:
        conn = psycopg2.connect(_dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"RT01-C upgrade-boundary proof needs real PostgreSQL: {exc}")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute((BASELINE_ROLES_SQL).read_text(encoding="utf-8"))
        cur.execute("drop schema if exists public cascade;")
        cur.execute("create schema public;")
        cur.execute(
            "grant usage on schema public to anon, authenticated, service_role;"
        )
        for name in RT01A_B_MIGRATIONS:
            _apply(cur, name)
    yield conn
    conn.close()


def _apply_rt01c(conn):
    with conn.cursor() as cur:
        # The 000004 guard raises on the dangerous upgrade boundary; when it does,
        # the base-binding migration below is never reached, exactly as in prod.
        _apply(cur, RT01C_MIGRATION)
        _apply(cur, RT01C_BASE_BINDING_MIGRATION)


def _scalar(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def _rt01b_publish_generation(conn):
    """Complete one RT01-B save so published_generation advances by 1."""
    with conn.cursor() as cur:
        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
        cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, "k", "1"),
        )
        cur.execute("select public.publish_campaign_save(%s)", (token,))


def _rt01b_begin_only(conn):
    """Open an RT01-B save and leave it ACTIVE (no publish/abort). Return token."""
    with conn.cursor() as cur:
        cur.execute("select lock_token from public.begin_campaign_save(30)")
        return cur.fetchone()[0]


def test_rt01c_refuses_migration_while_active_save_over_published_generation(rt01b_db):
    conn = rt01b_db
    # published generation N = 1
    _rt01b_publish_generation(conn)
    assert _scalar(conn, "select published_generation from public.campaign_runtime") == 1
    # active RT01-B save staging N+1 = 2, with a still-valid lock token
    active_token = _rt01b_begin_only(conn)
    assert active_token
    assert _scalar(conn, "select save_in_progress from public.campaign_runtime") is True
    assert _scalar(conn, "select staging_generation from public.campaign_runtime") == 2

    # RT01-C migration must fail closed rather than mint N's mirror token while an
    # active pre-migration save could still publish N+1 unmirrored.
    with pytest.raises(psycopg2.errors.RaiseException, match="RT01-C migration refused"):
        _apply_rt01c(conn)

    # The whole migration rolled back: RT01-C never added its columns, so no mirror
    # token was minted and the dangerous state was never entered.
    mirror_col_exists = _scalar(
        conn,
        """
        select exists(
          select 1 from information_schema.columns
          where table_schema = 'public'
            and table_name = 'campaign_runtime'
            and column_name = 'runtime_mirror_token'
        )
        """,
    )
    assert mirror_col_exists is False
    # The active save is untouched (never silently discarded).
    assert _scalar(conn, "select save_in_progress from public.campaign_runtime") is True
    assert _scalar(conn, "select published_generation from public.campaign_runtime") == 1


def test_rt01c_migration_succeeds_once_transitional_save_is_resolved(rt01b_db):
    conn = rt01b_db
    _rt01b_publish_generation(conn)
    active_token = _rt01b_begin_only(conn)

    with pytest.raises(psycopg2.errors.RaiseException, match="RT01-C migration refused"):
        _apply_rt01c(conn)

    # Operator resolves the transitional RT01-B save explicitly (abort here).
    with conn.cursor() as cur:
        cur.execute("select public.abort_campaign_save(%s)", (active_token,))
    assert _scalar(conn, "select save_in_progress from public.campaign_runtime") is False

    # Now RT01-C applies cleanly and converts published generation 1 to mirror-pending.
    _apply_rt01c(conn)
    assert (
        _scalar(conn, "select runtime_mirror_token is not null from public.campaign_runtime")
        is True
    )
    assert (
        _scalar(conn, "select runtime_published_confirmed from public.campaign_runtime")
        is False
    )


def test_clean_rt01b_to_rt01c_migration_succeeds(rt01b_db):
    """A normal RT01-B state with no active save migrates cleanly."""
    conn = rt01b_db
    _rt01b_publish_generation(conn)  # published generation 1, no active save
    assert _scalar(conn, "select save_in_progress from public.campaign_runtime") is False

    _apply_rt01c(conn)

    assert _scalar(conn, "select published_generation from public.campaign_runtime") == 1
    assert (
        _scalar(conn, "select runtime_mirror_token is not null from public.campaign_runtime")
        is True
    )
    assert (
        _scalar(conn, "select runtime_published_confirmed from public.campaign_runtime")
        is False
    )
    # The freshly-pending generation blocks a new BEGIN until its mirror is confirmed.
    with pytest.raises(psycopg2.errors.RaiseException, match="pending runtime-published mirror"):
        with conn.cursor() as cur:
            cur.execute("select public.begin_campaign_save(30)")


def test_clean_rt01c_migration_on_empty_runtime_succeeds(rt01b_db):
    """published_generation = 0 (never published) is not a dangerous boundary even
    with an active first save: no already-published generation can be skipped."""
    conn = rt01b_db
    # Open the very first save (staging generation 1) over published generation 0.
    _rt01b_begin_only(conn)
    assert _scalar(conn, "select published_generation from public.campaign_runtime") == 0
    assert _scalar(conn, "select save_in_progress from public.campaign_runtime") is True

    # Migration is allowed: no published generation exists to leave unmirrored.
    _apply_rt01c(conn)
    assert (
        _scalar(conn, "select runtime_mirror_token from public.campaign_runtime")
        is None
    )
