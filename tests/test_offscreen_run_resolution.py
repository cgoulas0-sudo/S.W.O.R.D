import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

import validate_runs  # noqa: E402
import validate_run_resolutions  # noqa: E402
from offscreen_resolution import (  # noqa: E402
    build_resolution_proposal,
    classify_primary_roll,
    classify_resolution,
    classify_severity_roll,
)
from validate_entities import load_records  # noqa: E402
from validate_run_resolutions import (  # noqa: E402
    RESOLUTION_SCHEMA_PATH,
    load_schema,
    main,
    validate_paths,
)

HOOKS = FIX / "hooks" / "valid"
SCENARIOS = FIX / "scenarios" / "valid"
RUNS = FIX / "runs" / "valid"
RESOLUTIONS = FIX / "run_resolutions" / "valid"

# Reusable Git-anchor proofs must not depend on a concrete RHC ancestor commit:
# a fixed RHC SHA is impossible fixture data inside a fresh independent
# repository that has no RHC ancestry. Each test builds its own temporary
# synthetic Git history (a `main` branch whose first commit carries the
# reusable Scenario/Hook records and their schemas) and points the validator's
# Git seam at it; the anchored Run and resolution records carry that synthetic
# commit, so every anchored read resolves against a real, reachable, test-local
# commit instead of RHC history.
SYNTHETIC_HISTORY_FILES = (
    "schemas/scenario.schema.json",
    "schemas/hook.schema.json",
    "tests/fixtures/scenarios/valid/01-scenario.json",
    "tests/fixtures/scenarios/valid/02-scenario.json",
    "tests/fixtures/hooks/valid/01-dormant.json",
    "tests/fixtures/hooks/valid/02-active.json",
    "tests/fixtures/hooks/valid/03-resolved.json",
    "tests/fixtures/hooks/valid/04-retired.json",
)

_ANCHOR = None
_SYNTHETIC_RUNS = None
_SYNTHETIC_RESOLUTIONS = None


def _init_synthetic_repo(repo, relative_paths):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Anchor",
        "GIT_AUTHOR_EMAIL": "synthetic-anchor@example.invalid",
        "GIT_COMMITTER_NAME": "Synthetic Anchor",
        "GIT_COMMITTER_EMAIL": "synthetic-anchor@example.invalid",
    }

    def git(*args, check=True):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=check, capture_output=True, text=True, env=env,
        )

    repo.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main")
    for relative in relative_paths:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic anchor")
    return git("rev-parse", "HEAD").stdout.strip()


def _redirected_run_git(repo):
    def run_git(args, repo_root=None):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False, capture_output=True, text=True, timeout=30,
        )

    return run_git


def _anchored_records(source_dir, target_dir):
    target_dir.mkdir()
    paths = []
    for source in load_records(source_dir):
        record = json.loads(source.read_text(encoding="utf-8"))
        record["campaign_anchor"]["base_commit"] = _ANCHOR
        path = target_dir / source.name
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


@pytest.fixture(autouse=True)
def _synthetic_history(tmp_path, monkeypatch):
    global _ANCHOR, _SYNTHETIC_RUNS, _SYNTHETIC_RESOLUTIONS
    repo = tmp_path / "synthetic-git"
    _ANCHOR = _init_synthetic_repo(repo, SYNTHETIC_HISTORY_FILES)
    monkeypatch.setattr(validate_runs, "_run_git", _redirected_run_git(repo))
    monkeypatch.setattr(validate_run_resolutions, "_run_git", _redirected_run_git(repo))
    _SYNTHETIC_RUNS = tmp_path / "synthetic-runs"
    _SYNTHETIC_RESOLUTIONS = tmp_path / "synthetic-resolutions"
    _anchored_records(RUNS, _SYNTHETIC_RUNS)
    _anchored_records(RESOLUTIONS, _SYNTHETIC_RESOLUTIONS)
    yield _ANCHOR


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _base():
    record = _load(RESOLUTIONS / "01-resolution.json")
    record["campaign_anchor"]["base_commit"] = _ANCHOR
    return record


