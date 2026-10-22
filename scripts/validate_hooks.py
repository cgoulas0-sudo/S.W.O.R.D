#!/usr/bin/env python3
"""Validate Entity V2 Hook records.

Usage:
    python scripts/validate_hooks.py <directory> [<directory> ...]

Each Hook is validated against schemas/hook.schema.json. Across all records passed
in together, hook_id must be unique. This foundation patch intentionally does not
resolve entity references against real campaign records, interpret campaign time,
or implement lifecycle mutation procedures.
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
SCHEMA_PATH = ROOT / "schemas" / "hook.schema.json"


def load_schema(schema_path=SCHEMA_PATH):
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def validate_record(record, schema):
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def _read_json_record(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constants,
        parse_float=_parse_float_reject_overflow,
    )


def validate_paths(paths, schema_path=SCHEMA_PATH):
    schema = load_schema(schema_path)
    errors_by_path = {}
    seen_ids = {}

    for path in paths:
        try:
            record = _read_json_record(path)
        except UnicodeDecodeError as exc:
            errors_by_path[path] = [f"invalid UTF-8: {exc}"]
            continue
        except json.JSONDecodeError as exc:
            errors_by_path[path] = [f"invalid JSON: {exc}"]
            continue
        except ValueError as exc:
            errors_by_path[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)
        if isinstance(record, dict):
            hook_id = record.get("hook_id")
            if isinstance(hook_id, str):
                if hook_id in seen_ids:
                    errors.append(f"hook_id '{hook_id}' duplicates {seen_ids[hook_id].name}")
                else:
                    seen_ids[hook_id] = path

        if errors:
            errors_by_path[path] = errors

    return errors_by_path


USAGE = "usage: validate_hooks.py <directory> [<directory> ...]"


def main(argv):
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2

    paths = []
    for directory in argv:
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
        print(f"\n{len(errors_by_path)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(f"OK: {len(paths)} Hook record(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
