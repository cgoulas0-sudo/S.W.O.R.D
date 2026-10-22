"""RT02 publication coherence (Proof Matrix F)."""

import pytest
import psycopg2

from rt02_util import (
    abort_save,
    begin_save,
    clock,
    establish_clock,
    published_clock,
    published_day,
    publish,
    scalar,
    stage,
    stage_clock,
)


def test_abort_after_staged_clock_leaves_published_truth_unchanged(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="dawn", elapsed_campaign_minutes=0))
    abort_save(db, token)

    assert published_day(db) == 1
    assert published_clock(db)["day"] == 1
    assert published_clock(db)["phase"] == "morning"


def test_publish_derives_published_day_from_clock_in_same_generation(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="afternoon", elapsed_campaign_minutes=120))
    publish(db, token)

    assert published_day(db) == 2
    assert published_clock(db)["day"] == 2
    assert published_clock(db)["phase"] == "afternoon"


def test_incoherent_backwards_candidate_fails_before_publication(db):
    establish_clock(db, clock(day=5, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot move backwards"):
        stage_clock(db, token, clock(day=3, phase="dawn", elapsed_campaign_minutes=0))
    # publication never happened; published truth intact
    assert published_day(db) == 5


def test_unknown_clock_day_keeps_published_day_null(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=None, phase="unknown", elapsed_campaign_minutes=30))
    publish(db, token)

    assert published_day(db) is None
    assert published_clock(db)["day"] is None
    assert published_clock(db)["elapsed_campaign_minutes"] == 30


def test_unrelated_save_copy_forward_preserves_clock_and_day(db):
    establish_clock(db, clock(day=2, phase="evening", elapsed_campaign_minutes=90))
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "daily_recap", {"status": "active"})
    publish(db, token)

    assert published_day(db) == 2
    assert published_clock(db)["day"] == 2
    assert published_clock(db)["phase"] == "evening"
    assert published_clock(db)["elapsed_campaign_minutes"] == 90


def test_publication_does_not_rewrite_earlier_generation(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="morning", elapsed_campaign_minutes=0))
    publish(db, token)

    gen1 = scalar(
        db,
        "select value from public.campaign_state_generations "
        "where generation = 1 and key = 'campaign_clock'",
    )
    gen2 = scalar(
        db,
        "select value from public.campaign_state_generations "
        "where generation = 2 and key = 'campaign_clock'",
    )
    assert gen1["day"] == 1
    assert gen2["day"] == 2
    assert published_day(db) == 2