def _source_run():
    record = _load(RUNS / "03-run.json")
    record["campaign_anchor"]["base_commit"] = _ANCHOR
    return record


def _source_scenario():
    return _load(SCENARIOS / "02-scenario.json")


def _source_hook():
    return _load(HOOKS / "02-active.json")


def _paths(resolution_paths=None, run_paths=None):
    return (
        load_records(HOOKS),
        load_records(SCENARIOS),
        run_paths or load_records(_SYNTHETIC_RUNS),
        resolution_paths or load_records(_SYNTHETIC_RESOLUTIONS),
    )


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema(RESOLUTION_SCHEMA_PATH))


@pytest.mark.parametrize(
    ("roll", "expected"),
    [
        (1, "critical_trigger"),
        (2, "bad"),
        (5, "bad"),
        (6, "below_average"),
        (10, "below_average"),
        (11, "normal"),
        (16, "normal"),
        (17, "above_average"),
        (19, "above_average"),
        (20, "exceptional"),
    ],
)
def test_primary_roll_bands_are_exact(roll, expected):
    assert classify_primary_roll(roll) == expected


@pytest.mark.parametrize(
    ("roll", "expected"),
    [(1, "minor"), (2, "minor"), (3, "moderate"), (4, "moderate"), (5, "serious"), (6, "catastrophic")],
)
def test_severity_roll_bands_are_exact(roll, expected):
    assert classify_severity_roll(roll) == expected


@pytest.mark.parametrize("roll", [0, 21, True, 1.0, "1"])
def test_primary_roll_rejects_invalid_values(roll):
    with pytest.raises(ValueError):
        classify_primary_roll(roll)


def test_primary_one_requires_severity():
    with pytest.raises(ValueError, match="required"):
        classify_resolution(1)


def test_non_one_forbids_severity():
    with pytest.raises(ValueError, match="only allowed"):
        classify_resolution(2, 1)


def test_builder_snapshots_run_scenario_hook_context_without_mutating_inputs():
    run = _source_run()
    scenario = _source_scenario()
    hook = _source_hook()
    original = deepcopy((run, scenario, hook))

    proposal = build_resolution_proposal("RP20", run, scenario, hook, 18)

    assert proposal["run_id"] == "R03"
    assert proposal["scenario_id"] == "S02"
    assert proposal["primary_hook_id"] == "H02"
    assert proposal["campaign_anchor"] == run["campaign_anchor"]
    assert proposal["campaign_anchor"] is not run["campaign_anchor"]
    assert proposal["objective_context"] == {
        "scenario_objective": scenario["objective"],
        "hook_objective": hook["objective"],
    }
    assert proposal["outcome_band"] == "above_average"
    assert proposal["proposed_consequences"][0]["scope"] == "run_objective"
    assert proposal["proposed_consequences"][0]["kind"] == "objective_result"
    assert (run, scenario, hook) == original


def test_builder_primary_one_records_severity():
    proposal = build_resolution_proposal(
        "RP21", _source_run(), _source_scenario(), _source_hook(), 1, 6
    )
    assert proposal["outcome_band"] == "critical_trigger"
    assert proposal["severity_roll"] == 6
    assert proposal["severity_band"] == "catastrophic"
    assert "catastrophic" in proposal["proposed_consequences"][0]["summary"]


def test_builder_rejects_played_run():
    run = {**_source_run(), "execution_mode": "played", "control_state": "active"}
    with pytest.raises(ValueError, match="off-screen"):
        build_resolution_proposal(
            "RP22", run, _source_scenario(), _source_hook(), 12
        )


def test_valid_fixture_batch_passes():
    assert validate_paths(*_paths()) == {}


