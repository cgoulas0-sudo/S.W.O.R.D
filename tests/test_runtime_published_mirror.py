import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import (  # noqa: E402
    ARTIFACT_PATH,
    MirrorError,
    _canonical_bytes,
    publish_or_repair_git_mirror,
)


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


def _candidate(generation=1, *, last=None, value=1, base=None):
    candidate = {
        "schema_version": 1,
        "generation": generation,
        "published_day": None,
        "mirror_token": f"{generation:08d}-1111-4111-8111-{generation:012d}",
        "last_confirmed_git_ref": last,
        "state": {"key": value},
    }
    if base is not None:
        # Simulate the database-bound bootstrap base anchor the DB repair path pins
        # before publication and returns to every retry.
        candidate["mirror_base_git_ref"] = base
    return candidate


def _is_ancestor(repo, ancestor, descendant):
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo, text=True, capture_output=True,
    )
    return result.returncode == 0


def _advance_main(repo, text):
    """Add a commit to main and push it, returning the new origin/main SHA."""
    (repo / "README.md").write_text(text, encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(
        repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.invalid",
        "commit", "-m", f"advance: {text.strip()}",
    )
    _git(repo, "push", "origin", "main")
    return _git(repo, "rev-parse", "origin/main").stdout.strip()


def test_mirror_creates_real_remote_commit_and_durable_artifact(tmp_path):
    repo = _repo(tmp_path)
    candidate = _candidate()
    proof = publish_or_repair_git_mirror(repo, candidate)

    assert proof["reused"] is False
    assert _git(repo, "cat-file", "-t", proof["git_ref"]).stdout.strip() == "commit"
    remote = _git(
        repo,
        "ls-remote",
        "--heads",
        "origin",
        "refs/heads/runtime-published",
    ).stdout
    assert remote.split()[0] == proof["git_ref"]

    artifact = json.loads(
        _git(repo, "show", f"{proof['git_ref']}:{ARTIFACT_PATH}").stdout
    )
    assert artifact["generation"] == 1
    assert artifact["mirror_token"] == candidate["mirror_token"]
    assert artifact["state"] == candidate["state"]


def test_retry_after_push_reuses_same_git_proof(tmp_path):
    repo = _repo(tmp_path)
    candidate = _candidate()
    first = publish_or_repair_git_mirror(repo, candidate)
    retry = publish_or_repair_git_mirror(repo, candidate)
    assert retry == {
        "generation": 1,
        "git_ref": first["git_ref"],
        "reused": True,
    }


def test_next_generation_uses_last_confirmed_checkpoint_as_parent(tmp_path):
    repo = _repo(tmp_path)
    first = publish_or_repair_git_mirror(repo, _candidate())
    second_candidate = _candidate(2, last=first["git_ref"], value=2)
    second = publish_or_repair_git_mirror(repo, second_candidate)

    parent = _git(
        repo,
        "show",
        "-s",
        "--format=%P",
        second["git_ref"],
    ).stdout.strip()
    assert parent == first["git_ref"]


def test_cli_does_not_offer_standalone_latest_head_recovery(tmp_path):
    repo = _repo(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "runtime_published_mirror.py"),
            "--repo",
            str(repo),
            "--recover",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --recover" in result.stderr


def test_unexpected_runtime_published_head_fails_closed(tmp_path):
    repo = _repo(tmp_path)
    first = publish_or_repair_git_mirror(repo, _candidate())

    (repo / "other.txt").write_text("tamper\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "tamper",
    )
    tamper = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(
        repo,
        "push",
        "--force",
        "origin",
        f"{tamper}:refs/heads/runtime-published",
    )

    with pytest.raises(MirrorError, match="does not match last confirmed"):
        publish_or_repair_git_mirror(
            repo,
            _candidate(2, last=first["git_ref"], value=2),
        )


def test_initial_mirror_refuses_to_overwrite_unrecognized_existing_branch(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "origin", f"{base}:refs/heads/runtime-published")

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, _candidate())


# --------------------------------------------------------------------------
# Test helpers that fabricate hostile remote runtime-published commits.
# --------------------------------------------------------------------------
def _commit_bytes_on(repo, artifact_bytes, *, parent, msg="tamper"):
    """Commit ``artifact_bytes`` at ARTIFACT_PATH on top of ``parent``; return SHA."""
    _git(repo, "checkout", "--detach", parent)
    target = repo / ARTIFACT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(artifact_bytes)
    _git(repo, "add", "-f", ARTIFACT_PATH)
    _git(
        repo, "-c", "user.name=Attacker", "-c", "user.email=attacker@evil.invalid",
        "commit", "-m", msg,
    )
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "main")
    return sha


def _orphan_commit_bytes(repo, artifact_bytes, msg="orphan"):
    """Commit ``artifact_bytes`` on an unrelated (parentless) root; return SHA."""
    _git(repo, "checkout", "--orphan", "rogue")
    _git(repo, "rm", "-rf", "--cached", ".", check=False)
    for path in repo.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink()
    target = repo / ARTIFACT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(artifact_bytes)
    _git(repo, "add", "-f", ARTIFACT_PATH)
    _git(
        repo, "-c", "user.name=Attacker", "-c", "user.email=attacker@evil.invalid",
        "commit", "-m", msg,
    )
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-f", "main")
    return sha


