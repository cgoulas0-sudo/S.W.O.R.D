"""RT02 migration / bootstrap safety (Proof Matrix A)."""

from pathlib import Path

import psycopg2
import pytest

from rt02_util import UNKNOWN_CLOCK

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
RT01_MIGRATIONS = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
    "20260908000004_rt01c_runtime_published_git_handshake.sql",
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    "20260908000006_rt01d_dm_read_engineering_release.sql",
)
RT02_MIGRATION = "20260911000001_rt02_campaign_clock.sql"


def _apply(cur, name):
    cur.execute((MIGRATIONS / name).read_text(encoding="utf-8"))


def _fresh_schema(cur):
    cur.execute(BASELINE_ROLES_SQL.read_text(encoding="utf-8"))
    cur.execute("drop schema if exists public cascade")
    cur.execute("create schema public")
    cur.execute("grant usage on schema public to anon, authenticated, service_role")


def test_full_chain_applies_and_unknown_is_not_invented(db):
    with db.cursor() as cur:
        cur.execute("select published_generation, published_day from public.campaign_runtime where id = 1")
        assert cur.fetchone() == (0, None)
        cur.execute(
            "select count(*) from public.campaign_state_generations where key = 'campaign_clock'"
        )
        assert cur.fetchone()[0] == 0


def test_rt02_upgrade_preserves_existing_unknown_published_truth(pg_connection):
    conn = pg_connection
    with conn.cursor() as cur:
        _fresh_schema(cur)
        for name in RT01_MIGRATIONS:
            _apply(cur, name)

        cur.execute("select published_generation, published_day from public.campaign_runtime where id = 1")
        assert cur.fetchone() == (0, None)

        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
        cur.execute("select public.stage_campaign_state(%s, 'x', '1'::jsonb)", (token,))
        cur.execute("select public.publish_campaign_save(%s)", (token,))

        cur.execute("select published_generation, published_day from public.campaign_runtime where id = 1")
        assert cur.fetchone() == (1, None)

        _apply(cur, RT02_MIGRATION)

        cur.execute("select published_generation, published_day from public.campaign_runtime where id = 1")
        assert cur.fetchone() == (1, None)
        cur.execute(
            "select count(*) from public.campaign_state_generations where key = 'campaign_clock'"
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "select count(*) from public.campaign_state_generations where generation = 1"
        )
        assert cur.fetchone()[0] == 1


def test_rt02_upgrade_refuses_in_flight_save(pg_connection):
    conn = pg_connection
    with conn.cursor() as cur:
        _fresh_schema(cur)
        for name in RT01_MIGRATIONS:
            _apply(cur, name)
        cur.execute("select public.begin_campaign_save(30)")

    with pytest.raises(psycopg2.errors.RaiseException, match="RT02 migration refused"):
        with conn.cursor() as cur:
            _apply(cur, RT02_MIGRATION)

    with conn.cursor() as cur:
        cur.execute("select save_in_progress from public.campaign_runtime where id = 1")
        assert cur.fetchone()[0] is True
        cur.execute(
            "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and proname = 'stage_campaign_clock'"
        )
        assert cur.fetchone()[0] == 0


def test_rt02_migration_is_forward_only_functional(db):
    with db.cursor() as cur:
        cur.execute(
            "select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and proname in "
            "('stage_campaign_clock','_rhc_normalize_campaign_clock','_rhc_phase_order') "
            "order by proname"
        )
        assert [row[0] for row in cur.fetchall()] == [
            "_rhc_normalize_campaign_clock",
            "_rhc_phase_order",
            "stage_campaign_clock",
        ]
