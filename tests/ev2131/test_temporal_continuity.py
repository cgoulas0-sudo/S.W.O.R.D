"""EV2-13.1 temporal-continuity proof.

Runs against real PostgreSQL 15 with the full forward migration chain and the
real save/publication/mirror-confirmation spine. Nothing is mocked.

The core temporal continuity law this module proves:

    World-calendar position may later move backward or forward. Experienced
    elapsed campaign time never moves backward. Timed status ageing follows
    experienced elapsed time only.

Proof Matrix coverage:
  * a forward elapsed jump crossing multiple thresholds exposes ALL still
    unacknowledged due thresholds in one deterministic read;
  * acknowledging one due threshold prevents it from being returned again as
    unprocessed while later thresholds stay discoverable;
  * there is no per-minute ticker/scheduler: a large jump is derived in one read
    and mutates nothing;
  * a backwards world-date displacement cannot produce negative elapsed age
    because the status surface has no calendar/date field and no subtraction
    path, and RT02 itself refuses to decrease elapsed minutes or the day;
  * stored timing anchors are absolute experienced-time anchors, never
    remaining-duration countdowns;
  * missing/malformed Clock truth fails closed on read as well as mutation.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ev2131"))
import ev2131_util as s  # noqa: E402


def _create_at_anchor(db, anchor, thresholds, target=s.HERO):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=anchor))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token,
             s.request(definition_obj=s.definition(thresholds=thresholds, target=target)))
    s.publish(db, token)
    s.confirm_mirror(db)


# ---------------------------------------------------------------------------
# Forward jump catch-up
# ---------------------------------------------------------------------------

def test_forward_jump_exposes_every_crossed_threshold(db):
    # JOHNNY example: application anchor 1000; thresholds due at 2440 and 5320;
    # the published Clock jumps from 1100 to 5500.
    _create_at_anchor(db, 1000, [
        s.threshold("T1", 1440, "minute"),   # 1000 + 1 day = 2440
        s.threshold("T2", 4320, "minute"),   # 1000 + 3 days = 5320
    ])

    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=1100))
    read = s.read_status(db)
    assert read["due_thresholds"] == []
    assert {t["threshold_id"] for t in read["pending_thresholds"]} == {"T1", "T2"}

    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=5500))
    read = s.read_status(db)
    assert read["application"]["age_elapsed_minutes"] == 4500
    due = {t["threshold_id"]: t for t in read["due_thresholds"]}
    assert set(due) == {"T1", "T2"}
    assert due["T1"]["due_at_elapsed_minutes"] == 2440
    assert due["T1"]["overdue_by_elapsed_minutes"] == 5500 - 2440
    assert due["T2"]["due_at_elapsed_minutes"] == 5320
    assert due["T2"]["overdue_by_elapsed_minutes"] == 180


def test_acknowledging_one_leaves_later_thresholds_discoverable(db):
    _create_at_anchor(db, 1000, [
        s.threshold("T1", 1440, "minute"),
        s.threshold("T2", 4320, "minute"),
    ])
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=5500))

    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(acknowledge=["T1"]))
    s.publish(db, token)
    s.confirm_mirror(db)

    read = s.read_status(db)
    assert [t["threshold_id"] for t in read["due_thresholds"]] == ["T2"]
    assert read["application"]["acknowledged_thresholds"] == [
        {"threshold_id": "T1", "acknowledged_at_elapsed_minutes": 5500}
    ]

    # A later read never re-presents the acknowledged threshold as unprocessed.
    again = s.read_status(db)
    assert "T1" not in {t["threshold_id"] for t in again["due_thresholds"]}
    assert "T1" not in {t["threshold_id"] for t in again["pending_thresholds"]}


def test_huge_forward_jump_needs_no_per_minute_ticker(db):
    # Thresholds are established once, then the Clock leaps a hundred million
    # minutes with no intermediate persistence.
    _create_at_anchor(db, 0, [
        s.threshold("T1", 1, "minute"),
        s.threshold("T2", 1440, "minute"),
    ])

    before = s.runtime_row(db)["published_generation"]
    generations_before = s.scalar(
        db, "select count(distinct generation) from public.campaign_state_generations"
    )
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100000000))
    read = s.read_status(db)
    assert {t["threshold_id"] for t in read["due_thresholds"]} == {"T1", "T2"}
    assert read["application"]["age_elapsed_minutes"] == 100000000

    # The read itself mutated nothing and created no per-minute rows.
    assert s.runtime_row(db)["published_generation"] > before
    assert s.scalar(
        db, "select count(distinct generation) from public.campaign_state_generations"
    ) == generations_before + 1  # only the Clock save advanced the store
    assert len(s.published_applied_statuses(db)) == 1


def test_acknowledged_threshold_stays_processed_across_later_jumps(db):
    _create_at_anchor(db, 0, [
        s.threshold("T1", 10, "minute"),
        s.threshold("T2", 1000, "minute"),
    ])
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=20))

    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(acknowledge=["T1"]))
    s.publish(db, token)
    s.confirm_mirror(db)

    read = s.read_status(db)
    assert [t["threshold_id"] for t in read["due_thresholds"]] == []
    assert [t["threshold_id"] for t in read["pending_thresholds"]] == ["T2"]

    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=2000))
    read = s.read_status(db)
    assert [t["threshold_id"] for t in read["due_thresholds"]] == ["T2"]
    assert "T1" not in {t["threshold_id"] for t in read["due_thresholds"]}


# ---------------------------------------------------------------------------
# Absolute anchors, not countdowns
# ---------------------------------------------------------------------------

def test_stored_anchors_are_absolute_not_countdowns(db):
    _create_at_anchor(db, 100, [s.threshold("T1", 100, "minute")])

    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=150))
    read = s.read_status(db)
    record = read["application"]
    assert record["applied_at_elapsed_minutes"] == 100
    assert record["thresholds"] == [
        {"threshold_id": "T1", "due_at_elapsed_minutes": 200}
    ]
    assert read["pending_thresholds"][0]["remaining_elapsed_minutes"] == 50

    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=250))
    read = s.read_status(db)
    # The stored due anchor never moved; only derived due-ness changed.
    assert read["application"]["thresholds"] == [
        {"threshold_id": "T1", "due_at_elapsed_minutes": 200}
    ]
    assert read["due_thresholds"][0]["overdue_by_elapsed_minutes"] == 50


def test_read_is_pure(db):
    _create_at_anchor(db, 100, [s.threshold("T1", 10, "minute")])
    row_before = s.runtime_row(db)
    state_before = s.published_state(db)
    s.read_status(db)
    s.read_status(db)
    assert s.runtime_row(db) == row_before
    assert s.published_state(db) == state_before


# ---------------------------------------------------------------------------
# World-calendar independence (the core invariant)
# ---------------------------------------------------------------------------

def test_status_surface_has_no_calendar_or_date_field(db):
    _create_at_anchor(db, 5000, [s.threshold("T1", 60, "minute")])
    record = s.published_applied_statuses(db)[0]
    assert set(record) == {
        "application_version", "application_id", "definition_id",
        "target_entity_id", "source_entity_id", "applied_at_elapsed_minutes",
        "thresholds", "acknowledged_thresholds", "ended_at_elapsed_minutes",
    }
    forbidden = ("date", "year", "month", "calendar", "harptos",
                 "dalereckoning", "day")
    for key in record:
        assert not any(token in key.lower() for token in forbidden)


def test_forward_world_date_displacement_changes_no_elapsed_anchor(db):
    # A world-calendar position move forward (day 1372 DR -> 1772 DR) with the
    # same experienced elapsed time must leave age and anchors untouched.
    s.publish_confirmed_clock(
        db, s.clock(day=1372, phase="morning", elapsed_campaign_minutes=5000)
    )
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition(
        thresholds=[s.threshold("T1", 60, "minute")])))
    s.publish(db, token)
    s.confirm_mirror(db)

    before = s.read_status(db)
    assert before["application"]["age_elapsed_minutes"] == 0
    assert before["application"]["applied_at_elapsed_minutes"] == 5000

    s.publish_confirmed_clock(
        db, s.clock(day=1772, phase="morning", elapsed_campaign_minutes=5000)
    )
    after = s.read_status(db)
    assert after["application"]["age_elapsed_minutes"] == 0
    assert after["application"]["applied_at_elapsed_minutes"] == 5000
    assert after["application"]["thresholds"] == before["application"]["thresholds"]
    assert after["due_thresholds"] == []


def test_backwards_world_date_cannot_produce_negative_age(db):
    # Backwards world-calendar placement is deferred to a later world-calendar
    # Mission; the status surface has no calendar subtraction path. RT02 itself
    # refuses to move the day or elapsed cursor backward, so there is no
    # representable state in which elapsed age could go negative.
    s.publish_confirmed_clock(
        db, s.clock(day=1372, phase="morning", elapsed_campaign_minutes=5000)
    )
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition(
        thresholds=[s.threshold("T1", 60, "minute")])))
    s.publish(db, token)
    s.confirm_mirror(db)

    # RT02 refuses a backwards elapsed cursor.
    _published, _staging, token, _expires = s.begin_save(db)
    with pytest.raises(Exception) as elapsed_exc:
        s.stage_clock(db, token, s.clock(day=1372, phase="morning",
                                         elapsed_campaign_minutes=4999))
    assert "cannot decrease" in str(elapsed_exc.value)
    s.abort_save(db, token)

    # RT02 refuses a backwards established day.
    _published, _staging, token, _expires = s.begin_save(db)
    with pytest.raises(Exception) as day_exc:
        s.stage_clock(db, token, s.clock(day=1000, phase="morning",
                                         elapsed_campaign_minutes=5000))
    assert "day cannot move backwards" in str(day_exc.value)
    s.abort_save(db, token)

    # Age remains a non-negative elapsed difference.
    assert s.read_status(db)["application"]["age_elapsed_minutes"] == 0


# ---------------------------------------------------------------------------
# Missing / malformed Clock fails closed on read too
# ---------------------------------------------------------------------------

def test_malformed_published_clock_fails_closed_on_read(db):
    _create_at_anchor(db, 100, [s.threshold("T1", 10, "minute")])
    s.break_glass(
        db,
        "update public.campaign_state_generations set value = %s::jsonb "
        "where key = 'campaign_clock' "
        "and generation = (select published_generation from public.campaign_runtime where id = 1)",
        (json.dumps({"schema_version": 1, "day": None, "phase": "unknown",
                     "elapsed_campaign_minutes": "not-a-number",
                     "long_rests_completed": 0}),),
    )
    err = s.read_status_error(db)
    assert "unreadable" in err


def test_read_of_unknown_application_is_truthful_absence(db):
    _create_at_anchor(db, 100, [s.threshold("T1", 10, "minute")])
    read = s.read_status(db, application_id="AS-99")
    assert read["application"] is None
    assert read["due_thresholds"] == []
    assert read["pending_thresholds"] == []


# ---------------------------------------------------------------------------
# Explicit end lifecycle (terminal, anchor-stable, no post-end processing)
# ---------------------------------------------------------------------------

def test_end_lifecycle_is_terminal_and_anchor_is_stable(db):
    # One soon-due threshold and one far threshold, applied at elapsed 100.
    _create_at_anchor(db, 100, [
        s.threshold("T1", 1, "minute"),      # due 101
        s.threshold("T2", 1000, "minute"),   # due 1100
    ])

    # Advance the authoritative published elapsed cursor to 200 so T1 is due.
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=200))
    authoritative = s.published_clock(db)["elapsed_campaign_minutes"]
    assert authoritative == 200

    # End the application. The terminal anchor must equal the authoritative
    # published RT02 elapsed cursor, never a caller-supplied value.
    _published, _staging, token, _expires = s.begin_save(db)
    ended = s.mutate(db, token, s.request(end=True))
    assert ended["application"]["ended_at_elapsed_minutes"] == authoritative
    s.publish(db, token)
    s.confirm_mirror(db)

    # An ended application exposes no due or pending thresholds, even though
    # T1's due anchor has already been crossed.
    read = s.read_status(db)
    assert read["application"]["ended_at_elapsed_minutes"] == authoritative
    assert read["due_thresholds"] == []
    assert read["pending_thresholds"] == []

    # Advance the Clock far past every threshold in a later published save.
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=2000))

    # Replaying "end": true must preserve the original terminal anchor, never
    # move it to the later elapsed cursor.
    _published, _staging, token, _expires = s.begin_save(db)
    replayed = s.mutate(db, token, s.request(end=True))
    assert replayed["application"]["ended_at_elapsed_minutes"] == authoritative
    s.publish(db, token)
    s.confirm_mirror(db)

    read = s.read_status(db)
    assert read["application"]["ended_at_elapsed_minutes"] == authoritative
    assert read["application"]["age_elapsed_minutes"] == 1900
    assert read["due_thresholds"] == []
    assert read["pending_thresholds"] == []

    # A new threshold acknowledgement after end fails closed.
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(db, token, s.request(acknowledge=["T1"]))
    assert "has ended" in err
