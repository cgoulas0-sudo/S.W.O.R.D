"""RT01-C proof that remote reuse is based on lineage + bytes, not commit metadata."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import ARTIFACT_PATH, _canonical_bytes, publish_or_repair_git_mirror  # noqa: E402


def _git(cwd: Path, *args: str):
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "init", "-b", "main", str(repo))
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    return repo


def _candidate(base: str):
    return {
        "schema_version": 1,
        "generation": 1,
        "published_day": None,
        "mirror_token": "00000001-1111-4111-8111-000000000001",
        "last_confirmed_git_ref": None,
        "mirror_base_git_ref": base,
        "state": {"key": 1},
    }


def test_same_parent_and_exact_bytes_are_reusable_even_if_metadata_differs(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "origin/main")
    candidate = _candidate(base)

    _git(repo, "checkout", "--detach", base)
    target = repo / ARTIFACT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical_bytes(candidate))
    _git(repo, "add", "-f", ARTIFACT_PATH)
    _git(
        repo,
        "-c",
        "user.name=Alternate Worker",
        "-c",
        "user.email=alternate@example.invalid",
        "commit",
        "-m",
        "alternate metadata, same checkpoint",
    )
    existing = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "origin", f"{existing}:refs/heads/runtime-published")
    _git(repo, "checkout", "-f", "main")

    proof = publish_or_repair_git_mirror(repo, candidate)
    assert proof == {"generation": 1, "git_ref": existing, "reused": True}
