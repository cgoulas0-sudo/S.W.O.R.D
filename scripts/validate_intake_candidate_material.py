#!/usr/bin/env python3
"""Validate Canon Intake candidate material envelopes against CI-01 candidates (CI-02.1).

Usage:
    python scripts/validate_intake_candidate_material.py <candidates-directory> <material-directory> [<material-directory> ...]

The first directory holds CI-01 candidate records; every following directory
holds CI-02.1 material envelopes that together form ONE validated material
set.

Every *.json material record is validated against
schemas/intake_candidate_material.schema.json, then the following
cross-record rules of the CI-02.1 contract are enforced over the whole set
(all fail closed):

- the referenced candidate_id must resolve to a valid CI-01 candidate in the
  candidate batch;
- at most one material envelope per candidate_id may exist in the set
  (deterministic duplicate detection at the contract layer).

The candidate batch is itself validated by the CI-01 contract first, so an
invalid candidate batch fails closed. Candidates are read-only inputs: this
validator performs no candidate or material mutation, no collision/re-import
detection, no decision, no promotion, and no persistence route (later Canon
Intake gates and the existing Save Gateway).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_entities as shared  # noqa: E402
import validate_intake_candidates as candidates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "intake_candidate_material.schema.json"

READ_HOOKS = candidates.READ_HOOKS


def load_schema(schema_path=SCHEMA_PATH):
    """Return the parsed candidate-material JSON Schema."""
    return candidates.load_schema(schema_path)


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    return candidates.validate_record(record, schema)


def read_record(path):
    """Read one JSON record through the shared fail-closed parse hooks."""
    return candidates.read_record(path)


def referenceable_candidates(candidate_paths, candidate_failures):
    """Return the set of candidate_ids usable as material references.

    Only candidates with no CI-01 validation failure at all (schema-valid and
    batch-unique) may be referenced, so an invalid candidate batch cannot be
    silently consumed by material envelopes.
    """
    referenceable = set()
    for path in candidate_paths:
        if path in candidate_failures:
            continue
        record = read_record(path)
        referenceable.add(record["candidate_id"])
    return referenceable


def validate_paths(candidate_paths, material_paths, schema_path=SCHEMA_PATH):
    """Validate one material set against one candidate batch.

    Returns (candidate_failures, material_failures): dicts {path: [errors]}
    containing only paths with at least one error.
    """
    schema = load_schema(schema_path)

    candidate_failures = candidates.validate_paths(candidate_paths)
    referenceable = referenceable_candidates(candidate_paths, candidate_failures)

    material_failures = {}
    seen_candidate_ids = {}

    for path in material_paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            material_failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            material_failures[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)

        candidate_id = record.get("candidate_id") if isinstance(record, dict) else None

        if isinstance(candidate_id, str):
            if candidate_id in seen_candidate_ids:
                errors.append(
                    f"candidate_id '{candidate_id}' already has a material "
                    f"envelope in this material set "
                    f"({seen_candidate_ids[candidate_id].name}); duplicate "
                    f"material envelopes fail closed"
                )
            else:
                seen_candidate_ids[candidate_id] = path

            if candidate_id not in referenceable:
                errors.append(
                    f"candidate_id '{candidate_id}' does not resolve to a valid "
                    f"CI-01 candidate in the candidate batch"
                )

        if errors:
            material_failures[path] = errors

    return candidate_failures, material_failures


def main(argv):
    if len(argv) < 2:
        print(
            "usage: validate_intake_candidate_material.py "
            "<candidates-directory> <material-directory> [<material-directory> ...]",
            file=sys.stderr,
        )
        return 2

    try:
        candidate_paths = shared.load_records(argv[0])
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    material_paths = []
    for directory in argv[1:]:
        try:
            material_paths.extend(shared.load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    candidate_failures, material_failures = validate_paths(
        candidate_paths, material_paths
    )

    for failures in (candidate_failures, material_failures):
        for path, errors in failures.items():
            shown = shared._display_path(path)
            for error in errors:
                print(f"FAIL: {shown}: {error}", file=sys.stderr)

    if candidate_failures or material_failures:
        total = len(candidate_failures) + len(material_failures)
        print(f"\n{total} record(s) failed validation.", file=sys.stderr)
        return 1

    print(
        f"OK: {len(candidate_paths)} Canon Intake candidate record(s) and "
        f"{len(material_paths)} Canon Intake candidate material record(s) valid "
        f"as one material set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
