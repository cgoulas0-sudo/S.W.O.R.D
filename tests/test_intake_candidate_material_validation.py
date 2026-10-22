"""CI-02.1 Canon Intake candidate material proof.

Covers the sidecar material envelope added by CI-02.1: one non-canon,
non-runtime envelope per CI-01 candidate carrying the actual material plus
enough proposed-target intent and base-publication context for the later
CI-03 collision/re-import checks, while source/provenance stay owned by the
referenced CI-01 candidate.

Per the CI-02.1 Surface Budget, all fixtures are inline in-memory records or
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
import validate_intake_decisions  # noqa: E402

CANDIDATE_SCHEMA_PATH = ROOT / "schemas" / "intake_candidate.schema.json"
DECISION_SCHEMA_PATH = ROOT / "schemas" / "intake_decision.schema.json"

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

CANDIDATES = [
    EXTRACTED_CANDIDATE,
    CLASSIFIED_CANDIDATE,
    SECOND_CLASSIFIED_CANDIDATE,
]

MATERIAL_BASE = {
    "candidate_id": "candidate:fixture-inn-rumor",
    "material_type": "fixture_lore_text",
    "material": "Fixture material: the rumor claims a caravan vanished near a "
                "fixture crossroads (synthetic).",
}

FULL_ENVELOPE = {
    **MATERIAL_BASE,
    "proposed_target": {
        "kind": "npc",
        "reference": "fixture-npc-innkeeper",
        "label": "Fixture proposed target label",
    },
    "base_publication": {
        "generation": 1,
        "git_ref": "0123456789abcdef0123456789abcdef01234567",
    },
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


def _errors(record):
    schema = validate_intake_candidate_material.load_schema()
    return validate_intake_candidate_material.validate_record(record, schema)


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _write_batch(tmp_path, records, subdir):
    directory = tmp_path / subdir
    directory.mkdir(exist_ok=True)
    return [_write(directory, f"{index:02d}.json", record)
            for index, record in enumerate(records, start=1)]


def _set(tmp_path, candidate_records=None, material_records=None):
    """Write one candidate batch + one material set; return both path lists."""
    candidate_paths = _write_batch(
        tmp_path, CANDIDATES if candidate_records is None else candidate_records,
        subdir="candidates",
    )
    material_paths = _write_batch(
        tmp_path, [MATERIAL_BASE] if material_records is None else material_records,
        subdir="material",
    )
    return candidate_paths, material_paths


def _set_errors(tmp_path, candidate_records=None, material_records=None):
    candidate_paths, material_paths = _set(
        tmp_path, candidate_records, material_records
    )
    candidate_failures, material_failures = (
        validate_intake_candidate_material.validate_paths(
            candidate_paths, material_paths
        )
    )
    return candidate_failures, material_failures


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(
        validate_intake_candidate_material.load_schema()
    )


def test_valid_material_envelope_resolves_to_existing_candidate(tmp_path):
    candidate_failures, material_failures = _set_errors(tmp_path)
    assert candidate_failures == {}
    assert material_failures == {}


def test_unknown_candidate_id_fails(tmp_path):
    _, material_failures = _set_errors(tmp_path, material_records=[
        {**MATERIAL_BASE, "candidate_id": "candidate:fixture-unknown-target"},
    ])
    assert material_failures, "material against an unknown candidate must fail"
    assert any(
        "does not resolve" in error
        for error in next(iter(material_failures.values()))
    )


def test_candidate_batch_must_be_valid_before_material_applies(tmp_path):
    broken = [
        {**CLASSIFIED_CANDIDATE, "provenance": None},
        *CANDIDATES[1:],
    ]
    candidate_failures, material_failures = _set_errors(
        tmp_path, candidate_records=broken
    )
    assert candidate_failures, "invalid candidate batch must fail"
    assert material_failures, "material must not consume an invalid candidate batch"


def test_duplicate_material_envelope_for_same_candidate_fails(tmp_path):
    _, material_failures = _set_errors(tmp_path, material_records=[
        {**MATERIAL_BASE},
        {**MATERIAL_BASE, "material_type": "fixture_alt_text",
         "material": "Fixture material: a different excerpt for the same "
                     "candidate (synthetic)."},
    ])
    assert material_failures, "duplicate material envelope must fail closed"
    assert any(
        "already has a material envelope" in error
        for error in next(iter(material_failures.values()))
    )


def test_material_and_material_type_are_required():
    record = {k: v for k, v in MATERIAL_BASE.items() if k != "material"}
    errors = _errors(record)
    assert any(
        error.startswith("material") or "'material' is a required property" in error
        for error in errors
    ), errors

    record = {k: v for k, v in MATERIAL_BASE.items() if k != "material_type"}
    errors = _errors(record)
    assert any(
        error.startswith("material_type")
        or "'material_type' is a required property" in error
        for error in errors
    ), errors


@pytest.mark.parametrize("bad_material", ["", "   ", "\n", "\t", None, 1, True, [], {}])
def test_blank_or_non_string_material_fails(bad_material):
    record = {**MATERIAL_BASE, "material": bad_material}
    errors = _errors(record)
    assert errors, f"material accepted {bad_material!r}"
    assert any(
        error.startswith("material") for error in errors
    ), f"rejected {bad_material!r} but not at material: {errors}"


@pytest.mark.parametrize(
    "bad_material_type",
    ["", "   ", "\n", None, 1, True, [], {}],
)
def test_blank_or_non_string_material_type_fails(bad_material_type):
    record = {**MATERIAL_BASE, "material_type": bad_material_type}
    errors = _errors(record)
    assert errors, f"material_type accepted {bad_material_type!r}"
    assert any(
        error.startswith("material_type") for error in errors
    ), f"rejected {bad_material_type!r} but not at material_type: {errors}"


def test_proposed_target_can_be_represented_when_known():
    record = {**MATERIAL_BASE, "proposed_target": FULL_ENVELOPE["proposed_target"]}
    assert _errors(record) == []


def test_target_may_remain_explicitly_absent_without_inference():
    assert _errors(MATERIAL_BASE) == []


@pytest.mark.parametrize("bad_target", [
    "npc",
    None,
    1,
    True,
    [],
    {},
    {"kind": "npc"},
    {"reference": "fixture-npc-innkeeper"},
    {"kind": "", "reference": "fixture-npc-innkeeper"},
    {"kind": "   ", "reference": "fixture-npc-innkeeper"},
    {"kind": "npc", "reference": ""},
    {"kind": "npc", "reference": None},
    {"kind": "npc", "reference": "fixture-npc-innkeeper", "label": ""},
    {"kind": "npc", "reference": "fixture-npc-innkeeper", "owner_status": "reconciled"},
])
def test_malformed_proposed_target_fails(bad_target):
    record = {**MATERIAL_BASE, "proposed_target": bad_target}
    errors = _errors(record)
    assert errors, f"proposed_target accepted {bad_target!r}"
    assert any(
        error.startswith("proposed_target") for error in errors
    ), f"rejected {bad_target!r} but not at proposed_target: {errors}"


@pytest.mark.parametrize("base_publication", [
    {"generation": 0},
    {"generation": 1},
    {"generation": 42},
    {"git_ref": "0123456789abcdef0123456789abcdef01234567"},
    {"generation": 7, "git_ref": "0123456789abcdef0123456789abcdef01234567"},
])
def test_base_publication_can_be_represented_when_known(base_publication):
    record = {**MATERIAL_BASE, "base_publication": base_publication}
    assert _errors(record) == [], base_publication


@pytest.mark.parametrize("bad_generation", ["1", 1.5, -1, True, False, None, [], {}])
def test_malformed_base_generation_fails(bad_generation):
    record = {**MATERIAL_BASE,
              "base_publication": {"generation": bad_generation}}
    errors = _errors(record)
    assert errors, f"base_publication.generation accepted {bad_generation!r}"
    assert any(
        error.startswith("base_publication") for error in errors
    ), f"rejected {bad_generation!r} but not at base_publication: {errors}"


@pytest.mark.parametrize("bad_git_ref", [
    "main",
    "runtime-published",
    "0123456789abcdef0123456789abcdef0123456",      # 39 chars
    "0123456789abcdef0123456789abcdef012345677",     # 41 chars
    "0123456789ABCDEF0123456789abcdef01234567",      # uppercase hex
    "0123456789ghijkl0123456789abcdef01234567",      # non-hex characters
    "0x0123456789abcdef0123456789abcdef0123456",     # prefix
    "",
    "   ",
    None,
    1,
    True,
    [],
    {},
])
def test_malformed_base_git_ref_fails(bad_git_ref):
    record = {**MATERIAL_BASE, "base_publication": {"git_ref": bad_git_ref}}
    errors = _errors(record)
    assert errors, f"base_publication.git_ref accepted {bad_git_ref!r}"
    assert any(
        error.startswith("base_publication") for error in errors
    ), f"rejected {bad_git_ref!r} but not at base_publication: {errors}"


def test_empty_base_publication_pin_fails():
    record = {**MATERIAL_BASE, "base_publication": {}}
    errors = _errors(record)
    assert errors, "an empty base_publication pin object must fail closed"


def test_source_and_provenance_are_not_duplicated_into_the_envelope():
    for extra in ("source", "provenance"):
        record = {**MATERIAL_BASE, extra: {"kind": "fixture", "reference": "fixture"}}
        errors = _errors(record)
        assert errors, f"material envelope accepted duplicated {extra!r}"


def test_no_approved_rejected_canon_or_published_state_exists():
    schema = validate_intake_candidate_material.load_schema()
    properties = schema["properties"]
    for forbidden in ("status", "outcome", "approval", "canon_status",
                      "published", "decision"):
        assert forbidden not in properties, forbidden
    record = {**MATERIAL_BASE, "outcome": "approved"}
    assert _errors(record), "material envelope must never carry a decision outcome"


def test_ci01_candidate_schema_remains_unchanged():
    schema = json.loads(CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert sorted(schema["properties"]) == [
        "candidate_id", "provenance", "source", "status", "summary",
    ]
    assert schema["required"] == ["candidate_id", "summary", "status", "source"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["status"]["enum"] == ["extracted", "classified"]


def test_ci02_decision_schema_remains_unchanged():
    schema = json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert sorted(schema["properties"]) == [
        "authority", "batch_label", "candidate_id", "decided_by", "decision_id",
        "note", "outcome",
    ]
    assert schema["required"] == [
        "decision_id", "candidate_id", "outcome", "authority", "decided_by",
    ]
    assert schema["additionalProperties"] is False


def test_validation_does_not_mutate_candidates_or_material(tmp_path):
    candidate_paths, material_paths = _set(tmp_path)
    before = {path: path.read_bytes() for path in (*candidate_paths, *material_paths)}
    listing_before = sorted(p.name for p in tmp_path.rglob("*"))

    candidate_failures, material_failures = (
        validate_intake_candidate_material.validate_paths(
            candidate_paths, material_paths
        )
    )
    assert candidate_failures == {}
    assert material_failures == {}

    after = {path: path.read_bytes() for path in (*candidate_paths, *material_paths)}
    assert after == before, "validation must never rewrite candidate/material bytes"
    assert sorted(p.name for p in tmp_path.rglob("*")) == listing_before, (
        "validation must never create or write files"
    )


@pytest.mark.parametrize(
    "extra_field",
    ["status", "outcome", "canon_status", "published", "approval", "source",
     "provenance", "payload", "visibility", "group_decision"],
)
def test_unknown_extra_fields_fail_at_top_level(extra_field):
    record = {**FULL_ENVELOPE, extra_field: "whatever"}
    assert _errors(record), f"accepted invented {extra_field!r}"


def test_unknown_extra_fields_fail_inside_optional_objects():
    record = {
        **MATERIAL_BASE,
        "proposed_target": {
            **FULL_ENVELOPE["proposed_target"],
            "owner_status": "reconciled",
        },
    }
    assert _errors(record), "accepted an invented proposed_target field"

    record = {
        **MATERIAL_BASE,
        "base_publication": {
            **FULL_ENVELOPE["base_publication"],
            "branch": "runtime-published",
        },
    }
    assert _errors(record), "accepted an invented base_publication field"


def test_mixed_candidate_types_and_material_shapes_coexist(tmp_path):
    material_records = [
        MATERIAL_BASE,
        {**MATERIAL_BASE,
         "candidate_id": "candidate:fixture-caravan-map",
         "material_type": "fixture_map_sketch",
         "material": "Fixture material: a torn map sketch excerpt (synthetic).",
         "proposed_target": {
             "kind": "location",
             "reference": "fixture-location-crossroads",
         }},
        {**MATERIAL_BASE,
         "candidate_id": "candidate:fixture-tavern-song",
         "material_type": "fixture_song_fragment",
         "material": "Fixture material: two bars of a tavern song (synthetic).",
         "base_publication": {"generation": 0}},
    ]
    candidate_failures, material_failures = _set_errors(
        tmp_path, material_records=material_records
    )
    assert candidate_failures == {}
    assert material_failures == {}, (
        "mixed candidate types and material shapes must coexist without any "
        "domain-specific payload schema"
    )


def test_material_exists_for_extracted_and_classified_candidates_alike(tmp_path):
    candidate_failures, material_failures = _set_errors(tmp_path, material_records=[
        MATERIAL_BASE,
        {**MATERIAL_BASE, "candidate_id": "candidate:fixture-caravan-map"},
    ])
    assert candidate_failures == {}
    assert material_failures == {}, (
        "material preservation must not invent an eligibility rule: extracted "
        "and classified candidates may both carry material"
    )


@pytest.mark.parametrize(
    "bad_id",
    ["", "   ", "candidate:", "candidate:Bad", "candidate:has space",
     "candidate:-x", "CANDIDATE:ok", "decision:ok", "item:vampire",
     "candidate:ok/extra", None, 1, True, [], {}],
)
def test_candidate_id_grammar_is_strict(bad_id):
    record = {**MATERIAL_BASE, "candidate_id": bad_id}
    errors = _errors(record)
    assert errors, f"accepted candidate_id {bad_id!r}"
    assert any(
        error.startswith("candidate_id") for error in errors
    ), f"rejected {bad_id!r} but not at candidate_id: {errors}"


def test_candidate_id_grammar_accepts_valid_slugs():
    for good_id in ("candidate:a", "candidate:fixture-inn-rumor", "candidate:abc-123"):
        assert _errors({**MATERIAL_BASE, "candidate_id": good_id}) == [], good_id


def test_required_properties_are_exactly_the_owned_contract():
    schema = validate_intake_candidate_material.load_schema()
    assert schema["required"] == ["candidate_id", "material_type", "material"]
    assert schema["additionalProperties"] is False


def test_ci01_and_ci02_contracts_still_validate_their_own_records(tmp_path):
    candidate_paths, _ = _set(tmp_path)
    candidate_failures = validate_intake_candidates.validate_paths(candidate_paths)
    assert candidate_failures == {}, "CI-01 regression must stay green"


ALL_VALID = [EXTRACTED_CANDIDATE, CLASSIFIED_CANDIDATE, MATERIAL_BASE, FULL_ENVELOPE]


def test_inline_fixtures_contain_no_real_rhc_campaign_facts():
    for record in ALL_VALID:
        if "summary" in record:
            assert "fixture" in record["summary"].lower(), record["candidate_id"]
        for text in _all_strings(record):
            for prefix in REAL_CAMPAIGN_PATH_PREFIXES:
                assert prefix not in text, (
                    f"fixture references real campaign path {prefix!r} in {text!r}"
                )
