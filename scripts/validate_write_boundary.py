#!/usr/bin/env python3
"""RHC write-authority validator (HWB-01 BUILD + HWB-03 SAVE).

One shared authority substrate and two enforcement points:

- local ordinary-commit fence: `.githooks/pre-commit` -> `check-staged`
- trusted server PR fence: `check-pr`, always executed from base-defined code
  while the PR head is treated only as Git objects/data.

The candidate branch namespace selects exactly one authorized lane:

- `save/*` receives the fixed server-owned SAVE repository-history contract
  (no JOHNNY is loaded): one new `canon/days/day_XXX.md` plus an optional
  `canon/timeline.md` companion, nothing else.
- every other branch is the HWB-01 BUILD lane, whose authority derives from
  the unique open branch-bound JOHNNY machine Surface Budget.

Default deny. Any ambiguity in authority, contract, identity, or candidate
evidence fails closed. This module deliberately implements no generic policy
language, no YAML grammar, no receipts, TTLs, or guard-version markers.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

MARKER_START = "<!-- RHC_SURFACE_BUDGET_V1"
MARKER_END = "-->"
SUPPORTED_VERSION = 1
CONTRACT_KEYS = frozenset(
    {"surface_budget_version", "repository", "branch", "base_sha", "mission", "allow"}
)
ALLOW_ACTIONS = ("create", "modify", "delete")
IDENTITY_KEYS = ("REPOSITORY", "BUILD/HEAD BRANCH", "BASE SHA", "MISSION IDENTITY")
SHA_40_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_STATUS_RE = re.compile(r"^(?P<code>[AMDTRC])(?P<score>\d{3})?$")

# Fixed SAVE repository-history lane (HWB-03). The branch namespace selects
# this lane; the policy below is repository-owned and intentionally tiny.
SAVE_BRANCH_PREFIX = "save/"
SAVE_DAY_RE = re.compile(r"^canon/days/day_(?P<day>[0-9]+)\.md$")
SAVE_TIMELINE_PATH = "canon/timeline.md"
SAVE_TEMPLATE_PATH = "canon/days/DAY_TEMPLATE.md"
SAVE_FILE_MODES = frozenset({"100644", "100755"})


class BoundaryError(Exception):
    """Any authority/contract/evidence ambiguity. Always fails closed."""


def _fail(message: str) -> "BoundaryError":
    return BoundaryError("WRITE BOUNDARY REFUSED: " + message)


# --------------------------------------------------------------------------
# Machine Surface Budget contract (the single machine authority block)
# --------------------------------------------------------------------------

def extract_machine_block(text: str) -> str:
    # The start marker must be a standalone block opener: a longer marker-like
    # token (e.g. prose imitation "..._V1X") is not a machine block.
    starts = [m.start() for m in
              re.finditer(re.escape(MARKER_START) + r"(?=\s)", text)]
    if len(starts) == 0:
        raise _fail("no RHC_SURFACE_BUDGET_V1 machine block found")
    if len(starts) > 1:
        raise _fail("multiple RHC_SURFACE_BUDGET_V1 machine blocks found")
    start = starts[0] + len(MARKER_START)
    end = text.find(MARKER_END, start)
    if end == -1:
        raise _fail("machine block is not closed with -->")
    raw = text[start:end]
    if not raw.strip():
        raise _fail("machine block is empty")
    return raw


def _validate_path(path: str, where: str) -> None:
    if not isinstance(path, str) or not path:
        raise _fail(f"{where}: path must be a non-empty string")
    if path != path.strip():
        raise _fail(f"{where}: path has leading/trailing whitespace: {path!r}")
    if "\\" in path:
        raise _fail(f"{where}: backslash not allowed in path: {path!r}")
    if path.startswith("/") or path.endswith("/"):
        raise _fail(f"{where}: path must be repository-relative: {path!r}")
    if path.startswith("./") or "//" in path or "../" in path or path == "..":
        raise _fail(f"{where}: traversal/relative prefix not allowed: {path!r}")
    for ch in "*?[]{}!|:\"<>":
        if ch in path:
            raise _fail(f"{where}: glob/special character {ch!r} not allowed: {path!r}")


def _reject_duplicate_keys(pairs: list) -> dict:
    """object_pairs_hook that refuses duplicate keys at ANY nesting depth.

    `json.loads` otherwise keeps the last value for a repeated key, letting a
    duplicated `allow`, identity, or action key silently replace earlier
    authority while still looking schema-valid. Duplicate semantic authority
    must fail closed.
    """
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _fail(f"duplicate JSON key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_contract(raw_json: str) -> dict:
    try:
        contract = json.loads(raw_json, object_pairs_hook=_reject_duplicate_keys)
    except BoundaryError:
        raise
    except (ValueError, TypeError) as exc:
        raise _fail(f"machine block is not valid JSON: {exc}") from None
    if not isinstance(contract, dict):
        raise _fail("machine block JSON must be an object")
    keys = frozenset(contract)
    unknown = keys - CONTRACT_KEYS
    missing = CONTRACT_KEYS - keys
    if unknown:
        raise _fail(f"unknown contract fields: {sorted(unknown)}")
    if missing:
        raise _fail(f"missing contract fields: {sorted(missing)}")

    version = contract["surface_budget_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise _fail("surface_budget_version must be an integer")
    if version != SUPPORTED_VERSION:
        raise _fail(f"unsupported surface_budget_version: {version}")

    for field in ("repository", "branch", "base_sha", "mission"):
        value = contract[field]
        if not isinstance(value, str) or not value.strip():
            raise _fail(f"{field} must be a non-empty string")
    if not SHA_40_RE.match(contract["base_sha"]):
        raise _fail("base_sha must be an exact 40-hex commit SHA")

    allow = contract["allow"]
    if not isinstance(allow, dict):
        raise _fail("allow must be an object")
    if frozenset(allow) != frozenset(ALLOW_ACTIONS):
        raise _fail(
            f"allow must have exactly the actions {list(ALLOW_ACTIONS)}, "
            f"got {sorted(allow)}"
        )

    seen: dict[str, str] = {}
    for action in ALLOW_ACTIONS:
        paths = allow[action]
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise _fail(f"allow.{action} must be a list of strings")
        if len(set(paths)) != len(paths):
            raise _fail(f"allow.{action} contains duplicate paths")
        for path in paths:
            _validate_path(path, f"allow.{action}")
            if path in seen and seen[path] != action:
                raise _fail(
                    f"path {path!r} declared under multiple actions "
                    f"({seen[path]} and {action}); ambiguous authority"
                )
            seen[path] = action
    return contract


def extract_and_parse_contract(text: str) -> dict:
    return parse_contract(extract_machine_block(text))


def cross_check_contract(contract: dict, identity: dict) -> None:
    for key in ("repository", "branch", "base_sha", "mission"):
        if contract[key] != identity[key]:
            raise _fail(
                f"machine contract {key} {contract[key]!r} does not match "
                f"JOHNNY identity {identity[key]!r}"
            )


# --------------------------------------------------------------------------
# JOHNNY identity header
# --------------------------------------------------------------------------

_IDENTITY_LINE = {
    key: re.compile(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", re.M)
    for key in IDENTITY_KEYS
}


def _identity_occurrences(body: str, key: str) -> list:
    """All values for an identity field, in document order.

    Uses `.*?` (not `.+?`) so an empty value is still an occurrence; callers
    can then distinguish a missing field from a malformed/empty one.
    """
    return _IDENTITY_LINE[key].findall(body)


def parse_identity(body: str) -> dict:
    """Parse the JOHNNY identity header, failing closed on any ambiguity.

    A field that is missing, repeated (duplicate), empty, or malformed cannot
    bind authority unambiguously, so every such case raises rather than
    silently taking the first/last occurrence or being treated as a non-match.
    """
    identity = {}
    for key in IDENTITY_KEYS:
        occurrences = _identity_occurrences(body, key)
        if not occurrences:
            raise _fail(f"JOHNNY identity field missing: {key}")
        if len(occurrences) > 1:
            raise _fail(f"JOHNNY identity field duplicated: {key}")
        if not occurrences[0]:
            raise _fail(f"JOHNNY identity field empty: {key}")
        identity[key] = occurrences[0]
    base_sha = identity["BASE SHA"]
    if not SHA_40_RE.match(base_sha):
        # A malformed BASE SHA must raise here so a candidate that targets this
        # repository/branch cannot be silently skipped as a mere non-match.
        raise _fail(f"JOHNNY identity BASE SHA is not an exact 40-hex SHA: {base_sha!r}")
    return {
        "repository": identity["REPOSITORY"],
        "branch": identity["BUILD/HEAD BRANCH"],
        "base_sha": base_sha,
        "mission": identity["MISSION IDENTITY"],
    }


def targets_repo_branch(body: str, actual: dict) -> bool:
    """True when a candidate header names this repository AND this branch.

    Detection is independent of full identity validity: if the header mentions
    the actual repository and branch, the candidate is aimed at this authority
    and must not be silently discarded just because another identity field is
    malformed, duplicated, incomplete, or conflicting.
    """
    repositories = _identity_occurrences(body, "REPOSITORY")
    branches = _identity_occurrences(body, "BUILD/HEAD BRANCH")
    repo_hit = any(r.lower() == actual["repository"].lower()
                   for r in repositories)
    branch_hit = any(b == actual["branch"] for b in branches)
    return repo_hit and branch_hit


# --------------------------------------------------------------------------
# JOHNNY discovery (exactly one matching open branch-bound authority)
# --------------------------------------------------------------------------

def discover_candidates() -> list:
    """Return (reference, title, body) for open JOHNNY CHECKPOINT candidates.

    PR-shaped records are excluded as authority. If GitHub discovery cannot
    produce complete evidence, fail closed.
    """
    fixture = os.environ.get("RHC_JOHNNY_FIXTURE")
    if fixture is not None:
        from pathlib import Path

        root = Path(fixture)
        if not root.is_dir():
            raise _fail(f"RHC_JOHNNY_FIXTURE is not a directory: {fixture}")
        return [
            (path.name, "JOHNNY CHECKPOINT", path.read_text(encoding="utf-8"))
            for path in sorted(root.glob("*.txt"))
        ]

    proc = subprocess.run(
        ["gh", "api", "--paginate",
         "repos/{owner}/{repo}/issues?state=open&per_page=100"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise _fail(f"GitHub JOHNNY discovery failed: {proc.stderr.strip()}")
    # --paginate concatenates JSON array pages; reassemble them.
    pages = []
    decoder = json.JSONDecoder()
    buffer = proc.stdout.strip()
    while buffer:
        obj, index = decoder.raw_decode(buffer)
        pages.extend(obj)
        buffer = buffer[index:].lstrip()
    candidates = []
    for item in pages:
        # PR records are never JOHNNY authority (the issues endpoint also
        # exposes PR-shaped records; they carry a pull_request key).
        if item.get("pull_request"):
            continue
        candidates.append(
            (f"#{item.get('number')}", str(item.get("title") or ""),
             str(item.get("body") or ""))
        )
    return candidates


def _normalize_newlines(text: str) -> str:
    """Normalize CRLF/CR to LF before any identity/targeting/contract parsing.

    Windows-authored candidate bodies (CRLF line endings) otherwise leave a
    trailing `\r` on every identity value. That `\r` makes identity parsing
    reject the value as malformed AND makes `targets_repo_branch` compare
    unequal to the real repository/branch, so a same-repo/branch candidate
    with CRLF endings would be silently treated as unrelated instead of
    forcing fail-closed ambiguity.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_matching_title(title: str) -> bool:
    return "JOHNNY CHECKPOINT" in title


