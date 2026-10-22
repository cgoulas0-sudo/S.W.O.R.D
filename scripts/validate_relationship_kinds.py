#!/usr/bin/env python3
"""Validate Entity V2 relationship-kind registry records.

Usage:
    python scripts/validate_relationship_kinds.py <directory> [<directory> ...]

Validates every *.json file in each given directory (non-recursive) against
schemas/relationship_kind.schema.json, then checks, across all records passed
in together:
  - kind uniqueness (no two records register the same kind)
  - inverse_of resolves to another kind present in the same batch
  - inverse_of pairs are mutually consistent (A.inverse_of == B implies
    B.inverse_of == A)
  - for a mutually consistent inverse_of pair, allowed_source_types/
    allowed_target_types mirror in reverse across the pair -- a restriction
    declared on one side with no matching mirror declared on the other is
    rejected too, not just a declared-vs-declared mismatch
  - for a symmetric kind, allowed_source_types and allowed_target_types must
    describe the same domain (unless both are left undeclared, which stays
    fully unrestricted)
Exits non-zero if any record fails schema validation or any batch-level rule
is violated. Reuses validate_entities.py's JSON-hardening hooks (duplicate
keys, non-finite numbers, invalid UTF-8) so both validators reject malformed
input the same way.
"""
import json
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_entities import (  # noqa: E402
    _display_path,
    _parse_float_reject_overflow,
    _reject_duplicate_keys,
    _reject_non_json_constants,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "relationship_kind.schema.json"


def load_schema(schema_path=SCHEMA_PATH):
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def _endpoint_type_set(value):
    """Normalize an allowed_source_types/allowed_target_types value to a set for
    comparison. A non-list value, or a list containing schema-invalid unhashable
    items (nested objects/arrays) -- either way already flagged separately by
    per-record schema validation -- counts as an empty/undeclared domain here
    rather than being iterated as a container or raising on set() construction.
    """
    if not isinstance(value, list):
        return set()
    try:
        return set(value)
    except TypeError:
        return set()


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def validate_paths(paths, schema_path=SCHEMA_PATH):
    """Validate a list of record file paths as one batch (schema + registry-level rules).

    Returns a dict of {path: [errors]} containing only paths with at least one error.
    """
    schema = load_schema(schema_path)
    errors_by_path = {}
    seen_kinds = {}
    kind_records = {}

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors_by_path[path] = [f"invalid UTF-8: {exc}"]
            continue

        try:
            record = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_non_json_constants,
                parse_float=_parse_float_reject_overflow,
            )
        except json.JSONDecodeError as exc:
            errors_by_path[path] = [f"invalid JSON: {exc}"]
            continue
        except ValueError as exc:
            errors_by_path[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)

        kind = record.get("kind") if isinstance(record, dict) else None
        if isinstance(kind, str):
            if kind in seen_kinds:
                errors.append(f"kind '{kind}' duplicates {seen_kinds[kind].name}")
            else:
                seen_kinds[kind] = path
                kind_records[kind] = record

        if errors:
            errors_by_path[path] = errors

    # Registry-level inverse_of consistency, over the first (non-duplicate)
    # record seen for each kind, regardless of that record's own schema
    # errors -- same "independent checks each contribute errors" posture as
    # the duplicate-kind check above.
    for kind, record in kind_records.items():
        path = seen_kinds[kind]
        inverse_of = record.get("inverse_of")
        if not isinstance(inverse_of, str):
            continue

        if inverse_of == kind:
            errors_by_path.setdefault(path, []).append(
                f"inverse_of '{inverse_of}' must not equal its own kind "
                "(use symmetric: true instead of a self-referential inverse_of)"
            )
            continue

        target_record = kind_records.get(inverse_of)
        if target_record is None:
            errors_by_path.setdefault(path, []).append(
                f"inverse_of '{inverse_of}' does not match any kind in this batch"
            )
            continue

        target_inverse = target_record.get("inverse_of")
        if target_inverse != kind:
            errors_by_path.setdefault(path, []).append(
                f"inverse_of '{inverse_of}' is not mutually consistent: "
                f"'{inverse_of}' declares inverse_of {target_inverse!r}, expected {kind!r}"
            )
            continue

        # An inverse pair describes the same real-world relationship read from
        # opposite ends, so its endpoint constraints must mirror in reverse:
        # this kind's allowed_source_types is the inverse's allowed_target_types,
        # and vice versa. A restriction declared on only one side is also
        # rejected -- an undeclared mirror means "unrestricted", which is wider
        # than the declared side and so does not actually mirror it. Both sides
        # left undeclared is the only case that stays fully unrestricted.
        source_types = record.get("allowed_source_types")
        target_types = record.get("allowed_target_types")
        inv_source_types = target_record.get("allowed_source_types")
        inv_target_types = target_record.get("allowed_target_types")

        if _endpoint_type_set(source_types) != _endpoint_type_set(inv_target_types):
            errors_by_path.setdefault(path, []).append(
                f"allowed_source_types {source_types} does not match inverse "
                f"'{inverse_of}''s allowed_target_types {inv_target_types} "
                "(an inverse pair's endpoint types must mirror each other in reverse)"
            )

        if _endpoint_type_set(target_types) != _endpoint_type_set(inv_source_types):
            errors_by_path.setdefault(path, []).append(
                f"allowed_target_types {target_types} does not match inverse "
                f"'{inverse_of}''s allowed_source_types {inv_source_types} "
                "(an inverse pair's endpoint types must mirror each other in reverse)"
            )

    # A symmetric kind reads the same relationship in both directions, so its
    # own source/target domains must describe the same set of entity types --
    # restricting only one endpoint, or restricting both to different sets, is
    # rejected. Leaving both undeclared stays fully unrestricted.
    for kind, record in kind_records.items():
        if record.get("symmetric") is not True:
            continue

        source_types = record.get("allowed_source_types")
        target_types = record.get("allowed_target_types")

        if _endpoint_type_set(source_types) != _endpoint_type_set(target_types):
            path = seen_kinds[kind]
            errors_by_path.setdefault(path, []).append(
                f"symmetric kind's allowed_source_types {source_types} does not "
                f"match its allowed_target_types {target_types} (a symmetric kind "
                "reads the same in both directions, so its endpoint domains must match)"
            )

    return errors_by_path


USAGE = "usage: validate_relationship_kinds.py <directory> [<directory> ...]"


def main(argv):
    directories = list(argv)
    if not directories:
        print(USAGE, file=sys.stderr)
        return 2

    paths = []
    for directory in directories:
        try:
            paths.extend(load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    errors_by_path = validate_paths(paths)

    for path, errors in errors_by_path.items():
        for error in errors:
            print(f"FAIL: {_display_path(path)}: {error}", file=sys.stderr)

    if errors_by_path:
        print(f"\n{len(errors_by_path)} of {len(paths)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(f"OK: {len(paths)} record(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
