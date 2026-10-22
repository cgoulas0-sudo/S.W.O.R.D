#!/usr/bin/env python3
"""POST-EV2-Z Clean Campaign Canvas exporter.

From an exact tracked Git HEAD, produce a deterministic clean campaign tree:

* COPY reusable engine/runtime/mechanics/schemas/validators/migrations/control
  and selected reusable proofs byte-for-byte with the Git file mode preserved;
* EXCLUDE RHC campaign instance material, story/history, canaries, engineering
  history, and factory-only POST-EV2-Z machinery;
* GENERATE_EMPTY the declared mutable campaign roots as contract-valid
  EMPTY / UNKNOWN state from fixed policy constants in the tracked policy,
  each materialized at its rule's output path -- a GENERATE_EMPTY rule may
  declare a campaign-neutral ``output_path`` so a generated root is never
  written at a campaign-specific source path; every declared remap target is
  itself validated fail-closed (a clean normalized path that neither collides
  with nor nests inside another policy path and never lands inside an EXCLUDE
  prefix);
* FAIL closed on any tracked path with no disposition, on more than one
  disposition, and on any retained route that would dangle into an excluded
  source path.

Classification is strictly structural and path-only. The exporter never scans,
reads, redacts, detects, rewrites, or otherwise interprets file *content* to
decide a disposition: COPY bytes are fetched verbatim from the exact Git blob
named by ``git ls-tree``. No content scanning, redaction, name detection, SHA
detection, or text rewriting is used to classify.

Reference integrity is a *verification* step, not a classification input. After
the file dispositions are fixed structurally, the exporter reads the retained
control-plane surfaces -- COPY surfaces through their source bytes and
GENERATE_EMPTY surfaces through their generated policy bytes -- and confirms
that every internal repository-relative route they mention resolves to a real
dependency of the exported tree. Species-aware on purpose: a Markdown
hyperlink (navigational) may be satisfied by a preserved skeleton directory,
while an executable workflow dependency (``run:`` argument, static
``working-directory``) is satisfied only by a real exported file at or under
the resolved path -- an empty preserved skeleton collects zero tests and
proves nothing. A local ``uses: ./path`` action is stricter still: it must ship
its ``action.yml``/``action.yaml`` metadata file at the action root, because a
folder of unrelated files without metadata cannot load as an action. A route
into an excluded source path, a route naming a path that exists nowhere in the
source tree, and a workflow dependency that only an empty skeleton would
satisfy all fail the export closed. This verification never changes a
disposition and never rewrites a byte.

A control-plane surface is either a Markdown document (whose navigational routes
are Markdown hyperlink targets) or a workflow/automation file under
``.github/workflows/`` (whose routes are the repository-relative command
arguments of its ``run:`` steps, including folded ``run:`` blocks, plus local
``uses:`` action directories and static step ``working-directory`` values).
Workflow routes are extracted by structurally parsing the workflow YAML with
PyYAML and walking ``jobs.*.steps[].run``, so every YAML-equivalent spelling of
the ``run`` key (quoting, escaping) is decoded exactly as GitHub Actions
decodes it. Each relative ``run:`` argument is then resolved against its
step's effective working directory (step-level ``working-directory``, else the
job's ``defaults.run.working-directory``, else the workflow's
``defaults.run.working-directory``, else the repository root), because that is
the directory GitHub Actions actually executes the command in. Both species are
checked: a retained workflow that invokes an excluded path would ship a
permanently-failing route into the clean canvas. A path operand (shell
argument) that carries any part of an Actions ``${{ ... }}`` expression is
dynamically computed and cannot be statically resolved -- even when the
expression is separated from a path fragment by a slash within the operand --
so it is recorded in the receipt's ``unresolved_dynamic_routes`` as explicitly
classified, consciously unproven -- never silently accepted and never claimed
as proved. A step whose effective
working directory cannot be statically resolved (an Actions expression,
absolute/``~`` path, ``..`` escape or backslash path) likewise cannot be
located: its repo-relative operands are recorded as consciously unproven rather
than silently proved as though rooted at the repository root.

The artifact's path set, bytes, modes, and sidecar receipt depend only on the
exact tracked Git HEAD, the tracked portability policy, the tracked
engine-version source, the tracked exporter implementation, and the fixed
generation constants. They do not depend on the branch name, remote URL,
wall-clock time, network, current working directory, untracked files, or prior
destination contents.

The receipt additionally carries a comparable ``engine_version`` read from the
single root-level ``ENGINE_VERSION`` source of truth at the exact source commit.
That version is metadata, not a disposition: it is independent of Git history
(a raw commit SHA has no ordering semantics), and the source path is itself
classified ``EXCLUDE`` so it never appears in the exported customer tree. A
missing or malformed version source fails the export closed.

The policy and exporter are factory machinery: they are EXCLUDE surfaces and
must never appear in the exported customer tree. Any export receipt/manifest is
factory-side evidence written outside the customer tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import yaml

POLICY_RELPATH = "bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json"

# The single root-level source of truth for the comparable engine version. It is
# independent of Git history: the exporter reads its value from the exact source
# commit and records it in the receipt, and the value never appears in the
# exported customer tree (it is a factory/control-plane input, not shipped).
ENGINE_VERSION_RELPATH = "ENGINE_VERSION"

COPY = "COPY"
EXCLUDE = "EXCLUDE"
GENERATE_EMPTY = "GENERATE_EMPTY"
ALLOWED_DISPOSITIONS = (COPY, EXCLUDE, GENERATE_EMPTY)

# Directories that are pure factory control-plane and are never recreated as
# skeleton in the exported tree, even empty.
FACTORY_DIR_PREFIXES = ("bootstrap/", "tests/post_ev2_z/")

GENERATED_FILE_MODE = "100644"
REGULAR_FILE_MODES = ("100644", "100755")
SYMLINK_MODE = "120000"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

# On-disk filesystem species of an emitted path, read with a no-follow
# ``os.lstat`` so a regular file and a symlink that share a relative path are
# never collapsed to the same bare string.
SPECIES_REGULAR = "regular"
SPECIES_SYMLINK = "symlink"
SPECIES_DIRECTORY = "directory"

# SemVer 2.0.0 (https://semver.org): MAJOR.MINOR.PATCH with optional
# prerelease and build metadata. Ordering-comparable and independent of Git
# history, unlike a raw commit SHA. Numeric identifiers use explicit ASCII
# ``[0-9]`` (never Python's Unicode-aware ``\d``), because SemVer permits only
# ASCII digits and a malformed source containing a Unicode decimal digit such
# as U+0661 must fail closed.
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

POLICY_KEYS = frozenset(
    {"policy_version", "mission", "repository", "branch", "base_sha",
     "dispositions", "match_semantics", "identity", "rules", "generate"}
)
RULE_KEYS = frozenset({"disposition", "match"})
# A GENERATE_EMPTY rule may additionally declare the repository-relative
# ``output_path`` where its generated root is materialized, remapping a
# campaign-specific source path to a campaign-neutral output path.
GENERATE_RULE_KEYS = RULE_KEYS | {"output_path"}

# The ``identity`` policy block declares the source campaign identity the
# exported artifact must not carry. It is independent verification of the
# emitted tree, never a classification input: it never rewrites a copied byte
# and never reclassifies a path.
#   * ``path_tokens``            -- source-owned campaign identity tokens that
#                                   must not appear in any emitted path (file or
#                                   preserved directory skeleton).
#   * ``content_surfaces``       -- emitted user-facing surfaces whose actual
#                                   bytes must not contain the declared tokens.
#   * ``omitted_skeleton_prefixes`` -- directory prefixes whose stale named
#                                   skeleton is not recreated in the export
#                                   (only empties are ever omitted; files still
#                                   materialize their parent directories).
IDENTITY_KEYS = frozenset(
    {"path_tokens", "content_surfaces", "omitted_skeleton_prefixes"}
)

TEXT_DOC_SUFFIX = ".md"
WORKFLOW_DIR_PREFIX = ".github/workflows/"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
_LINK_RE = re.compile(r"\]\(([^)\n]*)\)")
_FENCE_RE = re.compile(r"```.*?```", re.S)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}", re.S)
_ACTION_METADATA_NAMES = ("action.yml", "action.yaml")
_ROUTE_SUFFIXES = (
    ".md", ".json", ".py", ".sql", ".txt", ".yml", ".yaml",
    ".toml", ".cfg", ".ini", ".sh", ".csv", ".html",
)
_REJECT_SUBSTRINGS = ("XXX", "<", ">", "*", "|", "?", ":", "\\", " ", "%")

# Route species. A route's *satisfied-ness* depends on what kind of reference
# it is, because the reference resolves differently at runtime:
#
# * a Markdown hyperlink is navigational; a reader sent to a preserved (even
#   empty) campaign skeleton directory still finds the directory that exists;
# * a workflow ``run:`` argument / local ``uses:`` target / static
#   ``working-directory`` is an executable dependency: GitHub executes or
#   resolves it, so an empty preserved skeleton counts for nothing -- a pytest
#   argument naming a directory whose every test file was excluded collects
#   zero tests (exit 5, no tests ran) and proves nothing.
ROUTE_DOC = "doc"
ROUTE_WORKFLOW = "workflow"


class ExportError(Exception):
    """Any export precondition/classification failure. Always fails closed."""


def _fail(message: str) -> "ExportError":
    return ExportError("CLEAN CAMPAIGN EXPORT REFUSED: " + message)


# --------------------------------------------------------------------------
# Git object access (exact tracked tree truth)
# --------------------------------------------------------------------------

def _git_bytes(args, cwd):
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(cwd), capture_output=True,
    )
    if proc.returncode != 0:
        raise _fail(
            f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def rev_parse(ref, repo_root) -> str:
    # Peel to a guaranteed commit object: ``<ref>^{commit}`` dereferences an
    # annotated tag to its commit and rejects a tree/blob, so a 40-hex-looking
    # non-commit object is never silently accepted as the exact source commit.
    return _git_bytes(
        ["rev-parse", f"{ref}^{{commit}}"], repo_root
    ).decode("ascii").strip()


def tracked_entries(ref, repo_root):
    """Return [(mode, obj_type, blob_sha, path)] for exact tracked HEAD truth."""
    raw = _git_bytes(["ls-tree", "-r", "-z", "--full-tree", ref], repo_root)
    entries = []
    for chunk in raw.split(b"\x00"):
        if not chunk:
            continue
        meta, _, path = chunk.partition(b"\t")
        mode, otype, sha = meta.decode("ascii").split(" ")
        entries.append((mode, otype, sha, path.decode("utf-8")))
    return entries


def source_dirs(ref, repo_root):
    """Every directory prefix represented by the exact tracked tree.

    Folder structure is preserved into the exported canvas, so a retained
    directory route (``npc/profiles/``) resolves even when all of its files are
    excluded as campaign instance material.
    """
    dirs = set()
    for _mode, _otype, _sha, path in tracked_entries(ref, repo_root):
        parts = path.split("/")
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]) + "/")
    return dirs


# --------------------------------------------------------------------------
# Policy contract
# --------------------------------------------------------------------------

def load_policy(ref, repo_root) -> dict:
    raw = _git_bytes(["show", f"{ref}:{POLICY_RELPATH}"], repo_root)
    return parse_policy(raw.decode("utf-8"))


def parse_policy(text: str) -> dict:
    try:
        policy = json.loads(text)
    except ValueError as exc:
        raise _fail(f"policy is not valid JSON: {exc}") from None
    if not isinstance(policy, dict):
        raise _fail("policy JSON must be an object")
    keys = frozenset(policy)
    unknown = keys - POLICY_KEYS
    missing = POLICY_KEYS - keys
    if unknown:
        raise _fail(f"unknown policy fields: {sorted(unknown)}")
    if missing:
        raise _fail(f"missing policy fields: {sorted(missing)}")
    if policy["policy_version"] != 1:
        raise _fail(f"unsupported policy_version: {policy['policy_version']!r}")
    for field in ("mission", "repository", "branch"):
        if not isinstance(policy[field], str) or not policy[field].strip():
            raise _fail(f"{field} must be a non-empty string")
    if not isinstance(policy["base_sha"], str) or not SHA40_RE.match(policy["base_sha"]):
        raise _fail("base_sha must be an exact 40-hex commit SHA")

    rules = policy["rules"]
    if not isinstance(rules, list) or not rules:
        raise _fail("rules must be a non-empty list")
    seen_matches = set()
    seen_outputs = {}
    for rule in rules:
        if not isinstance(rule, dict):
            raise _fail(
                f"each rule must be an object with exactly {sorted(RULE_KEYS)}"
            )
        disposition = rule.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise _fail(f"unknown disposition: {disposition!r}")
        keys = frozenset(rule)
        if disposition == GENERATE_EMPTY:
            if keys not in (RULE_KEYS, GENERATE_RULE_KEYS):
                raise _fail(
                    "a GENERATE_EMPTY rule must have exactly "
                    f"{sorted(RULE_KEYS)} or {sorted(GENERATE_RULE_KEYS)}"
                )
        elif keys != RULE_KEYS:
            raise _fail(f"each rule must have exactly {sorted(RULE_KEYS)}")
        match = rule["match"]
        if not isinstance(match, str) or not match:
            raise _fail("rule match must be a non-empty string")
        # Classification Granularity Rule: no folder may be labelled COPY as a
        # single unit. COPY is always an exact path; EXCLUDE may be a prefix.
        if disposition == COPY and match.endswith("/"):
            raise _fail(f"COPY rule may not be a directory prefix: {match!r}")
        # A generated root is materialized file-by-file at one output path, so
        # a folder-level GENERATE_EMPTY rule has no coherent remap target.
        if disposition == GENERATE_EMPTY and match.endswith("/"):
            raise _fail(
                f"GENERATE_EMPTY rule may not be a directory prefix: {match!r}"
            )
        if match in seen_matches:
            raise _fail(f"duplicate rule match: {match!r}")
        if match in seen_outputs:
            raise _fail(
                f"rule match collides with a generated output_path: {match!r}"
            )
        seen_matches.add(match)
        if match != match.strip() or "\\" in match:
            raise _fail(f"rule match must be a clean repository-relative path: {match!r}")
        if match.startswith("/") or ".." in match or "//" in match:
            raise _fail(f"rule match must be repository-relative: {match!r}")
        output_path = rule.get("output_path")
        if output_path is not None:
            if not isinstance(output_path, str) or not output_path:
                raise _fail("generated output_path must be a non-empty string")
            if output_path == match:
                raise _fail(
                    "generated output_path must differ from its source match: "
                    f"{output_path!r}"
                )
            if output_path.endswith("/"):
                raise _fail(
                    f"generated output_path must be a file path: {output_path!r}"
                )
            if output_path != output_path.strip() or "\\" in output_path:
                raise _fail(
                    "generated output_path must be a clean repository-relative "
                    f"path: {output_path!r}"
                )
            if output_path.startswith("/") or ".." in output_path or "//" in output_path:
                raise _fail(
                    f"generated output_path must be repository-relative: {output_path!r}"
                )
            # Dot path components are normalization aliases: ``./README.md`` and
            # ``docs/./guide.md`` name different raw strings than the paths they
            # actually materialize, so raw-string collision checks below could
            # never see them. The remap target must be its own normal form.
            if "." in output_path.split("/"):
                raise _fail(
                    "generated output_path must not contain '.' or '..' path "
                    f"components: {output_path!r}"
                )
            if output_path in seen_matches or output_path in seen_outputs:
                raise _fail(
                    f"generated output_path collides with another rule: {output_path!r}"
                )
            seen_outputs[output_path] = match

    # Every remap target must respect every other policy path boundary, not
    # only raw string equality: an EXCLUDE prefix owns its whole namespace, an
    # exact rule path may not hide beneath the target or have the target hidden
    # beneath it, and the target may not straddle another generated output's
    # file/directory boundary. All shapes here are normalized (no alias
    # components survive above), so these prefix/containment comparisons are
    # exact-path checks.
    for output_path, source_match in seen_outputs.items():
        for rule in rules:
            other = rule["match"]
            if other == source_match:
                continue
            if other.endswith("/"):
                if output_path.startswith(other):
                    raise _fail(
                        "generated output_path lands inside an EXCLUDE prefix: "
                        f"{output_path!r} -> {other!r}"
                    )
            elif output_path.startswith(other + "/"):
                raise _fail(
                    "generated output_path nests inside an exact policy rule: "
                    f"{output_path!r} -> {other!r}"
                )
            if other.startswith(output_path + "/"):
                raise _fail(
                    "generated output_path collides with an exact policy rule "
                    f"nested inside it: {output_path!r} -> {other!r}"
                )
        for other_output in seen_outputs:
            if other_output == output_path:
                continue
            if other_output.startswith(output_path + "/") or output_path.startswith(
                other_output + "/"
            ):
                raise _fail(
                    "generated output_path straddles another generated output "
                    f"path: {output_path!r} -> {other_output!r}"
                )

    identity = policy["identity"]
    if not isinstance(identity, dict):
        raise _fail("identity must be an object")
    unknown_identity = frozenset(identity) - IDENTITY_KEYS
    if unknown_identity:
        raise _fail(f"unknown identity fields: {sorted(unknown_identity)}")
    missing_identity = {"path_tokens", "content_surfaces"} - frozenset(identity)
    if missing_identity:
        raise _fail(f"missing identity fields: {sorted(missing_identity)}")

    path_tokens = identity["path_tokens"]
    if not isinstance(path_tokens, list) or not path_tokens:
        raise _fail("identity path_tokens must be a non-empty list")
    for token in path_tokens:
        if not isinstance(token, str) or not token.strip():
            raise _fail("identity path token must be a non-empty string")
        if token != token.strip().lower():
            raise _fail(
                "identity path token must be a lowercase, trimmed string: "
                f"{token!r}"
            )

    content_surfaces = identity["content_surfaces"]
    if not isinstance(content_surfaces, dict) or not content_surfaces:
        raise _fail("identity content_surfaces must be a non-empty object")
    for surface, tokens in content_surfaces.items():
        if not isinstance(surface, str) or not surface:
            raise _fail("identity content surface must be a non-empty string")
        if (
            surface.endswith("/")
            or surface.startswith("/")
            or ".." in surface
            or "." in surface.split("/")
            or "//" in surface
            or "\\" in surface
            or surface != surface.strip()
        ):
            raise _fail(
                "identity content surface must be a clean repository-relative "
                f"file path: {surface!r}"
            )
        if not isinstance(tokens, list) or not tokens:
            raise _fail(
                f"identity content surface {surface!r} must declare a non-empty "
                "token list"
            )
        for token in tokens:
            if not isinstance(token, str) or not token.strip():
                raise _fail("identity content token must be a non-empty string")

    omitted = identity.get("omitted_skeleton_prefixes", [])
    if not isinstance(omitted, list):
        raise _fail("identity omitted_skeleton_prefixes must be a list")
    for prefix in omitted:
        if not isinstance(prefix, str) or not prefix.endswith("/"):
            raise _fail(
                "identity omitted skeleton prefix must be a directory prefix "
                f"ending in '/': {prefix!r}"
            )
        if (
            prefix.startswith("/")
            or ".." in prefix
            or "." in prefix.split("/")
            or "//" in prefix
            or "\\" in prefix
            or prefix != prefix.strip()
        ):
            raise _fail(
                "identity omitted skeleton prefix must be a clean "
                f"repository-relative directory: {prefix!r}"
            )
        if not any(
            rule["disposition"] == EXCLUDE
            and rule["match"].endswith("/")
            and prefix.startswith(rule["match"])
            for rule in rules
        ):
            raise _fail(
                "identity omitted skeleton prefix must be owned by an EXCLUDE "
                f"directory rule: {prefix!r}"
            )

    generate = policy["generate"]
    if not isinstance(generate, dict):
        raise _fail("generate must be an object")
    generated_paths = {
        rule.get("output_path", rule["match"])
        for rule in rules
        if rule["disposition"] == GENERATE_EMPTY
    }
    for path, document in generate.items():
        if path not in generated_paths:
            raise _fail(f"generated path has no GENERATE_EMPTY rule: {path!r}")
        if not isinstance(document, (dict, str)):
            raise _fail(
                f"generated document must be a JSON object or raw string: {path!r}"
            )
    for path in generated_paths:
        if path not in generate:
            raise _fail(f"GENERATE_EMPTY rule has no generation constant: {path!r}")
    return policy


# --------------------------------------------------------------------------
# Engine version (single source of truth; metadata only, never a disposition)
# --------------------------------------------------------------------------

def parse_engine_version(text: str) -> str:
    """Validate the single engine-version source value, or FAIL closed.

    The value is a SemVer 2.0.0 string. An empty or malformed source fails the
    export closed rather than emitting an unversioned or nonsensical receipt.
    """
    version = text.strip()
    if not version:
        raise _fail("engine version source is empty")
    if not SEMVER_RE.match(version):
        raise _fail(f"engine version source is not a valid semver: {version!r}")
    return version


def load_engine_version(ref, repo_root) -> str:
    """Read the engine version from the single source at the exact commit.

    The value is read from the exact source commit's ``ENGINE_VERSION`` (like
    the portability policy), so the receipt's engine version is bound to the
    exported tree and independent of the working tree, branch name, and Git
    history ordering. A missing or malformed source fails the export closed.
    """
    try:
        raw = _git_bytes(["show", f"{ref}:{ENGINE_VERSION_RELPATH}"], repo_root)
    except ExportError as exc:
        raise _fail(
            f"engine version source missing at {ref}:{ENGINE_VERSION_RELPATH}: {exc}"
        ) from None
    return parse_engine_version(raw.decode("utf-8"))


# --------------------------------------------------------------------------
# Structural classification (path-only; no content is ever consulted)
# --------------------------------------------------------------------------

def _match_length(match: str, path: str) -> int:
    if match.endswith("/"):
        return len(match) if path.startswith(match) else -1
    return len(match) if path == match else -1


def disposition_for_path(policy: dict, path: str) -> str:
    """Resolve exactly one disposition for a path, or FAIL closed.

    The rule with the longest matching string wins. No match is an
    unclassified path; more than one rule tied at the winning length is an
    ambiguous path. Both fail closed.
    """
    best_length = -1
    winners = []
    for rule in policy["rules"]:
        length = _match_length(rule["match"], path)
        if length < 0:
            continue
        if length > best_length:
            best_length = length
            winners = [rule]
        elif length == best_length:
            winners.append(rule)
    if not winners:
        raise _fail(f"unclassified tracked path: {path!r}")
    if len(winners) > 1:
        raise _fail(
            f"ambiguous tracked path (multiple dispositions tied): {path!r}"
        )
    return winners[0]["disposition"]


def generated_bytes(policy: dict, path: str) -> bytes:
    document = policy["generate"].get(path)
    if document is None:
        raise _fail(f"no generation constant for {path!r}")
    if isinstance(document, str):
        return (document.rstrip("\n") + "\n").encode("utf-8")
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def generate_output_path(policy: dict, path: str) -> str:
    """Return the exported output path for a GENERATE_EMPTY source path.

    A GENERATE_EMPTY rule may declare a campaign-neutral ``output_path`` so its
    generated root is materialized there instead of at its campaign-specific
    source path; a rule without ``output_path`` generates at the source path.
    """
    for rule in policy["rules"]:
        if rule["disposition"] == GENERATE_EMPTY and rule["match"] == path:
            return rule.get("output_path", path)
    raise _fail(f"no GENERATE_EMPTY rule for {path!r}")


# --------------------------------------------------------------------------
# Identity acceptance (verification only; never a classification input)
# --------------------------------------------------------------------------

def identity_acceptance(policy, emitted_paths, surface_bytes):
    """Return machine-readable identity-acceptance evidence for the export.

    Independent verification -- not a classification input, never a byte
    rewrite, never a path reclassification. In ``export`` it is applied twice:
    first to the expected pre-materialization tree (an early fail-fast
    preflight) and then, authoritatively, to the ACTUAL completed on-disk tree
    and its real content-surface bytes (the durable acceptance evidence the
    receipt records). Two structural checks:

    * every emitted path (exported file or preserved directory skeleton) must be
      free of every declared campaign-identity path token, so a named
      source-owned character/location/NPC/faction path -- or the empty skeleton
      of one, which leaks the name even with no file -- fails closed;
    * every declared identity content surface must be present in the export and
      its actual emitted bytes must be free of every declared campaign-identity
      content token, so a user-facing surface that asserts the source campaign's
      identity (for example a root README claiming to be the live campaign)
      fails closed.

    ``violations`` is empty on acceptance. The returned dict is the durable,
    machine-readable identity-acceptance evidence recorded in the receipt.
    """
    identity = policy["identity"]
    violations = []
    emitted = sorted(set(emitted_paths))
    for path in emitted:
        lowered = path.lower()
        for token in identity["path_tokens"]:
            if token.lower() in lowered:
                violations.append(
                    f"emitted path {path!r} carries campaign identity token "
                    f"{token!r}"
                )
    for surface in sorted(identity["content_surfaces"]):
        data = surface_bytes.get(surface)
        if data is None:
            violations.append(
                f"identity content surface {surface!r} is not present in the "
                "export"
            )
            continue
        text = data.decode("utf-8", "replace").lower()
        for token in identity["content_surfaces"][surface]:
            if token.lower() in text:
                violations.append(
                    f"identity content surface {surface!r} asserts campaign "
                    f"identity token {token!r}"
                )
    evidence = {
        "path_tokens": sorted(identity["path_tokens"]),
        "content_surfaces": {
            surface: sorted(tokens)
            for surface, tokens in sorted(identity["content_surfaces"].items())
        },
        "omitted_skeleton_prefixes": sorted(
            identity.get("omitted_skeleton_prefixes", [])
        ),
        "emitted_path_count": len(emitted),
        "violations": sorted(set(violations)),
    }
    evidence["accepted"] = not evidence["violations"]
    return evidence


# --------------------------------------------------------------------------
# Reference integrity (verification only; never a classification input)
# --------------------------------------------------------------------------

def _candidate_routes(text: str):
    """Yield normalized repository-relative link-route strings from a doc.

    A "route" is a Markdown hyperlink target (``](target)``): a navigational
    reference another document sends a reader to. Inline code spans and plain
    prose mentions are document *content* (examples, commands, symbol names),
    not routes, and are deliberately not treated as navigational authority; the
    references the Mission must keep live are the router/control links.
    """
    stripped = _FENCE_RE.sub("\n", text)
    raw_targets = [match.group(1).strip() for match in _LINK_RE.finditer(stripped)]
    seen = set()
    for raw in raw_targets:
        candidate = raw.split()[0] if raw else ""
        candidate = candidate.split("#", 1)[0].split("?", 1)[0]
        while candidate.startswith("./"):
            candidate = candidate[2:]
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if candidate.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if any(token in candidate for token in _REJECT_SUBSTRINGS):
            continue
        if not _TOKEN_RE.fullmatch(candidate):
            continue
        if "/" not in candidate and not candidate.endswith(_ROUTE_SUFFIXES):
            continue
        yield candidate


def _default_run_working_directory(container) -> str:
    """Return a container's ``defaults.run.working-directory`` string, or ''."""
    if not isinstance(container, dict):
        return ""
    defaults = container.get("defaults")
    if not isinstance(defaults, dict):
        return ""
    run_defaults = defaults.get("run")
    if not isinstance(run_defaults, dict):
        return ""
    value = run_defaults.get("working-directory")
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _step_working_directory(document, job, step) -> str:
    """Return the effective ``working-directory`` for a workflow step.

    GitHub Actions runs a step's command relative to its step-level
    ``working-directory`` if set, else the job's
    ``defaults.run.working-directory``, else the workflow-level
    ``defaults.run.working-directory``, else the repository root ('' here).
    """
    for source in (
        step.get("working-directory"),
        _default_run_working_directory(job),
        _default_run_working_directory(document),
    ):
        if isinstance(source, str) and source.strip():
            return source.strip()
    return ""


