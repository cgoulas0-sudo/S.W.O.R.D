#!/usr/bin/env python3
"""RT01-C/D external runtime-published Git publication mirror.

SQL publication may commit before Git, but the save is incomplete until a real
runtime-published checkpoint is externally created/read back and confirmed.
Retries finish the same SQL generation. RT01-D engineering releases additionally
adopt one exact approved origin/main commit as an ordered second parent.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

ARTIFACT_PATH = "runtime/published-checkpoint.json"
DEFAULT_BRANCH = "runtime-published"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_MIRROR_COMMIT_NAME = "RHC Runtime Mirror"
_MIRROR_COMMIT_EMAIL = "rhc-runtime-mirror@invalid.local"
_ENGINEERING_PATH_PREFIXES = (".github/", "docs/", "scripts/", "supabase/", "tests/")
_ENGINEERING_ROOT_FILES = {
    "AGENT_HANDOFF.md",
    "AGENTS.md",
    "BUILDER.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "ENGINE_CHANGELOG.md",
    "ORCHESTRATOR.md",
    "PLAY.md",
    "PROJECT_PRIMER.md",
    "README.md",
    "requirements.txt",
}


class MirrorError(RuntimeError):
    """Raised when mirror provenance/parity cannot be proven safely."""


def _run_git(
    repo: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if check and result.returncode:
        raise MirrorError(
            result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        )
    return result


def _commit_env() -> dict[str, str]:
    """Use a fixed worker identity without treating commit metadata as authority."""
    env = dict(os.environ)
    for var in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env.pop(var, None)
    env["GIT_AUTHOR_NAME"] = _MIRROR_COMMIT_NAME
    env["GIT_AUTHOR_EMAIL"] = _MIRROR_COMMIT_EMAIL
    env["GIT_COMMITTER_NAME"] = _MIRROR_COMMIT_NAME
    env["GIT_COMMITTER_EMAIL"] = _MIRROR_COMMIT_EMAIL
    return env


def _json_loads_exact(text: str) -> Any:
    """Decode JSON without converting PostgreSQL numeric values through float."""
    return json.loads(text, parse_float=Decimal)


def _canonical_json(value: Any) -> str:
    """Serialize deterministically while preserving Decimal values exactly."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MirrorError("runtime mirror JSON numbers must be finite")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MirrorError("runtime mirror JSON numbers must be finite")
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise MirrorError("runtime mirror JSON object keys must be strings")
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical_json(value[key])}"
            for key in sorted(value)
        ) + "}"
    raise MirrorError(f"unsupported runtime mirror JSON value type: {type(value).__name__}")


def _canonical_bytes(candidate: dict[str, Any]) -> bytes:
    payload = {
        "schema_version": 1,
        "generation": candidate["generation"],
        "published_day": candidate.get("published_day"),
        "mirror_token": candidate["mirror_token"],
        "last_confirmed_git_ref": candidate.get("last_confirmed_git_ref"),
        "state": candidate["state"],
    }
    return (_canonical_json(payload) + "\n").encode("utf-8")


def _validate_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("schema_version") != 1:
        raise MirrorError("unsupported runtime mirror candidate schema_version")
    generation = candidate.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise MirrorError("runtime mirror generation must be a positive integer")
    token = candidate.get("mirror_token")
    if not isinstance(token, str) or not token.strip():
        raise MirrorError("runtime mirror candidate requires a database-owned mirror_token")
    day = candidate.get("published_day")
    if day is not None and (
        isinstance(day, bool) or not isinstance(day, int) or day < 0
    ):
        raise MirrorError("published_day must be null or a non-negative integer")
    if not isinstance(candidate.get("state"), dict):
        raise MirrorError("runtime mirror state must be a JSON object")
    last = candidate.get("last_confirmed_git_ref")
    if last is not None and (
        not isinstance(last, str) or _FULL_SHA.fullmatch(last) is None
    ):
        raise MirrorError("last_confirmed_git_ref must be null or an exact full commit SHA")
    base = candidate.get("mirror_base_git_ref")
    if base is not None and (
        not isinstance(base, str) or _FULL_SHA.fullmatch(base) is None
    ):
        raise MirrorError("mirror_base_git_ref must be null or an exact full commit SHA")
    engineering = candidate.get("engineering_git_ref")
    if engineering is not None and (
        not isinstance(engineering, str) or _FULL_SHA.fullmatch(engineering) is None
    ):
        raise MirrorError("engineering_git_ref must be null or an exact full commit SHA")
    if engineering is not None and last is None:
        raise MirrorError("engineering release requires a confirmed runtime parent")