def _identity_matches(identity: dict, actual: dict, ancestry) -> bool:
    return (
        identity["repository"].lower() == actual["repository"].lower()
        and identity["branch"] == actual["branch"]
        and bool(SHA_40_RE.match(identity["base_sha"]))
        and ancestry(identity["base_sha"])
        and bool(identity["mission"])
    )


def select_authority(candidates: list, actual: dict, ancestry) -> dict:
    """Pick the unique open branch-bound JOHNNY matching actual state.

    `ancestry(base_sha)` must verify the claimed BASE SHA is a real commit
    that is an ancestor of the exact head being graded.
    """
    matches = []
    for reference, title, body in candidates:
        if not is_matching_title(title):
            continue
        body = _normalize_newlines(body)
        try:
            identity = parse_identity(body)
        except BoundaryError:
            # A candidate that targets this repository/branch but cannot bind
            # its identity unambiguously must FAIL CLOSED rather than be
            # silently skipped into a different usable authority. Only a
            # candidate clearly aimed elsewhere may be ignored.
            if targets_repo_branch(body, actual):
                raise
            continue  # cannot establish whether this candidate is the authority
        if not _identity_matches(identity, actual, ancestry):
            continue
        # This candidate matches the authority identity. A malformed or
        # ambiguous machine contract here must FAIL CLOSED rather than be
        # silently skipped into a different usable authority.
        contract = extract_and_parse_contract(body)
        cross_check_contract(contract, identity)
        matches.append({"reference": reference, "identity": identity,
                        "contract": contract})
    if len(matches) == 0:
        raise _fail(
            "no open branch-bound JOHNNY matches this repository/branch/base"
        )
    if len(matches) > 1:
        raise _fail(
            "multiple open JOHNNYs match this repository/branch/base: "
            + ", ".join(m["reference"] for m in matches)
        )
    return matches[0]


