#!/usr/bin/env python3
"""Validate EV2-09A off-screen Run resolution proposals.

Usage:
    python scripts/validate_run_resolutions.py \
        --hooks <hook-directory> \
        --scenarios <scenario-directory> \
        --runs <run-directory> \
        <resolution-directory>

EV2-09A proposals are non-canonical. Validation proves that each proposal:
- resolves to one existing off-screen Run;
- derives Scenario and Primary Hook from that Run's anchored campaign revision;
- preserves the Run's exact campaign anchor and objective context snapshot;
- uses the approved d20/d6 outcome bands exactly;
- contains bounded consequence references only;
- cannot encode an automatic character-death consequence kind.

Canon reconciliation/merge-back remains EV2-09B.
"""
import argparse
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from offscreen_resolution import classify_resolution  # noqa: E402
from validate_runs import (  # noqa: E402
    _git_object_type,
    _is_reachable_from_canonical_main,
    _run_git,
)
from validate_entities import (  # noqa: E402
    _display_path,
    _parse_float_reject_overflow,
    _reject_duplicate_keys,
    _reject_non_json_constants,
    load_records,
)

HOOK_SCHEMA_PATH = ROOT / "schemas" / "hook.schema.json"
SCENARIO_SCHEMA_PATH = ROOT / "schemas" / "scenario.schema.json"
RUN_SCHEMA_PATH = ROOT / "schemas" / "run.schema.json"
RESOLUTION_SCHEMA_PATH = ROOT / "schemas" / "run_resolution.schema.json"

ANCHORED_RECORD_TYPES = {
    "Scenario": {
        "id_field": "scenario_id",
        "schema_path": "schemas/scenario.schema.json",
        "required_keys": frozenset(
            ("premise", "objective", "trigger_condition", "primary_hook_id")
        ),
    },
    "Hook": {
        "id_field": "hook_id",
        "schema_path": "schemas/hook.schema.json",
        "required_keys": frozenset(
            ("objective", "status", "activation_condition", "resolution_condition")
        ),
    },
}


def load_schema(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_json_text(text):
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constants,
        parse_float=_parse_float_reject_overflow,
    )


def _read_json_record(path):
    return _parse_json_text(path.read_text(encoding="utf-8"))


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
                errors.append(
                    f"{id_field} '{record_id}' duplicates {seen_ids[record_id].name}"
                )
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


def _repo_relative_path(path):
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _read_record_at_commit(path, commit_id):
    """Read one repository JSON record exactly as it existed at commit_id."""
    relative_path = _repo_relative_path(path)
    if relative_path is None:
        raise ValueError(
            f"source path '{path}' is outside this repository; anchored content cannot be attested"
        )
    return _read_repo_json_at_commit(relative_path, commit_id)


def _read_repo_json_at_commit(relative_path, commit_id):
    result = _run_git(["show", f"{commit_id}:{relative_path}"])
    if result is None or result.returncode != 0:
        raise ValueError(
            f"cannot read source path '{relative_path}' at anchored commit '{commit_id}'"
        )
    try:
        return _parse_json_text(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"source path '{relative_path}' is invalid JSON at anchored commit '{commit_id}': {exc}"
        ) from exc


def _anchored_json_paths(commit_id):
    """Return JSON paths from the anchored tree, independent of today's paths."""
    result = _run_git(["ls-tree", "-r", "--name-only", "-z", commit_id])
    if result is None or result.returncode != 0:
        raise ValueError(f"cannot enumerate anchored commit '{commit_id}'")
    return [path for path in result.stdout.split("\0") if path and path.endswith(".json")]


def _anchored_record_validators(commit_id):
    """Build record validators from schemas that existed at the anchored revision."""
    validators = {}
    for label, spec in ANCHORED_RECORD_TYPES.items():
        schema_path = spec["schema_path"]
        try:
            schema = _read_repo_json_at_commit(schema_path, commit_id)
            jsonschema.Draft202012Validator.check_schema(schema)
        except (ValueError, jsonschema.exceptions.SchemaError) as exc:
            raise ValueError(
                f"cannot load valid anchored {label} schema '{schema_path}' "
                f"at commit '{commit_id}': {exc}"
            ) from exc
        validators[label] = jsonschema.Draft202012Validator(schema)
    return validators


def _build_anchored_record_index(commit_id):
    """Index only records valid under the schemas from this campaign revision."""
    index = {label: {} for label in ANCHORED_RECORD_TYPES}
    validators = _anchored_record_validators(commit_id)

    for relative_path in _anchored_json_paths(commit_id):
        try:
            record = _read_repo_json_at_commit(relative_path, commit_id)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue

        for label, spec in ANCHORED_RECORD_TYPES.items():
            record_id = record.get(spec["id_field"])
            if (
                isinstance(record_id, str)
                and spec["required_keys"].issubset(record.keys())
                and validators[label].is_valid(record)
            ):
                index[label].setdefault(record_id, []).append(
                    (relative_path, record)
                )

    return index


