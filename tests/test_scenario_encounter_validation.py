import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records  # noqa: E402
from validate_scenarios_encounters import (  # noqa: E402
    ENCOUNTER_SCHEMA_PATH,
    SCENARIO_SCHEMA_PATH,
    load_schema,
    main,
    validate_paths,
)

HOOKS = FIX / "hooks" / "valid"
SCENARIOS = FIX / "scenarios" / "valid"
ENCOUNTERS = FIX / "encounters" / "valid"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _base_scenario():
    return _load(SCENARIOS / "01-scenario.json")


def _base_encounter():
    return _load(ENCOUNTERS / "01-social.json")


def _valid_paths():
    return load_records(HOOKS), load_records(SCENARIOS), load_records(ENCOUNTERS)


def test_scenario_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema(SCENARIO_SCHEMA_PATH))


def test_encounter_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema(ENCOUNTER_SCHEMA_PATH))


def test_valid_scenario_and_encounter_batch_passes():
    assert validate_paths(*_valid_paths()) == {}


def test_valid_encounters_cover_all_scene_types():
    scene_types = {_load(path)["scene_type"] for path in load_records(ENCOUNTERS)}
    assert scene_types == {"social", "exploration", "combat", "mixed"}


def test_duplicate_scenario_id_rejected(tmp_path):
    first = _write(tmp_path, "01.json", {**_base_scenario(), "scenario_id": "S08"})
    second = _write(tmp_path, "02.json", {**_base_scenario(), "scenario_id": "S08", "title": "Duplicate"})
    errors = validate_paths(load_records(HOOKS), [first, second], load_records(ENCOUNTERS))
    assert any("duplicates" in e for e in errors[second])


def test_duplicate_encounter_id_rejected(tmp_path):
    first = _write(tmp_path, "01.json", {**_base_encounter(), "encounter_id": "E08"})
    second = _write(tmp_path, "02.json", {**_base_encounter(), "encounter_id": "E08", "title": "Duplicate"})
    errors = validate_paths(load_records(HOOKS), load_records(SCENARIOS), [first, second])
    assert any("duplicates" in e for e in errors[second])


def test_unknown_primary_hook_rejected(tmp_path):
    path = _write(tmp_path, "scenario.json", {**_base_scenario(), "scenario_id": "S10", "primary_hook_id": "H99"})
    errors = validate_paths(load_records(HOOKS), [path], load_records(ENCOUNTERS))
    assert any("primary_hook_id" in e and "does not resolve" in e for e in errors[path])


def test_unknown_related_hook_rejected(tmp_path):
    path = _write(tmp_path, "scenario.json", {**_base_scenario(), "scenario_id": "S11", "related_hook_ids": ["H99"]})
    errors = validate_paths(load_records(HOOKS), [path], load_records(ENCOUNTERS))
    assert any("related_hook_id" in e and "does not resolve" in e for e in errors[path])


def test_primary_hook_cannot_repeat_as_related(tmp_path):
    path = _write(tmp_path, "scenario.json", {**_base_scenario(), "scenario_id": "S12", "related_hook_ids": ["H01"]})
    errors = validate_paths(load_records(HOOKS), [path], load_records(ENCOUNTERS))
    assert any("must not also appear" in e for e in errors[path])


def test_unknown_scenario_on_encounter_rejected(tmp_path):
    path = _write(tmp_path, "encounter.json", {**_base_encounter(), "encounter_id": "E10", "scenario_id": "S99"})
    errors = validate_paths(load_records(HOOKS), load_records(SCENARIOS), [path])
    assert any("scenario_id" in e and "does not resolve" in e for e in errors[path])


def test_scenario_id_requires_s_plus_at_least_two_digits_and_strict_end():
    schema = load_schema(SCENARIO_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base_scenario()
    for bad in ("S1", "scenario-1", "S01\n", "S01\r", "S01 "):
        assert list(validator.iter_errors({**base, "scenario_id": bad})), bad


def test_encounter_id_requires_e_plus_at_least_two_digits_and_strict_end():
    schema = load_schema(ENCOUNTER_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base_encounter()
    for bad in ("E1", "encounter-1", "E01\n", "E01\r", "E01 "):
        assert list(validator.iter_errors({**base, "encounter_id": bad})), bad


def test_scenario_hook_ids_use_strict_hook_shape():
    schema = load_schema(SCENARIO_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base_scenario()
    for bad in ("H1", "H01\n", "hook-1"):
        assert list(validator.iter_errors({**base, "primary_hook_id": bad})), bad


def test_related_entity_ids_accept_all_current_entity_types():
    schema = load_schema(SCENARIO_SCHEMA_PATH)
    record = _base_scenario()
    record["related_entity_ids"] = [
        "character:test", "location:test", "faction:test", "party:test",
        "creature:test", "item:test", "ability:test", "status_effect:test",
    ]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record)) == []


def test_related_entity_ids_reject_mutable_role_prefix():
    schema = load_schema(SCENARIO_SCHEMA_PATH)
    record = _base_scenario()
    record["related_entity_ids"] = ["npc:test"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_scenario_rejects_actual_outcome_field():
    schema = load_schema(SCENARIO_SCHEMA_PATH)
    record = {**_base_scenario(), "outcome": "The party won."}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_encounter_rejects_actual_result_field():
    schema = load_schema(ENCOUNTER_SCHEMA_PATH)
    record = {**_base_encounter(), "result": "They negotiated successfully."}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_bad_scene_type_rejected():
    schema = load_schema(ENCOUNTER_SCHEMA_PATH)
    record = {**_base_encounter(), "scene_type": "puzzle"}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_cli_valid_fixture_batch(capsys):
    code = main([
        "--hooks", str(HOOKS),
        "--scenarios", str(SCENARIOS),
        "--encounters", str(ENCOUNTERS),
    ])
    assert code == 0
    assert "OK: 4 Hook, 2 Scenario, 4 Encounter" in capsys.readouterr().out


def test_blank_prepared_text_is_rejected():
    scenario_schema = load_schema(SCENARIO_SCHEMA_PATH)
    encounter_schema = load_schema(ENCOUNTER_SCHEMA_PATH)
    scenario_validator = jsonschema.Draft202012Validator(scenario_schema)
    encounter_validator = jsonschema.Draft202012Validator(encounter_schema)
    scenario = _base_scenario()
    for field in ("title", "premise", "objective", "trigger_condition"):
        assert list(scenario_validator.iter_errors({**scenario, field: "   "})), field
    encounter = _base_encounter()
    for field in ("title", "setup", "immediate_objective"):
        assert list(encounter_validator.iter_errors({**encounter, field: "   "})), field
