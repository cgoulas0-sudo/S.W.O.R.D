#!/usr/bin/env python3
"""Validate Canon Intake candidate records (CI-01).

Usage:
    python scripts/validate_intake_candidates.py <directory> [<directory> ...]

Every *.json record in the given directories is validated against
schemas/intake_candidate.schema.json, and candidate_id must stay unique
across the whole batch. The batch is the only cross-record rule CI-01 owns:
source references are free-form and are never resolved, verified, or stored,
no decision/approval workflow exists here, and no promotion, collision
detection, or persistence route is implemented (later Canon Intake gates,
CI-02+).
"""
import json
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_entities as shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "intake_candidate.schema.json"

# Refuse duplicate JSON keys, bare NaN/Infinity constants, and numeric
# literals that overflow to a non-finite float, exactly like every other
# RHC record reader.
READ_HOOKS = {
    "object_pairs_hook": shared._reject_duplicate_keys,
    "parse_constant": shared._reject_non_json_constants,
    "parse_float": shared._parse_float_reject_overflow,
}


def load_schema(schema_path=SCHEMA_PATH):
    """Return the parsed intake-candidate JSON Schema."""
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def read_record(path):
    """Read one JSON record through the shared fail-closed parse hooks."""
    return json.loads(path.read_text(encoding="utf-8"), **READ_HOOKS)


def duplicate_id_error(record, seen_ids, path):
    """Return the batch-uniqueness error for this record, if any."""
    candidate_id = record.get("candidate_id") if isinstance(record, dict) else None
    if not isinstance(candidate_id, str):
        return None
    if candidate_id in seen_ids:
        return f"candidate_id '{candidate_id}' duplicates {seen_ids[candidate_id].name}"
    seen_ids[candidate_id] = path
    return None


def validate_paths(paths, schema_path=SCHEMA_PATH):
    """Validate one batch of records; return {path: [errors]} for failures only."""
    schema = load_schema(schema_path)
    failures = {}
    seen_ids = {}

    for path in paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            failures[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)
        duplicate = duplicate_id_error(record, seen_ids, path)
        if duplicate:
            errors.append(duplicate)
        if errors:
            failures[path] = errors

    return failures


def main(argv):
    if not argv:
        print(
            "usage: validate_intake_candidates.py <directory> [<directory> ...]",
            file=sys.stderr,
        )
        return 2

    records = []
    for directory in argv:
        try:
            records.extend(shared.load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    failures = validate_paths(records)
    for path, errors in failures.items():
        shown = shared._display_path(path)
        for error in errors:
            print(f"FAIL: {shown}: {error}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(f"OK: {len(records)} Canon Intake candidate record(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