# --------------------------------------------------------------------------
# Git evidence
# --------------------------------------------------------------------------

def _git(*args, cwd=None, check=True):
    proc = subprocess.run(["git", "-c", "core.quotePath=false", *args],
                          cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise _fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def repo_identity(cwd=None) -> str:
    url = _git("remote", "get-url", "origin", cwd=cwd).stdout.strip()
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url)
    if not match:
        raise _fail(f"cannot derive GitHub repository identity from origin: {url}")
    return match.group(1)


def current_branch(cwd=None) -> str:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip()
    if not branch or branch == "HEAD":
        raise _fail("not on a named branch; cannot bind write authority")
    return branch


def head_sha(cwd=None) -> str:
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def commit_exists(sha: str, cwd=None) -> bool:
    proc = _git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}",
                cwd=cwd, check=False)
    return proc.returncode == 0 and proc.stdout.strip() == sha


def is_ancestor(ancestor: str, descendant: str, cwd=None) -> bool:
    proc = _git("merge-base", "--is-ancestor", ancestor, descendant,
                cwd=cwd, check=False)
    return proc.returncode == 0


# Copy detection must consider unchanged sources too, otherwise a copy from an
# unauthorized tracked source is emitted as a plain add and the source-side
# authority rule is silently unenforceable (--find-copies-harder).
_DIFF_FLAGS = ("-M", "-C", "--find-copies-harder")


