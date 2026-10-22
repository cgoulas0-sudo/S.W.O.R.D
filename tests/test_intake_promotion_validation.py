"""CI-04 Canon Intake promotion bridge proof.

Covers the smallest reusable promotion bridge added by CI-04: one CI-01
candidate, its CI-02 human approval, its CI-02.1 material envelope, and its
CI-03 collision result are bound into a legal promotion instruction, and an
authoritative route produces a promotion receipt whose success claim requires
real read-back evidence. Only a classified, explicitly human-approved
candidate with an exact CI-03 ``clear`` result is eligible; runtime_save routes
only to the existing RT01 Save Gateway authority and repository_canon only to
the existing repository-authorized path. CI-04 never becomes a second
persistence engine, never performs a raw SQL/Git/runtime-published write, and
promotes no real RHC campaign candidate.

Per the CI-04 Surface Budget, all fixtures are inline in-memory records or
tmp_path files: no external fixture directory is authorized for this patch, and
no real RHC campaign record is read, written, or referenced.
"""
import ast
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
import validate_intake_promotions  # noqa: E402

INSTRUCTION_SCHEMA_PATH = ROOT / "schemas" / "intake_promotion.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "intake_promotion_receipt.schema.json"

CANDIDATE_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate.schema.json"
DECISION_SCHEMA_PATH = ROOT / "schemas" / "intake_decision.schema.json"
MATERIAL_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate_material.schema.json"
COLLISION_SCHEMA_PATH = ROOT / "schemas" / "intake_collision.schema.json"

GIT_REF = "0123456789abcdef0123456789abcdef01234567"
OTHER_GIT_REF = "fedcba9876543210fedcba9876543210fedcba98"
COMMIT = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"

# --- CI-01 candidates -------------------------------------------------------

EXTRACTED_CANDIDATE = {
    "candidate_id": "candidate:fixture-inn-rumor",
    "summary": "Fixture candidate: an unnamed inn rumor about a lost caravan (synthetic).",
    "status": "extracted",
    "source": {
        "kind": "published_adventure",
        "reference": "example-published-adventure-volume-1",
        "locator": "chapter 2",
    },
}

CLASSIFIED_A = {
    **EXTRACTED_CANDIDATE,
    "candidate_id": "candidate:fixture-caravan-map",
    "summary": "Fixture candidate: a partially torn caravan map sketch (synthetic).",
    "status": "classified",
    "provenance": {"classification": "official"},
}

CLASSIFIED_B = {
    **CLASSIFIED_A,
    "candidate_id": "candidate:fixture-tavern-song",
    "summary": "Fixture candidate: two bars of a tavern song (synthetic).",
    "provenance": {"classification": "homebrew"},
}

CLASSIFIED_C = {
    **CLASSIFIED_A,
    "candidate_id": "candidate:fixture-mimic-lamp",
    "summary": "Fixture candidate: a mimic disguised as a lamp (synthetic).",
    "provenance": {"classification": "adapted"},
}

CLASSIFIED_D = {
    **CLASSIFIED_A,
    "candidate_id": "candidate:fixture-rain-ledger",
    "summary": "Fixture candidate: a rejected rain ledger entry (synthetic).",
    "provenance": {"classification": "homebrew"},
}

CANDIDATES = [EXTRACTED_CANDIDATE, CLASSIFIED_A, CLASSIFIED_B, CLASSIFIED_C,
              CLASSIFIED_D]

CANDIDATE_A = CLASSIFIED_A["candidate_id"]
CANDIDATE_B = CLASSIFIED_B["candidate_id"]
CANDIDATE_C = CLASSIFIED_C["candidate_id"]
CANDIDATE_D = CLASSIFIED_D["candidate_id"]
EXTRACTED_ID = EXTRACTED_CANDIDATE["candidate_id"]

# --- CI-02.1 material envelopes --------------------------------------------

TARGET_A = {"kind": "npc", "reference": "fixture-npc-innkeeper"}
TARGET_B = {"kind": "location", "reference": "fixture-location-crossroads"}
TARGET_OTHER = {"kind": "npc", "reference": "fixture-npc-someone-else"}

MATERIAL_A = {
    "candidate_id": CANDIDATE_A,
    "material_type": "fixture_lore_text",
    "material": "Fixture material: the rumor claims a caravan vanished near a "
                "fixture crossroads (synthetic).",
    "proposed_target": TARGET_A,
}

MATERIAL_B = {
    "candidate_id": CANDIDATE_B,
    "material_type": "fixture_song_fragment",
    "material": "Fixture material: two bars of a tavern song (synthetic).",
    "proposed_target": TARGET_B,
}

MATERIAL_C = {
    "candidate_id": CANDIDATE_C,
    "material_type": "fixture_item_note",
    "material": "Fixture material: a note about a mimic lamp (synthetic).",
    "proposed_target": TARGET_A,
}

MATERIALS = [MATERIAL_A, MATERIAL_B, MATERIAL_C]

# --- CI-02 decisions --------------------------------------------------------

DECISION_A = {
    "decision_id": "decision:fixture-approve-caravan-map",
    "candidate_id": CANDIDATE_A,
    "outcome": "approved",
    "authority": "human",
    "decided_by": "the fixture DM",
}

DECISION_B = {
    **DECISION_A,
    "decision_id": "decision:fixture-approve-tavern-song",
    "candidate_id": CANDIDATE_B,
}

DECISION_C = {
    **DECISION_A,
    "decision_id": "decision:fixture-approve-mimic-lamp",
    "candidate_id": CANDIDATE_C,
}

DECISION_D_REJECTED = {
    "decision_id": "decision:fixture-reject-rain-ledger",
    "candidate_id": CANDIDATE_D,
    "outcome": "rejected",
    "authority": "human",
    "decided_by": "the fixture DM",
}

