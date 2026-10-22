"""HB-01 shared provenance classification proof.

Covers the shared provenance contract across all four target surfaces
(entity identity, Hook, Scenario, Encounter): four-state acceptance,
invalid rejection, legacy backward compatibility, cross-schema vocabulary
identity, and proof that provenance is inert logistics metadata with no
effect on identity, lifecycle, or prepared-scene semantics.

No new fixture files are introduced: every record here is an in-memory
dictionary, and no real RHC campaign record is read or written.
"""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import validate_entities  # noqa: E402
import validate_hooks  # noqa: E402
import validate_scenarios_encounters as se  # noqa: E402

CLASSIFICATIONS = ["official", "homebrew", "adapted", "unknown"]

ENTITY_BASE = {
    "entity_id": "item:provenance-proof-item",
    "entity_type": "item",
    "display_name": "Provenance Proof Item (fixture)",
}

HOOK_BASE = {
    "hook_id": "H01",
    "title": "Provenance Proof Hook (fixture)",
    "objective": "Prove optional provenance on Hooks.",
    "status": "active",
    "activation_condition": "Fixture only.",
    "resolution_condition": "Fixture only.",
    "related_entity_ids": [],
}

SCENARIO_BASE = {
    "scenario_id": "S01",
    "title": "Provenance Proof Scenario (fixture)",
    "premise": "Fixture only.",
    "objective": "Prove optional provenance on Scenarios.",
    "trigger_condition": "Fixture only.",
    "primary_hook_id": "H01",
    "related_hook_ids": [],
    "related_entity_ids": [],
}

ENCOUNTER_BASE = {
    "encounter_id": "E01",
    "scenario_id": "S01",
    "title": "Provenance Proof Encounter (fixture)",
    "scene_type": "social",
    "setup": "Fixture only.",
    "immediate_objective": "Prove optional provenance on Encounters.",
    "related_entity_ids": [],
}

SURFACES = {
    "entity": validate_entities.load_schema(),
    "hook": validate_hooks.load_schema(),
    "scenario": se.load_schema(se.SCENARIO_SCHEMA_PATH),
    "encounter": se.load_schema(se.ENCOUNTER_SCHEMA_PATH),
}

BASES = {
    "entity": ENTITY_BASE,
    "hook": HOOK_BASE,
    "scenario": SCENARIO_BASE,
    "encounter": ENCOUNTER_BASE,
}


def _errors(surface, record):
    return validate_entities.validate_record(record, SURFACES[surface])


def _with_provenance(surface, provenance):
    return {**BASES[surface], "provenance": provenance}


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_all_four_target_schemas_share_identical_provenance_contract(surface):
    provenance = SURFACES[surface]["properties"]["provenance"]
    expected = SURFACES["entity"]["properties"]["provenance"]
    assert provenance == expected, (
        f"{surface} provenance sub-schema drifted from the shared contract"
    )


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_all_four_schemas_remain_valid_draft_2020_12(surface):
    jsonschema.Draft202012Validator.check_schema(SURFACES[surface])


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_provenance_is_optional_and_legacy_records_remain_valid(surface):
    assert "provenance" not in SURFACES[surface].get("required", [])
    assert _errors(surface, BASES[surface]) == []


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_each_surface_accepts_all_four_classifications(surface, classification):
    record = _with_provenance(surface, {"classification": classification})
    assert _errors(surface, record) == []


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_explicit_unknown_stays_unknown_and_absence_is_not_inferred(surface):
    unknown = _with_provenance(surface, {"classification": "unknown"})
    assert _errors(surface, unknown) == []
    assert _errors(surface, BASES[surface]) == []