def _run_commands(text: str):
    """Yield ``(command, working_directory)`` for every workflow ``run:`` step.

    The workflow is parsed with a real YAML parser (PyYAML) and the ``run``
    values are read by structurally walking ``jobs.*.steps[].run``. This is
    immune by construction to every YAML-equivalent spelling of the ``run``
    key -- bare, single-quoted, double-quoted, and double-quoted with escape
    sequences (``"\\u0072un":`` decodes to the key ``run``) -- because the
    parser is the same class of tool GitHub Actions itself uses to decide what
    ``run:`` means. Each command is paired with its step's effective working
    directory (step override, else job default, else workflow default, else
    repo root); keys such as ``on:``/``env:`` are deliberately not scanned.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _fail(f"retained workflow is not valid YAML: {exc}") from None
    if not isinstance(document, dict):
        return
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            command = step.get("run")
            if isinstance(command, str):
                yield command, _step_working_directory(document, job, step)


def _route_species(path: str) -> str | None:
    """Return the route species of a control-plane surface path, or None."""
    if path.endswith(TEXT_DOC_SUFFIX):
        return ROUTE_DOC
    if path.startswith(WORKFLOW_DIR_PREFIX) and path.endswith(WORKFLOW_SUFFIXES):
        return ROUTE_WORKFLOW
    return None


def _expression_spans(block: str) -> list:
    return [(m.start(), m.end()) for m in _EXPRESSION_RE.finditer(block)]


def _expression_operand_spans(block: str, spans) -> list:
    """Return the spans of shell words (path operands) carrying an expression.

    A ``run:`` value is a shell command line: arguments are separated by
    whitespace, while path separators (``/``) join fragments of a single path
    operand. GitHub Actions interpolates every ``${{ ... }}`` expression before
    the shell runs, so a path operand that contains any part of an expression is
    a dynamically computed string -- never a statically resolvable repository
    path. This is decided per *operand* (non-whitespace run), not per
    ``_TOKEN_RE`` fragment: an expression separated from a path fragment by a
    slash (``${{ matrix.dir }}/tests/unit``) shares the operand with the closing
    ``}}`` and is dynamic, whereas an argument separated by whitespace
    (``${{ matrix.dir }} unit.py``) is an independent operand.

    An Actions expression may itself contain whitespace (``${{ matrix.dir }}``),
    so a naive non-whitespace split would cut through the expression. That is
    harmless here because each word is tested against the parsed expression
    *span*: every word that overlaps any part of an expression span is dynamic
    (the ``${{`` fragment, the expression body, and the ``}}/fragment`` word
    alike), so internal expression whitespace never loses or misclassifies the
    operand, and a slash-joined fragment sharing the closing-delimiter word
    stays dynamic.
    """
    operands = []
    for word in re.finditer(r"\S+", block):
        word_start, word_end = word.span()
        if any(span_start < word_end and span_end > word_start
               for span_start, span_end in spans):
            operands.append((word_start, word_end))
    return operands


def _in_expression_operand(match, operand_spans) -> bool:
    """True when a token match lies inside a dynamically computed operand."""
    start, end = match.span()
    return any(
        operand_start <= start and end <= operand_end
        for operand_start, operand_end in operand_spans
    )


def _local_action_uses(text: str):
    """Yield repository-relative local action directories from ``uses:`` steps.

    A ``uses: ./path`` value names a repo-local composite/action directory that
    GitHub resolves from the repository root. An ``owner/repo@ref`` value
    references an external action and is deliberately not yielded.

    A repo-root local action -- ``uses: ./`` (or the equivalent ``uses: .//``
    spelling) -- names the repository root itself; it is yielded as the empty
    string ``""`` so it is a visible, checkable dependency rather than being
    silently discarded. The empty string is a real route: the root always
    exists, but it is only a valid action when it ships its
    ``action.yml``/``action.yaml`` metadata (checked by the caller).
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _fail(f"retained workflow is not valid YAML: {exc}") from None
    if not isinstance(document, dict):
        return
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return
    seen = set()
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str):
                continue
            candidate = uses.strip()
            if not candidate.startswith("./"):
                continue
            while candidate.startswith("./"):
                candidate = candidate[2:]
            candidate = candidate.rstrip("/")
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate


