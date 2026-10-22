#!/usr/bin/env python3
"""Validate Entity V2 relationship instance records.

Usage:
    python scripts/validate_relationship_instances.py --kinds <directory> <instance-directory> [<instance-directory> ...]

Each relationship instance is validated against schemas/relationship_instance.schema.json.
The supplied relationship-kind registry must itself be valid. Across all instance records
passed in together, this validator also enforces:
  - relationship_id uniqueness;
  - kind must exist in the registry;
  - source/target entity types must obey the kind's optional endpoint restrictions;
  - at most one active instance for the same (source_id, kind, target_id), where active
    means ended_at is absent.

No campaign-clock arithmetic is performed. started_at/ended_at are opaque established
labels in this foundation patch; their ordering/semantics belong to later work.
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
from validate_relationship_kinds import validate_paths as validate_kind_paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "relationship_instance.schema.json"


def load_schema(schema_path=SCHEMA_PATH):
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def validate_record(record, schema):
    """Return human-readable schema errors for one instance record."""
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


def _load_kind_registry(kind_paths):
    """Return {kind: record} after proving the supplied registry batch is valid."""
    kind_errors = validate_kind_paths(kind_paths)
    if kind_errors:
        return None, kind_errors

    registry = {}
    for path in kind_paths:
        try:
            record = _read_json_record(path)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return None, {path: [f"kind registry could not be loaded: {exc}"]}
        registry[record["kind"]] = record
    return registry, {}


def _entity_type(entity_id):
    if not isinstance(entity_id, str) or ":" not in entity_id:
        return None
    return entity_id.split(":", 1)[0]


def validate_paths(paths, kind_paths, schema_path=SCHEMA_PATH):
    """Validate relationship instances as one batch against one valid kind registry."""
    schema = load_schema(schema_path)
    errors_by_path = {}
    registry, kind_errors = _load_kind_registry(kind_paths)
    if kind_errors:
        for path, errors in kind_errors.items():
            errors_by_path[path] = [f"kind registry: {error}" for error in errors]
        return errors_by_path

    seen_ids = {}
    active_triples = {}

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
            relationship_id = record.get("relationship_id")
            source_id = record.get("source_id")
            kind = record.get("kind")
            target_id = record.get("target_id")

            if isinstance(relationship_id, str):
                if relationship_id in seen_ids:
                    errors.append(
                        f"relationship_id '{relationship_id}' duplicates {seen_ids[relationship_id].name}"
                    )
                else:
                    seen_ids[relationship_id] = path

            kind_record = registry.get(kind) if isinstance(kind, str) else None
            if isinstance(kind, str) and kind_record is None:
                errors.append(f"kind '{kind}' is not registered in the supplied relationship-kind registry")

            if kind_record is not None:
                source_type = _entity_type(source_id)
                target_type = _entity_type(target_id)
                allowed_sources = kind_record.get("allowed_source_types")
                allowed_targets = kind_record.get("allowed_target_types")

                if (
                    source_type is not None
                    and isinstance(allowed_sources, list)
                    and source_type not in allowed_sources
                ):
                    errors.append(
                        f"source_id type '{source_type}' is not allowed for kind '{kind}'"
                    )
                if (
                    target_type is not None
                    and isinstance(allowed_targets, list)
                    and target_type not in allowed_targets
                ):
                    errors.append(
                        f"target_id type '{target_type}' is not allowed for kind '{kind}'"
                    )

                if (
                    "ended_at" not in record
                    and isinstance(source_id, str)
                    and isinstance(kind, str)
                    and isinstance(target_id, str)
                ):
                    triple = (source_id, kind, target_id)
                    if triple in active_triples:
                        errors.append(
                            "active relationship duplicates "
                            f"{active_triples[triple].name} for "
                            f"(source_id={source_id!r}, kind={kind!r}, target_id={target_id!r})"
                        )
                    else:
                        active_triples[triple] = path

        if errors:
            errors_by_path[path] = errors

    return errors_by_path


USAGE = (
    "usage: validate_relationship_instances.py "
    "--kinds <directory> <instance-directory> [<instance-directory> ...]"
)


def main(argv):
    args = list(argv)
    if len(args) < 3 or args[0] != "--kinds":
        print(USAGE, file=sys.stderr)
        return 2

    kind_directory = args[1]
    instance_directories = args[2:]

    try:
        kind_paths = load_records(kind_directory)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    paths = []
    for directory in instance_directories:
        try:
            paths.extend(load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    errors_by_path = validate_paths(paths, kind_paths)

    for path, errors in errors_by_path.items():
        for error in errors:
            print(f"FAIL: {_display_path(path)}: {error}", file=sys.stderr)

    if errors_by_path:
        print(f"\n{len(errors_by_path)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(f"OK: {len(paths)} relationship instance record(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
