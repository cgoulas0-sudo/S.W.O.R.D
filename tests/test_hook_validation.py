import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records  # noqa: E402
from validate_hooks import load_schema, main, validate_paths, validate_record  # noqa: E402


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema())


def test_valid_fixtures_cover_all_lifecycle_states():
    paths = load_records(FIXTURES / "valid")
    assert len(paths) == 4
    assert validate_paths(paths) == {}
    statuses = {json.loads(path.read_text(encoding="utf-8"))["status"] for path in paths}
    assert statuses == {"dormant", "active", "resolved", "retired"}


def test_duplicate_hook_id_is_rejected_on_second_record():
    paths = load_records(FIXTURES / "invalid_duplicate_id")
    errors = validate_paths(paths)
    assert set(errors) == {paths[1]}
    assert any("duplicates" in error for error in errors[paths[1]])


def test_each_invalid_schema_fixture_fails_alone():
    for path in load_records(FIXTURES / "invalid_schema"):
        errors = validate_paths([path])
        assert path in errors, f"expected {path.name} to fail"


def test_retired_requires_reason():
    path = FIXTURES / "invalid_schema" / "retired_without_reason.json"
    assert path in validate_paths([path])


def test_non_retired_rejects_retirement_reason():
    path = FIXTURES / "invalid_schema" / "active_with_retirement_reason.json"
    assert path in validate_paths([path])


def test_hook_id_requires_h_plus_at_least_two_digits_and_strict_end():
    schema = load_schema()
    base = {
        "hook_id": "H01",
        "title": "Hook ID contract",
        "objective": "Prove the stable ID grammar.",
        "status": "active",
        "activation_condition": "Fixture only.",
        "resolution_condition": "Fixture only.",
        "related_entity_ids": [],
    }

    assert validate_record(base, schema) == []
    assert validate_record({**base, "hook_id": "H105"}, schema) == []

    for bad_id in ("H1", "quest-1", "H01\n", "H01\r", "H01 "):
        assert validate_record({**base, "hook_id": bad_id}, schema), bad_id


def test_related_entity_ids_accept_all_current_entity_types():
    schema = load_schema()
    record = {
        "hook_id": "H99",
        "title": "All types",
        "objective": "Reference every current entity type.",
        "status": "active",
        "activation_condition": "Fixture only.",
        "resolution_condition": "Fixture only.",
        "related_entity_ids": [
            "character:test", "location:test", "faction:test", "party:test",
            "creature:test", "item:test", "ability:test", "status_effect:test"
        ],
    }
    assert validate_record(record, schema) == []


def test_related_entity_ids_reject_unknown_prefix():
    schema = load_schema()
    record = {
        "hook_id": "H98",
        "title": "Bad ref",
        "objective": "Reject unknown entity types.",
        "status": "active",
        "activation_condition": "Fixture only.",
        "resolution_condition": "Fixture only.",
        "related_entity_ids": ["npc:test"],
    }
    assert validate_record(record, schema)


def test_related_entity_ids_are_unique():
    schema = load_schema()
    record = {
        "hook_id": "H97",
        "title": "Duplicate refs",
        "objective": "Reject duplicate related entity IDs.",
        "status": "active",
        "activation_condition": "Fixture only.",
        "resolution_condition": "Fixture only.",
        "related_entity_ids": ["character:test", "character:test"],
    }
    assert validate_record(record, schema)


def test_extra_fields_are_rejected_until_schema_evolves():
    schema = load_schema()
    record = {
        "hook_id": "H96",
        "title": "No scenario yet",
        "objective": "Prove EV2-07 fields cannot sneak into EV2-06.",
        "status": "active",
        "activation_condition": "Fixture only.",
        "resolution_condition": "Fixture only.",
        "related_entity_ids": [],
        "linked_scenario": "S01",
    }
    assert validate_record(record, schema)


def test_duplicate_json_keys_fail_cleanly(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(
        '{"hook_id":"H01","hook_id":"H02","title":"x","objective":"x",'
        '"status":"active","activation_condition":"x","resolution_condition":"x",'
        '"related_entity_ids":[]}',
        encoding="utf-8",
    )
    errors = validate_paths([path])
    assert path in errors
    assert any("duplicate key" in error for error in errors[path])


def test_invalid_utf8_is_failure_not_crash(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'{"hook_id":"H01","title":"\xff"}')
    errors = validate_paths([path])
    assert path in errors
    assert any("utf-8" in error.lower() for error in errors[path])


def test_cli_valid_fixture_batch(capsys):
    code = main([str(FIXTURES / "valid")])
    assert code == 0
    assert "OK: 4" in capsys.readouterr().out


def test_cli_requires_directory(capsys):
    code = main([])
    assert code == 2
    assert "usage:" in capsys.readouterr().err


def test_blank_core_text_is_rejected():
    schema = load_schema()
    for field in ("title", "objective", "activation_condition", "resolution_condition"):
        record = {
            "hook_id": "H95",
            "title": "x",
            "objective": "x",
            "status": "active",
            "activation_condition": "x",
            "resolution_condition": "x",
            "related_entity_ids": [],
        }
        record[field] = "   "
        assert validate_record(record, schema)