def _local_action_metadata_present(action_dir: str, files_present) -> bool:
    """Whether an exported local action root declares its required metadata.

    GitHub resolves a repo-local ``uses: ./path`` against an action directory
    whose root must contain an ``action.yml`` or ``action.yaml`` metadata file;
    without it the step cannot load the action. Any other file in the folder (a
    README, a script, a fixture) does not make the action runnable, so a folder
    containing unrelated files but no metadata satisfies nothing.

    A repo-root local action (``action_dir`` is the empty string) resolves at
    the repository root, so its metadata must be the root-level ``action.yml``
    or ``action.yaml`` -- never a leading-slash path such as ``/action.yml``,
    and never an unrelated root file.
    """
    prefix = f"{action_dir}/" if action_dir else ""
    return any(
        f"{prefix}{name}" in files_present
        for name in _ACTION_METADATA_NAMES
    )


def _working_directory_prefix(working_directory: str):
    """Resolve a step's effective working directory into a route prefix.

    Returns ``(prefix, unresolved)``. GitHub Actions runs a ``run:`` command
    relative to its effective working directory, so the command's path arguments
    resolve under that directory.

    * No working directory -> the repository root: ``("", False)``.
    * A statically resolvable repository-relative directory -> its prefix
      (trailing slash) with ``unresolved=False``.
    * A directory that is present but cannot be resolved structurally to a
      repository-relative location -- an Actions ``${{ ... }}`` expression, an
      absolute/``~`` path, a ``..`` escape, or a backslash path -> ``("", True)``.
      The command's real run location is unknown, so its repo-relative route
      operands must be classified as consciously unproven rather than silently
      treated as rooted at the repository root (which would falsely prove, or
      falsely fail, a path that may not exist there).
    """
    candidate = working_directory.strip()
    while candidate.startswith("./"):
        candidate = candidate[2:]
    candidate = candidate.rstrip("/")
    if not candidate:
        return "", False
    if candidate.startswith(("/", "~", "$")):
        return "", True
    if "${{" in candidate or "}}" in candidate or "\\" in candidate:
        return "", True
    if ".." in candidate.split("/"):
        return "", True
    return candidate + "/", False


