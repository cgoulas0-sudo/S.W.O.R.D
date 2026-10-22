#!/usr/bin/env python3
"""Validate EV2-07 Scenario + Encounter foundation records.

Usage:
    python scripts/validate_scenarios_encounters.py \
        --hooks <hook-directory> \
        --scenarios <scenario-directory> \
        --encounters <encounter-directory>

EV2-07 validates only prepared-story structure:
- Scenario IDs are unique.
- Every Scenario has exactly one persisted Primary Hook.
- Related Hooks, when present, also resolve to persisted Hooks.
- A Scenario cannot repeat its Primary Hook as a Related Hook.
- Encounter IDs are unique.
- Every Encounter belongs to one persisted Scenario.

This validator intentionally does not implement Run occurrence state, outcomes,
rewards/consequences persistence, campaign time, RAG, or real-data migration.
"""
import argparse
import json
import sys
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_entities import (  # noqa: E402
    _display_path,
    _parse_float_reject_overflow,
    _reject_duplicate_keys,
    _reject_non_json_constants,
    load_records,
)

SCENARIO_SCHEMA_PATH = ROOT / "schemas" / "scenario.schema.json"
ENCOUNTER_SCHEMA_PATH = ROOT / "schemas" / "encounter.schema.json"
HOOK_SCHEMA_PATH = ROOT / "schemas" / "hook.schema.json"


def load_schema(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_json_record(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constants,
        parse_float=_parse_float_reject_overflow,
    )


def _schema_errors(record, schema):
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=str)
    ]


def _read_batch(paths, schema, id_field):
    errors_by_path = {}
    records = {}
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

        errors = _schema_errors(record, schema)
        record_id = record.get(id_field) if isinstance(record, dict) else None

        if isinstance(record_id, str):
            if record_id in seen_ids:
                errors.append(f"{id_field} '{record_id}' duplicates {seen_ids[record_id].name}")
            else:
                seen_ids[record_id] = path
                if not errors:
                    records[record_id] = record

        if errors:
            errors_by_path[path] = errors

    return records, errors_by_path


def validate_paths(hook_paths, scenario_paths, encounter_paths):
    hook_schema = load_schema(HOOK_SCHEMA_PATH)
    scenario_schema = load_schema(SCENARIO_SCHEMA_PATH)
    encounter_schema = load_schema(ENCOUNTER_SCHEMA_PATH)

    hooks, hook_errors = _read_batch(hook_paths, hook_schema, "hook_id")
    scenarios, scenario_errors = _read_batch(scenario_paths, scenario_schema, "scenario_id")
    encounters, encounter_errors = _read_batch(encounter_paths, encounter_schema, "encounter_id")

    errors_by_path = {}
    for source in (hook_errors, scenario_errors, encounter_errors):
        for path, errors in source.items():
            errors_by_path.setdefault(path, []).extend(errors)

    scenario_path_by_id = {}
    for path in scenario_paths:
        try:
            record = _read_json_record(path)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        scenario_id = record.get("scenario_id") if isinstance(record, dict) else None
        if isinstance(scenario_id, str) and scenario_id not in scenario_path_by_id:
            scenario_path_by_id[scenario_id] = path

    for scenario_id, record in scenarios.items():
        path = scenario_path_by_id[scenario_id]
        primary = record["primary_hook_id"]
        related = record["related_hook_ids"]
        if primary not in hooks:
            errors_by_path.setdefault(path, []).append(
                f"primary_hook_id '{primary}' does not resolve to a persisted Hook"
            )
        for hook_id in related:
            if hook_id not in hooks:
                errors_by_path.setdefault(path, []).append(
                    f"related_hook_id '{hook_id}' does not resolve to a persisted Hook"
                )
        if primary in related:
            errors_by_path.setdefault(path, []).append(
                f"primary_hook_id '{primary}' must not also appear in related_hook_ids"
            )

    encounter_path_by_id = {}
    for path in encounter_paths:
        try:
            record = _read_json_record(path)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        encounter_id = record.get("encounter_id") if isinstance(record, dict) else None
        if isinstance(encounter_id, str) and encounter_id not in encounter_path_by_id:
            encounter_path_by_id[encounter_id] = path

    for encounter_id, record in encounters.items():
        path = encounter_path_by_id[encounter_id]
        scenario_id = record["scenario_id"]
        if scenario_id not in scenarios:
            errors_by_path.setdefault(path, []).append(
                f"scenario_id '{scenario_id}' does not resolve to a persisted Scenario"
            )

    return errors_by_path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks", required=True)
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--encounters", required=True)
    args = parser.parse_args(argv)

    try:
        hook_paths = load_records(args.hooks)
        scenario_paths = load_records(args.scenarios)
        encounter_paths = load_records(args.encounters)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    errors_by_path = validate_paths(hook_paths, scenario_paths, encounter_paths)
    for path, errors in errors_by_path.items():
        for error in errors:
            print(f"FAIL: {_display_path(path)}: {error}", file=sys.stderr)

    if errors_by_path:
        print(f"\n{len(errors_by_path)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(
        f"OK: {len(hook_paths)} Hook, {len(scenario_paths)} Scenario, "
        f"{len(encounter_paths)} Encounter record(s) valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