def _force_publish_branch(repo, sha):
    _git(repo, "push", "--force", "origin", f"{sha}:refs/heads/runtime-published")


# --------------------------------------------------------------------------
# P1 #2 — divergent remote commit must not be reusable (ancestry continuity).
# --------------------------------------------------------------------------
def test_divergent_commit_with_identical_artifact_rejected_for_confirmed_gen(tmp_path):
    """A commit whose bytes match gen N+1 but whose parent is NOT the confirmed
    checkpoint must be rejected, even though the artifact is byte-identical."""
    repo = _repo(tmp_path)
    first = publish_or_repair_git_mirror(repo, _candidate())
    base = _git(repo, "rev-parse", "origin/main").stdout.strip()

    gen2 = _candidate(2, last=first["git_ref"], value=2)
    # Byte-identical artifact for gen 2, but rooted on main instead of `first`.
    divergent = _commit_bytes_on(repo, _canonical_bytes(gen2), parent=base)
    assert divergent != first["git_ref"]
    _force_publish_branch(repo, divergent)

    with pytest.raises(MirrorError, match="does not match last confirmed"):
        publish_or_repair_git_mirror(repo, gen2)


def test_divergent_initial_commit_with_identical_artifact_rejected(tmp_path):
    """An unrelated (orphan) commit carrying a byte-identical initial artifact must
    not be reused as the initial runtime-published bootstrap."""
    repo = _repo(tmp_path)
    candidate = _candidate()
    rogue = _orphan_commit_bytes(repo, _canonical_bytes(candidate))
    _force_publish_branch(repo, rogue)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, candidate)


def test_next_generation_valid_commit_is_based_on_confirmed_checkpoint(tmp_path):
    """The legitimate gen N+1 publication commit's single parent is exactly the
    previous confirmed runtime checkpoint (the reusable-ancestry invariant)."""
    repo = _repo(tmp_path)
    first = publish_or_repair_git_mirror(repo, _candidate())
    second = publish_or_repair_git_mirror(
        repo, _candidate(2, last=first["git_ref"], value=2)
    )
    parents = _git(repo, "show", "-s", "--format=%P", second["git_ref"]).stdout.split()
    assert parents == [first["git_ref"]]
    # And a legitimate retry after that push still reuses the SAME SHA.
    retry = publish_or_repair_git_mirror(
        repo, _candidate(2, last=first["git_ref"], value=2)
    )
    assert retry == {"generation": 2, "git_ref": second["git_ref"], "reused": True}


# --------------------------------------------------------------------------
# P1 #3 — byte parity, not parsed-object equality, is the proof.
# --------------------------------------------------------------------------
def test_boolean_true_artifact_is_not_reused_for_numeric_one_candidate(tmp_path):
    """JSON `true` decodes to Python True and `1 == True`, so parsed-object
    equality would wrongly accept a boolean-substituted artifact. Byte parity
    must fail closed."""
    repo = _repo(tmp_path)
    numeric = _candidate(value=1)           # canonical state {"key":1}
    boolean_bytes = _canonical_bytes(_candidate(value=True))  # {"key":true}
    assert boolean_bytes != _canonical_bytes(numeric)

    base = _git(repo, "rev-parse", "origin/main").stdout.strip()
    tampered = _commit_bytes_on(repo, boolean_bytes, parent=base)
    _force_publish_branch(repo, tampered)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, numeric)


def test_semantically_equal_noncanonical_artifact_is_not_reused(tmp_path):
    """Same JSON meaning but different bytes (whitespace / key order) is not the
    exact published artifact."""
    repo = _repo(tmp_path)
    candidate = _candidate()
    canonical = _canonical_bytes(candidate)
    payload = json.loads(canonical.decode("utf-8"))
    # Re-serialize with pretty whitespace + reversed key order: same meaning,
    # different bytes.
    noncanonical = (
        json.dumps(payload, indent=2, sort_keys=False).encode("utf-8") + b"\n"
    )
    assert noncanonical != canonical
    assert json.loads(noncanonical) == json.loads(canonical)

    base = _git(repo, "rev-parse", "origin/main").stdout.strip()
    tampered = _commit_bytes_on(repo, noncanonical, parent=base)
    _force_publish_branch(repo, tampered)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, candidate)


def test_valid_canonical_artifact_still_reuses(tmp_path):
    """The exact canonical artifact from a legitimate push is still reused."""
    repo = _repo(tmp_path)
    candidate = _candidate()
    first = publish_or_repair_git_mirror(repo, candidate)
    retry = publish_or_repair_git_mirror(repo, candidate)
    assert retry == {"generation": 1, "git_ref": first["git_ref"], "reused": True}