def _workflow_routes(text: str):
    """Yield ``(route, is_dynamic)`` from workflow ``run:`` steps.

    Command arguments that name a repository path (``scripts/foo.py``,
    ``tests/rt02``, ``tests/fixtures/hooks/valid``) are routes; shell builtins,
    flags, environment variables, DSNs and ``${{ ... }}`` expressions are not.
    Each relative argument is resolved against its step's effective
    ``working-directory`` (step-level override, else the job default, else the
    workflow default, else the repository root) -- the directory GitHub
    Actions actually runs the command in -- before resolving to a source path.
    The same normalization and rejection rules as Markdown routes then apply.
    A route candidate that belongs to a path operand carrying an Actions
    ``${{ ... }}`` expression is yielded with ``is_dynamic``: the operand is a
    dynamically computed string, so it cannot be statically resolved and is
    never silently treated as either a satisfied or an excluded dependency.
    Classification is per path operand (shell word), not per ``_TOKEN_RE``
    fragment: an expression separated from a path fragment only by a slash
    (``${{ matrix.dir }}/tests/unit``) still makes that whole operand dynamic,
    while an argument separated by whitespace (``${{ matrix.dir }} unit.py``)
    is an independent operand and stays statically checked. A step whose
    effective working directory cannot be statically resolved (an Actions
    expression, absolute/``~`` path, ``..`` escape or backslash path) likewise
    marks every repo-relative operand it runs as ``is_dynamic``: the command's
    real run location is unknown, so a candidate that would otherwise appear to
    resolve at the repository root must not be claimed as proved. Deduplication
    is by
    normalized route *and* dynamic/static classification, not by route alone:
    the same route can occur both as a dynamic occurrence and as a static
    argument (in either order), and collapsing the two would either hide a
    missing static executable dependency behind a dynamic mention or drop the
    honest dynamic receipt entry. Only exact same-class duplicates are
    deduplicated.
    """
    seen = set()
    for block, working_directory in _run_commands(text):
        prefix, wd_unresolved = _working_directory_prefix(working_directory)
        operand_spans = _expression_operand_spans(block, _expression_spans(block))
        for match in _TOKEN_RE.finditer(block):
            candidate = match.group(0)
            while candidate.startswith("./"):
                candidate = candidate[2:]
            if not candidate:
                continue
            if any(token in candidate for token in _REJECT_SUBSTRINGS):
                continue
            if not _TOKEN_RE.fullmatch(candidate):
                continue
            if "/" not in candidate and not candidate.endswith(_ROUTE_SUFFIXES):
                continue
            route = f"{prefix}{candidate}" if prefix else candidate
            is_dynamic = wd_unresolved or _in_expression_operand(match, operand_spans)
            if (route, is_dynamic) in seen:
                continue
            seen.add((route, is_dynamic))
            yield route, is_dynamic


