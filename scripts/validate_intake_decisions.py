#!/usr/bin/env python3
"""Validate Canon Intake decision records against CI-01 candidates (CI-02).

Usage:
    python scripts/validate_intake_decisions.py <candidates-directory> <decision-directory> [<decision-directory> ...]

The first directory holds CI-01 candidate records; every following directory
holds CI-02 decision records that together form ONE validated decision set.

Every *.json decision record is validated against
schemas/intake_decision.schema.json, then the following cross-record rules
of the CI-02 contract are enforced over the whole set (all fail closed):

- decision_id must stay unique across the decision set (deterministic
  duplicate/replay detection at the contract layer);
- at most one decision per referenced candidate_id may exist in the set,
  whether the outcomes agree or conflict;
- the referenced candidate_id must resolve to a valid CI-01 candidate in
  the candidate batch;
- only a candidate currently represented as classified is decision-eligible.

The candidate batch is itself validated by the CI-01 contract first, so an
invalid candidate batch fails closed. Candidates are read-only inputs: this
validator performs no candidate mutation, no collision/re-import detection,
no promotion, no canon/runtime write, and no durable cross-run idempotency
storage (later Canon Intake gates and the existing Save Gateway).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_entities as shared  # noqa: E402
import validate_intake_candidates as candidates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "intake_decision.schema.json"

READ_HOOKS = candidates.READ_HOOKS


def load_schema(schema_path=SCHEMA_PATH):
    """Return the parsed intake-decision JSON Schema."""
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    return candidates.validate_record(record, schema)


def read_record(path):
    """Read one JSON record through the shared fail-closed parse hooks."""
    return candidates.read_record(path)


def eligible_candidates(candidate_paths, candidate_failures):
    """Return {candidate_id: status} for candidates usable as decision targets.

    Only candidates with no CI-01 validation failure at all (schema-valid and
    batch-unique) may be referenced, so an invalid candidate batch cannot be
    silently consumed by decisions.
    """
    eligible = {}
    for path in candidate_paths:
        if path in candidate_failures:
            continue
        record = read_record(path)
        eligible[record["candidate_id"]] = record["status"]
    return eligible


def validate_paths(candidate_paths, decision_paths, schema_path=SCHEMA_PATH):
    """Validate one decision set against one candidate batch.

    Returns (candidate_failures, decision_failures): dicts {path: [errors]}
    containing only paths with at least one error.
    """
    schema = load_schema(schema_path)

    candidate_failures = candidates.validate_paths(candidate_paths)
    eligible = eligible_candidates(candidate_paths, candidate_failures)

    decision_failures = {}
    seen_decision_ids = {}
    seen_candidate_ids = {}

    for path in decision_paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            decision_failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            decision_failures[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)

        decision_id = record.get("decision_id") if isinstance(record, dict) else None
        candidate_id = record.get("candidate_id") if isinstance(record, dict) else None

        if isinstance(decision_id, str):
            if decision_id in seen_decision_ids:
                errors.append(
                    f"decision_id '{decision_id}' duplicates "
                    f"{seen_decision_ids[decision_id].name}"
                )
            else:
                seen_decision_ids[decision_id] = path

        if isinstance(candidate_id, str):
            if candidate_id in seen_candidate_ids:
                errors.append(
                    f"candidate_id '{candidate_id}' already has a decision in "
                    f"this decision set ({seen_candidate_ids[candidate_id].name}); "
                    f"duplicate and replay decisions fail closed"
                )
            else:
                seen_candidate_ids[candidate_id] = path

            if candidate_id not in eligible:
                errors.append(
                    f"candidate_id '{candidate_id}' does not resolve to a valid "
                    f"CI-01 candidate in the candidate batch"
                )
            elif eligible[candidate_id] != "classified":
                errors.append(
                    f"candidate_id '{candidate_id}' is '{eligible[candidate_id]}'; "
                    f"only classified candidates are decision-eligible"
                )

        if errors:
            decision_failures[path] = errors

    return candidate_failures, decision_failures


def main(argv):
    if len(argv) < 2:
        print(
            "usage: validate_intake_decisions.py "
            "<candidates-directory> <decision-directory> [<decision-directory> ...]",
            file=sys.stderr,
        )
        return 2

    try:
        candidate_paths = shared.load_records(argv[0])
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    decision_paths = []
    for directory in argv[1:]:
        try:
            decision_paths.extend(shared.load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    candidate_failures, decision_failures = validate_paths(
        candidate_paths, decision_paths
    )

    for failures in (candidate_failures, decision_failures):
        for path, errors in failures.items():
            shown = shared._display_path(path)
            for error in errors:
                print(f"FAIL: {shown}: {error}", file=sys.stderr)

    if candidate_failures or decision_failures:
        total = len(candidate_failures) + len(decision_failures)
        print(f"\n{total} record(s) failed validation.", file=sys.stderr)
        return 1

    print(
        f"OK: {len(candidate_paths)} Canon Intake candidate record(s) and "
        f"{len(decision_paths)} Canon Intake decision record(s) valid as one "
        f"decision set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