def staged_changes(base_sha: str, cwd=None) -> list:
    """Return cumulative [(status, [paths...])] from Mission BASE to the index.

    Grading the prospective index against the JOHNNY-bound BASE (not HEAD)
    keeps the local fence and the server fence classifying the SAME cumulative
    Mission candidate across multiple ordinary commits.
    """
    out = _git("diff", "--cached", base_sha, *_DIFF_FLAGS,
               "--name-status", cwd=cwd).stdout
    return _parse_name_status(out)


def diff_between(base: str, head: str, cwd=None) -> list:
    out = _git("diff", *_DIFF_FLAGS, "--name-status", base, head,
               cwd=cwd).stdout
    return _parse_name_status(out)


def _parse_name_status(output: str) -> list:
    entries = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            raise _fail(f"unparsable git name-status line: {line!r}")
        status = parts[0]
        match = NAME_STATUS_RE.match(status)
        if not match:
            raise _fail(f"unknown git change status {status!r}; failing closed")
        paths = parts[1:]
        expected = 2 if match.group("code") in ("R", "C") else 1
        if len(paths) != expected:
            raise _fail(
                f"status {status} must carry exactly {expected} path(s), "
                f"got {paths!r}"
            )
        entries.append((status, paths))
    return entries


# --------------------------------------------------------------------------
# Action/path classifier (Surface Budget is path + action aware)
# --------------------------------------------------------------------------

def grade_changes(entries: list, allow: dict) -> list:
    """Grade candidate changes against the Surface Budget. Default deny."""
    authorized = []
    for status, paths in entries:
        code = status[0]
        if code == "A":
            _require(paths[0], allow["create"], status, paths,
                     "create a path not authorized for create")
        elif code == "M":
            _require(paths[0], allow["modify"], status, paths,
                     "modify a path not authorized for modify")
        elif code == "D":
            _require(paths[0], allow["delete"], status, paths,
                     "delete a path not authorized for delete")
        elif code == "R":
            # A rename is a delete of the source plus a create of the
            # destination; both sides must be independently authorized so a
            # rename cannot hide an unauthorized source or destination.
            _require(paths[0], allow["delete"], status, paths,
                     "rename source path not authorized for delete")
            _require(paths[1], allow["create"], status, paths,
                     "rename destination path not authorized for create")
        elif code == "C":
            _require(paths[1], allow["create"], status, paths,
                     "copy destination path not authorized for create")
            if paths[0] not in (allow["create"] + allow["modify"] + allow["delete"]):
                raise _fail(
                    f"copy source path {paths[0]!r} is not an authorized "
                    f"surface ({status})"
                )
        else:  # unreachable given _parse_name_status, kept fail-closed
            raise _fail(f"unknown git action {status!r}")
        authorized.append((status, paths))
    return authorized


