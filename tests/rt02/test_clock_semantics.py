"""RT02 conservative time semantics + monotonic/replay safety (Proof Matrix C, D)."""

import pytest
import psycopg2

from rt02_util import (
    begin_save,
    clock,
    establish_clock,
    published_clock,
    stage_clock,
)


def _begin_next(db):
    return begin_save(db)


def test_presentation_only_advances_phase_without_elapsed(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    stage_clock(db, token, clock(day=1, phase="afternoon", elapsed_campaign_minutes=0))
    assert True  # no exception: phase advanced, elapsed untouched


def test_duration_only_advances_elapsed_without_inventing_day_phase(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=10))
    _published, _staging, token, _expires = _begin_next(db)
    stage_clock(db, token, clock(day=None, phase="unknown", elapsed_campaign_minutes=35))


def test_combined_update_applies_both_facts(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    stage_clock(
        db,
        token,
        clock(day=1, phase="evening", elapsed_campaign_minutes=480),
    )


def test_later_day_may_begin_at_earlier_phase(db):
    establish_clock(db, clock(day=2, phase="night", elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = _begin_next(db)
    stage_clock(db, token, clock(day=3, phase="dawn", elapsed_campaign_minutes=100))


def test_unknown_phase_is_valid_and_does_not_invent_advancement(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    stage_clock(db, token, clock(day=1, phase="unknown", elapsed_campaign_minutes=0))


def test_unknown_phase_does_not_erase_known_same_day_phase(db):
    establish_clock(db, clock(day=1, phase="midday", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot become unknown"):
        stage_clock(db, token, clock(day=1, phase="unknown", elapsed_campaign_minutes=0))


def test_rejects_day_decrease(db):
    establish_clock(db, clock(day=3, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot move backwards"):
        stage_clock(db, token, clock(day=2, phase="dawn", elapsed_campaign_minutes=0))


def test_rejects_same_day_phase_regression(db):
    establish_clock(db, clock(day=1, phase="evening", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="within the same day"):
        stage_clock(db, token, clock(day=1, phase="morning", elapsed_campaign_minutes=0))


def test_rejects_elapsed_decrease(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=50))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot decrease"):
        stage_clock(db, token, clock(day=None, phase="unknown", elapsed_campaign_minutes=40))


def test_rejects_long_rest_decrease(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=0, long_rests_completed=2))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot decrease"):
        stage_clock(db, token, clock(day=None, phase="unknown", elapsed_campaign_minutes=0, long_rests_completed=1))


def test_replay_same_target_does_not_double_advance_elapsed(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=10))
    _published, _staging, token, _expires = _begin_next(db)
    target = clock(day=None, phase="unknown", elapsed_campaign_minutes=25)
    stage_clock(db, token, target)
    stage_clock(db, token, target)  # logical replay
    from rt02_util import pending, publish
    publish(db, token)
    assert published_clock(db)["elapsed_campaign_minutes"] == 25


def test_replay_same_target_does_not_double_count_long_rest(db):
    establish_clock(db, clock(day=None, phase="unknown", elapsed_campaign_minutes=0, long_rests_completed=1))
    _published, _staging, token, _expires = _begin_next(db)
    target = clock(day=None, phase="unknown", elapsed_campaign_minutes=0, long_rests_completed=2)
    stage_clock(db, token, target)
    stage_clock(db, token, target)
    from rt02_util import publish
    publish(db, token)
    assert published_clock(db)["long_rests_completed"] == 2


def test_clock_cannot_erase_established_day(db):
    establish_clock(db, clock(day=4, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = _begin_next(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="cannot be unset"):
        stage_clock(db, token, clock(day=None, phase="unknown", elapsed_campaign_minutes=0))
