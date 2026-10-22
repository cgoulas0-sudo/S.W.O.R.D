"""CI-02 Canon Intake decision contract proof.

Covers explicit human approve/reject decisions over CI-01 candidates,
selective (never batch-inherited) outcomes, fail-closed duplicate/conflict
handling, classified-only decision eligibility, and the structural
separation of decisions from candidate state, canon, and runtime truth.

Per the CI-02 Surface Budget, all fixtures are inline in-memory records or
tmp_path files: no external fixture directory is authorized for this patch,
and no real RHC campaign record is read, written, or referenced.
"""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import validate_intake_decisions  # noqa: E402

CANDIDATE_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate.schema.json"
DECISION_SCHEMA_PATH = ROOT / "schemas" / "intake_decision.schema.json"

CLASSIFIED_CANDIDATE = {
    "candidate_id": "candidate:fixture-inn-rumor",
    "summary": "Fixture candidate: an unnamed inn rumor about a lost caravan (synthetic).",
    "status": "classified",
    "source": {
        "kind": "published_adventure",
        "reference": "example-published-adventure-volume-1",
        "locator": "chapter 2",
        "origin": "unnamed fixture author",
        "label": "Fixture source label",
    },
    "provenance": {"classification": "official"},
}

EXTRACTED_CANDIDATE = {
    "candidate_id": "candidate:fixture-tavern-song",
    "summary": "Fixture candidate: an unclassified tavern song fragment (synthetic).",
    "status": "extracted",
    "source": {
        "kind": "session_notes",
        "reference": "fixture-session-notes-volume-2",
    },
}

SECOND_CLASSIFIED_CANDIDATE = {
    **CLASSIFIED_CANDIDATE,
    "candidate_id": "candidate:fixture-caravan-map",
    "summary": "Fixture candidate: a partially torn caravan map sketch (synthetic).",
    "provenance": {"classification": "homebrew"},
}

CANDIDATES = [CLASSIFIED_CANDIDATE, EXTRACTED_CANDIDATE, SECOND_CLASSIFIED_CANDIDATE]

DECISION_BASE = {
    "decision_id": "decision:fixture-approve-inn-rumor",
    "candidate_id": "candidate:fixture-inn-rumor",
    "outcome": "approved",
    "authority": "human",
    "decided_by": "fixture-dm",
}


def _errors(record, schema=None):
    schema = schema or validate_intake_decisions.load_schema()
    return validate_intake_decisions.validate_record(record, schema)


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _write_batch(tmp_path, records, subdir=""):
    directory = tmp_path / subdir if subdir else tmp_path
    if subdir:
        directory.mkdir(exist_ok=True)
    return [_write(directory, f"{i:02d}.json", record)
            for i, record in enumerate(records, start=1)]


def _set(tmp_path, candidate_records=None, decision_records=None):
    """Write one candidate batch + one decision set; return both path lists."""
    candidate_paths = _write_batch(
        tmp_path, CANDIDATES if candidate_records is None else candidate_records,
        subdir="candidates",
    )
    decision_paths = _write_batch(
        tmp_path, [DECISION_BASE] if decision_records is None else decision_records,
        subdir="decisions",
    )
    return candidate_paths, decision_paths


def _set_errors(tmp_path, candidate_records=None, decision_records=None):
    candidate_paths, decision_paths = _set(
        tmp_path, candidate_records, decision_records
    )
    candidate_failures, decision_failures = validate_intake_decisions.validate_paths(
        candidate_paths, decision_paths
    )
    return candidate_failures, decision_failures


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)


REAL_CAMPAIGN_PATH_PREFIXES = (
    "canon/",
    "characters/",
    "npc/",
    "villain/",
    "inventory/",
    "quests/",
    "state/",
    "entities/",
    "locations/",
    "beyond_the_heroes/",
)


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(
        validate_intake_decisions.load_schema()
    )


def test_classified_candidate_with_explicit_human_approved_decision_passes(tmp_path):
    candidate_failures, decision_failures = _set_errors(tmp_path)
    assert candidate_failures == {}
    assert decision_failures == {}


def test_classified_candidate_with_explicit_human_rejected_decision_passes(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE,
         "decision_id": "decision:fixture-reject-inn-rumor",
         "outcome": "rejected"},
    ])
    assert decision_failures == {}


def test_extracted_candidate_cannot_receive_a_decision(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE,
         "decision_id": "decision:fixture-decide-tavern-song",
         "candidate_id": "candidate:fixture-tavern-song"},
    ])
    assert decision_failures, "extracted candidate must not be decision-eligible"
    assert any(
        "only classified candidates are decision-eligible" in error
        for error in next(iter(decision_failures.values()))
    )


def test_unknown_candidate_id_fails(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE, "candidate_id": "candidate:fixture-unknown-target"},
    ])
    assert decision_failures, "decision against an unknown candidate must fail"
    assert any(
        "does not resolve" in error
        for error in next(iter(decision_failures.values()))
    )