def test_fixture_is_noncanonical_and_bounded_to_objective():
    record = _base()
    assert "canonical_writes" not in record
    assert "canon" not in record
    assert record["proposed_consequences"] == [
        {
            "consequence_id": "PC01",
            "scope": "run_objective",
            "kind": "objective_result",
            "summary": "Apply the above average result to the Run objective defined by Scenario S02 and Primary Hook H02.",
            "related_entity_ids": [],
            "location_ids": [],
        }
    ]


def test_anchor_must_exactly_match_source_run(tmp_path):
    record = _base()
    record["campaign_anchor"]["base_commit"] = "f" * 40
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("exactly match" in error for error in errors[path])


def test_objective_context_must_match_scenario_and_hook(tmp_path):
    record = _base()
    record["objective_context"]["hook_objective"] = "Invented objective"
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("objective_context" in error for error in errors[path])


def test_resolution_must_use_off_screen_run(tmp_path):
    run = _source_run()
    run["execution_mode"] = "played"
    run["control_state"] = "active"
    run_path = _write(tmp_path, "run.json", run)
    resolution_path = _write(tmp_path, "resolution.json", _base())
    errors = validate_paths(*_paths([resolution_path], [run_path]))
    assert any("not off_screen" in error for error in errors[resolution_path])


def test_scenario_and_primary_hook_must_follow_run_chain(tmp_path):
    record = _base()
    record["scenario_id"] = "S01"
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("does not match Run Scenario" in error for error in errors[path])


def test_roll_label_mismatch_is_rejected(tmp_path):
    record = _base()
    record["outcome_band"] = "bad"
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("does not match primary_roll" in error for error in errors[path])


def test_severity_label_mismatch_is_rejected(tmp_path):
    record = _base()
    record["primary_roll"] = 1
    record["outcome_band"] = "critical_trigger"
    record["severity_roll"] = 6
    record["severity_band"] = "serious"
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("does not match severity_roll" in error for error in errors[path])


def test_non_one_resolution_cannot_store_severity():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    record = _base()
    record["severity_roll"] = 2
    record["severity_band"] = "minor"
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_primary_one_requires_both_severity_fields():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    record = _base()
    record["primary_roll"] = 1
    record["outcome_band"] = "critical_trigger"
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_unrelated_entity_target_is_rejected(tmp_path):
    record = _base()
    record["proposed_consequences"] = [
        {
            "consequence_id": "PC10",
            "scope": "related_entity",
            "kind": "discovery",
            "summary": "Unrelated target should fail.",
            "related_entity_ids": ["item:not-in-context"],
            "location_ids": [],
        }
    ]
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("outside Run/Scenario/Hook context" in error for error in errors[path])


def test_participant_scope_must_target_actual_participant(tmp_path):
    record = _base()
    record["proposed_consequences"] = [
        {
            "consequence_id": "PC11",
            "scope": "participant",
            "kind": "setback",
            "summary": "Context-related faction is not a participant.",
            "related_entity_ids": ["faction:test-faction"],
            "location_ids": [],
        }
    ]
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("targets non-participants" in error for error in errors[path])


def test_related_participant_target_is_allowed(tmp_path):
    record = _base()
    record["proposed_consequences"] = [
        {
            "consequence_id": "PC12",
            "scope": "participant",
            "kind": "injury",
            "summary": "A bounded participant consequence.",
            "related_entity_ids": ["character:test-returning"],
            "location_ids": [],
        }
    ]
    path = _write(tmp_path, "resolution.json", record)
    assert validate_paths(*_paths([path])) == {}


def test_scenario_related_location_target_is_allowed(tmp_path):
    record = _base()
    record["proposed_consequences"] = [
        {
            "consequence_id": "PC13",
            "scope": "location",
            "kind": "world_change",
            "summary": "A bounded location consequence.",
            "related_entity_ids": [],
            "location_ids": ["location:test-hall"],
        }
    ]
    path = _write(tmp_path, "resolution.json", record)
    assert validate_paths(*_paths([path])) == {}


