"""RT03 EV2-08 validation of the matching published candidate (Proof Matrix C)."""

import json

import psycopg2
import pytest

from rt03_util import (
    begin_save,
    publish,
    publish_confirmed_runs,
    read_run,
    run,
    scalar,
)


def _publish_single(db, record):
    publish_confirmed_runs(db, [record])


def test_valid_played_active_run_is_trusted(db):
    record = run("R01", control_state="active")
    _publish_single(db, record)
    assert read_run(db, "R01")["run"] == record


def test_valid_played_parked_run_is_trusted_as_parked(db):
    record = run("R01", control_state="parked", mutable_owner_entity_ids=[])
    _publish_single(db, record)
    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "parked"


def test_valid_off_screen_run_is_trusted(db):
    record = run("R01", execution_mode="off_screen", control_state="not_applicable")
    _publish_single(db, record)
    assert read_run(db, "R01")["run"] == record


def test_parked_run_with_released_ownership_remains_valid(db):
    record = run(
        "R01",
        control_state="parked",
        participant_entity_ids=["character:test-hero"],
        mutable_owner_entity_ids=[],
    )
    _publish_single(db, record)
    assert read_run(db, "R01")["run"]["mutable_owner_entity_ids"] == []


def test_long_run_ids_remain_valid(db):
    record = run("R001234")
    _publish_single(db, record)
    assert read_run(db, "R001234")["run"]["run_id"] == "R001234"


def test_empty_encounter_and_location_lists_are_valid(db):
    record = run("R01", occurred_encounter_ids=[], location_ids=[])
    _publish_single(db, record)
    assert read_run(db, "R01")["run"]["occurred_encounter_ids"] == []


def test_optional_party_id_is_accepted_when_valid(db):
    record = run("R01", party_id="party:bor-family")
    _publish_single(db, record)
    assert read_run(db, "R01")["run"]["party_id"] == "party:bor-family"


def test_played_run_cannot_claim_not_applicable_control_state(db):
    _publish_single(db, run("R01", control_state="not_applicable"))
    with pytest.raises(psycopg2.errors.RaiseException, match="played Run control_state"):
        read_run(db, "R01")


def test_played_run_cannot_claim_unknown_control_state(db):
    _publish_single(db, run("R01", control_state="resolved"))
    with pytest.raises(psycopg2.errors.RaiseException, match="played Run control_state"):
        read_run(db, "R01")


def test_played_run_with_null_control_state_fails_closed(db):
    # JSON-null control_state must fail closed even though `null not in (...)`
    # is three-valued NULL in SQL (accepted P1 defect).
    _publish_single(db, run("R01", control_state=None))
    with pytest.raises(psycopg2.errors.RaiseException, match="played Run control_state"):
        read_run(db, "R01")


def test_off_screen_run_requires_not_applicable_control_state(db):
    _publish_single(db, run("R01", execution_mode="off_screen", control_state="active"))
    with pytest.raises(psycopg2.errors.RaiseException, match="off_screen Run control_state"):
        read_run(db, "R01")


def test_unknown_execution_mode_fails_closed(db):
    _publish_single(db, {**run("R01"), "execution_mode": "dreamed"})
    with pytest.raises(psycopg2.errors.RaiseException, match="execution_mode"):
        read_run(db, "R01")


def test_validator_enforces_run_identity_pattern(db):
    # The read only matches entries whose run_id equals the requested identity,
    # so the record-internal identity pattern is proven against the internal
    # validator directly (superuser harness; service_role is separately denied).
    assert scalar(db, "select public._rhc_validate_run_record(%s::jsonb)", (json.dumps(run("R01")),)) is True
    with pytest.raises(psycopg2.errors.RaiseException, match="run_id must be R followed"):
        scalar(db, "select public._rhc_validate_run_record(%s::jsonb)", (json.dumps({**run("R01"), "run_id": "X1"}),))


def test_missing_required_field_fails_closed(db):
    broken = run("R01")
    broken.pop("campaign_anchor")
    _publish_single(db, broken)
    with pytest.raises(psycopg2.errors.RaiseException, match="missing a required EV2-08 field"):
        read_run(db, "R01")