def _find_record_in_index(index, commit_id, expected_id, label):
    """Resolve one stable record ID from a prebuilt anchored record index."""
    matches = index[label].get(expected_id, [])
    if not matches:
        raise ValueError(
            f"cannot resolve anchored {label} '{expected_id}' at commit '{commit_id}'"
        )
    if len(matches) > 1:
        paths = ", ".join(path for path, _ in matches)
        raise ValueError(
            f"anchored {label} '{expected_id}' is ambiguous at commit '{commit_id}': {paths}"
        )
    return matches[0][1]


def _context_ids(run, scenario, hook):
    participants = set(run.get("participant_entity_ids", []))
    related = set()
    locations = set(run.get("location_ids", []))
    for entity_id in [
        *scenario.get("related_entity_ids", []),
        *hook.get("related_entity_ids", []),
    ]:
        if entity_id.startswith("location:"):
            locations.add(entity_id)
        else:
            related.add(entity_id)
    related.update(participants)
    if run.get("party_id"):
        related.add(run["party_id"])
    return participants, related, locations


def _anchored_record(
    *, index, commit_id, expected_id, label, errors_by_path, resolution_path,
):
    try:
        return _find_record_in_index(index, commit_id, expected_id, label)
    except ValueError as exc:
        errors_by_path.setdefault(resolution_path, []).append(str(exc))
        return None