def _require(path: str, allowed: list, status: str, paths: list, why: str) -> None:
    if path not in allowed:
        raise _fail(
            f"status {status} on {paths!r} would {why}: {path!r}"
        )


# --------------------------------------------------------------------------
# Fixed SAVE repository-history lane (branch namespace selects the policy)
# --------------------------------------------------------------------------

def is_save_branch(branch: str) -> bool:
    """`save/*` is the only namespace eligible for the fixed SAVE contract."""
    return branch.startswith(SAVE_BRANCH_PREFIX)


def is_save_day_path(path: str) -> bool:
    """True for a legal finalized-day archive path.

    `day_XXX.md` is schematic notation for the permanent archive, not a fixed
    three-digit format: leading zeroes are permitted and the digit count is
    uncapped, so `day_001.md`, `day_999.md`, `day_1000.md` and `day_12547.md`
    are all legal. The numeric archive identity must be greater than zero, so
    an all-zero identity such as `day_000.md`/`day_0.md` is refused rather than
    admitted as a finalized day.

    Positivity is decided without converting to `int`. Because the declared
    identity is unbounded, an identity wider than the interpreter's default
    decimal-string conversion limit (4,300 digits on Python 3.12+) would raise
    `ValueError` under `int()` and be rejected as an uncaught crash, silently
    narrowing the invariant. The regex already proves the identity is ASCII
    decimal, so it is positive iff stripping leading zeroes leaves a nonzero
    digit at any width.
    """
    match = SAVE_DAY_RE.match(path)
    if not match:
        return False
    return match.group("day").lstrip("0") != ""


def _parse_raw_name_status(output: str) -> list:
    """Parse `git diff --raw` into (status, paths, old_mode, new_mode).

    Modes are carried as evidence so a symlink/gitlink added at an otherwise
    legal path cannot masquerade as a regular finalized-day file.
    """
    entries = []
    for line in output.splitlines():
        if not line.strip():
            continue
        if not line.startswith(":"):
            raise _fail(f"unparsable git raw line: {line!r}")
        meta, tab, pathpart = line[1:].partition("\t")
        if not tab:
            raise _fail(f"unparsable git raw line (no path): {line!r}")
        fields = meta.split()
        if len(fields) != 5:
            raise _fail(f"unparsable git raw metadata: {line!r}")
        old_mode, new_mode, _old_sha, _new_sha, status = fields
        match = NAME_STATUS_RE.match(status)
        if not match:
            raise _fail(f"unknown git change status {status!r}; failing closed")
        paths = pathpart.split("\t")
        expected = 2 if match.group("code") in ("R", "C") else 1
        if len(paths) != expected:
            raise _fail(
                f"status {status} must carry exactly {expected} path(s), "
                f"got {paths!r}"
            )
        entries.append((status, paths, old_mode, new_mode))
    return entries


def staged_save_changes(base_sha: str, cwd=None) -> list:
    out = _git("diff", "--cached", "--raw", base_sha, *_DIFF_FLAGS,
               cwd=cwd).stdout
    return _parse_raw_name_status(out)


def diff_save_between(base: str, head: str, cwd=None) -> list:
    out = _git("diff", "--raw", *_DIFF_FLAGS, base, head, cwd=cwd).stdout
    return _parse_raw_name_status(out)


