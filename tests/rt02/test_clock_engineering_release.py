"""RT02 engineering-release compatibility (Proof Matrix I)."""

import pytest
import psycopg2

from rt02_util import (
    ENGINEERING_TARGET,
    begin_save,
    break_glass,
    clock,
    establish_clock,
    pending,
    publish,
    scalar,
    stage,
    stage_clock,
)


def begin_engineering(db, target=ENGINEERING_TARGET):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_engineering_release(%s, 30)", (target,))
        return cur.fetchone()


def test_engineering_release_clones_clock_and_day(db):
    establish_clock(db, clock(day=4, phase="evening", elapsed_campaign_minutes=100))
    current = begin_engineering(db)

    assert current[2] == 4  # published_day preserved
    assert scalar(
        db,
        "select value from public.campaign_state_generations "
        "where generation = 2 and key = 'campaign_clock'",
    ) == clock(day=4, phase="evening", elapsed_campaign_minutes=100)


def test_engineering_release_forbids_clock_staging(db):
    establish_clock(db, clock(day=4, phase="evening", elapsed_campaign_minutes=100))
    token = begin_engineering(db)[4]

    with pytest.raises(psycopg2.errors.RaiseException, match="forbids campaign state mutation"):
        stage_clock(db, token, clock(day=5, phase="dawn", elapsed_campaign_minutes=100))
    with pytest.raises(psycopg2.errors.RaiseException, match="forbids campaign state mutation"):
        stage(db, token, "campaign_clock", clock(day=5, phase="dawn"))


def test_engineering_release_publish_preserves_clock_and_day(db):
    establish_clock(db, clock(day=4, phase="evening", elapsed_campaign_minutes=100))
    token = begin_engineering(db)[4]
    publish(db, token)

    candidate = pending(db)
    assert candidate["published_day"] == 4
    assert candidate["state"]["campaign_clock"]["day"] == 4
    assert candidate["state"]["campaign_clock"]["phase"] == "evening"
    assert candidate["engineering_git_ref"] == ENGINEERING_TARGET


def test_engineering_release_publish_rejects_break_glass_clock_change(db):
    establish_clock(db, clock(day=4, phase="evening", elapsed_campaign_minutes=100))
    token = begin_engineering(db)[4]
    break_glass(
        db,
        "update public.campaign_state_generations "
        "set value = %s::jsonb where generation = 2 and key = 'campaign_clock'",
        ('{"schema_version":1,"day":5,"phase":"dawn",'
         '"elapsed_campaign_minutes":100,"long_rests_completed":0}',),
    )

    with pytest.raises(psycopg2.errors.RaiseException, match="may not change"):
        publish(db, token)
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1
    assert scalar(db, "select published_day from public.campaign_runtime") == 4
