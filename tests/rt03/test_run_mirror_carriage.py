"""RT03 mirror/fallback inheritance: existing checkpoint mirroring carries
published state generically, with no RT03-specific mirror code (Proof Matrix L)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import (  # noqa: E402
    ARTIFACT_PATH,
    publish_or_repair_git_mirror,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rt03_util import run  # noqa: E402


def _git(cwd: Path, *args: str, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result


def _repo(tmp_path: Path):
    bare = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "init", "-b", "main", str(repo))
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "base",
    )
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    return repo


def test_existing_mirror_worker_carries_published_runs_generically(tmp_path):
    repo = _repo(tmp_path)
    record = run("R01", outcome_summary="mirror carriage canary")
    candidate = {
        "schema_version": 1,
        "generation": 1,
        "published_day": None,
        "mirror_token": "00000001-1111-4111-8111-000000000001",
        "last_confirmed_git_ref": None,
        "state": {"runs": [record]},
    }

    proof = publish_or_repair_git_mirror(repo, candidate)

    artifact = json.loads(
        _git(repo, "show", f"{proof['git_ref']}:{ARTIFACT_PATH}").stdout
    )
    assert artifact["generation"] == 1
    assert artifact["state"]["runs"] == [record]