def _resolve_route(candidate: str, referencing_dir: str, source_files, source_dirs):
    """Return the exact source route a candidate resolves to, or None."""
    normalized = []
    if candidate:
        normalized.append(candidate)
    if referencing_dir:
        normalized.append(f"{referencing_dir.rstrip('/')}/{candidate}")
    for relative in normalized:
        if relative in source_files or relative in source_dirs:
            return relative
        if any(path.startswith(relative + "/") for path in source_files):
            return relative
    return None


def _dangling_lines(dangling):
    lines = []
    for referrer, candidate, resolved in dangling:
        if resolved is None:
            lines.append(
                f"  {referrer} -> {candidate!r} names a path that does not exist "
                "in the source tree"
            )
        else:
            lines.append(
                f"  {referrer} -> {candidate!r} resolves to excluded {resolved!r}"
            )
    return lines


def _route_satisfied(resolved: str, species: str, files_present, docs_present) -> bool:
    """Whether a resolved route is satisfied by the exported tree.

    Species-aware on purpose: a Markdown hyperlink may be satisfied by a
    preserved (even empty) campaign skeleton directory, because a reader sent
    there still finds the directory; an executable workflow dependency (``run:``
    argument, local ``uses:`` action, static ``working-directory``) is only
    satisfied by a real exported file at or under the resolved path -- an empty
    preserved skeleton collects zero tests/scripts and satisfies nothing.
    """
    if resolved in files_present:
        return True
    if species == ROUTE_WORKFLOW:
        return any(exported.startswith(resolved + "/") for exported in files_present)
    return resolved in docs_present or any(
        exported.startswith(resolved + "/") for exported in docs_present
    )


def _directory_satisfied(resolved: str, files_present) -> bool:
    """Whether a resolved route is a real exported *directory*.

    A workflow ``working-directory`` is a directory, not a file: GitHub
    ``cd``s into it before running the step, so the resolved path must be a
    real exported directory holding at least one exported file at or under it.
    An exported *file* at the exact resolved path is deliberately not enough
    (changing directory into a file is impossible), and a preserved empty
    skeleton or all-``EXCLUDE`` directory has no exported descendant, so none
    of them satisfy a working directory. A repository path is not one
    universal species: ``working-directory`` requires directory-ness, while a
    general ``run:`` argument may legitimately name either an exported file or
    a populated directory.
    """
    return any(exported.startswith(resolved + "/") for exported in files_present)


def _surface_route_failures(species, text, referencing_dir, source_files,
                            source_dirs, files_present, docs_present):
    """Return (failures, dynamic_routes) for one control-plane surface's bytes.

    ``failures`` are ``(candidate, resolved_or_None)``: an entry whose resolved
    value is None names a path that exists nowhere in the source tree (a
    statically written, never-existing dependency -- it cannot work in any
    exported tree either). ``dynamic_routes`` are candidates that cannot be
    located structurally -- a route operand carrying an Actions expression, or
    any operand (and the working directory itself) of a step whose effective
    working directory is unresolvable -- and are returned for
    explicit honest classification instead of being silently accepted or
    silently failed. Markdown documents keep the forward-placeholder tolerance
    (unresolvable link candidates are ignored): their routes are navigational,
    not executable commands.
    """
    failures = []
    dynamic_routes = []
    if species == ROUTE_WORKFLOW:
        for candidate, is_dynamic in _workflow_routes(text):
            if is_dynamic:
                dynamic_routes.append(candidate)
                continue
            resolved = _resolve_route(
                candidate, referencing_dir, source_files, source_dirs
            )
            if resolved is None:
                failures.append((candidate, None))
                continue
            if _route_satisfied(resolved, species, files_present, docs_present):
                continue
            failures.append((candidate, resolved))
        for _command, working_directory in _run_commands(text):
            prefix, unresolved = _working_directory_prefix(working_directory)
            if unresolved:
                # The command's real run location is a dynamic/absolute/escaping
                # path, so the step cannot be located structurally. Record the
                # unproven run location instead of silently skipping it (which
                # let a route operand masquerade as a repo-root dependency).
                dynamic_routes.append(f"working-directory {working_directory!r}")
                continue
            if not prefix:
                continue
            resolved = _resolve_route(
                prefix.rstrip("/"), "", source_files, source_dirs
            )
            if resolved is None:
                failures.append((f"working-directory {working_directory!r}", None))
                continue
            # A step's effective working directory is a DIRECTORY the runner
            # changes into, so it must satisfy the directory rule: a real
            # exported file at or under it, never the exact path itself when
            # that path is an exported file (chdir into a file is impossible)
            # and never an empty preserved skeleton or all-EXCLUDE directory
            # (which holds no exported descendant).
            if _directory_satisfied(resolved, files_present):
                continue
            failures.append((f"working-directory {working_directory!r}", resolved))
        for action_dir in _local_action_uses(text):
            if not action_dir:
                # Repo-root local action (``uses: ./``): the root always
                # exists, so it is not resolved against the source tree -- it
                # is valid only when the exported root ships its action
                # metadata. The empty route is checked, never silently
                # accepted or discarded.
                if not _local_action_metadata_present("", files_present):
                    failures.append(("local action uses '.'", "."))
                continue
            resolved = _resolve_route(
                action_dir, "", source_files, source_dirs
            )
            if resolved is None:
                failures.append((f"local action uses {action_dir!r}", None))
                continue
            if not _local_action_metadata_present(resolved, files_present):
                failures.append((f"local action uses {action_dir!r}", resolved))
    else:
        for candidate in _candidate_routes(text):
            resolved = _resolve_route(
                candidate, referencing_dir, source_files, source_dirs
            )
            if resolved is None:
                continue
            if _route_satisfied(resolved, species, files_present, docs_present):
                continue
            failures.append((candidate, resolved))
    return failures, dynamic_routes