DECISIONS = [DECISION_A, DECISION_B, DECISION_C, DECISION_D_REJECTED]

# --- CI-03 collision results (all clear by default) -------------------------


def _obs(target_state, target=None, current_material=None, target_identity=None):
    observation = {"target_state": target_state}
    if target is not None:
        observation["target"] = target
    if current_material is not None:
        observation["current_material"] = current_material
    if target_identity is not None:
        observation["target_identity"] = target_identity
    return observation


def _collision(candidate_id, envelope, observation):
    """Build a collision record whose result/reason are the computed values."""
    result, reason = validate_intake_collisions.classify(envelope, observation)
    return {
        "collision_id": "collision:" + candidate_id.split(":", 1)[1] + "-check",
        "candidate_id": candidate_id,
        "observation": observation,
        "result": result,
        "reason": reason,
    }


COLLISION_A = _collision(CANDIDATE_A, MATERIAL_A, _obs("absent", target=TARGET_A))
COLLISION_B = _collision(CANDIDATE_B, MATERIAL_B, _obs("absent", target=TARGET_B))
COLLISION_C = _collision(CANDIDATE_C, MATERIAL_C, _obs("absent", target=TARGET_A))

COLLISIONS = [COLLISION_A, COLLISION_B, COLLISION_C]

# --- CI-04 promotion instructions -------------------------------------------

PROMOTION_A = {
    "promotion_id": "promotion:fixture-caravan-map",
    "candidate_id": CANDIDATE_A,
    "route": "runtime_save",
    "resolved_target": TARGET_A,
    "material_type": "fixture_lore_text",
    "decision_id": DECISION_A["decision_id"],
    "collision_id": COLLISION_A["collision_id"],
    "expected_collision_result": "clear",
}

PROMOTION_B = {
    **PROMOTION_A,
    "promotion_id": "promotion:fixture-tavern-song",
    "candidate_id": CANDIDATE_B,
    "route": "repository_canon",
    "resolved_target": TARGET_B,
    "material_type": "fixture_song_fragment",
    "decision_id": DECISION_B["decision_id"],
    "collision_id": COLLISION_B["collision_id"],
}

RECEIPT_A_SUCCESS = {
    "receipt_id": "receipt:fixture-caravan-map-success",
    "promotion_id": PROMOTION_A["promotion_id"],
    "candidate_id": CANDIDATE_A,
    "route": "runtime_save",
    "outcome": "success",
    "evidence": {
        "kind": "runtime_publication",
        "generation": 4,
        "git_ref": GIT_REF,
        "confirmed": True,
    },
}

RECEIPT_B_SUCCESS = {
    "receipt_id": "receipt:fixture-tavern-song-success",
    "promotion_id": PROMOTION_B["promotion_id"],
    "candidate_id": CANDIDATE_B,
    "route": "repository_canon",
    "outcome": "success",
    "evidence": {
        "kind": "repository_commit",
        "commit": COMMIT,
        "confirmed": True,
    },
}

PROMOTIONS = [PROMOTION_A, PROMOTION_B, RECEIPT_A_SUCCESS, RECEIPT_B_SUCCESS]

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

ALLOWED_IMPORTS = {
    "json",
    "re",
    "sys",
    "weakref",
    "pathlib",
    "validate_entities",
    "validate_intake_candidates",
    "validate_intake_candidate_material",
    "validate_intake_collisions",
    "validate_intake_decisions",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
                material_records=None, collision_records=None,
                promotion_records=None):
    candidate_paths = _write_batch(
        tmp_path, CANDIDATES if candidate_records is None else candidate_records,
        subdir="candidates",
    )
    decision_paths = _write_batch(
        tmp_path, DECISIONS if decision_records is None else decision_records,
        subdir="decisions",
    )
    material_paths = _write_batch(
        tmp_path, MATERIALS if material_records is None else material_records,
        subdir="material",
    )
    collision_paths = _write_batch(
        tmp_path, COLLISIONS if collision_records is None else collision_records,
        subdir="collisions",
    )
    promotion_paths = _write_batch(
        tmp_path, PROMOTIONS if promotion_records is None else promotion_records,
        subdir="promotions",
    )
    return validate_intake_promotions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
        promotion_paths,
    )


def _context(tmp_path, candidate_records=None, decision_records=None,
             material_records=None, collision_records=None,
             instruction=PROMOTION_A):
    """Write the four upstream sets and return a validated PromotionContext."""
    candidate_paths = _write_batch(
        tmp_path, CANDIDATES if candidate_records is None else candidate_records,
        subdir="ctx-candidates",
    )
    decision_paths = _write_batch(
        tmp_path, DECISIONS if decision_records is None else decision_records,
        subdir="ctx-decisions",
    )
    material_paths = _write_batch(
        tmp_path, MATERIALS if material_records is None else material_records,
        subdir="ctx-material",
    )
    collision_paths = _write_batch(
        tmp_path, COLLISIONS if collision_records is None else collision_records,
        subdir="ctx-collisions",
    )
    return validate_intake_promotions.build_context(
        candidate_paths, decision_paths, material_paths, collision_paths,
        instruction)


def _instruction_errors(record):
    schema = validate_intake_promotions.load_schema()
    return validate_intake_promotions.validate_record(record, schema)


def _receipt_errors(record):
    schema = validate_intake_promotions.load_receipt_schema()
    return validate_intake_promotions.validate_record(record, schema)


def _first_errors(failures):
    return next(iter(failures.values()))


def _all_errors(failures):
    return [error for errors in failures.values() for error in errors]


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)