def grade_save_changes(entries: list) -> list:
    """Grade the fixed SAVE repository-history contract. Default deny.

    Legal candidate: ADD exactly one new `canon/days/day_<positive int>.md`,
    plus an optional ADD/MODIFY of `canon/timeline.md`. `day_XXX.md` is
    schematic notation, so leading zeroes and large archive identities are
    legal while a zero/non-positive identity is not. A copy of the day template
    into the new day path is accepted because Git's copy detection would
    otherwise misreport a legitimate template-derived day as a copy. Every
    delete, rename, type change, existing-day mutation, undeclared path, and an
    empty candidate (no new finalized day) fails closed.
    """
    day_adds = []
    for status, paths, _old_mode, new_mode in entries:
        code = status[0]
        if new_mode not in SAVE_FILE_MODES:
            raise _fail(
                f"SAVE lane permits regular files only; {status} {paths!r} "
                f"has mode {new_mode!r}"
            )
        if code == "A":
            path = paths[0]
            if is_save_day_path(path):
                day_adds.append(path)
            elif path != SAVE_TIMELINE_PATH:
                raise _fail(
                    f"SAVE lane may add only a new canon/days/day_XXX.md or "
                    f"canon/timeline.md; refused {status} {paths!r}"
                )
        elif code == "M":
            if paths[0] != SAVE_TIMELINE_PATH:
                raise _fail(
                    f"SAVE lane may modify only canon/timeline.md; finalized "
                    f"history is immutable; refused {status} {paths!r}"
                )
        elif code == "C":
            source, dest = paths
            if source != SAVE_TEMPLATE_PATH or not is_save_day_path(dest):
                raise _fail(
                    f"SAVE lane copy must originate from {SAVE_TEMPLATE_PATH!r} "
                    f"into a new canon/days/day_XXX.md; refused {status} {paths!r}"
                )
            day_adds.append(dest)
        else:  # D / R / T and anything else: no widening into history
            raise _fail(
                f"SAVE lane forbids {status} {paths!r}; finalized history is "
                f"immutable and no delete is legal"
            )
    if len(day_adds) != 1:
        raise _fail(
            f"SAVE lane must add exactly one new canon/days/day_XXX.md; "
            f"got {len(day_adds)}"
        )
    return entries


def save_base(cwd=None) -> str:
    """The SAVE branch's divergence point from `main`/`origin/main`.

    SAVE branches are cut from current `main`, so the merge-base with the
    shared mainline is the correct cumulative base for the local fence.
    """
    head = head_sha(cwd=cwd)
    for ref in ("origin/main", "main"):
        proc = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
                    cwd=cwd, check=False)
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        merge = _git("merge-base", head, ref, cwd=cwd, check=False)
        if merge.returncode == 0 and merge.stdout.strip():
            return merge.stdout.strip()
    raise _fail("SAVE lane cannot determine its base: no main merge-base")


# --------------------------------------------------------------------------
# Enforcement entry points
# --------------------------------------------------------------------------

def check_staged_save(cwd=None) -> str:
    """Local SAVE fence: grade staged changes against the fixed SAVE contract.

    A normal SAVE candidate must contain exactly one new finalized day artifact,
    so an empty cumulative candidate fails closed here rather than passing as a
    no-op.
    """
    base = save_base(cwd=cwd)
    entries = staged_save_changes(base, cwd=cwd)
    grade_save_changes(entries)
    detail = "; ".join(
        f"{status}:{','.join(paths)}" for status, paths, _old, _new in entries
    )
    return f"WRITE BOUNDARY OK: SAVE repository-history candidate authorized -> {detail}"


def check_staged(cwd=None) -> str:
    """Local ordinary-commit fence: grade staged changes against live authority."""
    branch = current_branch(cwd=cwd)
    if is_save_branch(branch):
        return check_staged_save(cwd=cwd)

    repository = repo_identity(cwd=cwd)
    head = head_sha(cwd=cwd)

    def ancestry(base_sha: str) -> bool:
        return commit_exists(base_sha, cwd=cwd) and is_ancestor(base_sha, head, cwd=cwd)

    authority = select_authority(discover_candidates(),
                                 {"repository": repository, "branch": branch},
                                 ancestry)
    contract = authority["contract"]
    allow = contract["allow"]

    entries = staged_changes(contract["base_sha"], cwd=cwd)
    if not entries:
        return (
            "WRITE BOUNDARY OK: no cumulative Mission changes staged; "
            f"authority={authority['reference']} mission={contract['mission']}"
        )
    grade_changes(entries, allow)
    detail = "; ".join(
        f"{status}:{','.join(paths)}" for status, paths in entries
    )
    return (
        "WRITE BOUNDARY OK: cumulative staged changes authorized by "
        f"{authority['reference']} mission={contract['mission']} -> {detail}"
    )