def check_reference_integrity(policy, tracked, export_files, skeleton_dirs,
                              repo_root, report=False):
    """Fail closed when a shipped route cannot be executed in the export.

    Retained control-plane surfaces are checked: COPY surfaces through their
    source bytes and GENERATE_EMPTY surfaces through their generated policy
    bytes. Markdown documents are checked via their link routes; workflow files
    via their ``run:`` command routes, local ``uses:`` actions and static
    ``working-directory`` steps, all decoded by a structural YAML parse and
    resolved against each step's effective working directory.

    A route fails closed when it resolves to an excluded source path, or --
    for the executable workflow species -- when the only thing that satisfies
    it in the export is an empty preserved skeleton directory (a directory
    named in a pytest command with zero exported test modules proves nothing),
    or when it names a path that exists nowhere in the source tree. Routes that
    never resolved to a real source path remain tolerated for Markdown
    documents only (forward placeholders such as ``canon/days/day_XXX.md``);
    a workflow's dynamically computed route operands, and the operands of any
    step whose effective working directory is unresolvable, are returned
    separately for explicit honest classification instead of being silently
    accepted.

    Returns ``(dangling, dynamic_routes)`` where ``dangling`` is the failure
    list (raising unless ``report``) and ``dynamic_routes`` is the list of
    ``(surface_path, candidate)`` fragments that were consciously not proved.
    """
    source_files = {path for _mode, _otype, _sha, path in tracked}
    source_dirs = set(skeleton_dirs)
    for _mode, _otype, _sha, path in tracked:
        parts = path.split("/")
        for index in range(1, len(parts)):
            source_dirs.add("/".join(parts[:index]) + "/")

    files_present = set(export_files)
    docs_present = files_present | set(skeleton_dirs)
    dangling = []
    dynamic_routes = []

    surfaces = []
    for mode, _otype, sha, path in tracked:
        disposition = disposition_for_path(policy, path)
        if disposition != COPY:
            continue
        species = _route_species(path)
        if species is None:
            continue
        text = _git_bytes(["cat-file", "blob", sha], repo_root).decode(
            "utf-8", "replace"
        )
        surfaces.append((path, path, species, text))
    for rule in policy["rules"]:
        if rule["disposition"] != GENERATE_EMPTY:
            continue
        output_path = rule.get("output_path", rule["match"])
        species = _route_species(output_path)
        if species is None:
            continue
        text = generated_bytes(policy, output_path).decode("utf-8")
        surfaces.append((rule["match"], output_path, species, text))

    for source_path, output_path, species, text in surfaces:
        referencing_dir = (
            output_path.rsplit("/", 1)[0] if "/" in output_path else ""
        )
        failures, surface_dynamic = _surface_route_failures(
            species, text, referencing_dir, source_files, source_dirs,
            files_present, docs_present,
        )
        for candidate, resolved in failures:
            dangling.append((output_path, candidate, resolved))
        for candidate in surface_dynamic:
            dynamic_routes.append((output_path, candidate))

    dynamic_routes = sorted(set(dynamic_routes))
    if not dangling:
        return [], dynamic_routes
    dangling.sort(key=lambda item: (item[0], item[1], item[2] or ""))
    if report:
        return dangling, dynamic_routes
    detail = "\n".join(_dangling_lines(dangling))
    raise _fail(
        "retained control-plane route(s) do not resolve to a runnable exported "
        "dependency:\n" + detail
    )


# --------------------------------------------------------------------------
# Path safety (transport only; not a path-security subsystem)
# --------------------------------------------------------------------------

def _resolved(path) -> Path:
    return Path(path).resolve()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(child), str(parent)]) == str(parent)
    except ValueError:
        return False


def _git_toplevel(repo_root) -> Path:
    """Return the true Git top level for the supplied --repo-root.

    ``--repo-root`` must name the real repository top level, not merely any
    directory inside it: Git itself discovers the true root, so a narrower
    caller-supplied path would silently defeat the overlap guards below.
    """
    raw = _git_bytes(["rev-parse", "--show-toplevel"], repo_root)
    toplevel = raw.decode("utf-8", "replace").strip()
    if not toplevel:
        raise _fail("could not determine the Git top level for --repo-root")
    return _resolved(toplevel)


def guard_paths(repo_root, output, receipt) -> None:
    repo_root = _resolved(repo_root)
    toplevel = _git_toplevel(repo_root)
    if toplevel != repo_root:
        raise _fail(
            f"--repo-root must resolve to the true Git top level {str(toplevel)!r}, "
            f"got {str(repo_root)!r}"
        )
    output = _resolved(output)
    receipt = _resolved(receipt)
    if output == repo_root or _is_within(output, repo_root) or _is_within(repo_root, output):
        raise _fail(
            f"source/output overlap refused: output {str(output)!r} overlaps "
            f"source tree {str(repo_root)!r}"
        )
    if receipt == repo_root or _is_within(receipt, repo_root):
        raise _fail(f"receipt must be outside the source repository: {str(receipt)!r}")
    if _is_within(receipt, output):
        raise _fail(f"receipt must be outside the exported tree: {str(receipt)!r}")


def _write_file(full: Path, data: bytes, mode: str) -> None:
    full.parent.mkdir(parents=True, exist_ok=True)
    if mode == SYMLINK_MODE:
        if full.exists() or full.is_symlink():
            full.unlink()
        os.symlink(data.decode("utf-8"), full)
        return
    if mode not in REGULAR_FILE_MODES:
        raise _fail(f"unsupported Git file mode {mode!r} for {str(full)!r}")
    full.write_bytes(data)
    try:
        os.chmod(full, 0o755 if mode == "100755" else 0o644)
    except OSError:
        pass


def _lstat_species(full: Path) -> str:
    """Return the no-follow filesystem species of an emitted path, or FAIL.

    ``os.lstat`` never follows a symbolic link, so a substituted symlink is
    classified as a symlink rather than as whatever its target happens to be; a
    symlink to a directory is therefore never traversed as a directory. Any
    species other than a regular file, a symlink or a directory fails closed.
    """
    try:
        mode = os.lstat(full).st_mode
    except OSError as exc:
        raise _fail(f"cannot stat emitted path {str(full)!r}: {exc}") from None
    if stat.S_ISLNK(mode):
        return SPECIES_SYMLINK
    if stat.S_ISDIR(mode):
        return SPECIES_DIRECTORY
    if stat.S_ISREG(mode):
        return SPECIES_REGULAR
    raise _fail(
        f"unexpected filesystem entry kind in emitted output: {str(full)!r}"
    )


def _actual_emitted_inventory(output) -> dict:
    """Map every ACTUAL emitted relative path to its no-follow species.

    Files (and symlinks, which are emitted leaves) are keyed bare; real
    directories are keyed with a trailing ``/``. Each entry's kind is read with
    ``os.lstat`` (see ``_lstat_species``), so a regular file and a symlink that
    share a relative path are NOT collapsed onto the same bare string -- the
    replaced kind stays visible to the inventory guard -- and a symlinked
    directory is recorded as one leaf and never traversed, so a link cannot
    smuggle an unbounded subtree past the guard. Any other filesystem species
    fails closed.

    Traversal completeness is part of the contract: this walk is a strict,
    no-follow ``os.scandir`` recursion rather than ``os.walk``. Python documents
    that ``os.walk`` silently IGNORES ``scandir`` errors unless ``onerror`` is
    supplied, and even a ``DirEntry`` classification error can be swallowed
    (CPython bpo-46084); either would silently drop a subtree's children so an
    unlisted extra path inside an expected directory could be certified clean.
    Here every directory whose ``scandir`` raises -- and every entry whose
    ``lstat`` raises -- fails the export closed, so a partial or unscannable
    inventory can never be accepted.
    """
    root = Path(output)
    inventory = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                children = list(entries)
        except OSError as exc:
            raise _fail(
                f"cannot scan emitted directory {str(directory)!r}: {exc}"
            ) from None
        for entry in children:
            full = Path(entry.path)
            relative = os.path.relpath(str(full), str(root)).replace(os.sep, "/")
            species = _lstat_species(full)
            if species == SPECIES_SYMLINK:
                inventory[relative] = SPECIES_SYMLINK
            elif species == SPECIES_DIRECTORY:
                inventory[relative + "/"] = SPECIES_DIRECTORY
                pending.append(full)
            else:
                inventory[relative] = SPECIES_REGULAR
    return inventory


# The exact POSIX permission bits a regular output must carry for its authorized
# Git mode. Git tracks only the executable bit, so ``100755`` materializes 0755
# and ``100644`` (COPY or GENERATE_EMPTY) materializes 0644.
def _permission_contract(mode: str):
    """Return the required POSIX permission bits for a regular Git mode, or None.

    ``None`` (a symlink or an unknown mode) carries no POSIX permission contract.
    """
    if mode == "100755":
        return 0o755
    if mode == "100644":
        return 0o644
    return None


