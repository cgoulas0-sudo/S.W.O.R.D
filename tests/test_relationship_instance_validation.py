import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
KINDS = FIXTURES / "relationship_kinds" / "valid"
INSTANCES = FIXTURES / "relationship_instances"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records  # noqa: E402
from validate_relationship_instances import load_schema, validate_record, validate_paths, main  # noqa: E402


def kind_paths():
    return load_records(KINDS)


def test_valid_fixtures_pass_as_batch():
    paths = load_records(INSTANCES / "valid")
    assert len(paths) == 4
    assert validate_paths(paths, kind_paths()) == {}


def test_faction_can_serve_location_when_kind_is_unrestricted():
    path = INSTANCES / "valid" / "01-faction-serves-location.json"
    assert validate_paths([path], kind_paths()) == {}


def test_ended_history_and_one_current_instance_same_triple_are_allowed():
    paths = [
        INSTANCES / "valid" / "02-parent-old-ended.json",
        INSTANCES / "valid" / "03-parent-current-active.json",
    ]
    assert validate_paths(paths, kind_paths()) == {}


def test_each_invalid_schema_fixture_fails_alone():
    for path in load_records(INSTANCES / "invalid_schema"):
        errors = validate_paths([path], kind_paths())
        assert path in errors, f"expected {path.name} to fail schema validation"


def test_duplicate_relationship_id_fails_only_second_record():
    paths = load_records(INSTANCES / "invalid_duplicate_id")
    errors = validate_paths(paths, kind_paths())
    assert set(errors) == {paths[1]}
    assert any("relationship_id" in e and "duplicates" in e for e in errors[paths[1]])


def test_unknown_kind_is_rejected():
    path = load_records(INSTANCES / "invalid_unknown_kind")[0]
    errors = validate_paths([path], kind_paths())
    assert any("not registered" in e for e in errors[path])


def test_endpoint_type_restriction_is_enforced():
    path = load_records(INSTANCES / "invalid_endpoint_type")[0]
    errors = validate_paths([path], kind_paths())
    assert any("source_id type" in e and "not allowed" in e for e in errors[path])


def test_second_active_duplicate_triple_is_rejected():
    paths = load_records(INSTANCES / "invalid_duplicate_active")
    errors = validate_paths(paths, kind_paths())
    assert set(errors) == {paths[1]}
    assert any("active relationship duplicates" in e for e in errors[paths[1]])


def test_ended_at_is_derived_activity_marker_not_active_boolean():
    schema = load_schema()
    assert "active" not in schema["properties"]
    record = {
        "relationship_id": "fixture-ended",
        "source_id": "character:test-a",
        "kind": "serves",
        "target_id": "faction:test-b",
        "ended_at": "day-3",
    }
    assert validate_record(record, schema) == []


def test_relationship_id_has_no_uuid_or_prefix_grammar():
    schema = load_schema()
    record = {
        "relationship_id": "plain stable human-chosen id",
        "source_id": "character:test-a",
        "kind": "serves",
        "target_id": "faction:test-b",
    }
    assert validate_record(record, schema) == []


def test_future_metadata_is_rejected_until_schema_is_versioned():
    path = INSTANCES / "invalid_schema" / "unversioned_strength.json"
    errors = validate_paths([path], kind_paths())
    assert path in errors


def test_started_and_ended_labels_are_not_chronologically_interpreted():
    schema = load_schema()
    record = {
        "relationship_id": "opaque-times",
        "source_id": "character:test-a",
        "kind": "serves",
        "target_id": "faction:test-b",
        "started_at": "after-the-festival",
        "ended_at": "before-the-festival",
    }
    assert validate_record(record, schema) == []


def test_kind_rejects_trailing_newline():
    schema = load_schema()
    record = {
        "relationship_id": "bad-kind-newline",
        "source_id": "character:test-a",
        "kind": "serves\n",
        "target_id": "faction:test-b",
    }
    assert validate_record(record, schema)


def test_source_and_target_ids_accept_all_current_entity_types():
    schema = load_schema()
    for source_type in ("character","location","faction","party","creature","item","ability","status_effect"):
        record = {
            "relationship_id": f"id {source_type}",
            "source_id": f"{source_type}:test-source",
            "kind": "serves",
            "target_id": "location:test-target",
        }
        assert validate_record(record, schema) == []


def test_duplicate_json_keys_fail_cleanly(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(
        '{"relationship_id":"first","relationship_id":"second",'
        '"source_id":"character:test-a","kind":"serves","target_id":"faction:test-b"}',
        encoding="utf-8",
    )
    errors = validate_paths([path], kind_paths())
    assert path in errors
    assert any("duplicate key" in e for e in errors[path])


def test_invalid_utf8_is_record_failure_not_crash(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'{"relationship_id":"bad","source_id":"character:test-a","kind":"serves","target_id":"faction:\xff"}')
    errors = validate_paths([path], kind_paths())
    assert path in errors
    assert any("utf-8" in e.lower() for e in errors[path])


def test_cli_valid_fixture_batch(capsys):
    code = main(["--kinds", str(KINDS), str(INSTANCES / "valid")])
    assert code == 0
    assert "OK: 4" in capsys.readouterr().out


def test_target_endpoint_type_restriction_is_enforced():
    paths = load_records(INSTANCES / "invalid_endpoint_type")
    path = paths[1]
    errors = validate_paths([path], kind_paths())
    assert any("target_id type" in e and "not allowed" in e for e in errors[path])


def test_multiple_ended_history_records_same_triple_are_allowed(tmp_path):
    records = [
        {
            "relationship_id": "ended-1",
            "source_id": "character:test-a",
            "kind": "serves",
            "target_id": "faction:test-b",
            "ended_at": "day-2",
        },
        {
            "relationship_id": "ended-2",
            "source_id": "character:test-a",
            "kind": "serves",
            "target_id": "faction:test-b",
            "ended_at": "day-7",
        },
    ]
    paths = []
    for index, record in enumerate(records, 1):
        path = tmp_path / f"{index}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        paths.append(path)
    assert validate_paths(paths, kind_paths()) == {}


def test_cli_requires_explicit_kind_registry(capsys):
    code = main([str(INSTANCES / "valid")])
    assert code == 2
    assert "--kinds" in capsys.readouterr().err


def test_whitespace_ended_at_is_rejected():
    path = INSTANCES / "invalid_schema" / "whitespace_ended_at.json"
    errors = validate_paths([path], kind_paths())
    assert path in errors