# --------------------------------------------------------------------------
# P1 #4 — caller Git identity env must not forge the commit identity.
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Fresh P1 — the bootstrap base anchor must be the EXACT selected main SHA,
# durably bound to the generation, never "any ancestor of current origin/main".
# --------------------------------------------------------------------------
def test_old_main_ancestor_bootstrap_commit_is_rejected(tmp_path):
    """OLD MAIN ANCESTOR ATTACK (Codex): an attacker roots a byte-identical
    bootstrap artifact on an OLD main ancestor. Because that ancestor is still
    reachable from the current tip, the previous loose ancestor check accepted it.
    Exact-anchor continuity must reject it. This test fails on reviewed HEAD 3088bb7
    (which reuses the rogue commit instead of raising)."""
    repo = _repo(tmp_path)
    old_main = _git(repo, "rev-parse", "origin/main").stdout.strip()
    # main advances past the anchor the attacker rooted on.
    _advance_main(repo, "one\n")
    current_main = _advance_main(repo, "two\n")
    assert current_main != old_main

    candidate = _candidate()
    rogue = _commit_bytes_on(repo, _canonical_bytes(candidate), parent=old_main)
    assert _is_ancestor(repo, old_main, current_main)  # sanity: it IS an ancestor
    _force_publish_branch(repo, rogue)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, candidate)


def test_bootstrap_publication_anchors_on_exact_current_main(tmp_path):
    """CURRENT EXACT MAIN BOOTSTRAP: the first legitimate publication commit's
    single parent is exactly the selected current origin/main anchor."""
    repo = _repo(tmp_path)
    _advance_main(repo, "grow\n")
    main = _git(repo, "rev-parse", "origin/main").stdout.strip()

    proof = publish_or_repair_git_mirror(repo, _candidate())

    assert proof["reused"] is False
    parents = _git(repo, "show", "-s", "--format=%P", proof["git_ref"]).stdout.split()
    assert parents == [main]


def test_bootstrap_retry_reuses_pushed_commit_after_main_advances(tmp_path):
    """RETRY SURVIVES MAIN ADVANCE: bootstrap selects main SHA A and pushes a commit
    on A; DB confirmation is (simulated) not completed; main advances to B; the retry
    reuses the SAME already-pushed SHA using the durably bound base A, and does NOT
    reject it merely because origin/main is now B."""
    repo = _repo(tmp_path)
    base_a = _git(repo, "rev-parse", "origin/main").stdout.strip()
    first = publish_or_repair_git_mirror(repo, _candidate())  # commit on A, pushed
    assert first["reused"] is False

    base_b = _advance_main(repo, "moved\n")  # main advances; confirmation never ran
    assert base_b != base_a

    # The DB durably bound base A and returns it to the retry (candidate carries it).
    retry = publish_or_repair_git_mirror(repo, _candidate(base=base_a))
    assert retry == {"generation": 1, "git_ref": first["git_ref"], "reused": True}


def test_bootstrap_reuse_rejected_when_bound_base_differs_from_remote_parent(tmp_path):
    """WRONG BOUND BASE: the generation is durably bound to base A, but the remote
    checkpoint is rooted on a different anchor (B). Reject fail-closed even though the
    artifact bytes are exact."""
    repo = _repo(tmp_path)
    base_a = _git(repo, "rev-parse", "origin/main").stdout.strip()
    base_b = _advance_main(repo, "elsewhere\n")
    assert base_b != base_a

    candidate = _candidate()
    rogue = _commit_bytes_on(repo, _canonical_bytes(candidate), parent=base_b)
    _force_publish_branch(repo, rogue)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, _candidate(base=base_a))


def test_bootstrap_reuse_requires_both_bound_base_and_exact_bytes(tmp_path):
    """P1 #2 + #3 combination in the bootstrap: reuse needs BOTH exact continuity AND
    exact bytes. A commit on the correct bound base A but with the WRONG artifact
    bytes is rejected (and the byte-identical-but-wrong-base case is covered above)."""
    repo = _repo(tmp_path)
    base_a = _git(repo, "rev-parse", "origin/main").stdout.strip()

    wrong_bytes = _canonical_bytes(_candidate(value=999))
    on_base = _commit_bytes_on(repo, wrong_bytes, parent=base_a)
    _force_publish_branch(repo, on_base)

    with pytest.raises(MirrorError, match="unrecognized checkpoint"):
        publish_or_repair_git_mirror(repo, _candidate(base=base_a))


def test_hostile_git_identity_env_cannot_forge_commit_identity(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Mallory")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "mallory@evil.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Mallory")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "mallory@evil.invalid")

    proof = publish_or_repair_git_mirror(repo, _candidate())

    meta = _git(
        repo, "show", "-s", "--format=%an%n%ae%n%cn%n%ce", proof["git_ref"]
    ).stdout.splitlines()
    assert meta == [
        "RHC Runtime Mirror",
        "rhc-runtime-mirror@invalid.local",
        "RHC Runtime Mirror",
        "rhc-runtime-mirror@invalid.local",
    ]
