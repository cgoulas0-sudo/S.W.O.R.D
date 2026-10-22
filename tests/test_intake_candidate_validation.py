"""CI-01 Canon Intake candidate contract proof.

Covers stable candidate identity, required and inspectable source attachment,
exact HB-01 provenance vocabulary reuse, the two-state pre-canon lifecycle,
and the structural impossibility of approval/publication states.

Per the CI-01 Surface Budget, all fixtures are inline in-memory records: no
external fixture directory is authorized for this patch, and no real RHC
campaign record is read, written, or referenced.
"""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import validate_intake_candidates  # noqa: E402

CLASSIFICATIONS = ["official", "homebrew", "adapted", "unknown"]

EXTRACTED_BASE = {
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


def _classified(classification):
    return {
        **EXTRACTED_BASE,
        "candidate_id": f"candidate:fixture-{classification}-candidate",
        "summary": f"Fixture candidate classified as {classification} (synthetic).",
        "status": "classified",
        "provenance": {"classification": classification},
    }


CLASSIFIED_BASES = {c: _classified(c) for c in CLASSIFICATIONS}

ALL_VALID = [EXTRACTED_BASE, *CLASSIFIED_BASES.values()]

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

INVALID_CLASSIFICATIONS = [
    "canon",
    "Official",
    "OFFICIAL",
    " official",
    "official ",
    "official\n",
    "homebrew mechanic",
    "unofficial",
    "",
    "   ",
    None,
    1,
    True,
    [],
    {},
]

MALFORMED_PROVENANCE = [
    "official",
    None,
    ["official"],
    {},
    {"Classification": "official"},
    {"classification": "official", "note": ""},
    {"classification": "official", "note": "   "},
    {"classification": "official", "note": "From a source book."},
    {"classification": "official", "source_url": "https://example.invalid"},
]

ILLEGAL_FINAL_STATES = [
    "approved",
    "APPROVED",
    "published",
    "canon",
    "accepted",
    "accepted_as_truth",
    "ready_for_review",
    "",
    "   ",
    "extracted ",
    " classified",
    None,
    1,
    True,
    [],
    {},
]


def _errors(record):
    schema = validate_intake_candidates.load_schema()
    return validate_intake_candidates.validate_record(record, schema)


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
        validate_intake_candidates.load_schema()
    )


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_classified_candidate_with_each_hb01_classification_passes(classification):
    assert _errors(CLASSIFIED_BASES[classification]) == []


def test_extracted_candidate_passes_without_provenance():
    assert _errors(EXTRACTED_BASE) == []


def test_classified_candidate_requires_explicit_provenance():
    record = {**EXTRACTED_BASE, "candidate_id": "candidate:fixture-no-prov",
              "status": "classified"}
    assert _errors(record), "classified without provenance must fail"


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_extracted_candidate_rejects_any_provenance(classification):
    record = {**EXTRACTED_BASE, "provenance": {"classification": classification}}
    assert _errors(record), "extracted must not carry a classification yet"


@pytest.mark.parametrize("bad_classification", INVALID_CLASSIFICATIONS)
def test_free_form_or_invalid_classification_fails(bad_classification):
    record = _classified("official")
    record["provenance"] = {"classification": bad_classification}
    errors = _errors(record)
    assert errors, f"accepted invalid classification {bad_classification!r}"
    assert any(
        error.startswith("provenance") for error in errors
    ), f"rejected {bad_classification!r} but not at provenance: {errors}"


@pytest.mark.parametrize("bad_provenance", MALFORMED_PROVENANCE)
def test_malformed_provenance_containers_fail(bad_provenance):
    record = _classified("official")
    record["provenance"] = bad_provenance
    assert _errors(record), f"accepted malformed provenance {bad_provenance!r}"


def test_provenance_reuses_the_exact_hb01_vocabulary_and_shape():
    entity_schema = json.loads(
        (ROOT / "schemas" / "entity.schema.json").read_text(encoding="utf-8")
    )
    intake_schema = validate_intake_candidates.load_schema()
    entity_prov = entity_schema["properties"]["provenance"]
    intake_prov = intake_schema["properties"]["provenance"]
    assert intake_prov["type"] == "object"
    assert intake_prov["additionalProperties"] is False
    assert intake_prov["required"] == ["classification"]
    assert (
        intake_prov["properties"]["classification"]
        == entity_prov["properties"]["classification"]
    ), "Canon Intake must reuse the HB-01 classification enum exactly"


