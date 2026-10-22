"""RT02 Clock shape validation (Proof Matrix B)."""

import pytest
import psycopg2

from rt02_util import begin_save, clock, stage_clock


def _stage_rejects(db, token, value, match):
    with pytest.raises(psycopg2.errors.RaiseException, match=match):
        stage_clock(db, token, value)


def test_rejects_invalid_schema_version(db):
    _published, _staging, token, _expires = begin_save(db)
    _stage_rejects(db, token, clock(schema_version=2), "schema_version")
    _stage_rejects(db, token, {"day": None, "phase": "unknown",
                               "elapsed_campaign_minutes": 0, "long_rests_completed": 0},
                   "schema_version")


def test_rejects_invalid_phase(db):
    _published, _staging, token, _expires = begin_save(db)
    _stage_rejects(db, token, clock(phase="teatime"), "phase")
    _stage_rejects(db, token, {"schema_version": 1, "day": None,
                               "elapsed_campaign_minutes": 0, "long_rests_completed": 0},
                   "phase")
    _stage_rejects(db, token, clock(phase=None), "phase")


def test_rejects_invalid_elapsed_minutes(db):
    _published, _staging, token, _expires = begin_save(db)
    _stage_rejects(db, token, clock(elapsed_campaign_minutes=-1), "elapsed_campaign_minutes")
    _stage_rejects(db, token, clock(elapsed_campaign_minutes=2.5), "elapsed_campaign_minutes")
    _stage_rejects(db, token, clock(elapsed_campaign_minutes="many"), "elapsed_campaign_minutes")


def test_rejects_invalid_long_rest_count(db):
    _published, _staging, token, _expires = begin_save(db)
    _stage_rejects(db, token, clock(long_rests_completed=-1), "long_rests_completed")
    _stage_rejects(db, token, clock(long_rests_completed=1.5), "long_rests_completed")
    _stage_rejects(db, token, clock(long_rests_completed=True), "long_rests_completed")


def test_rejects_invalid_day_but_allows_unknown(db):
    _published, _staging, token, _expires = begin_save(db)
    _stage_rejects(db, token, clock(day=-1), "day")
    _stage_rejects(db, token, clock(day="tomorrow"), "day")
    _stage_rejects(db, token, clock(day=1.5), "day")
    # null day (Unknown) is valid truth, not coerced.
    stage_clock(db, token, clock(day=None, phase="morning"))


def test_rejects_malformed_clock_payload(db):
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="JSON object"):
        stage_clock(db, token, ["not", "an", "object"])
    with pytest.raises(psycopg2.errors.RaiseException, match="JSON object"):
        stage_clock(db, token, "just a string")
    with pytest.raises(psycopg2.errors.RaiseException, match="JSON object"):
        stage_clock(db, token, None)