class _SyntheticAdapter(validate_intake_promotions.PromotionRouteAdapter):
    """Test-only route adapter emitting a caller-supplied receipt.

    Tracks how many times ``execute`` ran so a test can prove a rejected or
    invalid instruction never reached the authoritative adapter.
    """

    def __init__(self, route, receipt):
        self.route = route
        self._receipt = receipt
        self.calls = 0

    def execute(self, instruction):
        self.calls += 1
        return self._receipt


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


def test_instruction_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(
        validate_intake_promotions.load_schema()
    )


def test_receipt_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(
        validate_intake_promotions.load_receipt_schema()
    )


def test_instruction_required_and_closed():
    schema = validate_intake_promotions.load_schema()
    assert schema["required"] == [
        "promotion_id", "candidate_id", "route", "resolved_target",
        "material_type", "decision_id", "collision_id",
        "expected_collision_result",
    ]
    assert schema["additionalProperties"] is False


def test_receipt_required_and_closed():
    schema = validate_intake_promotions.load_receipt_schema()
    assert schema["required"] == [
        "receipt_id", "promotion_id", "candidate_id", "route", "outcome",
    ]
    assert schema["additionalProperties"] is False


def test_route_vocabulary_is_closed():
    schema = validate_intake_promotions.load_schema()
    assert schema["properties"]["route"]["enum"] == [
        "runtime_save", "repository_canon",
    ]
    receipt = validate_intake_promotions.load_receipt_schema()
    assert receipt["properties"]["route"]["enum"] == [
        "runtime_save", "repository_canon",
    ]


def test_receipt_outcome_and_evidence_vocabulary_is_closed():
    schema = validate_intake_promotions.load_receipt_schema()
    assert schema["properties"]["outcome"]["enum"] == ["success", "failure"]
    assert schema["properties"]["evidence"]["properties"]["kind"]["enum"] == [
        "runtime_publication", "repository_commit",
    ]
    assert schema["properties"]["evidence"]["properties"]["confirmed"][
        "const"] is True


def test_expected_collision_result_is_clear_only():
    schema = validate_intake_promotions.load_schema()
    assert schema["properties"]["expected_collision_result"]["const"] == "clear"


# ---------------------------------------------------------------------------
# Proof 1: classified + human-approved + CI-03 clear forms an instruction
# ---------------------------------------------------------------------------


def test_approved_clear_candidate_forms_promotion_instruction(tmp_path):
    *_, promotion_failures = _set_errors(tmp_path)
    assert promotion_failures == {}, promotion_failures


def test_both_legal_route_classes_validate(tmp_path):
    *_, promotion_failures = _set_errors(tmp_path)
    assert promotion_failures == {}


# ---------------------------------------------------------------------------
# Proof 2/3: rejected and extracted candidates are not promotion-eligible
# ---------------------------------------------------------------------------


def test_rejected_candidate_is_not_promotion_eligible(tmp_path):
    _, _, _, collision_failures, promotion_failures = _set_errors(
        tmp_path,
        decision_records=[{**DECISION_A, "outcome": "rejected"},
                          DECISION_B, DECISION_C],
    )
    assert promotion_failures, "a rejected candidate must not be promotable"
    assert collision_failures, "CI-03 must refuse a non-approved candidate"


def test_extracted_candidate_is_not_promotion_eligible(tmp_path):
    instruction = {**PROMOTION_A, "candidate_id": EXTRACTED_ID}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures, "an extracted candidate must not be promotable"
    assert any(
        "only classified candidates are promotion-eligible" in error
        for error in _all_errors(promotion_failures)
    )


# ---------------------------------------------------------------------------
# Proof 4/6: lineage IDs must resolve and bind the same candidate
# ---------------------------------------------------------------------------


