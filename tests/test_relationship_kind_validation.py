import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "relationship_kinds"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_relationship_kinds import load_schema, validate_record, validate_paths  # noqa: E402
from validate_entities import load_records  # noqa: E402


def test_valid_fixtures_pass_as_a_batch():
    paths = load_records(FIXTURES / "valid")
    assert len(paths) == 4

    errors_by_path = validate_paths(paths)

    assert errors_by_path == {}


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


def test_dangling_inverse_fixture_fails_as_its_own_batch():
    paths = load_records(FIXTURES / "invalid_dangling_inverse")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("does not match any kind in this batch" in e for e in errors)


def test_asymmetric_inverse_pair_flags_only_the_unreciprocated_side():
    paths = load_records(FIXTURES / "invalid_asymmetric_inverse")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert only_path.name == "kind-guards.json"
    assert any("not mutually consistent" in e for e in errors)


def test_reversed_endpoint_mismatch_fails_as_its_own_batch():
    paths = load_records(FIXTURES / "invalid_reversed_endpoints")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 2
    for errors in errors_by_path.values():
        assert any("must mirror each other in reverse" in e for e in errors)


def test_one_sided_endpoint_restriction_fails_as_its_own_batch():
    paths = load_records(FIXTURES / "invalid_one_sided_endpoints")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 2
    for errors in errors_by_path.values():
        assert any("must mirror each other in reverse" in e for e in errors)


def test_symmetric_endpoint_mismatch_fails_as_its_own_batch():
    paths = load_records(FIXTURES / "invalid_symmetric_endpoint_mismatch")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("symmetric kind" in e and "must match" in e for e in errors)


def test_self_referential_inverse_of_fails_as_its_own_batch():
    paths = load_records(FIXTURES / "invalid_self_inverse")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("must not equal its own kind" in e for e in errors)


def test_missing_directory_is_rejected(tmp_path):
    missing = tmp_path / "does-not-exist"

    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        load_records(missing)


def test_symmetric_kind_rejects_inverse_of_at_schema_level():
    schema = load_schema()
    record = {"kind": "twinned", "symmetric": True, "inverse_of": "twinned"}

    errors = validate_record(record, schema)

    assert errors, "symmetric: true combined with inverse_of should fail schema validation"


def test_kind_rejects_trailing_newline():
    schema = load_schema()
    record = {"kind": "serves\n"}

    errors = validate_record(record, schema)

    assert errors, "a kind with a trailing newline should fail schema validation"


def test_kind_pattern_avoids_python_only_regex_escapes():
    schema = load_schema()
    patterns = [
        schema["properties"]["kind"]["pattern"],
        schema["properties"]["inverse_of"]["pattern"],
    ]

    non_ecma262_escapes = ("\\Z", "\\A")
    for pattern in patterns:
        for escape in non_ecma262_escapes:
            assert escape not in pattern, (
                f"{escape!r} is a Python-only regex escape, not valid ECMA-262 "
                f"(the JSON Schema pattern dialect): {pattern!r}"
            )


def test_allowed_source_types_rejects_type_outside_closed_enum():
    schema = load_schema()
    record = {"kind": "guards", "allowed_source_types": ["monster"]}

    errors = validate_record(record, schema)

    assert errors, "allowed_source_types must be drawn from the closed entity_type enum"


def test_malformed_endpoint_items_fail_cleanly_without_crashing():
    paths = load_records(FIXTURES / "invalid_malformed_endpoint_items")

    errors_by_path = validate_paths(paths)

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("is not one of" in e for e in errors)