@pytest.mark.parametrize(
    "bad_id",
    ["", "   ", "candidate:", "candidate:Bad", "candidate:has space",
     "candidate:ok\n", "candidate:ok\r", "candidate:ok ", "candidate:-x",
     "CANDIDATE:ok", "intake:ok", "H01", "item:vampire", "candidate:ok/extra"],
)
def test_candidate_id_grammar_is_strict(bad_id):
    assert _errors({**EXTRACTED_BASE, "candidate_id": bad_id}), bad_id


def test_candidate_id_grammar_accepts_valid_slugs():
    for good_id in ("candidate:a", "candidate:fixture-inn-rumor", "candidate:abc-123"):
        assert _errors({**EXTRACTED_BASE, "candidate_id": good_id}) == [], good_id


def test_missing_candidate_id_fails():
    record = {k: v for k, v in EXTRACTED_BASE.items() if k != "candidate_id"}
    assert _errors(record)


def test_missing_source_attachment_fails():
    record = {k: v for k, v in EXTRACTED_BASE.items() if k != "source"}
    assert _errors(record)


def test_source_must_be_an_object():
    for bad_source in ("book", None, [], ["book"], 1, True):
        assert _errors({**EXTRACTED_BASE, "source": bad_source}), bad_source


@pytest.mark.parametrize("field", ["kind", "reference"])
@pytest.mark.parametrize("bad_value", [None, "", "   ", 1, True, [], {}])
def test_required_source_identity_fails_when_missing_or_blank(field, bad_value):
    source = {**EXTRACTED_BASE["source"], field: bad_value}
    errors = _errors({**EXTRACTED_BASE, "source": source})
    assert errors, f"source.{field} accepted {bad_value!r}"
    assert any(
        error.startswith(f"source.{field}") for error in errors
    ), f"rejected {bad_value!r} but not at source.{field}: {errors}"


@pytest.mark.parametrize("bad_value", ["", "   ", None, 1, True, [], {}])
def test_optional_source_fields_reject_blank_only_values(bad_value):
    for field in ("locator", "origin", "label"):
        source = {**EXTRACTED_BASE["source"], field: bad_value}
        assert _errors({**EXTRACTED_BASE, "source": source}), (field, bad_value)


@pytest.mark.parametrize("bad_status", ILLEGAL_FINAL_STATES)
def test_approval_publication_and_canon_like_states_fail(bad_status):
    record = {**_classified("official"), "status": bad_status}
    errors = _errors(record)
    assert errors, f"accepted illegal final state {bad_status!r}"
    assert any(
        error.startswith("status") for error in errors
    ), f"rejected {bad_status!r} but not at status: {errors}"


def test_no_approval_or_publication_state_exists_in_the_enum():
    schema = validate_intake_candidates.load_schema()
    enum = schema["properties"]["status"]["enum"]
    assert enum == ["extracted", "classified"]
    for forbidden in ("approved", "published", "canon", "accepted_as_truth"):
        assert forbidden not in enum


@pytest.mark.parametrize(
    "extra_field",
    ["canon_status", "visibility", "payload", "proposed_target",
     "approval", "source_url", "notes"],
)
def test_unknown_extra_fields_fail_at_top_level(extra_field):
    record = {**_classified("official"), extra_field: "whatever"}
    assert _errors(record), f"accepted invented {extra_field!r}"


def test_unknown_extra_fields_fail_inside_source():
    record = _classified("official")
    record["source"] = {**record["source"], "url": "https://example.invalid"}
    assert _errors(record), "accepted an invented source field"


def test_duplicate_candidate_id_rejected_across_batch(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(EXTRACTED_BASE, indent=2) + "\n", encoding="utf-8")
    b.write_text(
        json.dumps(
            {**EXTRACTED_BASE, "summary": "Different fixture candidate (synthetic)."},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    errors = validate_intake_candidates.validate_paths([a, b])
    assert set(errors) == {b}
    assert any("duplicates" in error for error in errors[b])


def test_inline_fixtures_contain_no_real_rhc_campaign_facts():
    for record in ALL_VALID:
        assert "fixture" in record["summary"].lower(), record["candidate_id"]
        for text in _all_strings(record):
            for prefix in REAL_CAMPAIGN_PATH_PREFIXES:
                assert prefix not in text, (
                    f"{record['candidate_id']} references real campaign path "
                    f"{prefix!r} in {text!r}"
                )


def test_real_rhc_item_canary_is_not_a_candidate():
    schema = validate_intake_candidates.load_schema()
    record = {
        **EXTRACTED_BASE,
        "candidate_id": "item:vampire",
        "source": {"kind": "fixture", "reference": "fixture-only"},
    }
    assert validate_intake_candidates.validate_record(record, schema)
