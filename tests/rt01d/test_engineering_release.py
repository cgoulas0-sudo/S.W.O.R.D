from pathlib import Path

import psycopg2
import pytest

from rt01d_util import (
    ENGINEERING_TARGET,
    begin_save,
    bind_base,
    break_glass,
    confirm,
    establish_confirmed_runtime,
    pending,
    publish,
    scalar,
    stage,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"


def begin_engineering(db, target=ENGINEERING_TARGET):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_engineering_release(%s, 30)", (target,))
        return cur.fetchone()


def test_engineering_release_requires_confirmed_runtime_and_exact_target(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="fully confirmed"):
        begin_engineering(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="exact full commit SHA"):
        begin_engineering(db, "main")


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_engineering_release_denies_client_roles(db, role):
    establish_confirmed_runtime(db)
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "select public.begin_engineering_release(%s, 30)",
                    (ENGINEERING_TARGET,),
                )
        finally:
            cur.execute("reset role")


def test_engineering_release_allows_service_role(db):
    establish_confirmed_runtime(db)
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select lock_token from public.begin_engineering_release(%s, 30)",
                (ENGINEERING_TARGET,),
            )
            assert cur.fetchone()[0]
        finally:
            cur.execute("reset role")


def test_begin_clones_exact_next_generation_and_binds_target(db):
    establish_confirmed_runtime(db, {"world": {"status": "unchanged"}})
    current = begin_engineering(db)

    assert current[:4] == (1, "b" * 40, None, 2)
    assert current[5] == ENGINEERING_TARGET
    assert scalar(
        db,
        "select value from public.campaign_state_generations where generation=2 and key='world'",
    ) == {"status": "unchanged"}
    assert scalar(db, "select staging_save_kind from public.campaign_runtime") == "engineering_release"


def test_engineering_release_rejects_stage_and_delete(db):
    establish_confirmed_runtime(db)
    current = begin_engineering(db)
    token = current[4]

    with pytest.raises(psycopg2.errors.RaiseException, match="forbids campaign state mutation"):
        stage(db, token, "baseline", {"status": "changed"})
    with pytest.raises(psycopg2.errors.RaiseException, match="forbids campaign state mutation"):
        scalar(db, "select public.delete_staged_campaign_state(%s, 'baseline')", (token,))


def test_publish_rejects_break_glass_campaign_state_change(db):
    establish_confirmed_runtime(db)
    token = begin_engineering(db)[4]
    break_glass(
        db,
        "update public.campaign_state_generations set value='{}'::jsonb where generation=2 and key='baseline'",
    )

    with pytest.raises(psycopg2.errors.RaiseException, match="may not change campaign state"):
        publish(db, token)
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1


def test_publish_rejects_break_glass_day_change(db):
    establish_confirmed_runtime(db)
    token = begin_engineering(db)[4]
    break_glass(db, "update public.campaign_runtime set published_day=9 where id=1")

    with pytest.raises(psycopg2.errors.RaiseException, match="may not change published day"):
        publish(db, token)
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1


def test_publish_keeps_state_day_and_target_and_retries_same_generation(db):
    establish_confirmed_runtime(db, {"world": {"status": "unchanged"}})
    token = begin_engineering(db)[4]
    publish(db, token)
    candidate = pending(db)

    assert candidate["generation"] == 2
    assert candidate["published_day"] is None
    assert candidate["engineering_git_ref"] == ENGINEERING_TARGET
    assert candidate["state"] == {"world": {"status": "unchanged"}}
    with pytest.raises(psycopg2.errors.RaiseException, match="pending runtime-published mirror"):
        begin_save(db)
    assert scalar(db, "select published_generation from public.campaign_runtime") == 2
    assert pending(db)["engineering_git_ref"] == ENGINEERING_TARGET


def test_ordinary_campaign_save_retains_rt01c_shape(db):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "ordinary", {"status": "saved"})
    publish(db, token)
    candidate = pending(db)

    assert candidate["generation"] == 1
    assert candidate["engineering_git_ref"] is None
    assert candidate["state"] == {"ordinary": {"status": "saved"}}


def test_post_d_ordinary_gateway_abort_publish_and_confirmation_lifecycle(db):
    _published, staging, token, _expires = begin_save(db)
    stage(db, token, "temporary", {"status": "discarded"})
    assert scalar(
        db, "select public.delete_staged_campaign_state(%s, 'temporary')", (token,)
    ) is True
    stage(db, token, "temporary", {"status": "discarded"})
    scalar(db, "select public.abort_campaign_save(%s)", (token,))
    assert scalar(
        db,
        "select count(*) from public.campaign_state_generations where generation=%s",
        (staging,),
    ) == 0

    _published, _staging, next_token, _expires = begin_save(db)
    stage(db, next_token, "ordinary", {"status": "published"})
    publish(db, next_token)
    candidate = pending(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="pending runtime-published mirror"):
        begin_save(db)

    bind_base(db, candidate)
    candidate = pending(db)
    confirm(db, candidate)
    published, next_generation, _token, _expires = begin_save(db)
    assert (published, next_generation) == (1, 2)


def test_post_d_ordinary_expired_save_recovers_same_candidate_generation(db):
    _published, staging, token, _expires = begin_save(db)
    stage(db, token, "stale", {"value": 1})
    break_glass(
        db,
        "update public.campaign_runtime set lock_expires_at=clock_timestamp()-interval '1 second' where id=1",
    )

    _published, recovered, replacement_token, _expires = begin_save(db)
    assert recovered == staging == 1
    assert replacement_token != token
    assert scalar(
        db,
        "select count(*) from public.campaign_state_generations where generation=1 and key='stale'",
    ) == 0


def test_post_d_runtime_owned_tables_remain_direct_dml_guarded(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "insert into public.campaign_state_generations(generation,key,value) values (1,'raw','1')"
                )
        finally:
            cur.execute("reset role")

    with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="guarded RHC save gateway"):
        with db.cursor() as cur:
            cur.execute(
                "insert into public.campaign_state_generations(generation,key,value) values (1,'raw','1')"
            )


def test_rt01d_upgrade_refuses_unclassified_active_save(pg_connection):
    earlier = (
        "20260908000001_rt01a_published_runtime_floor.sql",
        "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
        "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
        "20260908000004_rt01c_runtime_published_git_handshake.sql",
        "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    )
    with pg_connection.cursor() as cur:
        cur.execute(Path(BASELINE_ROLES_SQL).read_text(encoding="utf-8"))
        cur.execute("drop schema if exists public cascade;")
        cur.execute("create schema public;")
        cur.execute("grant usage on schema public to anon, authenticated, service_role;")
        for name in earlier:
            cur.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
        cur.execute("select public.begin_campaign_save(30)")

    migration = MIGRATIONS / "20260908000006_rt01d_dm_read_engineering_release.sql"
    with pytest.raises(psycopg2.errors.RaiseException, match="RT01-D migration refused"):
        with pg_connection.cursor() as cur:
            cur.execute(migration.read_text(encoding="utf-8"))
    assert scalar(pg_connection, "select save_in_progress from public.campaign_runtime") is True