def _posix_permission_modes_observable() -> bool:
    """Whether the host exposes POSIX permission bits via ``chmod``/``lstat``.

    On Windows ``os.chmod`` only toggles the read-only attribute, so a Git
    ``100755`` executable bit is not representable and cannot be proven locally;
    the Ubuntu CI job proves executable-mode fidelity on a POSIX host. When this
    returns ``False`` the mode contract is simply not asserted on this host -- it
    is never silently claimed as verified -- while path/kind/byte attestation
    still applies everywhere.
    """
    return os.name == "posix"


def _posix_mode_attestation() -> str:
    """Machine-readable POSIX-mode attestation status recorded in the receipt.

    Derived from the same capability predicate the mode verifier uses
    (``_posix_permission_modes_observable``), never caller-supplied, so the
    receipt cannot claim a proof the host did not perform: ``"verified"`` only
    when the host exposes POSIX permission bits -- in which case
    ``_emitted_mode_violations`` asserted every emitted regular file's real mode
    against its authorized Git ``100755``/``100644`` contract before this receipt
    was written -- and ``"not_observable"`` when the host cannot represent those
    bits and the mode contract was therefore not asserted. It is never
    ``"verified"`` while mode verification was skipped. This keeps
    ``identity_acceptance.accepted`` identity-only evidence and stops the receipt
    from silently implying a platform mode proof it did not make.
    """
    return "verified" if _posix_permission_modes_observable() else "not_observable"


def _emitted_mode_violations(full: Path, path: str, mode: str):
    """POSIX permission violations for one emitted regular file, or ``[]``.

    Compares the real, no-follow on-disk mode (``os.lstat`` + ``stat.S_IMODE``)
    against the mode its authorized Git disposition requires. A post-write
    0755 -> 0644 downgrade of an executable COPY -- or an accidental 0644 -> 0755
    execute bit -- leaves the path kind and bytes identical, so this is the only
    check that can catch it. Empty where the host cannot observe POSIX modes.
    """
    expected_bits = _permission_contract(mode)
    if expected_bits is None or not _posix_permission_modes_observable():
        return []
    try:
        actual_bits = stat.S_IMODE(os.lstat(full).st_mode)
    except OSError as exc:
        return [f"cannot stat emitted path {path!r} for its POSIX mode: {exc}"]
    if actual_bits != expected_bits:
        return [
            f"emitted path {path!r} has POSIX mode {oct(actual_bits)} but its "
            f"authorized Git mode {mode!r} requires {oct(expected_bits)}"
        ]
    return []


def _expected_output_inventory(policy, resolved, skeleton_dirs, export_files) -> dict:
    """Authoritative expected output path set with each path's declared species.

    Each retained file declares the species its authoritative source implies: a
    Git ``120000`` symlink COPY is expected to materialize as an actual on-disk
    symlink, while every regular-file COPY (``100644``/``100755``) and every
    GENERATE_EMPTY generated root is expected to materialize as an actual on-disk
    regular file. Every preserved skeleton directory and every ancestor directory
    of an exported file is expected to be a real directory. These kinds are the
    *declared expectation*, never derived from what actually landed on disk.
    """
    inventory = {}
    for mode, _sha, path, disposition in resolved:
        if disposition == EXCLUDE:
            continue
        if disposition == COPY:
            output_path = path
            species = SPECIES_SYMLINK if mode == SYMLINK_MODE else SPECIES_REGULAR
        else:  # GENERATE_EMPTY
            output_path = generate_output_path(policy, path)
            species = SPECIES_REGULAR
        inventory[output_path] = species
    for directory in skeleton_dirs:
        inventory[directory] = SPECIES_DIRECTORY
    for path in export_files:
        parts = path.split("/")
        for index in range(1, len(parts)):
            inventory["/".join(parts[:index]) + "/"] = SPECIES_DIRECTORY
    return inventory


def _emitted_inventory_violations(expected, actual):
    """Path and kind violations between the authorized and actual inventories.

    The authorized inventory is exactly the export's expected output paths with
    their declared species (every exported file, every preserved skeleton
    directory, and every ancestor directory). Any extra emitted path -- a hidden
    or identity-bearing path the policy never authorized -- or any missing
    authorized path fails the artifact identity closed. A path whose actual
    on-disk species differs from its authorized species -- a regular file
    replaced by a symlink, a symlinked skeleton where a real directory was
    authorized, or the reverse -- fails closed too, so a substituted link cannot
    be certified as the regular file it replaces.
    """
    violations = []
    for path in sorted(set(actual) - set(expected)):
        violations.append(
            f"unexpected emitted path {path!r} is not an authorized export output path"
        )
    for path in sorted(set(expected) - set(actual)):
        violations.append(
            f"authorized export output path {path!r} is missing from the emitted tree"
        )
    for path in sorted(set(expected) & set(actual)):
        if expected[path] != actual[path]:
            violations.append(
                f"emitted path {path!r} is an actual {actual[path]!r} but its "
                f"authorized export output kind is {expected[path]!r}"
            )
    return violations


def _emitted_content_violations(output, expected, actual, receipt_entries):
    """Byte-provenance and POSIX-mode violations for the ACTUAL emitted artifact.

    Every declared output entry carries the exact intended content of its exact
    source: a COPY blob's bytes, a generated constant's bytes, or a Git ``120000``
    symlink's target string. Comparing the real materialized bytes -- or a
    legitimate authorized symlink's real ``readlink`` target -- SHA-256 against
    that intended digest closes the sibling false-certification where a token-free
    but altered materialized regular file (or substituted link target) could
    otherwise pass while the receipt held only the intended blob SHA.

    Each emitted regular file's real, no-follow POSIX mode is additionally checked
    against the mode its authorized Git disposition requires (see
    ``_emitted_mode_violations``), so a post-write executable-bit change that
    leaves kind and bytes identical -- a 0755 -> 0644 downgrade of a ``100755``
    COPY or an accidental 0644 -> 0755 execute bit -- is caught. On a host that
    cannot observe POSIX permission bits the mode contract is not asserted (never
    silently claimed); Ubuntu CI proves it.

    It never follows a link out of the canvas: a regular file is read only from an
    ``lstat``-confirmed regular path and a symlink is compared by its target
    string. A path whose species already mismatches its authorized kind is skipped
    here because the inventory/kind guard has already reported it.
    """
    violations = []
    base = Path(output)
    for entry in receipt_entries:
        path = entry["path"]
        if actual.get(path) != expected.get(path):
            continue
        species = actual.get(path)
        if species == SPECIES_REGULAR:
            materialized = (base / path).read_bytes()
            violations.extend(
                _emitted_mode_violations(base / path, path, entry["mode"])
            )
        elif species == SPECIES_SYMLINK:
            materialized = os.readlink(str(base / path)).encode("utf-8")
        else:
            continue
        if hashlib.sha256(materialized).hexdigest() != entry["sha256"]:
            violations.append(
                f"emitted path {path!r} bytes do not match its authorized "
                "intended content"
            )
    return violations


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def default_receipt_path(output) -> Path:
    return Path(str(_resolved(output)) + ".receipt.json")


def _skeleton_dirs(ref, repo_root, policy=None):
    omitted = ()
    if policy is not None:
        omitted = tuple(
            policy.get("identity", {}).get("omitted_skeleton_prefixes", ())
        )
    return [
        directory for directory in sorted(source_dirs(ref, repo_root))
        if not directory.startswith(FACTORY_DIR_PREFIXES)
        and not any(directory.startswith(prefix) for prefix in omitted)
    ]


