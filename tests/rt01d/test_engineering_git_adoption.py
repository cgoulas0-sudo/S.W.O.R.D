import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import (  # noqa: E402
    ARTIFACT_PATH,
    MirrorError,
    _canonical_bytes,
    publish_or_repair_git_mirror,
    repair_pending_runtime_mirror,
)

from rt01d_util import scalar, stage  # noqa: E402


def _git(cwd: Path, *args: str, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _repo(tmp_path: Path):
    bare = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "init", "-b", "main", str(repo))
    (repo / "scripts").mkdir()
    (repo / "scripts" / "base.py").write_text("BASE = True\n", encoding="utf-8")
    _git(repo, "add", "scripts/base.py")
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


def _candidate(generation=1, *, last=None, engineering=None, value=1):
    return {
        "schema_version": 1,
        "generation": generation,
        "published_day": None,
        "mirror_token": f"{generation:08d}-2222-4222-8222-{generation:012d}",
        "last_confirmed_git_ref": last,
        "engineering_git_ref": engineering,
        "state": {"key": value},
    }


def _advance_main(repo: Path, relative_path: str, contents: str):
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    _git(repo, "add", relative_path)
    _git(
        repo,
        "-c",
        "user.name=Dev",
        "-c",
        "user.email=dev@example.invalid",
        "commit",
        "-m",
        f"change {relative_path}",
    )
    _git(repo, "push", "origin", "main")
    return _git(repo, "rev-parse", "origin/main")


def _first_runtime(repo: Path):
    return publish_or_repair_git_mirror(repo, _candidate())["git_ref"]


