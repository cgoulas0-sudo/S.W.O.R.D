#!/usr/bin/env python3
"""Validate EV2-08 Run foundation records.

Usage:
    python scripts/validate_runs.py \
        --scenarios <scenario-directory> \
        --encounters <encounter-directory> \
        <run-directory>

EV2-08 validates only Run occurrence structure and actor ownership:
- Run IDs are unique.
- Every Run resolves to one persisted Scenario.
- Every occurred Encounter resolves and belongs to that Scenario.
- Mutable-owned actors must also be historical participants.
- A mutable actor may be owned by at most one Run in the validated batch.
- Played/off-screen execution mode remains separate from parked/active control state.
- Every campaign_anchor.base_commit resolves to an actual Git commit reachable from canonical main history.

This validator intentionally does not implement Run closure/sync, off-screen
resolution, structured world deltas, conflict reconciliation, canon merge-back,
campaign-clock arithmetic, registry/locks, RAG, or real-data migration.
"""
import argparse
import json
import subprocess
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

RUN_SCHEMA_PATH = ROOT / "schemas" / "run.schema.json"
SCENARIO_SCHEMA_PATH = ROOT / "schemas" / "scenario.schema.json"
ENCOUNTER_SCHEMA_PATH = ROOT / "schemas" / "encounter.schema.json"


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


def _path_by_id(paths, id_field):
    result = {}
    for path in paths:
        try:
            record = _read_json_record(path)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        record_id = record.get(id_field) if isinstance(record, dict) else None
        if isinstance(record_id, str) and record_id not in result:
            result[record_id] = path
    return result


def _run_git(args, repo_root=ROOT):
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_object_type(object_id, repo_root=ROOT):
    """Return the Git object type for object_id, or None when it cannot resolve."""
    result = _run_git(["cat-file", "-t", object_id], repo_root)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip()


def _canonical_main_ref(repo_root=ROOT):
    """Return the canonical main ref available in this checkout, preferring origin/main."""
    for ref in ("refs/remotes/origin/main", "refs/heads/main"):
        result = _run_git(["rev-parse", "--verify", "--quiet", ref], repo_root)
        if result is not None and result.returncode == 0:
            return ref
    return None


def _is_reachable_from_canonical_main(commit_id, repo_root=ROOT):
    """Return True only when commit_id is an ancestor of canonical main."""
    canonical_ref = _canonical_main_ref(repo_root)
    if canonical_ref is None:
        return False
    result = _run_git(["merge-base", "--is-ancestor", commit_id, canonical_ref], repo_root)
    return result is not None and result.returncode == 0


def validate_paths(scenario_paths, encounter_paths, run_paths):
    scenario_schema = load_schema(SCENARIO_SCHEMA_PATH)
    encounter_schema = load_schema(ENCOUNTER_SCHEMA_PATH)
    run_schema = load_schema(RUN_SCHEMA_PATH)

    scenarios, scenario_errors = _read_batch(scenario_paths, scenario_schema, "scenario_id")
    encounters, encounter_errors = _read_batch(encounter_paths, encounter_schema, "encounter_id")
    runs, run_errors = _read_batch(run_paths, run_schema, "run_id")

    errors_by_path = {}
    for source in (scenario_errors, encounter_errors, run_errors):
        for path, errors in source.items():
            errors_by_path.setdefault(path, []).extend(errors)

    run_path_by_id = _path_by_id(run_paths, "run_id")
    mutable_owner_to_run = {}

    for run_id, record in runs.items():
        path = run_path_by_id[run_id]
        scenario_id = record["scenario_id"]

        base_commit = record["campaign_anchor"]["base_commit"]
        object_type = _git_object_type(base_commit)
        if object_type != "commit":
            detail = "does not resolve" if object_type is None else f"resolves to Git object type '{object_type}'"
            errors_by_path.setdefault(path, []).append(
                f"campaign_anchor.base_commit '{base_commit}' {detail}; expected an actual Git commit in this repository"
            )
        elif not _is_reachable_from_canonical_main(base_commit):
            errors_by_path.setdefault(path, []).append(
                f"campaign_anchor.base_commit '{base_commit}' is not reachable from canonical main history"
            )

        if scenario_id not in scenarios:
            errors_by_path.setdefault(path, []).append(
                f"scenario_id '{scenario_id}' does not resolve to a persisted Scenario"
            )

        for encounter_id in record["occurred_encounter_ids"]:
            encounter = encounters.get(encounter_id)
            if encounter is None:
                errors_by_path.setdefault(path, []).append(
                    f"occurred_encounter_id '{encounter_id}' does not resolve to a persisted Encounter"
                )
            elif encounter["scenario_id"] != scenario_id:
                errors_by_path.setdefault(path, []).append(
                    f"Encounter '{encounter_id}' belongs to Scenario '{encounter['scenario_id']}', "
                    f"not Run Scenario '{scenario_id}'"
                )

        participants = set(record["participant_entity_ids"])
        for entity_id in record["mutable_owner_entity_ids"]:
            if entity_id not in participants:
                errors_by_path.setdefault(path, []).append(
                    f"mutable owner '{entity_id}' must also appear in participant_entity_ids"
                )

            previous_run = mutable_owner_to_run.get(entity_id)
            if previous_run is not None:
                errors_by_path.setdefault(path, []).append(
                    f"mutable owner '{entity_id}' is already owned by Run '{previous_run}'"
                )
            else:
                mutable_owner_to_run[entity_id] = run_id

    return errors_by_path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--encounters", required=True)
    parser.add_argument("runs")
    args = parser.parse_args(argv)

    try:
        scenario_paths = load_records(args.scenarios)
        encounter_paths = load_records(args.encounters)
        run_paths = load_records(args.runs)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    errors_by_path = validate_paths(scenario_paths, encounter_paths, run_paths)
    for path, errors in errors_by_path.items():
        for error in errors:
            print(f"FAIL: {_display_path(path)}: {error}", file=sys.stderr)

    if errors_by_path:
        print(f"\n{len(errors_by_path)} record(s) failed validation.", file=sys.stderr)
        return 1

    print(
        f"OK: {len(scenario_paths)} Scenario, {len(encounter_paths)} Encounter, "
        f"{len(run_paths)} Run record(s) valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