def test_unknown_field_fails_closed(db):
    _publish_single(db, {**run("R01"), "hook_id": "H01"})
    with pytest.raises(psycopg2.errors.RaiseException, match="outside the EV2-08 contract"):
        read_run(db, "R01")


def test_structured_world_delta_fails_closed(db):
    _publish_single(db, {**run("R01"), "world_changes": []})
    with pytest.raises(psycopg2.errors.RaiseException, match="outside the EV2-08 contract"):
        read_run(db, "R01")


def test_invalid_scenario_id_fails_closed(db):
    _publish_single(db, run("R01", scenario_id="S1"))
    with pytest.raises(psycopg2.errors.RaiseException, match="scenario_id"):
        read_run(db, "R01")


def test_invalid_encounter_id_fails_closed(db):
    _publish_single(db, run("R01", occurred_encounter_ids=["E1"]))
    with pytest.raises(psycopg2.errors.RaiseException, match="occurred_encounter_ids"):
        read_run(db, "R01")


def test_duplicate_encounter_entries_fail_closed(db):
    _publish_single(db, run("R01", occurred_encounter_ids=["E01", "E01"]))
    with pytest.raises(psycopg2.errors.RaiseException, match="duplicate entries"):
        read_run(db, "R01")


def test_invalid_party_id_fails_closed(db):
    _publish_single(db, run("R01", party_id="party:Bad Slug"))
    with pytest.raises(psycopg2.errors.RaiseException, match="party_id"):
        read_run(db, "R01")


def test_participant_list_requires_at_least_one_actor(db):
    _publish_single(db, run("R01", participant_entity_ids=[]))
    with pytest.raises(psycopg2.errors.RaiseException, match="participant_entity_ids"):
        read_run(db, "R01")


def test_non_actor_participant_id_fails_closed(db):
    _publish_single(db, run("R01", participant_entity_ids=["location:tavern"]))
    with pytest.raises(psycopg2.errors.RaiseException, match="participant_entity_ids"):
        read_run(db, "R01")


def test_mutable_owner_outside_participants_fails_closed(db):
    _publish_single(
        db,
        run("R01", participant_entity_ids=["character:test-hero"], mutable_owner_entity_ids=["character:not-a-participant"]),
    )
    with pytest.raises(psycopg2.errors.RaiseException, match="mutable owner must also appear"):
        read_run(db, "R01")


def test_non_actor_mutable_owner_fails_closed(db):
    _publish_single(db, run("R01", mutable_owner_entity_ids=["party:crew"]))
    with pytest.raises(psycopg2.errors.RaiseException, match="mutable_owner_entity_ids"):
        read_run(db, "R01")


def test_invalid_location_id_fails_closed(db):
    _publish_single(db, run("R01", location_ids=["loc:tavern"]))
    with pytest.raises(psycopg2.errors.RaiseException, match="location_ids"):
        read_run(db, "R01")


def test_anchor_requires_exact_lowercase_hex_commit(db):
    for bad_commit in ("abc", "G" * 40, "A" * 40, "a" * 39, "a" * 40 + "\n"):
        _publish_single(db, run("R01", base_commit=bad_commit))
        with pytest.raises(psycopg2.errors.RaiseException, match="base_commit"):
            read_run(db, "R01")


def test_anchor_time_must_be_nonblank(db):
    _publish_single(db, run("R01", campaign_time="   "))
    with pytest.raises(psycopg2.errors.RaiseException, match="campaign_time"):
        read_run(db, "R01")


def test_anchor_rejects_unknown_fields(db):
    broken = run("R01")
    broken["campaign_anchor"] = {**broken["campaign_anchor"], "clock_day": 3}
    _publish_single(db, broken)
    with pytest.raises(psycopg2.errors.RaiseException, match="campaign_anchor contains fields outside"):
        read_run(db, "R01")


def test_blank_outcome_summary_fails_closed(db):
    _publish_single(db, run("R01", outcome_summary="   "))
    with pytest.raises(psycopg2.errors.RaiseException, match="outcome_summary"):
        read_run(db, "R01")


def test_outcome_summary_stays_optional(db):
    record = run("R01")
    record.pop("outcome_summary", None)
    _publish_single(db, record)
    assert read_run(db, "R01")["run"] == record