def test_engineering_release_has_ordered_parents_and_engineering_tree(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    engineering = _advance_main(repo, "scripts/engine.py", "ENABLED = True\n")
    candidate = _candidate(2, last=runtime_parent, engineering=engineering, value=2)

    proof = publish_or_repair_git_mirror(repo, candidate)
    parents = _git(repo, "show", "-s", "--format=%P", proof["git_ref"]).split()
    changed_from_engineering = _git(
        repo, "diff", "--name-only", engineering, proof["git_ref"]
    ).splitlines()

    assert parents == [runtime_parent, engineering]
    assert changed_from_engineering == [ARTIFACT_PATH]
    assert _git(repo, "show", f"{proof['git_ref']}:scripts/engine.py") == "ENABLED = True"
    assert _git(repo, "show", f"{proof['git_ref']}:{ARTIFACT_PATH}").encode() + b"\n" == _canonical_bytes(candidate)


def test_engineering_release_retry_reuses_same_remote_commit(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    engineering = _advance_main(repo, "scripts/engine.py", "ENABLED = True\n")
    candidate = _candidate(2, last=runtime_parent, engineering=engineering, value=2)

    first = publish_or_repair_git_mirror(repo, candidate)
    retry = publish_or_repair_git_mirror(repo, candidate)
    assert retry == {"generation": 2, "git_ref": first["git_ref"], "reused": True}


def test_engineering_target_must_be_reachable_from_origin_main(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    _git(repo, "switch", "-c", "unapproved")
    (repo / "scripts" / "unapproved.py").write_text("UNAPPROVED = True\n", encoding="utf-8")
    _git(repo, "add", "scripts/unapproved.py")
    _git(
        repo,
        "-c",
        "user.name=Dev",
        "-c",
        "user.email=dev@example.invalid",
        "commit",
        "-m",
        "unapproved",
    )
    unapproved = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(MirrorError, match="not reachable from origin/main"):
        publish_or_repair_git_mirror(
            repo, _candidate(2, last=runtime_parent, engineering=unapproved, value=2)
        )


def test_engineering_release_rejects_campaign_content_paths(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    engineering = _advance_main(
        repo, "state/live_status.json", '{"status":"changed"}\n'
    )

    with pytest.raises(MirrorError, match="bounded engineering/runtime-support scope"):
        publish_or_repair_git_mirror(
            repo, _candidate(2, last=runtime_parent, engineering=engineering, value=2)
        )


def test_engineering_release_rejects_campaign_path_renamed_into_allowed_scope(
    tmp_path,
):
    repo = _repo(tmp_path)
    _advance_main(repo, "state/live_status.json", '{"status":"protected"}\n')
    runtime_parent = _first_runtime(repo)
    _git(repo, "config", "diff.renames", "true")
    _git(repo, "mv", "state/live_status.json", "scripts/live_status.json")
    _git(
        repo,
        "-c",
        "user.name=Dev",
        "-c",
        "user.email=dev@example.invalid",
        "commit",
        "-m",
        "rename protected campaign path",
    )
    _git(repo, "push", "origin", "main")
    engineering = _git(repo, "rev-parse", "origin/main")

    with pytest.raises(MirrorError, match="bounded engineering/runtime-support scope"):
        publish_or_repair_git_mirror(
            repo, _candidate(2, last=runtime_parent, engineering=engineering, value=2)
        )


def test_engineering_release_rejects_reversed_parent_order(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    engineering = _advance_main(repo, "scripts/engine.py", "ENABLED = True\n")
    candidate = _candidate(2, last=runtime_parent, engineering=engineering, value=2)

    _git(repo, "checkout", "--detach", engineering)
    artifact = repo / ARTIFACT_PATH
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(_canonical_bytes(candidate))
    _git(repo, "add", "-f", ARTIFACT_PATH)
    tree = _git(repo, "write-tree")
    reversed_commit = _git(
        repo,
        "-c",
        "user.name=Attacker",
        "-c",
        "user.email=attacker@example.invalid",
        "commit-tree",
        tree,
        "-p",
        engineering,
        "-p",
        runtime_parent,
        "-m",
        "reversed",
    )
    _git(repo, "push", "--force", "origin", f"{reversed_commit}:refs/heads/runtime-published")
    _git(repo, "checkout", "-f", "main")

    with pytest.raises(MirrorError, match="does not match last confirmed"):
        publish_or_repair_git_mirror(repo, candidate)


def test_bound_engineering_target_survives_later_main_advance(tmp_path):
    repo = _repo(tmp_path)
    runtime_parent = _first_runtime(repo)
    bound_target = _advance_main(repo, "scripts/engine.py", "VERSION = 1\n")
    newer_main = _advance_main(repo, "scripts/later.py", "VERSION = 2\n")
    assert newer_main != bound_target

    proof = publish_or_repair_git_mirror(
        repo, _candidate(2, last=runtime_parent, engineering=bound_target, value=2)
    )
    assert _git(repo, "show", "-s", "--format=%P", proof["git_ref"]).split() == [
        runtime_parent,
        bound_target,
    ]


def test_full_sql_git_engineering_release_and_read_confirmation(db, pg_dsn, tmp_path):
    repo = _repo(tmp_path)
    with db.cursor() as cur:
        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
    stage(db, token, "live_status", {"status": "published"})
    scalar(db, "select public.publish_campaign_save(%s)", (token,))
    first = repair_pending_runtime_mirror(pg_dsn, repo)

    engineering = _advance_main(repo, "scripts/engine.py", "ENABLED = True\n")
    with db.cursor() as cur:
        cur.execute(
            "select lock_token from public.begin_engineering_release(%s, 30)",
            (engineering,),
        )
        release_token = cur.fetchone()[0]
    scalar(db, "select public.publish_campaign_save(%s)", (release_token,))
    second = repair_pending_runtime_mirror(pg_dsn, repo)

    assert _git(repo, "show", "-s", "--format=%P", second["git_ref"]).split() == [
        first["git_ref"],
        engineering,
    ]
    read = scalar(db, "select public.dm_runtime_read()")
    assert read["runtime"]["generation"] == 2
    assert read["runtime"]["git_ref"] == second["git_ref"]
    assert read["runtime"]["mirror_confirmed"] is True
    assert read["context"]["world"]["status"] == "published"
