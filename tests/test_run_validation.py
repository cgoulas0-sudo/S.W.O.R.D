import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

import validate_runs  # noqa: E402
from validate_entities import load_records  # noqa: E402
from validate_runs import RUN_SCHEMA_PATH, load_schema, main, validate_paths  # noqa: E402

SCENARIOS = FIX / "scenarios" / "valid"
ENCOUNTERS = FIX / "encounters" / "valid"
RUNS = FIX / "runs" / "valid"

# The reusable Run-anchor proof must not depend on a concrete RHC ancestor
# commit: a fixed RHC SHA is impossible fixture data inside a fresh independent
# repository that has no RHC ancestry. Each test therefore builds its own
# temporary synthetic Git history (a `main` branch with one commit) and points
# the validator's Git seam at it, while the Run records carry that synthetic
# commit as their campaign anchor.
_ANCHOR = None
_SYNTHETIC_RUNS = None


def _init_synthetic_repo(repo):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Anchor",
        "GIT_AUTHOR_EMAIL": "synthetic-anchor@example.invalid",
        "GIT_COMMITTER_NAME": "Synthetic Anchor",
        "GIT_COMMITTER_EMAIL": "synthetic-anchor@example.invalid",
    }
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    (repo / "synthetic-anchor.txt").write_text("synthetic anchor\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "-A"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic anchor"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _redirected_run_git(repo):
    def run_git(args, repo_root=None):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    return run_git


@pytest.fixture(autouse=True)
def _synthetic_history(tmp_path, monkeypatch):
    global _ANCHOR, _SYNTHETIC_RUNS
    repo = tmp_path / "synthetic-git"
    _ANCHOR = _init_synthetic_repo(repo)
    monkeypatch.setattr(validate_runs, "_run_git", _redirected_run_git(repo))
    _SYNTHETIC_RUNS = tmp_path / "synthetic-runs"
    _SYNTHETIC_RUNS.mkdir()
    for source in load_records(RUNS):
        record = json.loads(source.read_text(encoding="utf-8"))
        record["campaign_anchor"]["base_commit"] = _ANCHOR
        (_SYNTHETIC_RUNS / source.name).write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    yield _ANCHOR


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _base():
    record = _load(RUNS / "01-run.json")
    record["campaign_anchor"]["base_commit"] = _ANCHOR
    return record


def _paths(run_paths=None):
    return load_records(SCENARIOS), load_records(ENCOUNTERS), run_paths or load_records(_SYNTHETIC_RUNS)


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema(RUN_SCHEMA_PATH))


def test_valid_fixture_batch_passes():
    assert validate_paths(*_paths()) == {}


def test_valid_fixtures_cover_played_active_parked_and_off_screen():
    records = [_load(path) for path in load_records(RUNS)]
    pairs = {(r["execution_mode"], r["control_state"]) for r in records}
    assert pairs == {("played", "active"), ("played", "parked"), ("off_screen", "not_applicable")}


def test_duplicate_run_id_rejected(tmp_path):
    a = _write(tmp_path, "a.json", {**_base(), "run_id": "R10"})
    b = _write(tmp_path, "b.json", {**_base(), "run_id": "R10", "outcome_summary": "Different record"})
    errors = validate_paths(*_paths([a, b]))
    assert any("duplicates" in e for e in errors[b])


def test_run_id_requires_r_plus_at_least_two_digits_and_strict_end():
    schema = load_schema(RUN_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base()
    for bad in ("R1", "run-1", "R01\n", "R01\r", "R01 "):
        assert list(validator.iter_errors({**base, "run_id": bad})), bad


def test_played_run_cannot_use_not_applicable_control_state():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "control_state": "not_applicable"}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_off_screen_run_requires_not_applicable_control_state():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "execution_mode": "off_screen", "control_state": "active"}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_unknown_scenario_rejected(tmp_path):
    path = _write(tmp_path, "run.json", {**_base(), "scenario_id": "S99", "occurred_encounter_ids": []})
    errors = validate_paths(*_paths([path]))
    assert any("scenario_id" in e and "does not resolve" in e for e in errors[path])


def test_unknown_encounter_rejected(tmp_path):
    path = _write(tmp_path, "run.json", {**_base(), "occurred_encounter_ids": ["E99"]})
    errors = validate_paths(*_paths([path]))
    assert any("occurred_encounter_id" in e and "does not resolve" in e for e in errors[path])