def test_missing_decision_reference_fails(tmp_path):
    instruction = {**PROMOTION_A, "decision_id": "decision:fixture-ghost"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures
    assert any(
        "does not resolve to a valid CI-02 decision" in error
        for error in _all_errors(promotion_failures)
    )


def test_promotion_decision_lineage_must_bind_same_candidate(tmp_path):
    instruction = {**PROMOTION_A, "decision_id": DECISION_B["decision_id"]}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures
    assert any(
        "belongs to candidate" in error
        for error in _all_errors(promotion_failures)
    )


def test_promotion_collision_lineage_must_bind_same_candidate(tmp_path):
    instruction = {**PROMOTION_A, "collision_id": COLLISION_B["collision_id"]}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures
    assert any(
        "belongs to candidate" in error
        for error in _all_errors(promotion_failures)
    )


def test_missing_collision_reference_fails(tmp_path):
    instruction = {**PROMOTION_A, "collision_id": "collision:fixture-ghost"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures
    assert any(
        "does not resolve to a valid CI-03 collision result" in error
        for error in _all_errors(promotion_failures)
    )


# ---------------------------------------------------------------------------
# Proof 5: every non-clear CI-03 result fails promotion
# ---------------------------------------------------------------------------


def _nonclear_collision_and_material(tmp_path, result):
    if result == "duplicate":
        return MATERIAL_A, _collision(CANDIDATE_A, MATERIAL_A, _obs(
            "present", target=TARGET_A, current_material=MATERIAL_A["material"]))
    if result == "conflict":
        return MATERIAL_A, _collision(CANDIDATE_A, MATERIAL_A, _obs(
            "present", target=TARGET_A,
            current_material="Fixture material: a genuinely different story "
                             "(synthetic)."))
    if result == "stale":
        envelope = {**MATERIAL_A, "base_publication": {"generation": 1}}
        return envelope, _collision(CANDIDATE_A, envelope, _obs(
            "present", target=TARGET_A,
            target_identity={"generation": 2},
            current_material="Fixture material: a different story (synthetic)."))
    if result == "unresolved":
        return MATERIAL_A, _collision(CANDIDATE_A, MATERIAL_A, _obs(
            "unknown", target=TARGET_A))
    raise AssertionError(result)


@pytest.mark.parametrize("result", ["duplicate", "stale", "conflict",
                                    "unresolved"])
def test_non_clear_collision_result_fails_promotion(tmp_path, result):
    envelope, collision = _nonclear_collision_and_material(tmp_path, result)
    assert collision["result"] == result
    *_, promotion_failures = _set_errors(
        tmp_path,
        material_records=[envelope, MATERIAL_B, MATERIAL_C],
        collision_records=[collision, COLLISION_B, COLLISION_C],
    )
    assert promotion_failures, (
        f"CI-03 result {result!r} must not be promotion-eligible"
    )
    assert any(
        "only a clear collision result is promotion-eligible" in error
        for error in _all_errors(promotion_failures)
    )


# ---------------------------------------------------------------------------
# Proof 7/8/9/10: explicit legal route resolution, no guessing, no rerouting
# ---------------------------------------------------------------------------


def test_route_authority_registry_is_explicit_and_closed():
    assert validate_intake_promotions.route_authority("runtime_save") == (
        "RT01 Save Gateway"
    )
    assert validate_intake_promotions.route_authority("repository_canon") == (
        "repository-authorized canon owner path"
    )
    for bad in ("direct_sql", "sql", "generic_write", "", None, 1, True):
        with pytest.raises(validate_intake_promotions.PromotionError):
            validate_intake_promotions.route_authority(bad)


def test_unknown_route_fails_closed(tmp_path):
    instruction = {**PROMOTION_A, "route": "direct_sql"}
    assert _instruction_errors(instruction), "route enum must be closed"
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures


def test_resolved_target_must_match_proposed_target(tmp_path):
    instruction = {**PROMOTION_A, "resolved_target": TARGET_OTHER}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures, "a rerouted target must fail closed"
    assert any(
        "does not match the candidate's proposed_target" in error
        for error in _all_errors(promotion_failures)
    )


def test_route_is_not_inferred_from_material_prose(tmp_path):
    prose_material = {
        **MATERIAL_A,
        "material": "Fixture material: this prose mentions repository_canon and "
                    "runtime_save but the declared route alone governs "
                    "(synthetic).",
    }
    instruction = {**PROMOTION_A, "route": "runtime_save"}
    *_, promotion_failures = _set_errors(
        tmp_path,
        material_records=[prose_material, MATERIAL_B, MATERIAL_C],
        promotion_records=[instruction],
    )
    assert promotion_failures == {}, (
        "the declared route must govern and must never be inferred from prose"
    )

    bad = {**PROMOTION_A, "route": "sql_direct"}
    *_, promotion_failures = _set_errors(
        tmp_path,
        material_records=[prose_material, MATERIAL_B, MATERIAL_C],
        promotion_records=[bad],
    )
    assert promotion_failures, (
        "prose suggesting a route must not rescue an illegal declared route"
    )


def test_instruction_material_type_must_match_envelope(tmp_path):
    instruction = {**PROMOTION_A, "material_type": "fixture_song_fragment"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[instruction])
    assert promotion_failures
    assert any(
        "does not match the candidate material envelope" in error
        for error in _all_errors(promotion_failures)
    )


# ---------------------------------------------------------------------------
# Proof 11/12: runtime success requires authoritative runtime read-back
# ---------------------------------------------------------------------------


def test_runtime_success_without_evidence_fails(tmp_path):
    receipt = {k: v for k, v in RECEIPT_A_SUCCESS.items() if k != "evidence"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures, (
        "runtime_save success must not be claimable without read-back evidence"
    )
    assert any(
        "requires authoritative read-back evidence" in error
        for error in _all_errors(promotion_failures)
    )


@pytest.mark.parametrize("bad_evidence", [
    {"kind": "runtime_publication", "generation": 4, "git_ref": GIT_REF},
    {"kind": "runtime_publication", "git_ref": GIT_REF, "confirmed": True},
    {"kind": "runtime_publication", "generation": 4, "confirmed": True},
    {"kind": "runtime_publication", "generation": 0, "git_ref": GIT_REF,
     "confirmed": True},
    {"kind": "runtime_publication", "generation": True, "git_ref": GIT_REF,
     "confirmed": True},
    {"kind": "runtime_publication", "generation": 4, "git_ref": "main",
     "confirmed": True},
    {"kind": "runtime_publication", "generation": 4,
     "git_ref": GIT_REF.upper(), "confirmed": True},
    {"kind": "runtime_publication", "generation": 4, "git_ref": GIT_REF,
     "confirmed": False},
    {"kind": "repository_commit", "commit": COMMIT, "confirmed": True},
])
def test_runtime_success_with_incomplete_evidence_fails(tmp_path, bad_evidence):
    receipt = {**RECEIPT_A_SUCCESS, "evidence": bad_evidence}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures, f"accepted evidence {bad_evidence!r}"


def test_runtime_success_with_confirmed_generation_and_ref_passes(tmp_path):
    *_, promotion_failures = _set_errors(tmp_path)
    assert promotion_failures == {}, promotion_failures


# ---------------------------------------------------------------------------
# Proof 13: repository_canon success requires repository read-back evidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_evidence", [
    {"kind": "repository_commit", "confirmed": True},
    {"kind": "repository_commit", "commit": "main", "confirmed": True},
    {"kind": "repository_commit", "commit": COMMIT.upper(), "confirmed": True},
    {"kind": "repository_commit", "commit": COMMIT, "confirmed": False},
    {"kind": "runtime_publication", "generation": 1, "git_ref": GIT_REF,
     "confirmed": True},
])
def test_repository_success_with_invalid_evidence_fails(tmp_path, bad_evidence):
    receipt = {**RECEIPT_B_SUCCESS, "evidence": bad_evidence}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_B, receipt])
    assert promotion_failures, f"accepted evidence {bad_evidence!r}"


