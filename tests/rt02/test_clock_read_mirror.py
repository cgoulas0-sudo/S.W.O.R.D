"""RT02 read isolation + mirror carriage (Proof Matrix G, H)."""

from rt02_util import (
    begin_save,
    clock,
    establish_clock,
    pending,
    publish,
    scalar,
    stage,
    stage_clock,
)


def _published_clock_via_read(db):
    result = scalar(db, "select public.dm_runtime_read('campaign_clock')")
    matches = [item for item in result["results"] if item["key"] == "campaign_clock"]
    return matches[0]["value"] if matches else None


def test_read_facade_exposes_published_clock(db):
    establish_clock(
        db, clock(day=3, phase="night", elapsed_campaign_minutes=60, long_rests_completed=1)
    )
    clock_value = _published_clock_via_read(db)
    assert clock_value["day"] == 3
    assert clock_value["phase"] == "night"
    assert clock_value["elapsed_campaign_minutes"] == 60
    assert clock_value["long_rests_completed"] == 1

    context = scalar(db, "select public.dm_runtime_read()")
    assert context["runtime"]["day"] == 3


def test_staged_clock_is_invisible_to_read_facade(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="dawn", elapsed_campaign_minutes=0))

    assert _published_clock_via_read(db)["day"] == 1
    assert scalar(db, "select public.dm_runtime_read()")["runtime"]["day"] == 1


def test_zero_hit_targeted_read_preserves_metadata(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    result = scalar(db, "select public.dm_runtime_read('absent-clock-key')")
    assert result["results"] == []
    assert result["runtime"]["day"] == 1


def test_pending_mirror_carries_exact_clock_state(db):
    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="afternoon", elapsed_campaign_minutes=120))
    publish(db, token)

    candidate = pending(db)
    assert candidate["published_day"] == 2
    assert candidate["state"]["campaign_clock"]["day"] == 2
    assert candidate["state"]["campaign_clock"]["phase"] == "afternoon"
    assert candidate["state"]["campaign_clock"]["elapsed_campaign_minutes"] == 120


def test_confirm_carries_clock_through_verifier_boundary(db):
    from rt02_util import confirm

    establish_clock(db, clock(day=1, phase="morning", elapsed_campaign_minutes=0))
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock(day=2, phase="night", elapsed_campaign_minutes=200))
    publish(db, token)

    candidate = pending(db)
    confirm(db, candidate)

    runtime = scalar(db, "select public.dm_runtime_read()")["runtime"]
    assert runtime["day"] == 2
    assert runtime["mirror_confirmed"] is True
    assert _published_clock_via_read(db)["day"] == 2
