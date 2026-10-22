import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "entities"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records, load_schema, main, validate_record, validate_paths  # noqa: E402


def test_valid_fixtures_pass_as_a_batch():
    paths = load_records(FIXTURES / "valid")
    assert len(paths) == 10

    errors_by_path = validate_paths(paths)

    assert errors_by_path == {}


def test_each_entity_type_is_represented_in_valid_fixtures():
    import json

    types_seen = {
        json.loads(p.read_text(encoding="utf-8"))["entity_type"]
        for p in load_records(FIXTURES / "valid")
    }

    assert types_seen == {
        "character", "location", "faction", "party", "creature", "item",
        "ability", "status_effect",
    }


def test_each_invalid_schema_fixture_fails_alone():
    for path in load_records(FIXTURES / "invalid_schema"):
        errors_by_path = validate_paths([path])
        assert path in errors_by_path, f"expected {path.name} to fail schema validation"


def test_invalid_duplicate_fixtures_pass_individually():
    for path in load_records(FIXTURES / "invalid_duplicate"):
        errors_by_path = validate_paths([path])
        assert errors_by_path == {}, f"{path.name} should be schema-valid on its own"


def test_invalid_duplicate_fixtures_fail_as_a_batch():
    paths = load_records(FIXTURES / "invalid_duplicate")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("duplicates" in e for e in errors)


def test_valid_and_duplicate_fixtures_together_only_flag_the_second_duplicate():
    valid_paths = load_records(FIXTURES / "valid")
    dup_paths = load_records(FIXTURES / "invalid_duplicate")

    errors_by_path = validate_paths(valid_paths + dup_paths)

    assert set(errors_by_path.keys()) == {dup_paths[1]}


def test_missing_directory_is_rejected(tmp_path):
    missing = tmp_path / "does-not-exist"

    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        load_records(missing)


def test_directory_with_no_json_records_is_rejected(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        load_records(empty)


def test_entity_id_rejects_trailing_newline():
    schema = load_schema()
    record = {
        "entity_id": "character:test-trailing-newline\n",
        "entity_type": "character",
        "display_name": "Trailing Newline (fixture)",
    }

    errors = validate_record(record, schema)

    assert errors, "entity_id with a trailing newline should fail schema validation"


def test_reference_rejects_trailing_newline():
    schema = load_schema()
    record = {
        "entity_id": "character:test-trailing-newline-ref",
        "entity_type": "character",
        "display_name": "Trailing Newline Reference (fixture)",
        "references": ["character:test-hero\n"],
    }

    errors = validate_record(record, schema)

    assert errors, "a reference with a trailing newline should fail schema validation"


def test_entity_id_pattern_avoids_python_only_regex_escapes():
    schema = load_schema()
    patterns = [
        schema["properties"]["entity_id"]["pattern"],
        schema["properties"]["references"]["items"]["pattern"],
    ]

    non_ecma262_escapes = ("\\Z", "\\A")
    for pattern in patterns:
        for escape in non_ecma262_escapes:
            assert escape not in pattern, (
                f"{escape!r} is a Python-only regex escape, not valid ECMA-262 "
                f"(the JSON Schema pattern dialect): {pattern!r}"
            )


def test_main_reports_failure_for_invalid_record_outside_repo_root(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "bad.json").write_text(
        json.dumps({"entity_id": "character:test-outside", "entity_type": "character"}),
        encoding="utf-8",
    )

    exit_code = main([str(outside)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "display_name" in captured.err


def test_duplicate_json_object_keys_are_rejected(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(
        '{"entity_id": "character:test-dup-key", "entity_id": "character:test-dup-key-2", '
        '"entity_type": "character", "display_name": "Dup Key (fixture)"}',
        encoding="utf-8",
    )

    errors_by_path = validate_paths([path])

    assert path in errors_by_path, "a record with a duplicated JSON key should fail validation"
    assert any("duplicate" in e.lower() for e in errors_by_path[path])


def test_invalid_utf8_is_a_per_record_failure_not_a_crash(tmp_path):
    path = tmp_path / "bad_utf8.json"
    path.write_bytes(
        b'{"entity_id": "character:test-bad-utf8", "entity_type": "character", "display_name": "\xff\xfe"}'
    )

    errors_by_path = validate_paths([path])

    assert path in errors_by_path, "a file with invalid UTF-8 should fail as a record, not raise"
    assert any("utf-8" in e.lower() for e in errors_by_path[path])


def test_whitespace_only_display_name_is_rejected():
    schema = load_schema()
    record = {
        "entity_id": "character:test-whitespace-name",
        "entity_type": "character",
        "display_name": "   ",
    }

    errors = validate_record(record, schema)

    assert errors, "a whitespace-only display_name should fail schema validation"


def test_whitespace_only_subtype_is_rejected():
    schema = load_schema()
    record = {
        "entity_id": "character:test-whitespace-subtype",
        "entity_type": "character",
        "display_name": "Whitespace Subtype (fixture)",
        "subtype": "   ",
    }

    errors = validate_record(record, schema)

    assert errors, "a whitespace-only subtype should fail schema validation"


def test_subtype_does_not_change_entity_id_pattern():
    """subtype is classification metadata only: entity_id must still be
    prefixed by entity_type, never by subtype (e.g. a character with
    subtype 'villain' still requires entity_id 'character:<slug>', not
    'villain:<slug>')."""
    schema = load_schema()
    record = {
        "entity_id": "villain:test-role-prefix",
        "entity_type": "character",
        "display_name": "Role-Prefixed ID (fixture)",
        "subtype": "villain",
    }

    errors = validate_record(record, schema)

    assert errors, "entity_id must not be prefixed by subtype/role instead of entity_type"