def _ls_remote_branch(repo: Path, remote: str, branch: str) -> str | None:
    result = _run_git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    line = result.stdout.strip()
    if not line:
        return None
    sha = line.split()[0]
    if _FULL_SHA.fullmatch(sha) is None:
        raise MirrorError(f"remote {branch} did not resolve to an exact commit SHA")
    return sha


def _fetch_branch(repo: Path, remote: str, branch: str) -> None:
    _run_git(
        repo,
        "fetch",
        "--no-tags",
        remote,
        f"refs/heads/{branch}:refs/remotes/{remote}/{branch}",
    )


def _read_artifact_bytes(repo: Path, ref: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{ARTIFACT_PATH}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return result.stdout


def _artifact_bytes_match(repo: Path, ref: str, candidate: dict[str, Any]) -> bool:
    blob = _read_artifact_bytes(repo, ref)
    return blob is not None and blob == _canonical_bytes(candidate)


def _commit_parents(repo: Path, sha: str) -> list[str]:
    parents = _run_git(repo, "show", "-s", "--format=%P", sha).stdout.split()
    for parent in parents:
        if _FULL_SHA.fullmatch(parent) is None:
            raise MirrorError(f"commit {sha} has a non-exact parent reference")
    return parents


def _commit_changes_only_artifact(repo: Path, parent: str, sha: str) -> bool:
    changed = _run_git(repo, "diff", "--name-only", parent, sha).stdout.splitlines()
    return [line for line in changed if line.strip()] == [ARTIFACT_PATH]


def _is_reusable_publication(
    repo: Path,
    commit_sha: str,
    candidate: dict[str, Any],
    expected_old: str | None,
    bootstrap_base: str | None,
) -> bool:
    """Prove exact checkpoint continuity and exact artifact bytes.

    Commit metadata is not a runtime authority surface. The proof is the real remote
    commit SHA that is read back, its exact parent anchor, its artifact-only shape,
    and byte parity with the database-owned published candidate.
    """
    parents = _commit_parents(repo, commit_sha)
    engineering = candidate.get("engineering_git_ref")
    if engineering is not None:
        if expected_old is None or parents != [expected_old, engineering]:
            return False
        if not _commit_changes_only_artifact(repo, engineering, commit_sha):
            return False
        if not _engineering_scope_is_allowed(repo, expected_old, engineering):
            return False
    else:
        if len(parents) != 1:
            return False
        parent = parents[0]
        anchor = expected_old if expected_old is not None else bootstrap_base
        if anchor is None or parent != anchor:
            return False
        if not _commit_changes_only_artifact(repo, parent, commit_sha):
            return False
    return _artifact_bytes_match(repo, commit_sha, candidate)


def _initial_main_base(repo: Path, remote: str) -> str:
    _run_git(
        repo,
        "fetch",
        "--no-tags",
        remote,
        f"refs/heads/main:refs/remotes/{remote}/main",
    )
    sha = _run_git(repo, "rev-parse", f"refs/remotes/{remote}/main").stdout.strip()
    if _FULL_SHA.fullmatch(sha) is None:
        raise MirrorError("remote main did not resolve to an exact commit SHA")
    return sha


def _engineering_scope_is_allowed(
    repo: Path, runtime_parent: str, engineering_ref: str
) -> bool:
    """Allow only bounded engineering/runtime-support paths from approved main."""
    changed = _run_git(
        repo,
        "diff",
        "--no-renames",
        "--name-only",
        "--diff-filter=ACDMRT",
        runtime_parent,
        engineering_ref,
    ).stdout.splitlines()
    paths = [path for path in changed if path and path != ARTIFACT_PATH]
    if not paths:
        return False
    return all(
        path in _ENGINEERING_ROOT_FILES
        or path.startswith(_ENGINEERING_PATH_PREFIXES)
        for path in paths
    )


def _validate_engineering_target(
    repo: Path,
    remote: str,
    runtime_parent: str,
    engineering_ref: str,
) -> None:
    """Prove the bound target is approved-main ancestry and path-bounded."""
    main_sha = _initial_main_base(repo, remote)
    commit = _run_git(
        repo, "cat-file", "-e", f"{engineering_ref}^{{commit}}", check=False
    )
    if commit.returncode:
        raise MirrorError("engineering release target is not an available commit")
    reachable = _run_git(
        repo,
        "merge-base",
        "--is-ancestor",
        engineering_ref,
        main_sha,
        check=False,
    )
    if reachable.returncode:
        raise MirrorError("engineering release target is not reachable from origin/main")
    if not _engineering_scope_is_allowed(repo, runtime_parent, engineering_ref):
        raise MirrorError(
            "engineering release contains no approved change or changes paths outside "
            "the bounded engineering/runtime-support scope"
        )


def _build_publication_commit(
    repo: Path,
    base_sha: str,
    candidate: dict[str, Any],
    engineering_ref: str | None = None,
) -> str:
    """Create one checkpoint commit locally and return its actual SHA."""
    artifact_bytes = _canonical_bytes(candidate)
    with tempfile.TemporaryDirectory(prefix="rhc-runtime-mirror-") as tmp:
        worktree = Path(tmp) / "worktree"
        tree_base = engineering_ref or base_sha
        _run_git(repo, "worktree", "add", "--detach", str(worktree), tree_base)
        try:
            target = worktree / ARTIFACT_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact_bytes)
            _run_git(
                worktree,
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.safecrlf=false",
                "add",
                "-f",
                ARTIFACT_PATH,
            )
            tree_sha = _run_git(worktree, "write-tree").stdout.strip()
            commit_args = ["commit-tree", tree_sha, "-p", base_sha]
            if engineering_ref is not None:
                commit_args.extend(["-p", engineering_ref])
            commit_args.extend(
                ["-m", f"Runtime published generation {candidate['generation']}"]
            )
            sha = _run_git(worktree, *commit_args, env=_commit_env()).stdout.strip()
            if _FULL_SHA.fullmatch(sha) is None:
                raise MirrorError("worker-created publication did not produce an exact SHA")
            return sha
        finally:
            _run_git(repo, "worktree", "remove", "--force", str(worktree), check=False)