def test_repository_success_with_exact_commit_passes(tmp_path):
    *_, promotion_failures = _set_errors(tmp_path)
    assert promotion_failures == {}, promotion_failures


# ---------------------------------------------------------------------------
# Proof 14: failure/incomplete never masquerades as success
# ---------------------------------------------------------------------------


def test_failure_receipt_without_evidence_is_valid(tmp_path):
    receipt = {
        "receipt_id": "receipt:fixture-caravan-map-failure",
        "promotion_id": PROMOTION_A["promotion_id"],
        "candidate_id": CANDIDATE_A,
        "route": "runtime_save",
        "outcome": "failure",
        "failure_reason": "Fixture reason: mirror read-back not confirmed.",
    }
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures == {}, promotion_failures


def test_failure_receipt_carrying_success_evidence_fails(tmp_path):
    receipt = {
        **RECEIPT_A_SUCCESS,
        "receipt_id": "receipt:fixture-caravan-map-failure",
        "outcome": "failure",
    }
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures, (
        "a failure must never carry success evidence"
    )
    assert any(
        "failure receipt must not carry success evidence" in error
        for error in _all_errors(promotion_failures)
    )


def test_evidence_confirmed_must_be_literal_true(tmp_path):
    for bogus in (1, "true", "yes", None):
        receipt = {**RECEIPT_A_SUCCESS,
                   "evidence": {**RECEIPT_A_SUCCESS["evidence"],
                                "confirmed": bogus}}
        assert _receipt_errors(receipt), f"accepted confirmed={bogus!r}"


# ---------------------------------------------------------------------------
# Proof 15/16/17: replay / idempotency fails closed
# ---------------------------------------------------------------------------


def test_duplicate_promotion_id_fails(tmp_path):
    duplicate = {**PROMOTION_A, "candidate_id": CANDIDATE_C,
                 "resolved_target": TARGET_A,
                 "material_type": "fixture_item_note",
                 "decision_id": DECISION_C["decision_id"],
                 "collision_id": COLLISION_C["collision_id"]}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, duplicate])
    assert promotion_failures, "duplicate promotion_id must fail closed"
    assert any(
        "duplicates" in error for error in _all_errors(promotion_failures)
    )


def test_second_instruction_for_same_candidate_fails(tmp_path):
    duplicate = {**PROMOTION_A,
                 "promotion_id": "promotion:fixture-caravan-map-second"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, duplicate])
    assert promotion_failures
    assert any(
        "already has a promotion instruction" in error
        for error in _all_errors(promotion_failures)
    )


def test_duplicate_receipt_id_fails(tmp_path):
    second = {**RECEIPT_A_SUCCESS, "promotion_id": PROMOTION_B["promotion_id"],
              "candidate_id": CANDIDATE_B, "route": "repository_canon",
              "evidence": {"kind": "repository_commit", "commit": COMMIT,
                           "confirmed": True}}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, PROMOTION_B,
                                     RECEIPT_A_SUCCESS, second])
    assert promotion_failures, "duplicate receipt_id must fail closed"
    assert any(
        "duplicates" in error for error in _all_errors(promotion_failures)
    )


def test_two_success_receipts_for_one_promotion_fail(tmp_path):
    second = {**RECEIPT_A_SUCCESS,
              "receipt_id": "receipt:fixture-caravan-map-success-2"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, RECEIPT_A_SUCCESS, second])
    assert promotion_failures, (
        "more than one success receipt for one promotion must fail closed"
    )
    assert any(
        "more than one success receipt" in error
        for error in _all_errors(promotion_failures)
    )


def test_receipt_must_resolve_its_instruction(tmp_path):
    receipt = {**RECEIPT_A_SUCCESS,
               "promotion_id": "promotion:fixture-ghost"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures
    assert any(
        "does not resolve to a valid promotion instruction" in error
        for error in _all_errors(promotion_failures)
    )


def test_receipt_route_must_match_instruction(tmp_path):
    receipt = {**RECEIPT_A_SUCCESS, "route": "repository_canon",
               "evidence": {"kind": "repository_commit", "commit": COMMIT,
                            "confirmed": True}}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures
    assert any(
        "does not match the promotion instruction route" in error
        for error in _all_errors(promotion_failures)
    )


def test_receipt_candidate_must_match_instruction(tmp_path):
    receipt = {**RECEIPT_A_SUCCESS, "candidate_id": CANDIDATE_B}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[PROMOTION_A, receipt])
    assert promotion_failures
    assert any(
        "does not match promotion instruction candidate" in error
        for error in _all_errors(promotion_failures)
    )


def test_ambiguous_promotion_record_fails_closed(tmp_path):
    both = {**PROMOTION_A, **RECEIPT_A_SUCCESS}
    neither = {"foo": "bar"}
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[both, neither])
    assert promotion_failures


@pytest.mark.parametrize("bad_record", [
    ["not", "an", "object"],
    "not-an-object",
    7,
    True,
    None,
])
def test_non_object_promotion_record_fails_closed(tmp_path, bad_record):
    *_, promotion_failures = _set_errors(
        tmp_path, promotion_records=[bad_record])
    assert promotion_failures


# ---------------------------------------------------------------------------
# Proof 18: source/provenance lineage survives and cannot be replaced
# ---------------------------------------------------------------------------


