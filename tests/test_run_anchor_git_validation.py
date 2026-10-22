import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records  # noqa: E402
from validate_runs import _canonical_main_ref, validate_paths  # noqa: E402

SCENARIOS = FIX / "scenarios" / "valid"
ENCOUNTERS = FIX / "encounters" / "valid"
RUNS = FIX / "runs" / "valid"


def _base():
    return json.loads((RUNS / "01-run.json").read_text(encoding="utf-8"))


def _write(tmp_path, sha):
    record = _base()
    record["campaign_anchor"]["base_commit"] = sha
    path = tmp_path / "run.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _validate(path):
    return validate_paths(load_records(SCENARIOS), load_records(ENCOUNTERS), [path])


def _main_ref():
    main_ref = _canonical_main_ref()
    assert main_ref is not None
    return main_ref


def _synthetic_unmerged_commit():
    main_ref = _main_ref()
    main_sha = subprocess.check_output(
        ["git", "rev-parse", main_ref], cwd=ROOT, text=True
    ).strip()
    tree_sha = subprocess.check_output(
        ["git", "rev-parse", f"{main_sha}^{{tree}}"], cwd=ROOT, text=True
    ).strip()
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "EV2 Test",
            "GIT_AUTHOR_EMAIL": "ev2-test@example.invalid",
            "GIT_COMMITTER_NAME": "EV2 Test",
            "GIT_COMMITTER_EMAIL": "ev2-test@example.invalid",
        }
    )
    result = subprocess.run(
        ["git", "commit-tree", tree_sha, "-p", main_sha],
        cwd=ROOT,
        input="synthetic unmerged Run-anchor test commit\n",
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return result.stdout.strip(), main_sha, main_ref


def test_invented_commit_shaped_sha_is_rejected(tmp_path):
    path = _write(tmp_path, "f" * 40)
    errors = _validate(path)
    assert any("expected an actual Git commit" in error for error in errors[path])


def test_tree_sha_is_rejected(tmp_path):
    tree_sha = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    path = _write(tmp_path, tree_sha)
    errors = _validate(path)
    assert any("object type 'tree'" in error for error in errors[path])


def test_blob_sha_is_rejected(tmp_path):
    blob_sha = subprocess.check_output(["git", "rev-parse", "HEAD:requirements.txt"], cwd=ROOT, text=True).strip()
    path = _write(tmp_path, blob_sha)
    errors = _validate(path)
    assert any("object type 'blob'" in error for error in errors[path])


def test_historical_main_commit_is_accepted(tmp_path):
    main_ref = _main_ref()
    commit_sha = subprocess.check_output(["git", "rev-parse", main_ref], cwd=ROOT, text=True).strip()
    path = _write(tmp_path, commit_sha)
    assert _validate(path) == {}


def test_unmerged_commit_is_rejected(tmp_path):
    commit_sha, main_sha, main_ref = _synthetic_unmerged_commit()
    assert commit_sha != main_sha
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit_sha, main_ref],
        cwd=ROOT,
        check=False,
    ).returncode == 1
    path = _write(tmp_path, commit_sha)
    errors = _validate(path)
    assert any("not reachable from canonical main history" in error for error in errors[path])
