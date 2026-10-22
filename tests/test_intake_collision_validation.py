"""CI-03 Canon Intake collision classification proof.

Covers the deterministic collision classifier added by CI-03: an explicitly
human-approved CI-01 candidate with its CI-02.1 material envelope is compared
against one trusted caller-supplied authoritative current-target/publication
observation, and exactly one of clear | duplicate | stale | conflict |
unresolved is produced. Only clear is promotion-eligible; CI-04 owns
promotion.

The observation is embedded in each collision result and is bound to the
referenced candidate's proposed_target, so one observation cannot clear
multiple different targets. Nested publication identity is strictly
validated, a present target with unavailable material classifies unresolved,
and the declared reason must equal the deterministic computed reason.

Per the CI-03 Surface Budget, all fixtures are inline in-memory records or
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

import validate_intake_candidate_material  # noqa: E402
import validate_intake_candidates  # noqa: E402
import validate_intake_collisions  # noqa: E402
import validate_intake_decisions  # noqa: E402

CANDIDATE_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate.schema.json"
DECISION_SCHEMA_PATH = ROOT / "schemas" / "intake_decision.schema.json"
MATERIAL_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate_material.schema.json"

GIT_REF = "0123456789abcdef0123456789abcdef01234567"
OTHER_GIT_REF = "fedcba9876543210fedcba9876543210fedcba98"

EXTRACTED_CANDIDATE = {
    "candidate_id": "candidate:fixture-inn-rumor",
    "summary": "Fixture candidate: an unnamed inn rumor about a lost caravan (synthetic).",
    "status": "extracted",
    "source": {
        "kind": "published_adventure",
        "reference": "example-published-adventure-volume-1",
        "locator": "chapter 2",
        "origin": "unnamed fixture author",
        "label": "Fixture source label",
    },
}

CLASSIFIED_CANDIDATE = {
    **EXTRACTED_CANDIDATE,
    "candidate_id": "candidate:fixture-caravan-map",
    "summary": "Fixture candidate: a partially torn caravan map sketch (synthetic).",
    "status": "classified",
    "provenance": {"classification": "official"},
}

SECOND_CLASSIFIED_CANDIDATE = {
    **CLASSIFIED_CANDIDATE,
    "candidate_id": "candidate:fixture-tavern-song",
    "summary": "Fixture candidate: an unclassified tavern song fragment (synthetic).",
    "provenance": {"classification": "homebrew"},
}

THIRD_CLASSIFIED_CANDIDATE = {
    **CLASSIFIED_CANDIDATE,
    "candidate_id": "candidate:fixture-mimic-lamp",
    "summary": "Fixture candidate: a mimic disguised as a lamp (synthetic).",
    "provenance": {"classification": "adapted"},
}

CANDIDATES = [
    EXTRACTED_CANDIDATE,
    CLASSIFIED_CANDIDATE,
    SECOND_CLASSIFIED_CANDIDATE,
    THIRD_CLASSIFIED_CANDIDATE,
]

CANDIDATE_A = CLASSIFIED_CANDIDATE["candidate_id"]
CANDIDATE_B = SECOND_CLASSIFIED_CANDIDATE["candidate_id"]
CANDIDATE_C = THIRD_CLASSIFIED_CANDIDATE["candidate_id"]

TARGET_A = {"kind": "npc", "reference": "fixture-npc-innkeeper"}
TARGET_B = {"kind": "location", "reference": "fixture-location-crossroads"}
TARGET_OTHER = {"kind": "npc", "reference": "fixture-npc-someone-else"}

MATERIAL_BASE = {
    "candidate_id": CANDIDATE_A,
    "material_type": "fixture_lore_text",
    "material": "Fixture material: the rumor claims a caravan vanished near a "
                "fixture crossroads (synthetic).",
    "proposed_target": TARGET_A,
}

MATERIAL_B = {
    **MATERIAL_BASE,
    "candidate_id": CANDIDATE_B,
    "material_type": "fixture_song_fragment",
    "material": "Fixture material: two bars of a tavern song (synthetic).",
    "proposed_target": TARGET_B,
}

MATERIAL_C = {
    **MATERIAL_BASE,
    "candidate_id": CANDIDATE_C,
    "material_type": "fixture_item_note",
    "material": "Fixture material: a note about a mimic lamp (synthetic).",
    "proposed_target": TARGET_A,
}

MATERIALS = [MATERIAL_BASE, MATERIAL_B, MATERIAL_C]

DECISION_BASE = {
    "decision_id": "decision:fixture-approve-caravan-map",
    "candidate_id": CANDIDATE_A,
    "outcome": "approved",
    "authority": "human",
    "decided_by": "the fixture DM",
}

APPROVED_DECISIONS = [
    DECISION_BASE,
    {**DECISION_BASE,
     "decision_id": "decision:fixture-approve-tavern-song",
     "candidate_id": CANDIDATE_B},
    {**DECISION_BASE,
     "decision_id": "decision:fixture-approve-mimic-lamp",
     "candidate_id": CANDIDATE_C},
]

OBS_PRESENT_DIFFERENT = {
    "target_state": "present",
    "current_material": "Fixture material: a genuinely different inn story "
                        "already established in fixture truth (synthetic).",
}

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


def _obs(target_state, target=None, current_material=None, target_identity=None):
    observation = {"target_state": target_state}
    if target is not None:
        observation["target"] = target
    if current_material is not None:
        observation["current_material"] = current_material
    if target_identity is not None:
        observation["target_identity"] = target_identity
    return observation


def _record(candidate_id, envelope, observation, result=None, reason=None):
    """Build a collision record whose declared result/reason default to computed."""
    computed_result, computed_reason = validate_intake_collisions.classify(
        envelope, observation
    )
    return {
        "collision_id": "collision:" + candidate_id.split(":", 1)[1] + "-check",
        "candidate_id": candidate_id,
        "observation": observation,
        "result": computed_result if result is None else result,
        "reason": computed_reason if reason is None else reason,
    }


COLLISION_BASE = _record(
    CANDIDATE_A, MATERIAL_BASE, _obs("absent", target=TARGET_A)
)


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _write_batch(tmp_path, records, subdir):
    directory = tmp_path / subdir
    directory.mkdir(exist_ok=True)
    return [_write(directory, f"{index:02d}.json", record)
            for index, record in enumerate(records, start=1)]


def _set_errors(tmp_path, candidate_records=None, decision_records=None,
                material_records=None, collision_records=None):
    candidate_paths = _write_batch(
        tmp_path, CANDIDATES if candidate_records is None else candidate_records,
        subdir="candidates",
    )
    decision_paths = _write_batch(
        tmp_path, APPROVED_DECISIONS if decision_records is None else decision_records,
        subdir="decisions",
    )
    material_paths = _write_batch(
        tmp_path, MATERIALS if material_records is None else material_records,
        subdir="material",
    )
    collision_paths = _write_batch(
        tmp_path, [COLLISION_BASE] if collision_records is None else collision_records,
        subdir="collisions",
    )
    return validate_intake_collisions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
    )


def _errors(record):
    schema = validate_intake_collisions.load_schema()
    return validate_intake_collisions.validate_record(record, schema)


def _first_errors(failures):
    return next(iter(failures.values()))


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(
        validate_intake_collisions.load_schema()
    )


def test_result_vocabulary_is_closed():
    schema = validate_intake_collisions.load_schema()
    assert schema["properties"]["result"]["enum"] == [
        "clear", "duplicate", "stale", "conflict", "unresolved",
    ]
    assert schema["required"] == [
        "collision_id", "candidate_id", "observation", "result", "reason",
    ]
    assert schema["additionalProperties"] is False


def test_observation_is_required_and_closed():
    assert _errors({k: v for k, v in COLLISION_BASE.items()
                    if k != "observation"})
    record = {**COLLISION_BASE, "observation": {"target_state": "absent",
                                                "invented": 1}}
    assert _errors(record), "unknown observation field must fail closed"


@pytest.mark.parametrize("bad_observation", [
    {},                                                   # missing target_state
    {"target": TARGET_A},                                 # missing target_state
    "absent",                                             # scalar observation
    1,
    True,
    [],
    None,
    {"target_state": "gone"},                             # illegal target_state
    {"target_state": None},
    {"target_state": "absent", "target": "npc"},          # scalar/non-object target
    {"target_state": "absent", "target": 7},
    {"target_state": "absent", "target": []},
    {"target_state": "absent", "target": {}},             # empty target
    {"target_state": "absent", "target": {"kind": "npc"}},        # missing ref
    {"target_state": "absent", "target": {"reference": "x"}},     # missing kind
    {"target_state": "absent", "target_identity": "x"},   # scalar identity
    {"target_state": "absent", "target_identity": []},
    {"target_state": "absent", "current_material": "x"},  # forbidden material
    {"target_state": "present", "target": TARGET_A,
     "current_material": 1},                              # malformed material
])
def test_schema_invalid_observation_fails_closed_without_crash(
        tmp_path, bad_observation):
    record = {**COLLISION_BASE, "observation": bad_observation}
    candidate_failures, decision_failures, material_failures, \
        collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, (
        f"schema-invalid observation {bad_observation!r} must fail closed"
    )
    assert _errors(record), (
        f"schema-invalid observation {bad_observation!r} must surface schema errors"
    )


@pytest.mark.parametrize("bad_record", [
    ["not", "an", "object"],
    "not-an-object",
    7,
    True,
    None,
])
def test_non_object_collision_record_fails_closed_without_crash(
        tmp_path, bad_record):
    *_, collision_failures = _set_errors(
        tmp_path, collision_records=[bad_record])
    assert collision_failures, (
        f"non-object collision record {bad_record!r} must fail closed"
    )


# ---------------------------------------------------------------------------
# Proof matrix: the nine classification branches
# ---------------------------------------------------------------------------


def test_approved_candidate_target_absent_classifies_clear(tmp_path):
    candidate_failures, decision_failures, material_failures, \
        collision_failures = _set_errors(tmp_path)
    assert candidate_failures == {}
    assert decision_failures == {}
    assert material_failures == {}
    assert collision_failures == {}, collision_failures


def test_present_exact_material_match_classifies_duplicate(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A, current_material=MATERIAL_BASE["material"]))
    assert record["result"] == "duplicate"
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_present_different_material_classifies_conflict(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A,
        current_material=OBS_PRESENT_DIFFERENT["current_material"]))
    assert record["result"] == "conflict"
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_base_generation_mismatch_classifies_stale(tmp_path):
    envelope = {**MATERIAL_BASE, "base_publication": {"generation": 1}}
    record = _record(CANDIDATE_A, envelope, _obs(
        "present", target=TARGET_A, target_identity={"generation": 2},
        current_material=MATERIAL_BASE["material"]))
    assert record["result"] == "stale"
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[envelope], collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_base_git_ref_mismatch_classifies_stale(tmp_path):
    envelope = {**MATERIAL_BASE, "base_publication": {"git_ref": GIT_REF}}
    record = _record(CANDIDATE_A, envelope, _obs(
        "present", target=TARGET_A,
        target_identity={"git_ref": OTHER_GIT_REF},
        current_material=MATERIAL_BASE["material"]))
    assert record["result"] == "stale"
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[envelope], collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_matching_known_base_pin_permits_target_comparison(tmp_path):
    envelope = {**MATERIAL_BASE,
                "base_publication": {"generation": 1, "git_ref": GIT_REF}}
    record = _record(CANDIDATE_A, envelope, _obs(
        "present", target=TARGET_A,
        target_identity={"generation": 1, "git_ref": GIT_REF},
        current_material=MATERIAL_BASE["material"]))
    assert record["result"] == "duplicate"
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[envelope], collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_absent_proposed_target_classifies_unresolved(tmp_path):
    envelope = {k: v for k, v in MATERIAL_BASE.items() if k != "proposed_target"}
    record = _record(CANDIDATE_A, envelope, _obs("unknown"))
    assert record["result"] == "unresolved"
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[envelope], collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_target_observation_unknown_classifies_unresolved(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("unknown", target=TARGET_A))
    assert record["result"] == "unresolved"
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures == {}, collision_failures


def test_present_target_with_missing_current_material_is_unresolved(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("present", target=TARGET_A))
    assert record["result"] == "unresolved"
    assert "current material is unavailable" in record["reason"]
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures == {}, collision_failures


# ---------------------------------------------------------------------------
# Finding 1 regression: observation bound to the candidate's proposed_target
# ---------------------------------------------------------------------------


def test_observation_target_must_match_proposed_target(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("absent", target=TARGET_OTHER))
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "mismatched observation target must fail closed"
    assert any(
        "does not match the candidate's proposed_target" in error
        for error in _first_errors(collision_failures)
    )


def test_observation_target_required_when_envelope_proposes_one(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("absent"))
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "unbound observation must fail closed"
    assert any(
        "does not bind the candidate's proposed_target" in error
        for error in _first_errors(collision_failures)
    )


def test_observation_target_forbidden_when_no_proposed_target(tmp_path):
    envelope = {k: v for k, v in MATERIAL_BASE.items() if k != "proposed_target"}
    record = _record(CANDIDATE_A, envelope, _obs("unknown", target=TARGET_A))
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[envelope], collision_records=[record])
    assert collision_failures, "unproposed target binding must fail closed"
    assert any(
        "has no proposed_target" in error
        for error in _first_errors(collision_failures)
    )


def test_one_observation_cannot_clear_a_different_candidates_target(tmp_path):
    # Candidate B proposes TARGET_B (the crossroads); an observation bound to
    # candidate A's TARGET_A (the innkeeper) must not clear B.
    record = _record(CANDIDATE_B, MATERIAL_B, _obs("absent", target=TARGET_A))
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, (
        "one observation must not clear a different candidate's target"
    )


def test_same_target_may_be_shared_by_two_candidates(tmp_path):
    observation = _obs("absent", target=TARGET_A)
    record_a = _record(CANDIDATE_A, MATERIAL_BASE, observation)
    record_c = _record(CANDIDATE_C, MATERIAL_C, observation)
    *_, collision_failures = _set_errors(
        tmp_path, collision_records=[record_a, record_c])
    assert collision_failures == {}, collision_failures


# ---------------------------------------------------------------------------
# Finding 3 regression: strict nested publication identity validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("good_identity", [
    {"generation": 0},
    {"generation": 7},
    {"git_ref": GIT_REF},
    {"generation": 1, "git_ref": GIT_REF},
])
def test_valid_target_identity_accepted(good_identity):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "unknown", target=TARGET_A, target_identity=good_identity))
    assert _errors(record) == [], good_identity


@pytest.mark.parametrize("bad_identity", [
    {},
    {"generation": -1},
    {"generation": True},
    {"generation": False},
    {"generation": 1.5},
    {"generation": "1"},
    {"generation": None},
    {"git_ref": "main"},
    {"git_ref": "runtime-published"},
    {"git_ref": "0123456789abcdef0123456789abcdef0123456"},
    {"git_ref": "0123456789abcdef0123456789abcdef012345677"},
    {"git_ref": "0123456789ABCDEF0123456789abcdef01234567"},
    {"git_ref": "0123456789ghijkl0123456789abcdef01234567"},
    {"git_ref": None},
    {"generation": 1, "invented": "x"},
    {"git_ref": GIT_REF, "invented": "x"},
])
def test_malformed_target_identity_fails(bad_identity):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "unknown", target=TARGET_A, target_identity=bad_identity))
    assert _errors(record), f"accepted target_identity {bad_identity!r}"


def test_unknown_fields_rejected_in_observation_nesting():
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "unknown", target={**TARGET_A, "label": "extra"}))
    assert _errors(record), "unknown target field must fail closed"

    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("unknown", target=TARGET_A))
    record["observation"]["current_publication"] = {"generation": 1}
    assert _errors(record), "unknown observation field must fail closed"


# ---------------------------------------------------------------------------
# Finding 2 regression: present + missing material is allowed and unresolved
# ---------------------------------------------------------------------------


def test_schema_allows_present_without_current_material():
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("present", target=TARGET_A))
    assert record["result"] == "unresolved"
    assert _errors(record) == [], (
        "present target without current material must be representable, not a "
        "schema error"
    )


@pytest.mark.parametrize("state", ["absent", "unknown"])
def test_current_material_forbidden_when_target_not_present(state):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        state, target=TARGET_A, current_material="stray material"))
    assert _errors(record), (
        f"current_material must be forbidden when target_state is {state}"
    )


@pytest.mark.parametrize("bad_material", ["", "   ", "\n", 1, True, [], {}])
def test_present_with_malformed_current_material_fails(bad_material):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A, current_material=bad_material))
    assert _errors(record), f"accepted current_material {bad_material!r}"


def test_present_with_explicit_null_current_material_fails():
    observation = {"target_state": "present", "target": TARGET_A,
                   "current_material": None}
    record = _record(CANDIDATE_A, MATERIAL_BASE, observation)
    assert _errors(record), "explicit null current_material must fail closed"


# ---------------------------------------------------------------------------
# Finding 4 regression: declared reason must match computed evidence
# ---------------------------------------------------------------------------


def test_computed_reason_is_deterministic_and_authoritative():
    result, reason = validate_intake_collisions.classify(
        MATERIAL_BASE, _obs("absent", target=TARGET_A))
    assert (result, reason) == (
        "clear", "proposed target is known absent from current authoritative truth"
    )


def test_reason_must_match_computed_reason(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs("absent", target=TARGET_A))
    record["reason"] = "because the caller said so"
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "mismatched reason must fail closed"
    assert any(
        "does not match the deterministic reason" in error
        for error in _first_errors(collision_failures)
    )


def test_declared_result_must_match_computed_classification(tmp_path):
    record = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A,
        current_material=OBS_PRESENT_DIFFERENT["current_material"]),
        result="clear")
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "declared result must match deterministic classification"


# ---------------------------------------------------------------------------
# Fail-closed eligibility
# ---------------------------------------------------------------------------


def test_rejected_decision_is_not_eligible(tmp_path):
    *_, collision_failures = _set_errors(
        tmp_path, decision_records=[{**DECISION_BASE, "outcome": "rejected"}],
    )
    assert collision_failures, "rejected decision must not be collision-eligible"
    assert any(
        "human-approved" in error
        for error in _first_errors(collision_failures)
    )


def test_missing_decision_is_not_eligible(tmp_path):
    *_, collision_failures = _set_errors(tmp_path, decision_records=[])
    assert collision_failures, "missing decision must not be collision-eligible"


def test_non_human_authority_fails_through_ci02_validation(tmp_path):
    candidate_failures, decision_failures, *_ = _set_errors(
        tmp_path, decision_records=[{**DECISION_BASE, "authority": "ai"}])
    assert decision_failures, "non-human authority must fail CI-02 validation"
    assert not candidate_failures


def test_unknown_candidate_linkage_fails(tmp_path):
    record = {**COLLISION_BASE, "candidate_id": "candidate:fixture-ghost"}
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "unknown candidate linkage must fail closed"


def test_collision_without_material_envelope_fails(tmp_path):
    *_, collision_failures = _set_errors(
        tmp_path, material_records=[MATERIAL_B, MATERIAL_C])
    assert collision_failures, "collision without material must fail closed"
    assert any(
        "material envelope" in error
        for error in _first_errors(collision_failures)
    )


def test_duplicate_collision_result_for_same_candidate_fails(tmp_path):
    *_, collision_failures = _set_errors(
        tmp_path, collision_records=[COLLISION_BASE,
                                     {**COLLISION_BASE,
                                      "collision_id": "collision:fixture-second"}])
    assert collision_failures, "duplicate collision result must fail closed"
    assert any(
        "already has a collision result" in error
        for error in _first_errors(collision_failures)
    )


def test_duplicate_collision_id_fails(tmp_path):
    record_b = _record(CANDIDATE_B, MATERIAL_B, _obs("absent", target=TARGET_B))
    record_b["collision_id"] = COLLISION_BASE["collision_id"]
    *_, collision_failures = _set_errors(
        tmp_path, collision_records=[COLLISION_BASE, record_b])
    assert collision_failures, "duplicate collision_id must fail closed"


def test_result_outside_vocabulary_fails(tmp_path):
    record = {**COLLISION_BASE, "result": "probably-fine"}
    *_, collision_failures = _set_errors(tmp_path, collision_records=[record])
    assert collision_failures, "illegal result vocabulary must fail closed"


# ---------------------------------------------------------------------------
# Determinism / exact comparison
# ---------------------------------------------------------------------------


def test_exact_comparison_is_byte_faithful(tmp_path):
    same = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A, current_material=MATERIAL_BASE["material"]))
    *_, collision_failures = _set_errors(tmp_path, collision_records=[same])
    assert collision_failures == {}

    # Whitespace differs: NOT equal, must classify conflict.
    trailing = _record(CANDIDATE_A, MATERIAL_BASE, _obs(
        "present", target=TARGET_A,
        current_material=MATERIAL_BASE["material"] + "\n"))
    assert trailing["result"] == "conflict"
    *_, collision_failures = _set_errors(tmp_path, collision_records=[trailing])
    assert collision_failures == {}, collision_failures


def test_classify_is_pure_and_repeatable():
    for _ in range(3):
        assert validate_intake_collisions.classify(
            MATERIAL_BASE, _obs("present", target=TARGET_A,
                                current_material=MATERIAL_BASE["material"])
        )[0] == "duplicate"
        assert validate_intake_collisions.classify(
            MATERIAL_BASE, _obs("present", target=TARGET_A,
                                current_material="different")
        )[0] == "conflict"
        assert validate_intake_collisions.classify(
            MATERIAL_BASE, _obs("absent", target=TARGET_A))[0] == "clear"
        assert validate_intake_collisions.classify(
            MATERIAL_BASE, _obs("unknown", target=TARGET_A))[0] == "unresolved"


# ---------------------------------------------------------------------------
# Input immutability + upstream contract stability
# ---------------------------------------------------------------------------


def test_validation_does_not_mutate_any_input(tmp_path):
    candidate_paths = _write_batch(tmp_path, CANDIDATES, subdir="candidates")
    decision_paths = _write_batch(tmp_path, APPROVED_DECISIONS, subdir="decisions")
    material_paths = _write_batch(tmp_path, MATERIALS, subdir="material")
    collision_paths = _write_batch(tmp_path, [COLLISION_BASE], subdir="collisions")
    before = {path: path.read_bytes() for path in (
        *candidate_paths, *decision_paths, *material_paths, *collision_paths,
    )}
    listing_before = sorted(p.name for p in tmp_path.rglob("*"))

    failures = validate_intake_collisions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths)
    assert all(not f for f in failures)

    after = {path: path.read_bytes() for path in (
        *candidate_paths, *decision_paths, *material_paths, *collision_paths,
    )}
    assert after == before, "validation must never rewrite input bytes"
    assert sorted(p.name for p in tmp_path.rglob("*")) == listing_before, (
        "validation must never create or write files"
    )


def test_ci01_ci02_ci021_schemas_remain_unchanged():
    candidate_schema = json.loads(
        CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert candidate_schema["required"] == [
        "candidate_id", "summary", "status", "source"]
    assert candidate_schema["additionalProperties"] is False
    assert candidate_schema["properties"]["status"]["enum"] == [
        "extracted", "classified"]

    decision_schema = json.loads(
        DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert decision_schema["required"] == [
        "decision_id", "candidate_id", "outcome", "authority", "decided_by"]
    assert decision_schema["additionalProperties"] is False

    material_schema = json.loads(
        MATERIAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert material_schema["required"] == [
        "candidate_id", "material_type", "material"]
    assert material_schema["additionalProperties"] is False


def test_upstream_contract_sets_still_validate(tmp_path):
    candidate_paths = _write_batch(tmp_path, CANDIDATES, subdir="candidates")
    candidate_failures = validate_intake_candidates.validate_paths(candidate_paths)
    assert candidate_failures == {}, "CI-01 regression must stay green"

    decision_paths = _write_batch(
        tmp_path, APPROVED_DECISIONS, subdir="decisions2")
    candidate_failures, decision_failures = (
        validate_intake_decisions.validate_paths(candidate_paths, decision_paths)
    )
    assert candidate_failures == {} and decision_failures == {}

    material_paths = _write_batch(tmp_path, MATERIALS, subdir="material2")
    candidate_failures, material_failures = (
        validate_intake_candidate_material.validate_paths(
            candidate_paths, material_paths
        )
    )
    assert candidate_failures == {} and material_failures == {}


# ---------------------------------------------------------------------------
# Fixture hygiene
# ---------------------------------------------------------------------------


ALL_VALID = [
    EXTRACTED_CANDIDATE, CLASSIFIED_CANDIDATE, MATERIAL_BASE, MATERIAL_B,
    MATERIAL_C, DECISION_BASE, COLLISION_BASE,
]


def test_inline_fixtures_contain_no_real_rhc_campaign_facts():
    for record in ALL_VALID:
        if "summary" in record:
            assert "fixture" in record["summary"].lower(), record["candidate_id"]
        for text in _all_strings(record):
            for prefix in REAL_CAMPAIGN_PATH_PREFIXES:
                assert prefix not in text, (
                    f"fixture references real campaign path {prefix!r} in {text!r}"
                )