def test_instruction_rejects_duplicated_source_or_provenance():
    for field in ("source", "provenance", "material", "status", "canon"):
        instruction = {**PROMOTION_A, field: "whatever"}
        assert _instruction_errors(instruction), (
            f"instruction must not duplicate {field!r}; lineage is by reference"
        )


def test_source_provenance_lineage_recoverable_via_candidate_id():
    assert CLASSIFIED_A["source"]["reference"].startswith("example-")
    assert CLASSIFIED_A["provenance"]["classification"] == "official"
    assert "source" not in PROMOTION_A
    assert "provenance" not in PROMOTION_A
    assert PROMOTION_A["candidate_id"] == CLASSIFIED_A["candidate_id"]


# ---------------------------------------------------------------------------
# Proof 19: validation never mutates CI-01/02/02.1/03/CI-04 inputs
# ---------------------------------------------------------------------------


def test_validation_does_not_mutate_any_input(tmp_path):
    candidate_paths = _write_batch(tmp_path, CANDIDATES, subdir="candidates")
    decision_paths = _write_batch(tmp_path, DECISIONS, subdir="decisions")
    material_paths = _write_batch(tmp_path, MATERIALS, subdir="material")
    collision_paths = _write_batch(tmp_path, COLLISIONS, subdir="collisions")
    promotion_paths = _write_batch(tmp_path, PROMOTIONS, subdir="promotions")
    all_paths = (*candidate_paths, *decision_paths, *material_paths,
                 *collision_paths, *promotion_paths)
    before = {path: path.read_bytes() for path in all_paths}
    listing_before = sorted(p.name for p in tmp_path.rglob("*"))

    failures = validate_intake_promotions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
        promotion_paths,
    )
    assert all(not f for f in failures)

    after = {path: path.read_bytes() for path in all_paths}
    assert after == before, "validation must never rewrite input bytes"
    assert sorted(p.name for p in tmp_path.rglob("*")) == listing_before, (
        "validation must never create or write files"
    )


# ---------------------------------------------------------------------------
# Proof 20: all four prior CI schemas remain unchanged
# ---------------------------------------------------------------------------


def test_prior_ci_schemas_remain_unchanged():
    candidate_schema = json.loads(
        CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert candidate_schema["required"] == [
        "candidate_id", "summary", "status", "source"]
    assert candidate_schema["properties"]["status"]["enum"] == [
        "extracted", "classified"]
    assert candidate_schema["additionalProperties"] is False

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

    collision_schema = json.loads(
        COLLISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert collision_schema["required"] == [
        "collision_id", "candidate_id", "observation", "result", "reason"]
    assert collision_schema["properties"]["result"]["enum"] == [
        "clear", "duplicate", "stale", "conflict", "unresolved"]
    assert collision_schema["additionalProperties"] is False


def test_upstream_contract_sets_still_validate(tmp_path):
    candidate_paths = _write_batch(tmp_path, CANDIDATES, subdir="candidates")
    assert validate_intake_candidates.validate_paths(candidate_paths) == {}

    decision_paths = _write_batch(tmp_path, DECISIONS, subdir="decisions2")
    candidate_failures, decision_failures = (
        validate_intake_decisions.validate_paths(candidate_paths, decision_paths)
    )
    assert candidate_failures == {} and decision_failures == {}

    material_paths = _write_batch(tmp_path, MATERIALS, subdir="material2")
    candidate_failures, material_failures = (
        validate_intake_candidate_material.validate_paths(
            candidate_paths, material_paths)
    )
    assert candidate_failures == {} and material_failures == {}


# ---------------------------------------------------------------------------
# Proof 21: no raw SQL/Git/runtime-published direct-write mechanism
# ---------------------------------------------------------------------------


def test_validator_introduces_no_direct_write_mechanism():
    source = (ROOT / "scripts" / "validate_intake_promotions.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= ALLOWED_IMPORTS, (
        f"CI-04 validator must not import write/network machinery: "
        f"{imported - ALLOWED_IMPORTS}"
    )
    for forbidden in ("subprocess", "psycopg2", "sqlalchemy", "socket",
                      "requests", "urllib", "shutil", "os.system"):
        assert forbidden not in source, (
            f"CI-04 validator must not reference {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Proof 22 + P1 gate: dispatch only after full validation, receipt validated
# ---------------------------------------------------------------------------


def test_dispatch_promotion_delegates_to_registered_adapter(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    receipt = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)
    assert receipt == RECEIPT_A_SUCCESS
    assert receipt is not RECEIPT_A_SUCCESS
    assert adapter.calls == 1
    assert _receipt_errors(receipt) == []


def test_dispatch_promotion_requires_validated_context(tmp_path):
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, None)
    assert adapter.calls == 0


def test_manual_or_forged_context_cannot_authorize_dispatch():
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.PromotionContext(
            {CANDIDATE_A}, {CANDIDATE_A: "classified"},
            {CANDIDATE_A: "approved"},
            {DECISION_A["decision_id"]: DECISION_A},
            {CANDIDATE_A: MATERIAL_A},
            {COLLISION_A["collision_id"]: COLLISION_A})
    forged = object.__new__(validate_intake_promotions.PromotionContext)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, forged)
    assert adapter.calls == 0


def test_context_is_immutable_and_instruction_snapshot_cannot_be_swapped(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    for field, value in (("approved", {CANDIDATE_D: "approved"}),
                         ("candidate_status", {CANDIDATE_D: "classified"}),
                         ("_proof", ()), ("__dict__", {})):
        with pytest.raises((AttributeError, TypeError,
                            validate_intake_promotions.PromotionError)):
            object.__setattr__(context, field, value)
    with pytest.raises(validate_intake_promotions.PromotionError):
        context.approved = {CANDIDATE_D: "approved"}
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {**PROMOTION_A, "promotion_id": "promotion:fixture-swapped"},
            {"runtime_save": adapter}, context)
    assert adapter.calls == 0
    assert validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context) == RECEIPT_A_SUCCESS