@pytest.mark.parametrize(
    "bad_classification",
    [
        "canon",
        "Official",
        "OFFICIAL",
        " official",
        "official ",
        "official\n",
        "homebrew mechanic",
        "",
        "   ",
        None,
        1,
        True,
        [],
        {},
    ],
)
@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_each_surface_rejects_invalid_classification(surface, bad_classification):
    record = _with_provenance(surface, {"classification": bad_classification})
    errors = _errors(surface, record)
    assert errors, f"{surface} accepted invalid classification {bad_classification!r}"
    assert any(
        error.startswith("provenance") for error in errors
    ), f"{surface} rejected {bad_classification!r} but not at provenance: {errors}"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_each_surface_rejects_malformed_provenance_containers(surface):
    for bad_provenance in (
        "official",
        None,
        ["official"],
        {},
        {"Classification": "official"},
        {"classification": "official", "note": ""},
        {"classification": "official", "note": "   "},
        {"classification": "official", "note": "From a source book."},
        {"classification": "official", "source_url": "https://example.invalid"},
    ):
        errors = _errors(surface, _with_provenance(surface, bad_provenance))
        assert errors, f"{surface} accepted malformed provenance {bad_provenance!r}"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_provenance_grants_no_extra_fields_on_the_record(surface):
    for extra_field in ("canon_status", "visibility", "source_book", "page"):
        record = {
            **_with_provenance(surface, {"classification": "official"}),
            extra_field: "whatever",
        }
        assert _errors(surface, record), (
            f"{surface} accepted invented {extra_field!r} alongside provenance"
        )


def test_provenance_has_no_effect_on_entity_identity():
    official = _with_provenance("entity", {"classification": "official"})
    assert _errors("entity", official) == []

    mismatched = {**official, "entity_id": "villain:provenance-proof-role"}
    assert _errors("entity", mismatched), (
        "provenance must not relax entity_type/entity_id prefix coupling"
    )

    trailing = {**official, "entity_id": "item:provenance-proof-item\n"}
    assert _errors("entity", trailing), (
        "provenance must not relax entity_id strict-end shape"
    )

    unknown_type = {**official, "entity_type": "npc"}
    assert _errors("entity", unknown_type), (
        "provenance must not admit new entity types"
    )


def test_provenance_has_no_effect_on_hook_lifecycle():
    retired = {**_with_provenance("hook", {"classification": "homebrew"}), "status": "retired"}
    assert _errors("hook", retired), (
        "provenance must not remove the retired retirement_reason requirement"
    )

    retired_ok = {**retired, "retirement_reason": "Objective is no longer possible."}
    assert _errors("hook", retired_ok) == []

    active_with_reason = {
        **_with_provenance("hook", {"classification": "homebrew"}),
        "retirement_reason": "Should stay forbidden while active.",
    }
    assert _errors("hook", active_with_reason), (
        "provenance must not permit retirement_reason outside retired status"
    )

    bad_status = {**_with_provenance("hook", {"classification": "homebrew"}), "status": "archived"}
    assert _errors("hook", bad_status), (
        "provenance must not admit lifecycle states outside the approved enum"
    )


def test_provenance_has_no_effect_on_scenario_semantics():
    with_outcome = {
        **_with_provenance("scenario", {"classification": "adapted"}),
        "outcome": "The party won.",
    }
    assert _errors("scenario", with_outcome), (
        "provenance must not admit actual-play outcome storage on Scenarios"
    )

    bad_hook_id = {
        **_with_provenance("scenario", {"classification": "adapted"}),
        "primary_hook_id": "quest-1",
    }
    assert _errors("scenario", bad_hook_id), (
        "provenance must not relax the Primary Hook ID shape"
    )


def test_provenance_has_no_effect_on_encounter_semantics():
    with_result = {
        **_with_provenance("encounter", {"classification": "unknown"}),
        "result": "They negotiated successfully.",
    }
    assert _errors("encounter", with_result), (
        "provenance must not admit actual-play result storage on Encounters"
    )

    bad_scene_type = {
        **_with_provenance("encounter", {"classification": "unknown"}),
        "scene_type": "puzzle",
    }
    assert _errors("encounter", bad_scene_type), (
        "provenance must not admit scene types outside the approved enum"
    )


def test_real_rhc_item_canary_still_validates_without_provenance():
    paths = validate_entities.load_records(ROOT / "entities" / "items")
    assert validate_entities.validate_paths(paths) == {}
