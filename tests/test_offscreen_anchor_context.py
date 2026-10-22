import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

import validate_run_resolutions as validation  # noqa: E402
import validate_runs  # noqa: E402
from validate_entities import load_records  # noqa: E402

HOOKS = FIX / "hooks" / "valid"
SCENARIOS = FIX / "scenarios" / "valid"
RUNS = FIX / "runs" / "valid"
RESOLUTIONS = FIX / "run_resolutions" / "valid"

# These reusable Git-anchor proofs must not depend on a concrete RHC ancestor
# commit: a fixed RHC SHA is impossible fixture data inside a fresh independent
# repository that has no RHC ancestry. Each test builds its own temporary
# synthetic Git history (a `main` branch whose first commit carries the
# reusable Scenario/Hook records and their schemas) and points the validator's
# Git seam at it, so every anchored read resolves against a real, reachable,
# test-local commit instead of RHC history.
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


@pytest.fixture(autouse=True)
def _synthetic_history(tmp_path, monkeypatch):
    global _ANCHOR, _SYNTHETIC_RUNS
    repo = tmp_path / "synthetic-git"
    _ANCHOR = _init_synthetic_repo(repo, SYNTHETIC_HISTORY_FILES)
    monkeypatch.setattr(validation, "_run_git", _redirected_run_git(repo))
    monkeypatch.setattr(validate_runs, "_run_git", _redirected_run_git(repo))
    _SYNTHETIC_RUNS = tmp_path / "synthetic-runs"
    _SYNTHETIC_RUNS.mkdir()
    run = _load(RUNS / "03-run.json")
    run["campaign_anchor"]["base_commit"] = _ANCHOR
    (_SYNTHETIC_RUNS / "03-run.json").write_text(
        json.dumps(run, indent=2) + "\n", encoding="utf-8"
    )
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


def _run_paths():
    return load_records(_SYNTHETIC_RUNS)


def _source_run():
    record = _load(RUNS / "03-run.json")
    record["campaign_anchor"]["base_commit"] = _ANCHOR
    return record


def _source_scenario():
    return _load(SCENARIOS / "02-scenario.json")


def _source_hook():
    return _load(HOOKS / "02-active.json")


def _anchored_fixture_reader(path, commit_id):
    assert commit_id == _source_run()["campaign_anchor"]["base_commit"]
    if Path(path).name == "scenario.json":
        return _source_scenario()
    if Path(path).name == "hook.json":
        return _source_hook()
    raise AssertionError(path)


def _later_source_paths(tmp_path):
    scenario = _source_scenario()
    scenario["objective"] = "Later scenario objective."
    scenario["related_entity_ids"].append("item:later-added")

    hook = _source_hook()
    hook["objective"] = "Later hook objective."

    return (
        _write(tmp_path, "hook.json", hook),
        _write(tmp_path, "scenario.json", scenario),
    )


def test_git_reader_loads_source_context_from_run_anchor():
    anchor = _source_run()["campaign_anchor"]["base_commit"]

    scenario = validation._read_record_at_commit(
        SCENARIOS / "02-scenario.json", anchor
    )
    hook = validation._read_record_at_commit(HOOKS / "02-active.json", anchor)

    assert scenario["scenario_id"] == "S02"
    assert scenario["objective"] == _source_scenario()["objective"]
    assert hook["hook_id"] == "H02"
    assert hook["objective"] == _source_hook()["objective"]


def test_historical_objective_snapshot_survives_later_source_edits(
    tmp_path, monkeypatch
):
    hook_path, scenario_path = _later_source_paths(tmp_path)
    resolution_path = _write(tmp_path, "resolution.json", _base())

    monkeypatch.setattr(
        validation, "_read_record_at_commit", _anchored_fixture_reader
    )

    errors = validation.validate_paths(
        [hook_path],
        [scenario_path],
        _run_paths(),
        [resolution_path],
    )

    assert errors == {}


def test_later_objectives_cannot_pass_as_historical_snapshot(
    tmp_path, monkeypatch
):
    hook_path, scenario_path = _later_source_paths(tmp_path)
    resolution = _base()
    resolution["objective_context"] = {
        "scenario_objective": "Later scenario objective.",
        "hook_objective": "Later hook objective.",
    }
    resolution_path = _write(tmp_path, "resolution.json", resolution)

    monkeypatch.setattr(
        validation, "_read_record_at_commit", _anchored_fixture_reader
    )

    errors = validation.validate_paths(
        [hook_path],
        [scenario_path],
        _run_paths(),
        [resolution_path],
    )

    assert any(
        "objective_context" in error
        for error in errors[resolution_path]
    )


def test_later_added_related_entity_is_not_part_of_anchored_context(
    tmp_path, monkeypatch
):
    hook_path, scenario_path = _later_source_paths(tmp_path)
    resolution = _base()
    resolution["proposed_consequences"] = [
        {
            "consequence_id": "PC20",
            "scope": "related_entity",
            "kind": "discovery",
            "summary": "Later-added context must not leak backward.",
            "related_entity_ids": ["item:later-added"],
            "location_ids": [],
        }
    ]
    resolution_path = _write(tmp_path, "resolution.json", resolution)

    monkeypatch.setattr(
        validation, "_read_record_at_commit", _anchored_fixture_reader
    )

    errors = validation.validate_paths(
        [hook_path],
        [scenario_path],
        _run_paths(),
        [resolution_path],
    )

    assert any(
        "outside Run/Scenario/Hook context" in error
        for error in errors[resolution_path]
    )