def test_factory_context_snapshots_upstream_and_instruction(tmp_path):
    instruction = {**PROMOTION_A, "resolved_target": dict(TARGET_A)}
    context = _context(tmp_path, instruction=instruction)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    instruction["resolved_target"]["reference"] = "fixture-other-owner"
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            instruction, {"runtime_save": adapter}, context)
    assert adapter.calls == 0
    assert validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context) == RECEIPT_A_SUCCESS


def test_dispatch_promotion_unknown_route_fails_closed(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {**PROMOTION_A, "route": "direct_sql"}, {"direct_sql": adapter},
            context)
    assert adapter.calls == 0


def test_dispatch_promotion_missing_adapter_fails_closed(tmp_path):
    context = _context(tmp_path)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {}, context)


def test_dispatch_promotion_adapter_route_mismatch_fails_closed(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("repository_canon", RECEIPT_A_SUCCESS)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)
    assert adapter.calls == 0


def test_synthetic_adapters_cover_both_routes_without_writing(tmp_path):
    context = _context(tmp_path)
    context_b = _context(tmp_path, instruction=PROMOTION_B)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    runtime = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    repository = _SyntheticAdapter("repository_canon", RECEIPT_B_SUCCESS)
    adapters = {"runtime_save": runtime, "repository_canon": repository}

    receipt_a = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, adapters, context)
    receipt_b = validate_intake_promotions.dispatch_promotion(
        PROMOTION_B, adapters, context_b)

    assert _receipt_errors(receipt_a) == []
    assert _receipt_errors(receipt_b) == []
    assert sorted(p.name for p in tmp_path.rglob("*")) == before, (
        "the adapter boundary must not write anything itself"
    )


def test_raw_unvalidated_instruction_cannot_dispatch(tmp_path):
    context = _context(tmp_path)
    spy = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)

    # A raw partial record is not a validated instruction.
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {"candidate_id": CANDIDATE_A, "route": "runtime_save"},
            {"runtime_save": spy}, context)

    # A mutated instruction no longer matches the factory's validated proof.
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {**PROMOTION_A, "decision_id": "decision:fixture-ghost"},
            {"runtime_save": spy}, context)

    assert spy.calls == 0, "raw/unvalidated instructions must not reach an adapter"


def test_rejected_candidate_cannot_reach_adapter(tmp_path):
    context = _context(tmp_path)
    spy = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    instruction = {
        **PROMOTION_A,
        "candidate_id": CANDIDATE_D,
        "decision_id": DECISION_D_REJECTED["decision_id"],
    }
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            instruction, {"runtime_save": spy}, context)
    with pytest.raises(validate_intake_promotions.PromotionError):
        _context(tmp_path, instruction=instruction)
    assert spy.calls == 0


def test_non_clear_collision_cannot_reach_adapter(tmp_path):
    conflict = _collision(CANDIDATE_A, MATERIAL_A, _obs(
        "present", target=TARGET_A,
        current_material="Fixture material: a different established story "
                         "(synthetic)."))
    assert conflict["result"] == "conflict"
    spy = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    context = _context(tmp_path)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {**PROMOTION_A, "collision_id": "collision:fixture-other-check"},
            {"runtime_save": spy}, context)
    with pytest.raises(validate_intake_promotions.PromotionError):
        _context(tmp_path, collision_records=[conflict, COLLISION_B, COLLISION_C])
    assert spy.calls == 0


def test_rerouted_target_cannot_reach_adapter(tmp_path):
    context = _context(tmp_path)
    spy = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            {**PROMOTION_A, "resolved_target": TARGET_OTHER},
            {"runtime_save": spy}, context)
    assert spy.calls == 0


def test_invalid_success_receipt_cannot_be_returned_as_success(tmp_path):
    context = _context(tmp_path)
    bad_receipt = {k: v for k, v in RECEIPT_A_SUCCESS.items() if k != "evidence"}
    adapter = _SyntheticAdapter("runtime_save", bad_receipt)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)
    assert adapter.calls == 1, "the adapter ran; its unread-back success was refused"


def test_receipt_must_match_exact_promotion_even_with_same_candidate_route(tmp_path):
    context = _context(tmp_path)
    wrong = {**RECEIPT_A_SUCCESS,
             "promotion_id": "promotion:fixture-another-promotion"}
    adapter = _SyntheticAdapter("runtime_save", wrong)
    with pytest.raises(validate_intake_promotions.PromotionError,
                       match="promotion_id.*does not match"):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)
    assert adapter.calls == 1
    assert wrong["candidate_id"] == PROMOTION_A["candidate_id"]
    assert wrong["route"] == PROMOTION_A["route"]


def test_receipt_exact_promotion_candidate_route_and_readback_pass(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    receipt = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)
    assert (receipt["promotion_id"], receipt["candidate_id"], receipt["route"]) == (
        PROMOTION_A["promotion_id"], PROMOTION_A["candidate_id"],
        PROMOTION_A["route"])
    assert receipt["evidence"] == RECEIPT_A_SUCCESS["evidence"]


@pytest.mark.parametrize("forged", [
    None,
    "not-a-receipt",
    {**RECEIPT_A_SUCCESS, "route": "repository_canon",
     "evidence": {"kind": "repository_commit", "commit": COMMIT,
                  "confirmed": True}},
    {**RECEIPT_A_SUCCESS,
     "evidence": {**RECEIPT_A_SUCCESS["evidence"], "confirmed": False}},
    {**RECEIPT_A_SUCCESS, "candidate_id": CANDIDATE_B},
    {**RECEIPT_A_SUCCESS,
     "evidence": {"kind": "runtime_publication", "generation": 4,
                  "git_ref": GIT_REF}},
])
def test_forged_or_mismatched_receipt_fails_closed(tmp_path, forged):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", forged)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)