def test_encounter_must_belong_to_runs_scenario(tmp_path):
    path = _write(tmp_path, "run.json", {**_base(), "occurred_encounter_ids": ["E01"]})
    errors = validate_paths(*_paths([path]))
    assert any("not Run Scenario" in e for e in errors[path])


def test_mutable_owner_must_also_be_historical_participant(tmp_path):
    path = _write(tmp_path, "run.json", {**_base(), "mutable_owner_entity_ids": ["character:not-participant"]})
    errors = validate_paths(*_paths([path]))
    assert any("must also appear" in e for e in errors[path])


def test_same_actor_cannot_have_two_mutable_run_owners(tmp_path):
    a = _write(tmp_path, "a.json", {**_base(), "run_id": "R10", "mutable_owner_entity_ids": ["character:test-hero"]})
    b = _write(tmp_path, "b.json", {**_base(), "run_id": "R11", "mutable_owner_entity_ids": ["character:test-hero"]})
    errors = validate_paths(*_paths([a, b]))
    assert any("already owned" in e for e in errors[b])


def test_handoff_preserves_old_participation_without_old_mutable_ownership(tmp_path):
    old = _write(tmp_path, "old.json", {
        **_base(),
        "run_id": "R20",
        "control_state": "parked",
        "participant_entity_ids": ["character:test-hero"],
        "mutable_owner_entity_ids": [],
    })
    new = _write(tmp_path, "new.json", {
        **_base(),
        "run_id": "R21",
        "participant_entity_ids": ["character:test-hero"],
        "mutable_owner_entity_ids": ["character:test-hero"],
    })
    assert validate_paths(*_paths([old, new])) == {}


def test_campaign_anchor_requires_exact_40_hex_commit():
    schema = load_schema(RUN_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base()
    for bad in ("abc", "G"*40, "a"*39, "a"*40 + "\n"):
        record = {**base, "campaign_anchor": {**base["campaign_anchor"], "base_commit": bad}}
        assert list(validator.iter_errors(record)), bad


def test_campaign_anchor_time_must_be_nonblank():
    schema = load_schema(RUN_SCHEMA_PATH)
    base = _base()
    record = {**base, "campaign_anchor": {**base["campaign_anchor"], "campaign_time": "   "}}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_participant_ids_are_actor_types_only():
    schema = load_schema(RUN_SCHEMA_PATH)
    base = _base()
    for bad in ("location:test", "party:test", "item:test"):
        record = {**base, "participant_entity_ids": [bad], "mutable_owner_entity_ids": []}
        assert list(jsonschema.Draft202012Validator(schema).iter_errors(record)), bad


def test_location_list_may_be_empty_when_location_is_not_established():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "location_ids": []}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record)) == []


def test_party_id_is_optional():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = _base()
    record.pop("party_id")
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record)) == []


def test_outcome_summary_if_present_must_be_nonblank():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "outcome_summary": "   "}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_direct_hook_field_is_rejected():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "hook_id": "H01"}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_structured_world_delta_is_rejected():
    schema = load_schema(RUN_SCHEMA_PATH)
    record = {**_base(), "world_changes": []}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_cli_valid_fixture_batch(capsys):
    code = main([
        "--scenarios", str(SCENARIOS),
        "--encounters", str(ENCOUNTERS),
        str(_SYNTHETIC_RUNS),
    ])
    assert code == 0
    assert "OK: 2 Scenario, 4 Encounter, 3 Run" in capsys.readouterr().out


def test_duplicate_json_key_is_rejected(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(
        '{"run_id":"R30","run_id":"R31","execution_mode":"played","control_state":"active",'
        '"scenario_id":"S01","occurred_encounter_ids":[],"participant_entity_ids":["character:test"],'
        '"mutable_owner_entity_ids":["character:test"],"location_ids":[],'
        '"campaign_anchor":{"base_commit":"18bebc813f1af0a8478b97654bd86885e2a5bc25","campaign_time":"Day 1"}}',
        encoding="utf-8",
    )
    errors = validate_paths(*_paths([path]))
    assert any("duplicate key" in e for e in errors[path])


def test_invalid_utf8_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'{"run_id":"R30","x":"\xff"}')
    errors = validate_paths(*_paths([path]))
    assert any("invalid UTF-8" in e for e in errors[path])