def test_candidate_batch_must_be_valid_before_decisions_apply(tmp_path):
    broken = [
        {**CLASSIFIED_CANDIDATE, "provenance": None},
        *CANDIDATES[1:],
    ]
    candidate_failures, decision_failures = _set_errors(
        tmp_path, candidate_records=broken
    )
    assert candidate_failures, "invalid candidate batch must fail"
    assert decision_failures, "decisions must not consume an invalid candidate batch"


@pytest.mark.parametrize(
    "bad_id",
    ["", "   ", "decision:", "decision:Bad", "decision:has space",
     "decision:ok\n", "decision:ok\r", "decision:ok ", "decision:-x",
     "DECISION:ok", "candidate:inn-rumor", "item:vampire", "R01",
     "decision:ok/extra", None, 1, True, [], {}],
)
def test_missing_blank_or_malformed_decision_identity_fails(bad_id):
    record = {**DECISION_BASE, "decision_id": bad_id}
    errors = _errors(record)
    assert errors, f"accepted decision_id {bad_id!r}"
    assert any(
        error.startswith("decision_id") for error in errors
    ), f"rejected {bad_id!r} but not at decision_id: {errors}"


@pytest.mark.parametrize(
    "bad_outcome",
    ["approve", "reject", "accept", "pass", "Approved", "APPROVED",
     "approved ", " approved", "approved\n", "approve_all", "",
     "   ", None, 1, True, [], {}],
)
def test_free_form_or_ambiguous_outcome_fails(bad_outcome):
    record = {**DECISION_BASE, "outcome": bad_outcome}
    errors = _errors(record)
    assert errors, f"accepted outcome {bad_outcome!r}"
    assert any(
        error.startswith("outcome") for error in errors
    ), f"rejected {bad_outcome!r} but not at outcome: {errors}"


def test_outcome_enum_is_exactly_approved_or_rejected():
    schema = validate_intake_decisions.load_schema()
    enum = schema["properties"]["outcome"]["enum"]
    assert enum == ["approved", "rejected"]


def test_missing_outcome_fails():
    record = {k: v for k, v in DECISION_BASE.items() if k != "outcome"}
    assert _errors(record)


@pytest.mark.parametrize("bad_authority", [
    "ai", "system", "auto", "human_dm", "Human", "assistant", "", "   ",
    "human\n", None, 1, True, [], {},
])
def test_non_human_or_missing_authority_marker_fails(bad_authority):
    record = {**DECISION_BASE, "authority": bad_authority}
    errors = _errors(record)
    assert errors, f"accepted authority {bad_authority!r}"
    assert any(
        error.startswith("authority") for error in errors
    ), f"rejected {bad_authority!r} but not at authority: {errors}"


def test_missing_authority_marker_fails():
    record = {k: v for k, v in DECISION_BASE.items() if k != "authority"}
    errors = _errors(record)
    assert any(
        error.startswith("authority") or "'authority' is a required property" in error
        for error in errors
    ), errors


@pytest.mark.parametrize("bad_decided_by", ["", "   ", "\n", None, 1, True, [], {}])
def test_blank_or_missing_human_authority_reference_fails(bad_decided_by):
    record = {**DECISION_BASE, "decided_by": bad_decided_by}
    errors = _errors(record)
    assert errors, f"accepted decided_by {bad_decided_by!r}"
    assert any(
        error.startswith("decided_by") for error in errors
    ), f"rejected {bad_decided_by!r} but not at decided_by: {errors}"


def test_missing_human_authority_reference_fails():
    record = {k: v for k, v in DECISION_BASE.items() if k != "decided_by"}
    errors = _errors(record)
    assert any(
        error.startswith("decided_by") or "'decided_by' is a required property" in error
        for error in errors
    ), errors


def test_valid_optional_note_and_batch_label_pass(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE, "note": "Fixture reason: rumor is plausible.",
         "batch_label": "fixture-batch-1"},
    ])
    assert decision_failures == {}


@pytest.mark.parametrize("bad_value", ["", "   ", "\n", None, 1, True, [], {}])
@pytest.mark.parametrize("field", ["note", "batch_label"])
def test_optional_fields_reject_blank_or_non_string_values(field, bad_value):
    record = {**DECISION_BASE, field: bad_value}
    errors = _errors(record)
    assert errors, f"{field} accepted {bad_value!r}"
    assert any(
        error.startswith(field) for error in errors
    ), f"rejected {bad_value!r} but not at {field}: {errors}"


def test_candidate_records_remain_byte_identical_through_validation(tmp_path):
    candidate_paths, decision_paths = _set(tmp_path)
    before = {path: path.read_bytes() for path in candidate_paths}
    listing_before = sorted(p.name for p in tmp_path.rglob("*"))

    candidate_failures, decision_failures = validate_intake_decisions.validate_paths(
        candidate_paths, decision_paths
    )
    assert candidate_failures == {}
    assert decision_failures == {}

    after = {path: path.read_bytes() for path in candidate_paths}
    assert after == before, "validation must never rewrite candidate bytes"
    assert sorted(p.name for p in tmp_path.rglob("*")) == listing_before, (
        "validation must never create or write files"
    )