def test_valid_instruction_and_valid_receipt_succeeds(tmp_path):
    context = _context(tmp_path)
    adapter = _SyntheticAdapter("runtime_save", RECEIPT_A_SUCCESS)
    receipt = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)
    assert receipt["outcome"] == "success"
    assert receipt["evidence"]["confirmed"] is True
    assert adapter.calls == 1


# ---------------------------------------------------------------------------
# Round 3 P1: freeze the adapter-returned receipt before validating it
#
# The adapter still owns the object it returns. CI-04 must snapshot it to
# canonical bytes immediately, validate that exact frozen snapshot, and expose
# that same snapshot -- never validate the live adapter-owned object and then
# read or copy it again.
# ---------------------------------------------------------------------------


class _GunReceipt(dict):
    """Adapter-owned mapping that mutates itself when validation reads a key.

    Models an adapter that still holds the object it returned and keeps
    mutating it while CI-04 processes the result. If CI-04 validated this live
    object and then re-read it, the mutation would escape into the exposed
    receipt; snapshotting first means it cannot.
    """

    def __init__(self, valid, trigger_key, forged):
        super().__init__(valid)
        self._trigger_key = trigger_key
        self._forged = forged
        self.fired = False

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if not self.fired and key == self._trigger_key:
            self.fired = True
            for forged_key, forged_value in self._forged.items():
                super().__setitem__(forged_key, forged_value)
        return value


def test_adapter_owned_receipt_mutating_on_read_cannot_leak_into_exposed_result(tmp_path):
    context = _context(tmp_path)
    live = _GunReceipt(RECEIPT_A_SUCCESS, "outcome",
                       {"promotion_id": "promotion:fixture-forged"})
    adapter = _SyntheticAdapter("runtime_save", live)

    exposed = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)

    assert exposed == RECEIPT_A_SUCCESS
    assert exposed is not live
    assert exposed["promotion_id"] == PROMOTION_A["promotion_id"]


def test_exposed_receipt_is_an_independent_plain_dict_snapshot(tmp_path):
    context = _context(tmp_path)
    live = json.loads(json.dumps(RECEIPT_A_SUCCESS))
    adapter = _SyntheticAdapter("runtime_save", live)

    exposed = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)

    assert type(exposed) is dict
    assert exposed is not live
    assert exposed == RECEIPT_A_SUCCESS

    live["promotion_id"] = "promotion:fixture-forged"
    assert exposed["promotion_id"] == PROMOTION_A["promotion_id"]


@pytest.mark.parametrize("field,value", [
    ("promotion_id", "promotion:fixture-forged"),
    ("candidate_id", CANDIDATE_B),
    ("route", "repository_canon"),
    ("outcome", "failure"),
    ("evidence", {"kind": "runtime_publication", "generation": 99,
                  "git_ref": OTHER_GIT_REF, "confirmed": True}),
])
def test_post_return_field_mutation_cannot_change_exposed_snapshot(
        tmp_path, field, value):
    context = _context(tmp_path)
    live = json.loads(json.dumps(RECEIPT_A_SUCCESS))
    adapter = _SyntheticAdapter("runtime_save", live)

    exposed = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)
    frozen = json.loads(json.dumps(exposed))

    live[field] = value

    assert exposed == frozen
    assert exposed == RECEIPT_A_SUCCESS


def test_post_return_nested_evidence_mutation_cannot_change_exposed_snapshot(tmp_path):
    context = _context(tmp_path)
    live = json.loads(json.dumps(RECEIPT_A_SUCCESS))
    adapter = _SyntheticAdapter("runtime_save", live)

    exposed = validate_intake_promotions.dispatch_promotion(
        PROMOTION_A, {"runtime_save": adapter}, context)

    live["evidence"]["generation"] = 99
    live["evidence"]["git_ref"] = OTHER_GIT_REF
    live["evidence"]["confirmed"] = False

    assert exposed["evidence"]["generation"] == 4
    assert exposed["evidence"]["git_ref"] == GIT_REF
    assert exposed["evidence"]["confirmed"] is True


def test_unserializable_adapter_receipt_fails_closed(tmp_path):
    context = _context(tmp_path)
    unserializable = {**RECEIPT_A_SUCCESS, "unserializable": object()}
    adapter = _SyntheticAdapter("runtime_save", unserializable)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)
    assert adapter.calls == 1


def test_nan_adapter_receipt_fails_closed(tmp_path):
    context = _context(tmp_path)
    nan_receipt = {**RECEIPT_A_SUCCESS, "note": float("nan")}
    adapter = _SyntheticAdapter("runtime_save", nan_receipt)
    with pytest.raises(validate_intake_promotions.PromotionError):
        validate_intake_promotions.dispatch_promotion(
            PROMOTION_A, {"runtime_save": adapter}, context)


# ---------------------------------------------------------------------------
# Fixture hygiene
# ---------------------------------------------------------------------------


def test_inline_fixtures_contain_no_real_rhc_campaign_facts():
    for record in (*CANDIDATES, *MATERIALS, *DECISIONS, *COLLISIONS,
                   *PROMOTIONS):
        if "summary" in record:
            assert "fixture" in record["summary"].lower(), record["candidate_id"]
        for text in _all_strings(record):
            for prefix in REAL_CAMPAIGN_PATH_PREFIXES:
                assert prefix not in text, (
                    f"fixture references real campaign path {prefix!r} in {text!r}"
                )