def check_pr_save(base_sha: str, head_sha_arg: str, cwd=None) -> str:
    """Trusted server SAVE fence: grade the exact PR head/base as data.

    No JOHNNY is loaded. The base is the PR base from trusted event context;
    the head is consumed only as Git objects and graded against the fixed
    SAVE contract, keeping local/server SAVE semantics equivalent. An empty
    PR candidate is invalid because a normal SAVE must add exactly one new
    finalized day artifact, so it fails closed here.
    """
    if not is_ancestor(base_sha, head_sha_arg, cwd=cwd):
        raise _fail("SAVE PR base is not an ancestor of the PR head")
    entries = diff_save_between(base_sha, head_sha_arg, cwd=cwd)
    grade_save_changes(entries)
    detail = "; ".join(
        f"{status}:{','.join(paths)}" for status, paths, _old, _new in entries
    )
    return f"WRITE BOUNDARY OK: SAVE PR candidate authorized -> {detail}"


def check_pr(base_sha: str, head_sha_arg: str, head_branch: str,
             repository: str, head_repository: str | None = None,
             cwd=None) -> str:
    """Trusted server fence: grade the exact PR head/base with base-defined code.

    The caller must execute this validator from the trusted BASE revision; the
    PR head is consumed only as Git objects. `repository` (base) and
    `head_repository` come from the trusted event context and are never
    PR-controlled text. A PR whose head repository differs from the
    authority-bound repository (e.g. a fork reusing the branch name) is
    refused so branch-name identity alone cannot inherit authority.
    """
    if not SHA_40_RE.match(base_sha) or not SHA_40_RE.match(head_sha_arg):
        raise _fail("PR base/head must be exact 40-hex commit SHAs")
    if not commit_exists(base_sha, cwd=cwd) or not commit_exists(head_sha_arg, cwd=cwd):
        raise _fail("PR base/head objects are not both present in the repository")
    if not head_repository:
        raise _fail("PR head repository identity is required (event context)")
    if head_repository.lower() != repository.lower():
        raise _fail(
            f"PR head repository {head_repository!r} differs from the "
            f"authority-bound repository {repository!r}; refusing branch-name "
            f"identity confusion"
        )
    if is_save_branch(head_branch):
        return check_pr_save(base_sha, head_sha_arg, cwd=cwd)

    def ancestry(candidate: str) -> bool:
        return candidate == base_sha and is_ancestor(base_sha, head_sha_arg, cwd=cwd)

    authority = select_authority(
        discover_candidates(),
        {"repository": repository, "branch": head_branch},
        ancestry,
    )
    contract = authority["contract"]
    if contract["base_sha"] != base_sha:
        raise _fail(
            f"PR base {base_sha} does not equal the JOHNNY-bound base "
            f"{contract['base_sha']}"
        )
    allow = contract["allow"]
    entries = diff_between(base_sha, head_sha_arg, cwd=cwd)
    if not entries:
        return (
            "WRITE BOUNDARY OK: PR diff is empty; "
            f"authority={authority['reference']} mission={contract['mission']}"
        )
    grade_changes(entries, allow)
    detail = "; ".join(
        f"{status}:{','.join(paths)}" for status, paths in entries
    )
    return (
        "WRITE BOUNDARY OK: PR diff authorized by "
        f"{authority['reference']} mission={contract['mission']} -> {detail}"
    )


def main(argv: list) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="RHC write authority")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-staged",
                   help="grade staged changes against the live branch-bound authority")
    pr = sub.add_parser("check-pr", help="grade an exact PR head/base (server fence)")
    pr.add_argument("base_sha")
    pr.add_argument("head_sha")
    pr.add_argument("head_branch")
    pr.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    pr.add_argument("--head-repository",
                    default=os.environ.get("PR_HEAD_REPO", ""))
    vc = sub.add_parser("validate-contract",
                        help="extract + validate the machine contract from text")
    vc.add_argument("file", nargs="?", default="-",
                    help="file containing JOHNNY text ('-' for stdin)")

    args = parser.parse_args(argv)
    try:
        if args.command == "check-staged":
            print(check_staged())
        elif args.command == "check-pr":
            if not args.repository:
                raise _fail("repository identity is required (event context)")
            print(check_pr(args.base_sha, args.head_sha, args.head_branch,
                           args.repository, args.head_repository))
        elif args.command == "validate-contract":
            text = sys.stdin.read() if args.file == "-" else open(
                args.file, encoding="utf-8").read()
            contract = extract_and_parse_contract(text)
            print(json.dumps(contract, indent=2))
    except BoundaryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
