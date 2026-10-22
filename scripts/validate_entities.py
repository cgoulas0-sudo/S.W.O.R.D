#!/usr/bin/env python3
"""Validate Entity V2 records against an Entity V2 schema.

Usage:
    python scripts/validate_entities.py [--schema PATH] <directory> [<directory> ...]

Validates every *.json file in each given directory (non-recursive) against
the given schema (default: schemas/entity.schema.json, the identity layer),
then checks entity_id uniqueness across all records passed in together.
Exits non-zero if any record fails schema validation or any entity_id
collides. The same schema-agnostic checks (JSON/UTF-8 validity, duplicate
keys, rejection of non-finite numeric values -- both bare NaN/Infinity/
-Infinity constants and ordinary number literals like 1e400 that overflow
to +/-inf -- duplicate attribute/topic names within one record's entries,
cross-file entity_id uniqueness) apply to the state, knowledge, and
inventory schemas via --schema.
"""
import json
import math
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "entity.schema.json"


def load_schema(schema_path=SCHEMA_PATH):
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def _reject_duplicate_keys(pairs):
    """object_pairs_hook: raise if a JSON object repeats a key, instead of silently keeping the last value."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate key: {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_non_json_constants(constant):
    """parse_constant hook: raise instead of accepting NaN/Infinity/-Infinity.

    Python's json module accepts these three bare tokens as a non-standard
    extension; they are not valid JSON per RFC 8259, and a schema's "number"
    type otherwise accepts the resulting float silently.
    """
    raise ValueError(f"{constant} is not valid JSON")


def _parse_float_reject_overflow(text):
    """parse_float hook: raise if a syntactically ordinary JSON number literal
    (e.g. 1e400) overflows to +/-inf as a Python float.

    This is distinct from _reject_non_json_constants: 1e400 is standard JSON
    number syntax, so it never reaches parse_constant. Without this hook a
    schema's "number" type would silently accept the resulting infinite
    float, the same non-finite-value gap the NaN/Infinity fix closed for the
    bare-token case.
    """
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} overflows to a non-finite number")
    return value


def _duplicate_entry_key_errors(record):
    """Return errors for entries that repeat the same attribute/topic name.

    uniqueItems only rejects whole-entry duplicates; two entries naming the
    same attribute/topic with different status/value are structurally
    distinct objects that uniqueItems lets through, even though they are a
    contradiction (the same attribute can't independently be two different
    known values). Entries without an "attribute" or "topic" key (e.g.
    inventory's "item") are unaffected.
    """
    entries = record.get("entries") if isinstance(record, dict) else None
    if not isinstance(entries, list):
        return []

    errors = []
    seen = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in ("attribute", "topic"):
            if field in entry:
                value = entry[field]
                if not isinstance(value, (str, int, float, bool)):
                    break  # not hashable / not schema-valid anyway; schema validation reports the type error
                key = (field, value)
                if key in seen:
                    errors.append(f"entries: duplicate {field} {value!r}")
                else:
                    seen[key] = True
                break
    return errors


def load_records(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"not a directory: {directory}")
    records = sorted(directory.glob("*.json"))
    if not records:
        raise FileNotFoundError(f"no *.json records found in: {directory}")
    return records


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def _display_path(path):
    """Repo-relative path when possible, else the absolute path."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def validate_paths(paths, schema_path=SCHEMA_PATH):
    """Validate a list of record file paths as one batch (schema + cross-file uniqueness).

    Returns a dict of {path: [errors]} containing only paths with at least one error.
    """
    schema = load_schema(schema_path)
    errors_by_path = {}
    seen_ids = {}

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
        errors.extend(_duplicate_entry_key_errors(record))

        entity_id = record.get("entity_id") if isinstance(record, dict) else None
        if isinstance(entity_id, str):
            if entity_id in seen_ids:
                errors.append(
                    f"entity_id '{entity_id}' duplicates {seen_ids[entity_id].name}"
                )
            else:
                seen_ids[entity_id] = path

        if errors:
            errors_by_path[path] = errors

    return errors_by_path


USAGE = "usage: validate_entities.py [--schema PATH] <directory> [<directory> ...]"


def main(argv):
    schema_path = SCHEMA_PATH
    directories = []

    it = iter(argv)
    for arg in it:
        if arg == "--schema":
            try:
                schema_path = Path(next(it))
            except StopIteration:
                print(USAGE, file=sys.stderr)
                return 2
        else:
            directories.append(arg)

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

    errors_by_path = validate_paths(paths, schema_path=schema_path)

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