def test_candidate_records_remain_semantically_unchanged(tmp_path):
    candidate_paths, decision_paths = _set(tmp_path)
    before = [json.loads(path.read_text(encoding="utf-8")) for path in candidate_paths]

    validate_intake_decisions.validate_paths(candidate_paths, decision_paths)

    after = [json.loads(path.read_text(encoding="utf-8")) for path in candidate_paths]
    assert after == before


def test_candidate_status_enum_remains_exactly_extracted_or_classified():
    schema = json.loads(CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["properties"]["status"]["enum"]
    assert enum == ["extracted", "classified"]
    for forbidden in ("approved", "rejected", "published", "canon",
                      "accepted_as_truth"):
        assert forbidden not in enum


def test_decision_is_a_sidecar_without_candidate_state_semantics():
    schema = validate_intake_decisions.load_schema()
    assert "status" not in schema["properties"], (
        "a decision must never carry or mutate candidate lifecycle state"
    )
    text = DECISION_SCHEMA_PATH.read_text(encoding="utf-8")
    candidate_schema = json.loads(CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert json.loads(text)["properties"]["candidate_id"]["pattern"] == (
        candidate_schema["properties"]["candidate_id"]["pattern"]
    ), "decision candidate_id must use the exact CI-01 grammar"


def test_mixed_outcomes_in_one_labeled_group_are_legal(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE,
         "decision_id": "decision:fixture-approve-inn-rumor",
         "batch_label": "fixture-review-batch"},
        {**DECISION_BASE,
         "decision_id": "decision:fixture-reject-caravan-map",
         "candidate_id": "candidate:fixture-caravan-map",
         "outcome": "rejected",
         "batch_label": "fixture-review-batch"},
    ])
    assert decision_failures == {}, (
        "a group label must never impose one uniform outcome; mixed "
        "approve/reject in one validated group must pass"
    )


def test_duplicate_decision_id_rejected_across_the_set(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE},
        {**DECISION_BASE, "outcome": "rejected",
         "candidate_id": "candidate:fixture-caravan-map"},
    ])
    assert decision_failures, "duplicate decision identity must fail closed"
    assert any(
        "duplicates" in error
        for error in next(iter(decision_failures.values()))
    )


@pytest.mark.parametrize("second_outcome", ["approved", "rejected"])
def test_second_decision_for_same_candidate_fails_closed(tmp_path, second_outcome):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE},
        {**DECISION_BASE,
         "decision_id": "decision:fixture-second-decision",
         "outcome": second_outcome},
    ])
    assert decision_failures, (
        f"two decisions for one candidate (second outcome {second_outcome!r}) "
        f"must fail closed"
    )
    assert any(
        "already has a decision" in error
        for error in next(iter(decision_failures.values()))
    )


def test_same_outcome_replay_and_conflict_both_fail(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE},
        {**DECISION_BASE,
         "decision_id": "decision:fixture-replay",
         "outcome": "approved",
         "decided_by": "fixture-dm-2"},
        {**DECISION_BASE,
         "decision_id": "decision:fixture-conflict",
         "outcome": "rejected"},
    ])
    assert len(decision_failures) == 2, "replay and conflict must both fail"
    for errors in decision_failures.values():
        assert any("already has a decision" in error for error in errors)


def test_two_independent_candidates_each_get_their_own_outcome(tmp_path):
    _, decision_failures = _set_errors(tmp_path, decision_records=[
        {**DECISION_BASE},
        {**DECISION_BASE,
         "decision_id": "decision:fixture-decide-caravan-map",
         "candidate_id": "candidate:fixture-caravan-map",
         "outcome": "rejected"},
    ])
    assert decision_failures == {}


@pytest.mark.parametrize(
    "extra_field",
    ["status", "canon_status", "published", "approval_state", "payload",
     "provenance", "source", "visibility", "group_decision",
     "batch_outcome"],
)
def test_unknown_extra_fields_fail_at_top_level(extra_field):
    record = {**DECISION_BASE, extra_field: "whatever"}
    errors = _errors(record)
    assert errors, f"accepted invented {extra_field!r}"


def test_no_batch_inherited_outcome_field_exists():
    schema = validate_intake_decisions.load_schema()
    properties = schema["properties"]
    for forbidden in ("batch_outcome", "group_outcome", "approve_all",
                      "inherit", "status"):
        assert forbidden not in properties, forbidden


def test_required_properties_are_exactly_the_owned_contract():
    schema = validate_intake_decisions.load_schema()
    assert schema["required"] == [
        "decision_id", "candidate_id", "outcome", "authority", "decided_by",
    ]
    assert schema["additionalProperties"] is False


def test_inline_fixtures_contain_no_real_rhc_campaign_facts():
    for record in (*CANDIDATES, DECISION_BASE):
        if "summary" in record:
            assert "fixture" in record["summary"].lower(), record["candidate_id"]
        for text in _all_strings(record):
            for prefix in REAL_CAMPAIGN_PATH_PREFIXES:
                assert prefix not in text, (
                    f"fixture references real campaign path {prefix!r} in {text!r}"
                )