def test_shared_anchor_builds_historical_index_once(tmp_path, monkeypatch):
    first = _base()
    second = _base()
    second["resolution_id"] = "RP02"

    first_path = _write(tmp_path, "01-resolution.json", first)
    second_path = _write(tmp_path, "02-resolution.json", second)

    real_builder = validation._build_anchored_record_index
    calls = []

    def counting_builder(commit_id):
        calls.append(commit_id)
        return real_builder(commit_id)

    monkeypatch.setattr(
        validation, "_build_anchored_record_index", counting_builder
    )

    errors = validation.validate_paths(
        load_records(HOOKS),
        load_records(SCENARIOS),
        _run_paths(),
        [first_path, second_path],
    )

    assert errors == {}
    assert calls == [_source_run()["campaign_anchor"]["base_commit"]]


def test_anchored_index_ignores_schema_invalid_same_id_candidates(monkeypatch):
    anchor = _source_run()["campaign_anchor"]["base_commit"]
    valid_hook = _source_hook()
    invalid_hook = _source_hook()
    invalid_hook["title"] = ""

    valid_scenario = _source_scenario()
    invalid_scenario = _source_scenario()
    invalid_scenario["objective"] = ""

    hook_schema = validation.load_schema(validation.HOOK_SCHEMA_PATH)
    scenario_schema = validation.load_schema(validation.SCENARIO_SCHEMA_PATH)
    historical = {
        "schemas/hook.schema.json": hook_schema,
        "schemas/scenario.schema.json": scenario_schema,
        "history/valid-hook.json": valid_hook,
        "history/invalid-hook.json": invalid_hook,
        "history/valid-scenario.json": valid_scenario,
        "history/invalid-scenario.json": invalid_scenario,
    }

    monkeypatch.setattr(
        validation,
        "_anchored_json_paths",
        lambda commit_id: [path for path in historical if path.startswith("history/")],
    )
    monkeypatch.setattr(
        validation,
        "_read_repo_json_at_commit",
        lambda path, commit_id: historical[path],
    )

    index = validation._build_anchored_record_index(anchor)

    assert [path for path, _ in index["Hook"]["H02"]] == [
        "history/valid-hook.json"
    ]
    assert [path for path, _ in index["Scenario"]["S02"]] == [
        "history/valid-scenario.json"
    ]
    assert validation._find_record_in_index(
        index, anchor, "H02", "Hook"
    ) == valid_hook
    assert validation._find_record_in_index(
        index, anchor, "S02", "Scenario"
    ) == valid_scenario


def test_anchored_index_uses_historical_schema_not_future_head_schema(monkeypatch):
    anchor = _source_run()["campaign_anchor"]["base_commit"]
    hook = _source_hook()
    scenario = _source_scenario()

    anchored_hook_schema = validation.load_schema(validation.HOOK_SCHEMA_PATH)
    anchored_scenario_schema = validation.load_schema(validation.SCENARIO_SCHEMA_PATH)

    future_hook_schema = json.loads(json.dumps(anchored_hook_schema))
    future_hook_schema["required"].append("future_required_field")
    future_hook_schema["properties"]["future_required_field"] = {
        "type": "string",
        "minLength": 1,
    }
    assert not validation.jsonschema.Draft202012Validator(
        future_hook_schema
    ).is_valid(hook)

    historical = {
        "schemas/hook.schema.json": anchored_hook_schema,
        "schemas/scenario.schema.json": anchored_scenario_schema,
        "history/hook.json": hook,
        "history/scenario.json": scenario,
    }

    monkeypatch.setattr(
        validation,
        "_anchored_json_paths",
        lambda commit_id: ["history/hook.json", "history/scenario.json"],
    )
    monkeypatch.setattr(
        validation,
        "_read_repo_json_at_commit",
        lambda path, commit_id: historical[path],
    )

    index = validation._build_anchored_record_index(anchor)

    assert validation._find_record_in_index(index, anchor, "H02", "Hook") == hook
    assert validation._find_record_in_index(
        index, anchor, "S02", "Scenario"
    ) == scenario


def test_anchored_context_does_not_require_current_source_copies(
    tmp_path, monkeypatch
):
    resolution_path = _write(tmp_path, "resolution.json", _base())
    anchor = _source_run()["campaign_anchor"]["base_commit"]

    anchored_index = {
        "Scenario": {
            "S02": [("history/scenario.json", _source_scenario())],
        },
        "Hook": {
            "H02": [("history/hook.json", _source_hook())],
        },
    }

    def build_index(commit_id):
        assert commit_id == anchor
        return anchored_index

    monkeypatch.setattr(
        validation, "_git_object_type", lambda commit_id: "commit"
    )
    monkeypatch.setattr(
        validation, "_is_reachable_from_canonical_main", lambda commit_id: True
    )
    monkeypatch.setattr(
        validation,
        "_build_anchored_record_index",
        build_index,
    )

    errors = validation.validate_paths(
        [],
        [],
        _run_paths(),
        [resolution_path],
    )

    assert errors == {}