def validate_paths(hook_paths, scenario_paths, run_paths, resolution_paths):
    hook_schema = load_schema(HOOK_SCHEMA_PATH)
    scenario_schema = load_schema(SCENARIO_SCHEMA_PATH)
    run_schema = load_schema(RUN_SCHEMA_PATH)
    resolution_schema = load_schema(RESOLUTION_SCHEMA_PATH)

    hooks, hook_errors = _read_batch(hook_paths, hook_schema, "hook_id")
    scenarios, scenario_errors = _read_batch(scenario_paths, scenario_schema, "scenario_id")
    runs, run_errors = _read_batch(run_paths, run_schema, "run_id")
    resolutions, resolution_errors = _read_batch(
        resolution_paths, resolution_schema, "resolution_id"
    )

    errors_by_path = {}
    for source in (hook_errors, scenario_errors, run_errors, resolution_errors):
        for path, errors in source.items():
            errors_by_path.setdefault(path, []).extend(errors)

    resolution_path_by_id = _path_by_id(resolution_paths, "resolution_id")
    anchored_indexes = {}

    for resolution_id, record in resolutions.items():
        path = resolution_path_by_id[resolution_id]
        run = runs.get(record["run_id"])
        if run is None:
            errors_by_path.setdefault(path, []).append(
                f"run_id '{record['run_id']}' does not resolve to a persisted Run"
            )
            continue

        if run["execution_mode"] != "off_screen":
            errors_by_path.setdefault(path, []).append(
                f"Run '{record['run_id']}' is not off_screen"
            )
        if run["control_state"] != "not_applicable":
            errors_by_path.setdefault(path, []).append(
                f"Run '{record['run_id']}' off-screen control_state must be not_applicable"
            )

        base_commit = run["campaign_anchor"]["base_commit"]
        object_type = _git_object_type(base_commit)
        anchor_is_valid = False
        if object_type != "commit":
            detail = "does not resolve" if object_type is None else f"resolves to Git object type '{object_type}'"
            errors_by_path.setdefault(path, []).append(
                f"source Run campaign_anchor.base_commit '{base_commit}' {detail}; expected an actual Git commit in this repository"
            )
        elif not _is_reachable_from_canonical_main(base_commit):
            errors_by_path.setdefault(path, []).append(
                f"source Run campaign_anchor.base_commit '{base_commit}' is not reachable from canonical main history"
            )
        else:
            anchor_is_valid = True

        if record["scenario_id"] != run["scenario_id"]:
            errors_by_path.setdefault(path, []).append(
                f"scenario_id '{record['scenario_id']}' does not match Run Scenario '{run['scenario_id']}'"
            )

        scenario = scenarios.get(record["scenario_id"])
        hook = hooks.get(record["primary_hook_id"])

        if anchor_is_valid:
            try:
                if base_commit not in anchored_indexes:
                    anchored_indexes[base_commit] = _build_anchored_record_index(
                        base_commit
                    )
                anchored_index = anchored_indexes[base_commit]
            except ValueError as exc:
                errors_by_path.setdefault(path, []).append(str(exc))
                continue

            anchored_scenario = _anchored_record(
                index=anchored_index,
                commit_id=base_commit,
                expected_id=record["scenario_id"],
                label="Scenario",
                errors_by_path=errors_by_path,
                resolution_path=path,
            )
            if anchored_scenario is None:
                continue
            if record["primary_hook_id"] != anchored_scenario.get("primary_hook_id"):
                errors_by_path.setdefault(path, []).append(
                    f"primary_hook_id '{record['primary_hook_id']}' does not match anchored Scenario Primary Hook '{anchored_scenario.get('primary_hook_id')}'"
                )
                continue
            anchored_hook = _anchored_record(
                index=anchored_index,
                commit_id=base_commit,
                expected_id=record["primary_hook_id"],
                label="Hook",
                errors_by_path=errors_by_path,
                resolution_path=path,
            )
            if anchored_hook is None:
                continue
            scenario = anchored_scenario
            hook = anchored_hook
        else:
            if scenario is None:
                errors_by_path.setdefault(path, []).append(
                    f"scenario_id '{record['scenario_id']}' does not resolve to a persisted Scenario"
                )
                continue
            if hook is None:
                errors_by_path.setdefault(path, []).append(
                    f"primary_hook_id '{record['primary_hook_id']}' does not resolve to a persisted Hook"
                )
                continue

        if record["campaign_anchor"] != run["campaign_anchor"]:
            errors_by_path.setdefault(path, []).append(
                "campaign_anchor must exactly match the source Run campaign_anchor"
            )

        expected_context = {
            "scenario_objective": scenario["objective"],
            "hook_objective": hook["objective"],
        }
        if record["objective_context"] != expected_context:
            errors_by_path.setdefault(path, []).append(
                "objective_context must exactly snapshot the anchored Scenario and Primary Hook objectives"
            )

        try:
            expected_outcome, expected_severity = classify_resolution(
                record["primary_roll"], record.get("severity_roll")
            )
        except ValueError as exc:
            errors_by_path.setdefault(path, []).append(str(exc))
        else:
            if record["outcome_band"] != expected_outcome:
                errors_by_path.setdefault(path, []).append(
                    f"outcome_band '{record['outcome_band']}' does not match primary_roll {record['primary_roll']} -> '{expected_outcome}'"
                )
            if expected_severity is not None and record.get("severity_band") != expected_severity:
                errors_by_path.setdefault(path, []).append(
                    f"severity_band '{record.get('severity_band')}' does not match severity_roll {record.get('severity_roll')} -> '{expected_severity}'"
                )

        participants, allowed_related, allowed_locations = _context_ids(run, scenario, hook)
        seen_consequence_ids = set()
        for consequence in record["proposed_consequences"]:
            consequence_id = consequence["consequence_id"]
            if consequence_id in seen_consequence_ids:
                errors_by_path.setdefault(path, []).append(
                    f"consequence_id '{consequence_id}' is duplicated within resolution '{resolution_id}'"
                )
            seen_consequence_ids.add(consequence_id)
            related_ids = set(consequence["related_entity_ids"])
            location_ids = set(consequence["location_ids"])
            unknown_related = sorted(related_ids - allowed_related)
            if unknown_related:
                errors_by_path.setdefault(path, []).append(
                    f"consequence '{consequence_id}' references entity IDs outside Run/Scenario/Hook context: {', '.join(unknown_related)}"
                )
            unknown_locations = sorted(location_ids - allowed_locations)
            if unknown_locations:
                errors_by_path.setdefault(path, []).append(
                    f"consequence '{consequence_id}' references locations outside Run/Scenario/Hook context: {', '.join(unknown_locations)}"
                )
            if consequence["scope"] == "participant":
                nonparticipants = sorted(related_ids - participants)
                if nonparticipants:
                    errors_by_path.setdefault(path, []).append(
                        f"participant-scoped consequence '{consequence_id}' targets non-participants: {', '.join(nonparticipants)}"
                    )

    return errors_by_path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks", required=True)
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--runs", required=True)
    parser.add_argument("resolutions")
    args = parser.parse_args(argv)
    try:
        hook_paths = load_records(args.hooks)
        scenario_paths = load_records(args.scenarios)
        run_paths = load_records(args.runs)
        resolution_paths = load_records(args.resolutions)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    errors_by_path = validate_paths(hook_paths, scenario_paths, run_paths, resolution_paths)
    for path, errors in errors_by_path.items():
        for error in errors:
            print(f"FAIL: {_display_path(path)}: {error}", file=sys.stderr)
    if errors_by_path:
        print(f"\n{len(errors_by_path)} record(s) failed validation.", file=sys.stderr)
        return 1
    print(
        f"OK: {len(hook_paths)} Hook, {len(scenario_paths)} Scenario, {len(run_paths)} Run, {len(resolution_paths)} resolution proposal(s) valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
