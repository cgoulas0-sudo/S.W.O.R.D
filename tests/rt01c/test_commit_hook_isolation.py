"""RT01-C regression proof that mirror commit construction does not run hooks."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import publish_or_repair_git_mirror  # noqa: E402


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


def _candidate():
    return {
        "schema_version": 1,
        "generation": 1,
        "published_day": None,
        "mirror_token": "00000001-1111-4111-8111-000000000001",
        "last_confirmed_git_ref": None,
        "state": {"key": 1},
    }


def test_prepare_commit_msg_hook_is_not_run_by_mirror_worker(tmp_path):
    repo = _repo(tmp_path)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    marker = tmp_path / "hook-fired"
    hook = hooks / "prepare-commit-msg"
    hook.write_text(f"#!/bin/sh\necho fired > '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))

    first = publish_or_repair_git_mirror(repo, _candidate())
    assert marker.exists() is False

    retry = publish_or_repair_git_mirror(repo, _candidate())
    assert retry == {"generation": 1, "git_ref": first["git_ref"], "reused": True}
