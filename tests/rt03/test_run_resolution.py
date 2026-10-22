"""RT03 identity input + exact published resolution (Proof Matrix A, B)."""

import psycopg2
import pytest

from rt03_util import read_run, run, begin_save, publish, stage, stage_runs


def test_valid_run_id_resolves_exactly_one_published_run(db):
    record = run("R01", outcome_summary="The tavern brawl ended without injuries.")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            record,
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    publish(db, token)

    result = read_run(db, "R01")
    assert result["mode"] == "run"
    assert result["run_id"] == "R01"
    assert result["run"] == record
    assert result["runtime"]["generation"] == 1

    other = read_run(db, "R02")
    assert other["run"]["run_id"] == "R02"


@pytest.mark.parametrize(
    "bad_id",
    ["R1", "r01", "RUN01", "X01", "01", "", "   ", "R 01", "R01 ", " R01", "R01\n", "R01\r"],
)
def test_malformed_run_id_fails_closed(db, bad_id):
    with pytest.raises(psycopg2.errors.RaiseException, match="run_id must be R followed"):
        read_run(db, bad_id)


def test_null_run_id_fails_closed(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="run_id must be R followed"):
        read_run(db, None)


def test_run_payload_supplied_as_input_is_only_an_identity_and_fails_closed(db):
    payload = run("R01")
    with pytest.raises(psycopg2.errors.RaiseException, match="run_id must be R followed"):
        read_run(db, str(payload))


def test_run_shaped_truth_outside_the_system_namespace_is_not_authority(db):
    """The caller owns only the identity: no alternate key, path or payload is consulted."""
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "run:R01", run("R01"))
    stage(db, token, "runs_history", [run("R01")])
    stage(db, token, "audit_log", {"mentions": "R01"})
    stage(db, token, "runs", [run("R02")])
    publish(db, token)

    result = read_run(db, "R01")
    assert result["run"] is None
    assert result["runtime"]["generation"] == 1


def test_missing_identity_returns_truthful_absence_with_metadata(db):
    result = read_run(db, "R01")
    assert result["mode"] == "run"
    assert result["runtime"]["generation"] == 0
    assert result["run"] is None

    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [])
    publish(db, token)
    result = read_run(db, "R01")
    assert result["runtime"]["generation"] == 1
    assert result["run"] is None


def test_missing_id_after_other_runs_does_not_fabricate(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01"), run("R02")])
    publish(db, token)

    result = read_run(db, "R99")
    assert result["run"] is None
    assert result["runtime"]["generation"] == 1


def test_duplicate_authoritative_claims_fail_closed(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01", outcome_summary="first claim"),
            run("R01", outcome_summary="second claim"),
        ],
    )
    publish(db, token)

    with pytest.raises(psycopg2.errors.RaiseException, match="duplicate authoritative Run claims"):
        read_run(db, "R01")


def test_identical_duplicate_bytes_still_fail_closed(db):
    record = run("R01")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [record, record])
    publish(db, token)

    with pytest.raises(psycopg2.errors.RaiseException, match="duplicate authoritative Run claims"):
        read_run(db, "R01")


def test_unrelated_values_mentioning_the_same_text_do_not_match(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            "R01",
            41,
            {"note": "references R01 without claiming it"},
            run("R01"),
        ],
    )
    stage(db, token, "notes", "someone wrote R01 here")
    publish(db, token)

    result = read_run(db, "R01")
    assert result["run"] == run("R01")


def test_cross_run_mutable_owner_conflict_fails_closed(db):
    """Accepted P2: EV2-08 allows at most one mutable-owner claim per actor
    across the published Run batch, so neither claimant is trusted, even
    though each requested Run is individually valid."""
    hero = run("R01", outcome_summary="R01 currently owns the hero")
    rival = run("R02", outcome_summary="R02 claims the same hero")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [hero, rival])
    publish(db, token)

    with pytest.raises(psycopg2.errors.RaiseException, match="claimed by both R01 and R02"):
        read_run(db, "R01")
    with pytest.raises(psycopg2.errors.RaiseException, match="claimed by both R02 and R01"):
        read_run(db, "R02")


def test_disjoint_mutable_owners_across_runs_are_all_readable(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run(
                "R01",
                participant_entity_ids=["character:test-hero"],
                mutable_owner_entity_ids=["character:test-hero"],
            ),
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    publish(db, token)

    assert read_run(db, "R01")["run"]["run_id"] == "R01"
    assert read_run(db, "R02")["run"]["run_id"] == "R02"


def test_shared_participation_without_shared_ownership_is_not_a_conflict(db):
    """Historical participation may overlap freely; only mutable-owner claims
    are exclusive."""
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run(
                "R01",
                participant_entity_ids=["character:test-hero", "character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-hero"],
            ),
            run(
                "R02",
                participant_entity_ids=["character:test-hero", "character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    publish(db, token)

    assert read_run(db, "R01")["run"]["run_id"] == "R01"
    assert read_run(db, "R02")["run"]["run_id"] == "R02"


def test_parked_run_without_current_claims_remains_readable_alongside_active_run(db):
    """Parked historical Run keeps participation history with no current
    claims; the handoff pattern stays readable (EV2-08 Madma example)."""
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run(
                "R01",
                control_state="parked",
                participant_entity_ids=["character:test-hero"],
                mutable_owner_entity_ids=[],
            ),
            run("R02", mutable_owner_entity_ids=["character:test-hero"]),
        ],
    )
    publish(db, token)

    parked = read_run(db, "R01")
    assert parked["run"]["control_state"] == "parked"
    assert parked["run"]["mutable_owner_entity_ids"] == []
    assert read_run(db, "R02")["run"]["run_id"] == "R02"


@pytest.mark.parametrize("broken", ["missing", "null", "scalar"])
def test_unreadable_other_run_owner_list_fails_closed(db, broken):
    """When the requested Run claims owners, uniqueness must be provable: an
    unreadable owner list on another published entry fails closed."""
    rival = run("R02")
    if broken == "missing":
        rival.pop("mutable_owner_entity_ids")
    elif broken == "null":
        rival["mutable_owner_entity_ids"] = None
    else:
        rival["mutable_owner_entity_ids"] = "character:test-hero"
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01"), rival])
    publish(db, token)

    with pytest.raises(psycopg2.errors.RaiseException, match="unreadable mutable_owner_entity_ids"):
        read_run(db, "R01")


def test_zero_claim_run_is_not_blocked_by_an_unreadable_other_owner_list(db):
    """A Run with no mutable owners cannot conflict with anything, so the
    uniqueness proof is vacuous and does not need the other entries' lists."""
    rival = run("R02")
    rival.pop("mutable_owner_entity_ids")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01", mutable_owner_entity_ids=[]),
            rival,
        ],
    )
    publish(db, token)

    result = read_run(db, "R01")
    assert result["run"]["mutable_owner_entity_ids"] == []