def publish_or_repair_git_mirror(
    repo_root: str | os.PathLike[str],
    candidate: dict[str, Any],
    *,
    remote: str = "origin",
    branch: str = DEFAULT_BRANCH,
) -> dict[str, Any]:
    """Create/reuse the real durable Git artifact for one pending SQL generation."""
    repo = Path(repo_root).resolve()
    _validate_candidate(candidate)
    if not (repo / ".git").exists():
        raise MirrorError(f"{repo} is not a Git working repository")

    expected_old = candidate.get("last_confirmed_git_ref")
    engineering_ref = candidate.get("engineering_git_ref")
    bootstrap_base: str | None = None
    if expected_old is None:
        bootstrap_base = candidate.get("mirror_base_git_ref")
        if bootstrap_base is None:
            bootstrap_base = _initial_main_base(repo, remote)

    # Inspect/fetch the real remote branch before constructing a child. This makes
    # a fresh clone able to resolve the previously confirmed runtime checkpoint.
    remote_head = _ls_remote_branch(repo, remote, branch)
    if remote_head is not None:
        _fetch_branch(repo, remote, branch)
        if engineering_ref is not None and expected_old is not None:
            _validate_engineering_target(
                repo, remote, expected_old, engineering_ref
            )
        if _is_reusable_publication(
            repo, remote_head, candidate, expected_old, bootstrap_base
        ):
            return {
                "generation": candidate["generation"],
                "git_ref": remote_head,
                "reused": True,
            }

    if expected_old is not None:
        if remote_head != expected_old:
            raise MirrorError(
                f"{branch} head {remote_head!r} does not match last confirmed Git ref {expected_old}"
            )
        base_sha = expected_old
    else:
        if remote_head is not None:
            raise MirrorError(
                f"{branch} already exists at an unrecognized checkpoint; refusing initial overwrite"
            )
        if bootstrap_base is None:
            raise MirrorError("bootstrap runtime mirror has no exact base anchor")
        base_sha = bootstrap_base

    new_sha = _build_publication_commit(
        repo, base_sha, candidate, engineering_ref=engineering_ref
    )
    if not _is_reusable_publication(
        repo, new_sha, candidate, expected_old, bootstrap_base
    ):
        raise MirrorError("locally built runtime-published commit failed continuity/parity proof")

    lease = f"refs/heads/{branch}:{expected_old or ''}"
    _run_git(
        repo,
        "push",
        f"--force-with-lease={lease}",
        remote,
        f"{new_sha}:refs/heads/{branch}",
    )

    readback = _ls_remote_branch(repo, remote, branch)
    if readback != new_sha:
        raise MirrorError(
            f"{branch} read-back mismatch: expected {new_sha}, got {readback}"
        )
    _fetch_branch(repo, remote, branch)
    if not _is_reusable_publication(
        repo, readback, candidate, expected_old, bootstrap_base
    ):
        raise MirrorError("final runtime-published continuity/parity proof failed")

    return {
        "generation": candidate["generation"],
        "git_ref": readback,
        "reused": False,
    }