def export(repo_root, ref="HEAD", output=None, receipt=None, report_references=False) -> dict:
    """Run one deterministic export and return the sidecar receipt object."""
    repo_root = _resolved(repo_root)
    if output is None:
        raise _fail("an output path is required")
    output = _resolved(output)
    receipt = _resolved(receipt) if receipt is not None else default_receipt_path(output)

    guard_paths(repo_root, output, receipt)

    if output.exists():
        raise _fail(
            f"refusing destructive overwrite: output path already exists: {str(output)!r}"
        )
    if receipt.exists():
        raise _fail(
            f"refusing destructive overwrite: receipt path already exists: {str(receipt)!r}"
        )

    source_commit = rev_parse(ref, repo_root)
    if not SHA40_RE.match(source_commit):
        raise _fail(f"could not resolve {ref!r} to an exact commit SHA")

    policy = load_policy(source_commit, repo_root)
    engine_version = load_engine_version(source_commit, repo_root)

    tracked = tracked_entries(source_commit, repo_root)
    resolved = []
    for mode, otype, sha, path in tracked:
        if otype != "blob":
            raise _fail(f"unsupported tracked object type {otype!r} for {path!r}")
        disposition = disposition_for_path(policy, path)
        resolved.append((mode, sha, path, disposition))

    skeleton_dirs = _skeleton_dirs(source_commit, repo_root, policy)
    export_files = [
        generate_output_path(policy, path) if disposition == GENERATE_EMPTY else path
        for _mode, _sha, path, disposition in resolved
        if disposition != EXCLUDE
    ]
    dangling, dynamic_routes = check_reference_integrity(
        policy, tracked, export_files, skeleton_dirs, repo_root,
        report=report_references,
    )
    if report_references and dangling:
        for line in _dangling_lines(dangling):
            print("DANGLING ROUTE:" + line, file=sys.stdout)

    # Stage 1 -- early expected-tree preflight. The path set is every exported
    # file plus every preserved directory skeleton (and each exported file's
    # ancestor directories) with its declared species; the declared content
    # surfaces are the intended bytes (COPY blob or generated policy constant).
    # This runs BEFORE materialization so a predicted leak fails fast with no
    # output tree created, preserving the preflight-negative contract. It is NOT
    # the durable acceptance evidence: the actual artifact may differ from this
    # prediction.
    expected_inventory = _expected_output_inventory(
        policy, resolved, skeleton_dirs, export_files
    )
    expected_emitted_paths = set(expected_inventory)
    content_surfaces = set(policy["identity"]["content_surfaces"])
    expected_surface_bytes = {}
    for mode, sha, path, disposition in resolved:
        if disposition == EXCLUDE:
            continue
        if disposition == COPY:
            output_path = path
            emitted = _git_bytes(["cat-file", "blob", sha], repo_root)
        else:  # GENERATE_EMPTY
            output_path = generate_output_path(policy, path)
            emitted = generated_bytes(policy, output_path)
        if output_path in content_surfaces:
            expected_surface_bytes[output_path] = emitted
    preflight_evidence = identity_acceptance(
        policy, expected_emitted_paths, expected_surface_bytes
    )
    if preflight_evidence["violations"]:
        detail = "\n".join(
            "  " + violation for violation in preflight_evidence["violations"]
        )
        raise _fail(
            "emitted clean canvas carries source campaign identity:\n" + detail
        )

    output.mkdir(parents=True, exist_ok=False)

    counts = {COPY: 0, EXCLUDE: 0, GENERATE_EMPTY: 0}
    receipt_entries = []
    for mode, sha, path, disposition in resolved:
        counts[disposition] += 1
        if disposition == EXCLUDE:
            continue
        if disposition == COPY:
            entry_path = path
            data = _git_bytes(["cat-file", "blob", sha], repo_root)
            _write_file(output / entry_path, data, mode)
            entry_mode = mode
        else:  # GENERATE_EMPTY
            entry_path = generate_output_path(policy, path)
            data = generated_bytes(policy, entry_path)
            _write_file(output / entry_path, data, GENERATED_FILE_MODE)
            entry_mode = GENERATED_FILE_MODE
        receipt_entries.append(
            {
                "path": entry_path,
                "disposition": disposition,
                "mode": entry_mode,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    # Preserve the campaign folder skeleton so retained directory routes resolve
    # even where every file inside was excluded as instance material.
    for directory in skeleton_dirs:
        (output / directory).mkdir(parents=True, exist_ok=True)

    # Stage 2 -- independent post-materialization inspection of the ACTUAL
    # completed output. This is the durable acceptance evidence: scan the real
    # emitted tree with one strict, no-follow ``os.scandir`` walk, reading each
    # entry's no-follow filesystem species with ``os.lstat`` (files AND
    # directories; an unscannable directory or unlstat-able entry fails closed
    # rather than silently dropping a subtree), read each declared content
    # surface through its real on-disk bytes (only from an lstat-confirmed
    # regular path, never by following a substituted link out of the canvas),
    # compare the actual path/kind inventory to the authorized expected
    # inventory, attest every emitted regular file's real bytes (or an authorized
    # symlink's real ``readlink`` target) against its exact intended digest, and
    # verify each regular file's real POSIX mode against its authorized Git
    # ``100755``/``100644`` mode. A leaked path token,
    # a mutated content surface, an extra (even token-free) path, a missing
    # authorized path, a substituted path kind (a regular file replaced by a
    # symlink), altered bytes, a changed executable bit, or ANY unreadable
    # path/scan failure fails the export closed BEFORE any accepted receipt is
    # written, so a receipt can never certify either the predicted pre-write tree
    # or bytes/modes that are not on disk. POSIX permission fidelity is asserted
    # only where the host exposes permission bits (``os.name == 'posix'``); on
    # Windows the executable bit is not representable and is never silently
    # claimed verified, and the Ubuntu CI job runs those proofs for real. It
    # never rewrites a byte and never reclassifies a path; it does not attempt to
    # defend against hostile mutation AFTER this inspection.
    actual_inventory = _actual_emitted_inventory(output)
    actual_surface_bytes = {}
    for surface in sorted(content_surfaces):
        species = actual_inventory.get(surface)
        if species == SPECIES_REGULAR:
            actual_surface_bytes[surface] = (output / surface).read_bytes()
        elif species == SPECIES_SYMLINK:
            # An authorized symlink content surface is scanned by its target
            # string; the link is never followed to a file outside the canvas.
            actual_surface_bytes[surface] = os.readlink(
                str(output / surface)
            ).encode("utf-8")
    identity_evidence = identity_acceptance(
        policy, actual_inventory, actual_surface_bytes
    )
    post_write_violations = list(identity_evidence["violations"])
    post_write_violations += _emitted_inventory_violations(
        expected_inventory, actual_inventory
    )
    post_write_violations += _emitted_content_violations(
        output, expected_inventory, actual_inventory, receipt_entries
    )
    if post_write_violations:
        detail = "\n".join(
            "  " + violation for violation in sorted(set(post_write_violations))
        )
        raise _fail(
            "emitted clean canvas carries source campaign identity:\n" + detail
        )

    policy_bytes = _git_bytes(["show", f"{source_commit}:{POLICY_RELPATH}"], repo_root)
    receipt_object = {
        "policy_version": policy["policy_version"],
        "mission": policy["mission"],
        "engine_version": engine_version,
        "source_commit": source_commit,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "path_count": len(receipt_entries),
        "dispositions": counts,
        # Durable, machine-readable identity acceptance evidence for the ACTUAL
        # completed artifact: ``identity_acceptance`` was re-run over the real
        # emitted tree, the actual path/kind inventory was compared against the
        # authorized expected inventory (see ``_actual_emitted_inventory`` /
        # ``_emitted_inventory_violations``), and every emitted regular file's
        # real bytes -- or an authorized symlink's real ``readlink`` target --
        # was attested against its exact intended digest, plus each regular
        # file's real POSIX mode against its authorized Git mode (see
        # ``_emitted_content_violations`` / ``_emitted_mode_violations``). Any
        # leak, mutation, extra or missing path, unscannable directory,
        # substituted path kind, altered bytes, or changed executable bit would
        # have failed the export closed before this receipt was written, so these
        # bytes certify the artifact, not the prediction.
        "identity_acceptance": identity_evidence,
        # Capability-honest attestation of what this host actually proved. The
        # path/kind inventory, byte/link-target digest, and POSIX-mode checks all
        # ran and passed before this receipt was written; the POSIX-mode status is
        # derived from the same capability predicate the verifier uses, so it is
        # ``verified`` only on a host that exposes permission bits and
        # ``not_observable`` where the mode contract was not asserted -- the
        # receipt never implies a mode proof it did not make. The identity-only
        # ``identity_acceptance.accepted`` flag is deliberately not overloaded to
        # mean platform mode proof.
        "artifact_attestation": {
            "path_inventory": "verified",
            "path_kind": "verified",
            "content_digest": "verified",
            "posix_mode": _posix_mode_attestation(),
        },
        # Route fragments in shipped workflows that directly abut an Actions
        # expression cannot be statically resolved. They are recorded here as
        # explicitly classified, consciously unproven -- never silently
        # accepted and never claimed as proved dependency closure.
        "unresolved_dynamic_routes": [
            {"path": path, "route": route} for path, route in dynamic_routes
        ],
        "entries": sorted(receipt_entries, key=lambda item: item["path"]),
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(receipt_object, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt_object


def main(argv) -> int:
    parser = argparse.ArgumentParser(
        description="Export the POST-EV2-Z clean campaign canvas from exact Git HEAD"
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", default=None)
    parser.add_argument(
        "--report-references",
        action="store_true",
        help="print dangling retained routes instead of failing (diagnostic only)",
    )
    args = parser.parse_args(argv)

    try:
        receipt = export(
            repo_root=args.repo_root,
            ref=args.ref,
            output=args.output,
            receipt=args.receipt,
            report_references=args.report_references,
        )
    except ExportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "CLEAN CAMPAIGN EXPORT OK: "
        f"source={receipt['source_commit']} files={receipt['path_count']} "
        f"dispositions={receipt['dispositions']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
