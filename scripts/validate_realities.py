#!/usr/bin/env python3
"""Validate RHC reality identity records against schemas/reality.schema.json.

Usage:
    python scripts/validate_realities.py <directory> [<directory> ...]

Validates every *.json file in each given directory (non-recursive) against
schemas/reality.schema.json, then checks, across all records passed in together:
  - reality_id uniqueness (no two records register the same reality)
  - the validated set contains exactly one root reality: the single record that
    declares no parent_reality_id (the root is a structural role, not a fixed id)
  - every other reality declares exactly one parent (validated here, since the
    schema no longer privileges any single identity)
  - every declared parent resolves to an admitted reality in the same batch
  - parent lineage is acyclic (including a self-parent)

This validator checks identity and lineage only. It never requires a per-subject
availability map, never copies/removes inherited content, never invents a
divergence, and never promotes external material to canon. Reuses
validate_entities.py's JSON-hardening hooks (duplicate keys, non-finite numbers,
invalid UTF-8) so malformed input is rejected the same way everywhere.

The unique root reality is a structural role: the single admitted record that
declares no ``parent_reality_id``. The root is not a fixed identity -- any valid
``reality:<lower-slug>`` id may be the root of a campaign, so a clean/new campaign
may initialize a different valid root reality id without editing or forking the
engine. Exactly one parentless root must exist in any validated set; every other
record must declare exactly one admitted parent that resolves and is acyclic.

An empty validated set (zero records) is a zero-root state and fails closed:
``validate_paths`` rejects an empty registry/batch explicitly, and a registry
directory with no ``*.json`` record is rejected by the shared record loader.
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
SCHEMA_PATH = ROOT / "schemas" / "reality.schema.json"


def load_schema(schema_path=SCHEMA_PATH):
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def _has_parent_cycle(start_id, records):
    """True when following parent_reality_id from start_id revisits/aself a reality.

    Each reality has at most one parent, so lineage is a chain. A repeated id
    (including start_id reached again) is a cycle and fails closed; an id whose
    parent is absent terminates the chain (resolution is checked separately).
    """
    seen = []
    current = start_id
    while current is not None:
        if current in seen:
            return True
        seen.append(current)
        entry = records.get(current)
        if entry is None:
            return False
        parent = entry[1].get("parent_reality_id")
        if not isinstance(parent, str):
            return False
        current = parent
    return False


def validate_paths(paths, schema_path=SCHEMA_PATH):
    """Validate a list of record file paths as one batch (schema + lineage law).

    Returns a dict of {path: [errors]} containing only paths with at least one error.

    An empty batch (zero records) is a zero-root state and raises ``ValueError``:
    exactly one parentless root reality is required, and zero records cannot
    satisfy it.
    """
    if not paths:
        raise ValueError(
            "validated reality set has no root reality: an empty "
            "registry/batch (zero records) is a zero-root state; exactly one "
            "parentless root reality is required"
        )
    schema = load_schema(schema_path)
    errors_by_path = {}
    seen_ids = {}
    records = {}

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

        reality_id = record.get("reality_id") if isinstance(record, dict) else None
        if isinstance(reality_id, str):
            if reality_id in seen_ids:
                errors.append(
                    f"reality_id '{reality_id}' duplicates {seen_ids[reality_id].name}"
                )
            else:
                seen_ids[reality_id] = path
                records[reality_id] = (path, record)

        if errors:
            errors_by_path[path] = errors

    # Exactly one structural root must exist in any validated set: the unique
    # admitted reality record that declares no parent_reality_id. A zero-root or
    # multi-root set is rejected.
    root_ids = [
        reality_id
        for reality_id, (_path, record) in records.items()
        if "parent_reality_id" not in record
    ]
    if records and len(root_ids) != 1:
        message = (
            "validated reality set has no root reality: exactly one "
            "parentless reality is required"
            if len(root_ids) == 0
            else "validated reality set has more than one parentless root reality"
        )
        for path, _record in records.values():
            errors_by_path.setdefault(path, []).append(message)

    # Lineage law, over the first (non-duplicate) record seen for each id,
    # independent of that record's own schema errors -- matching the
    # independent-checks posture used by the other registry validators.
    for reality_id, (path, record) in records.items():
        if "parent_reality_id" not in record:
            # This record is the structural root; it must not also declare a
            # parent (guaranteed by its absence above) and needs no further
            # lineage check.
            continue

        parent = record.get("parent_reality_id")
        if not isinstance(parent, str):
            errors_by_path.setdefault(path, []).append(
                "a non-root reality must declare exactly one parent_reality_id"
            )
            continue
        if parent not in records:
            errors_by_path.setdefault(path, []).append(
                f"parent_reality_id '{parent}' does not resolve to an admitted "
                "reality in this batch"
            )
        elif _has_parent_cycle(reality_id, records):
            errors_by_path.setdefault(path, []).append(
                f"parent lineage for '{reality_id}' contains a cycle"
            )

    return errors_by_path


USAGE = "usage: validate_realities.py <directory> [<directory> ...]"


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

    try:
        errors_by_path = validate_paths(paths)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

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