def test_unrelated_location_target_is_rejected(tmp_path):
    record = _base()
    record["proposed_consequences"] = [
        {
            "consequence_id": "PC14",
            "scope": "location",
            "kind": "world_change",
            "summary": "An unrelated location should fail.",
            "related_entity_ids": [],
            "location_ids": ["location:elsewhere"],
        }
    ]
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("locations outside" in error for error in errors[path])


def test_duplicate_consequence_ids_are_rejected(tmp_path):
    record = _base()
    second = deepcopy(record["proposed_consequences"][0])
    second["summary"] = "Different summary, same local consequence ID."
    record["proposed_consequences"].append(second)
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("duplicated within resolution" in error for error in errors[path])


def test_automatic_death_kind_does_not_exist():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    record = _base()
    record["proposed_consequences"][0]["kind"] = "death"
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_empty_consequence_batch_is_rejected():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    record = _base()
    record["proposed_consequences"] = []
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_canon_mutation_fields_are_rejected():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    record = _base()
    record["canonical_writes"] = []
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(record))


def test_cli_valid_fixture_batch(capsys):
    code = main([
        "--hooks", str(HOOKS),
        "--scenarios", str(SCENARIOS),
        "--runs", str(_SYNTHETIC_RUNS),
        str(_SYNTHETIC_RESOLUTIONS),
    ])
    assert code == 0
    assert "1 resolution proposal(s) valid" in capsys.readouterr().out


def test_resolution_and_consequence_ids_require_strict_two_digit_minimum():
    schema = load_schema(RESOLUTION_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    base = _base()
    for bad in ("RP1", "RP01\n", "RP01\r", "RP01 "):
        assert list(validator.iter_errors({**base, "resolution_id": bad})), bad

    for bad in ("PC1", "PC01\n", "PC01\r", "PC01 "):
        record = deepcopy(base)
        record["proposed_consequences"][0]["consequence_id"] = bad
        assert list(validator.iter_errors(record)), bad


def test_duplicate_resolution_id_is_rejected(tmp_path):
    a = _write(tmp_path, "a.json", _base())
    other = _base()
    other["primary_roll"] = 19
    b = _write(tmp_path, "b.json", other)
    errors = validate_paths(*_paths([a, b]))
    assert any("duplicates" in error for error in errors[b])


def test_unknown_run_is_rejected(tmp_path):
    record = _base()
    record["run_id"] = "R99"
    path = _write(tmp_path, "resolution.json", record)
    errors = validate_paths(*_paths([path]))
    assert any("does not resolve to a persisted Run" in error for error in errors[path])


def test_source_run_anchor_must_resolve_to_canonical_git_commit(tmp_path):
    run = _source_run()
    run["campaign_anchor"]["base_commit"] = "f" * 40
    run_path = _write(tmp_path, "run.json", run)

    resolution = _base()
    resolution["campaign_anchor"]["base_commit"] = "f" * 40
    resolution_path = _write(tmp_path, "resolution.json", resolution)

    errors = validate_paths(*_paths([resolution_path], [run_path]))
    assert any("expected an actual Git commit" in error for error in errors[resolution_path])


def test_duplicate_json_key_is_rejected(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(
        '{"resolution_id":"RP30","resolution_id":"RP31","run_id":"R03",'
        '"scenario_id":"S02","primary_hook_id":"H02",'
        '"campaign_anchor":{"base_commit":"18bebc813f1af0a8478b97654bd86885e2a5bc25","campaign_time":"Day 13, dawn"},'
        '"objective_context":{"scenario_objective":"x","hook_objective":"x"},'
        '"primary_roll":18,"outcome_band":"above_average","proposed_consequences":[]}',
        encoding="utf-8",
    )
    errors = validate_paths(*_paths([path]))
    assert any("duplicate key" in error for error in errors[path])


def test_invalid_utf8_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'{"resolution_id":"RP30","x":"\xff"}')
    errors = validate_paths(*_paths([path]))
    assert any("invalid UTF-8" in error for error in errors[path])