def _load_pending_from_db(conn) -> dict[str, Any]:
    # Cast JSONB to text so psycopg2 cannot silently route fractional numerics
    # through binary float before our precision-preserving decoder sees them.
    with conn.cursor() as cur:
        cur.execute("select public.get_pending_runtime_mirror()::text")
        row = cur.fetchone()
    if not row:
        raise MirrorError("no pending runtime mirror candidate returned by PostgreSQL")
    candidate = _json_loads_exact(row[0])
    if not isinstance(candidate, dict):
        raise MirrorError("PostgreSQL returned an invalid runtime mirror candidate")
    return candidate


def _bind_base_in_db(conn, candidate: dict[str, Any], base_sha: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("set role rhc_mirror_verifier")
            cur.execute(
                "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                (candidate["generation"], candidate["mirror_token"], base_sha),
            )
            cur.execute("reset role")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _ensure_bootstrap_base_bound(
    conn, repo: Path, candidate: dict[str, Any], remote: str
) -> dict[str, Any]:
    if candidate.get("last_confirmed_git_ref") is not None:
        return candidate
    if candidate.get("mirror_base_git_ref"):
        return candidate
    base_sha = _initial_main_base(repo, remote)
    _bind_base_in_db(conn, candidate, base_sha)
    return _load_pending_from_db(conn)


def _confirm_in_db(conn, candidate: dict[str, Any], git_ref: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("set role rhc_mirror_verifier")
            cur.execute(
                "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
                (candidate["generation"], candidate["mirror_token"], git_ref),
            )
            cur.execute("reset role")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def repair_pending_runtime_mirror(
    dsn: str,
    repo_root: str | os.PathLike[str],
    *,
    remote: str = "origin",
) -> dict[str, Any]:
    """Finish the current SQL-published generation without publishing another one."""
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover
        raise MirrorError("psycopg2 is required for the PostgreSQL mirror repair path") from exc

    conn = psycopg2.connect(dsn)
    try:
        candidate = _load_pending_from_db(conn)
        repo = Path(repo_root).resolve()
        candidate = _ensure_bootstrap_base_bound(conn, repo, candidate, remote)
        proof = publish_or_repair_git_mirror(repo_root, candidate, remote=remote)
        readback = _ls_remote_branch(repo, remote, DEFAULT_BRANCH)
        if readback != proof["git_ref"]:
            raise MirrorError("final runtime-published read-back proof failed")
        _fetch_branch(repo, remote, DEFAULT_BRANCH)
        if not _artifact_bytes_match(repo, readback, candidate):
            raise MirrorError("final runtime-published read-back proof failed")
        _confirm_in_db(conn, candidate, proof["git_ref"])
        return proof
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair/confirm the pending RHC runtime-published Git mirror"
    )
    parser.add_argument("--repo", default=".")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--dsn", help="PostgreSQL admin/verifier DSN for full repair + confirmation")
    parser.add_argument("--candidate-json", help="JSON file for Git-only mirror proof/testing")
    args = parser.parse_args()

    if args.dsn:
        print(json.dumps(repair_pending_runtime_mirror(args.dsn, args.repo, remote=args.remote), sort_keys=True))
        return 0
    if args.candidate_json:
        candidate = _json_loads_exact(Path(args.candidate_json).read_text(encoding="utf-8"))
        print(json.dumps(publish_or_repair_git_mirror(args.repo, candidate, remote=args.remote), sort_keys=True))
        return 0
    parser.error("choose --dsn or --candidate-json")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
