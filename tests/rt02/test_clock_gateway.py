"""RT02 gateway / authorization safety (Proof Matrix E)."""

import pytest
import psycopg2

from rt02_util import begin_save, break_glass, clock, delete_staged, stage, stage_clock


def test_clock_staging_requires_active_matching_save(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
        stage_clock(db, "no-such-token", clock(day=1))


def test_clock_staging_fails_closed_on_expired_lock(db):
    _published, _staging, token, _expires = begin_save(db)
    break_glass(
        db,
        "update public.campaign_runtime "
        "set lock_expires_at = now() - interval '1 minute' where id = 1",
    )
    with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
        stage_clock(db, token, clock(day=1))


def test_generic_stage_cannot_bypass_clock_validation(db):
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="stage_campaign_clock"):
        stage(db, token, "campaign_clock", {"day": -1, "phase": "bogus"})


def test_generic_delete_cannot_remove_engine_owned_clock(db):
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        delete_staged(db, token, "campaign_clock")


def test_service_role_cannot_insert_clock_directly(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "insert into public.campaign_state_generations "
                    "(generation, key, value) values (1, 'campaign_clock', '{}'::jsonb)"
                )
        finally:
            cur.execute("reset role")


def test_raw_owner_dml_remains_guarded(db):
    with db.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="save gateway"):
            cur.execute(
                "insert into public.campaign_state_generations "
                "(generation, key, value) values (1, 'campaign_clock', '{}'::jsonb)"
            )
