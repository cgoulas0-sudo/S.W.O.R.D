#!/usr/bin/env python3
"""POST-EV2-6 project-wide story retrieval with explicit hydration admission.

This utility intentionally keeps four responsibilities separate:

    discovery -> candidate receipt -> hydration admission -> bounded excerpt

It does NOT implement a generic META/NON_META interpreter for arbitrary mixed
Markdown/JSON. Existing source/domain owners retain semantic authority.

The generated manifest is derived, disposable, and non-authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
from pathlib import Path

MANIFEST_VERSION = 1
MANIFEST_KIND = "story_retrieval_manifest"

DEFAULT_LIMIT = 10
MAX_RESULTS = 50
MAX_EXCERPT_CHARS = 400

AUTHORITATIVE_PROFILE = "authoritative"
DM_PROFILE = "dm"
PROFILES = (AUTHORITATIVE_PROFILE, DM_PROFILE)

SOURCE_RULES = (
    ("canon/days/", "PLAYED_HISTORY", "canon"),
    ("canon/", "CANON", "canon"),
    ("characters/", "CHARACTER", "canon"),
    ("npc/", "NPC", "canon"),
    ("villain/", "VILLAIN", "canon"),
    ("locations/profiles/", "LOCATION", "canon"),
    ("inventory/", "ITEM", "canon"),
    ("knowledge/", "KNOWLEDGE", "canon"),
    ("beyond_the_heroes/entries/", "BTH_OCCURRED", "canon_backstage"),
    ("beyond_the_heroes/ideas/", "BTH_IDEA", "non_canon"),
    ("planned/", "DM_ONLY_PLAN", "non_canon"),
    ("brainstorm/", "NON_CANON_BRAINSTORM", "non_canon"),
)

WALK_ROOTS = (
    "canon",
    "characters",
    "npc",
    "villain",
    "locations/profiles",
    "inventory",
    "knowledge",
    "beyond_the_heroes/entries",
    "beyond_the_heroes/ideas",
    "planned",
    "brainstorm",
)

EXCLUDED_BASENAMES = {
    "readme.md",
    "meta_non_meta_protocol.md",
    "knowledge_system.md",
    "npc_system.md",
}
STORY_SUFFIXES = {".md", ".json"}

VISIBILITIES = {"meta", "non_meta"}
_JSON_VISIBILITY_KEYS = ("visibility", "default_visibility")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_WORD_RE = re.compile(r"[a-z0-9_']+", re.IGNORECASE)

# Marker discovery only. These regexes do not assign section scope.
_MARKDOWN_ANY_VIS_RE = re.compile(
    r"^[ \t]*(?:(?:[-+*])\s+|>\s*)?(?:#{1,6}\s+)?"
    r"\*{0,2}visibility:?\*{0,2}\s*(non_meta|meta)\b",
    re.IGNORECASE | re.MULTILINE,
)
_MARKDOWN_TOP_VIS_RE = re.compile(
    r"^[ \t]*(?:>\s*)?\*{0,2}visibility:?\*{0,2}\s*(non_meta|meta)\b",
    re.IGNORECASE,
)
_MARKDOWN_SECTION_RE = re.compile(r"^[ \t]*##+\s+")


def classify_path(relpath: str):
    rel = relpath.replace("\\", "/")
    best = None
    for prefix, source_class, authority in SOURCE_RULES:
        if rel.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, source_class, authority)
    return best


def is_excluded(relpath: str) -> bool:
    name = posixpath.basename(relpath).lower()
    if name in EXCLUDED_BASENAMES:
        return True
    if "_template." in name or name.endswith("_template"):
        return True
    if name.endswith("_state.json") or name.endswith("_state.md"):
        return True
    return False


def _markdown_visibility_evidence(text: str) -> dict:
    """Return conservative whole-source evidence without section interpretation."""
    markers = [m.group(1).lower() for m in _MARKDOWN_ANY_VIS_RE.finditer(text)]

    header_lines = []
    for line in text.splitlines():
        if _MARKDOWN_SECTION_RE.match(line):
            break
        header_lines.append(line)

    top_level = None
    for line in header_lines:
        match = _MARKDOWN_TOP_VIS_RE.match(line)
        if match:
            top_level = match.group(1).lower()
            break

    if "meta" in markers:
        mode = "meta_or_mixed"
        player_safe = False
    elif top_level == "non_meta":
        mode = "unambiguous_non_meta"
        player_safe = True
    elif markers:
        mode = "ambiguous"
        player_safe = False
    else:
        mode = "unclassified"
        player_safe = False

    return {
        "mode": mode,
        "top_level": top_level,
        "markers": sorted(set(markers)),
        "player_safe_whole_source": player_safe,
    }


def _walk_json_visibility(value, found: list) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _JSON_VISIBILITY_KEYS and isinstance(child, str):
                lowered = child.lower()
                if lowered in VISIBILITIES:
                    found.append(lowered)
            else:
                _walk_json_visibility(child, found)
    elif isinstance(value, list):
        for child in value:
            _walk_json_visibility(child, found)


def _json_visibility_evidence(text: str) -> dict:
    """Return conservative whole-source evidence from JSON structure."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return {
            "mode": "invalid_json",
            "root": None,
            "markers": [],
            "player_safe_whole_source": False,
        }

    markers = []
    _walk_json_visibility(document, markers)

    root = None
    if isinstance(document, dict):
        for key in ("visibility", "default_visibility"):
            value = document.get(key)
            if isinstance(value, str) and value.lower() in VISIBILITIES:
                root = value.lower()
                break

    if "meta" in markers or root == "meta":
        mode = "meta_or_mixed"
        player_safe = False
    elif root == "non_meta":
        mode = "unambiguous_non_meta"
        player_safe = True
    elif markers:
        mode = "ambiguous"
        player_safe = False
    else:
        mode = "unclassified"
        player_safe = False

    return {
        "mode": mode,
        "root": root,
        "markers": sorted(set(markers)),
        "player_safe_whole_source": player_safe,
    }


def visibility_evidence(path: Path, text: str) -> dict:
    if path.suffix.lower() == ".json":
        return _json_visibility_evidence(text)
    return _markdown_visibility_evidence(text)


def collect_sources(base_dir) -> list:
    base = Path(base_dir).resolve()
    seen = set()
    records = []

    for walk_root in WALK_ROOTS:
        root = base / walk_root
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                rel = path.relative_to(base).as_posix()
                if rel in seen or is_excluded(rel):
                    continue
                classification = classify_path(rel)
                if classification is None or path.suffix.lower() not in STORY_SUFFIXES:
                    continue

                seen.add(rel)
                data = path.read_bytes()
                text = data.decode("utf-8", errors="replace")
                _, source_class, authority = classification
                evidence = visibility_evidence(path, text)
                records.append(
                    {
                        "path": rel,
                        "source_class": source_class,
                        "authority": authority,
                        "content_sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                        "visibility_evidence": evidence,
                    }
                )

    records.sort(key=lambda record: record["path"])
    return records


def compute_fingerprint(sources) -> str:
    canonical = [
        {
            "path": source["path"],
            "source_class": source["source_class"],
            "authority": source["authority"],
            "content_sha256": source["content_sha256"],
            "visibility_evidence": source["visibility_evidence"],
        }
        for source in sorted(sources, key=lambda record: record["path"])
    ]
    payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git_head(base_dir):
    try:
        result = subprocess.run(
            ["git", "-C", str(base_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def build_manifest(base_dir, git_head=None) -> dict:
    sources = collect_sources(base_dir)
    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": MANIFEST_KIND,
        "built_from": {
            "base": str(Path(base_dir).resolve()),
            "git_head": git_head if git_head is not None else _git_head(base_dir),
        },
        "source_policy": {
            "roots": list(WALK_ROOTS),
            "excluded_basenames": sorted(EXCLUDED_BASENAMES),
        },
        "sources": sources,
        "fingerprint": compute_fingerprint(sources),
    }


def manifest_integrity(manifest) -> str | None:
    if not isinstance(manifest, dict):
        return "manifest is not an object"
    if manifest.get("kind") != MANIFEST_KIND:
        return "manifest kind is invalid"
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return "manifest version is unsupported"

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return "manifest has no source list"

    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            return "manifest source is not an object"
        path = source.get("path")
        if not isinstance(path, str) or not path:
            return "manifest source path is invalid"
        if path in seen:
            return f"duplicate source path: {path}"
        seen.add(path)

        classification = classify_path(path)
        if classification is None:
            return f"source outside declared policy: {path}"
        _, source_class, authority = classification
        if source.get("source_class") != source_class:
            return f"source_class mismatch: {path}"
        if source.get("authority") != authority:
            return f"authority mismatch: {path}"

        digest = source.get("content_sha256")
        if not isinstance(digest, str) or not _HEX64_RE.match(digest):
            return f"invalid digest: {path}"

        evidence = source.get("visibility_evidence")
        if not isinstance(evidence, dict):
            return f"invalid visibility evidence: {path}"
        if not isinstance(evidence.get("player_safe_whole_source"), bool):
            return f"invalid player-safe evidence: {path}"

    try:
        recomputed = compute_fingerprint(sources)
    except (KeyError, TypeError, ValueError):
        return "manifest sources cannot be fingerprinted"
    if recomputed != manifest.get("fingerprint"):
        return "manifest fingerprint mismatch"
    return None


def check_freshness(manifest: dict, base_dir) -> dict:
    integrity_error = manifest_integrity(manifest)
    if integrity_error is not None:
        return {
            "status": "stale",
            "integrity_error": integrity_error,
            "expected_fingerprint": manifest.get("fingerprint")
            if isinstance(manifest, dict)
            else None,
            "current_fingerprint": None,
            "added_paths": [],
            "removed_paths": [],
            "changed_paths": [],
        }

    current = collect_sources(base_dir)
    current_fingerprint = compute_fingerprint(current)
    expected_fingerprint = manifest["fingerprint"]

    old = {source["path"]: source for source in manifest["sources"]}
    new = {source["path"]: source for source in current}

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        path
        for path in set(old) & set(new)
        if (
            old[path]["content_sha256"] != new[path]["content_sha256"]
            or old[path]["visibility_evidence"] != new[path]["visibility_evidence"]
            or old[path]["source_class"] != new[path]["source_class"]
            or old[path]["authority"] != new[path]["authority"]
        )
    )

    return {
        "status": "fresh"
        if current_fingerprint == expected_fingerprint
        else "stale",
        "integrity_error": None,
        "expected_fingerprint": expected_fingerprint,
        "current_fingerprint": current_fingerprint,
        "added_paths": added,
        "removed_paths": removed,
        "changed_paths": changed,
    }


def _query_terms(query: str) -> list:
    return _WORD_RE.findall((query or "").lower())


def _match_text(text: str, terms) -> dict | None:
    lowered = text.lower()
    first_position = None
    total = 0
    for term in terms:
        pattern = re.compile(
            r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])"
        )
        matches = list(pattern.finditer(lowered))
        if not matches:
            return None
        total += len(matches)
        position = matches[0].start()
        if first_position is None or position < first_position:
            first_position = position

    line = text.count("\n", 0, first_position) + 1
    start = max(0, first_position - MAX_EXCERPT_CHARS // 3)
    end = min(len(text), start + MAX_EXCERPT_CHARS)
    return {
        "score": total,
        "line": line,
        "excerpt": text[start:end].strip(),
        "matched_terms": list(terms),
    }


def admit_source(source: dict, profile: str) -> tuple[bool, str]:
    if profile == DM_PROFILE:
        return True, "dm profile may hydrate declared searchable material"

    if source["authority"] == "non_canon":
        return False, "non-canon material is DM-only"

    evidence = source["visibility_evidence"]
    if not evidence.get("player_safe_whole_source", False):
        return (
            False,
            "player-safe hydration requires unambiguous whole-source NON_META evidence",
        )

    return True, "unambiguous whole-source NON_META evidence"


def _coverage(manifest: dict, profile: str) -> dict:
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    return {
        "profile": profile,
        "indexed_source_count": len(sources),
        "source_classes": sorted(
            {
                source.get("source_class")
                for source in sources
                if isinstance(source, dict) and source.get("source_class")
            }
        ),
        "complete": None,
    }


def query_manifest(
    manifest: dict,
    base_dir,
    query: str,
    limit: int = DEFAULT_LIMIT,
    profile: str = AUTHORITATIVE_PROFILE,
) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile!r}")
    limit = max(1, min(int(limit), MAX_RESULTS))

    freshness = check_freshness(manifest, base_dir)
    complete = freshness["status"] == "fresh"
    coverage = _coverage(manifest, profile)
    coverage["complete"] = complete

    terms = _query_terms(query)
    hits = []
    admission_rejections = 0
    hydration_mismatch_paths = []

    if complete and terms:
        for source in manifest["sources"]:
            admitted, reason = admit_source(source, profile)
            if not admitted:
                admission_rejections += 1
                continue

            path = Path(base_dir) / source["path"]
            try:
                data = path.read_bytes()
            except OSError:
                hydration_mismatch_paths.append(source["path"])
                break

            digest = hashlib.sha256(data).hexdigest()
            if digest != source["content_sha256"]:
                hydration_mismatch_paths.append(source["path"])
                break

            text = data.decode("utf-8", errors="replace")
            match = _match_text(text, terms)
            if match is None:
                continue

            hits.append(
                {
                    "path": source["path"],
                    "source_class": source["source_class"],
                    "authority": source["authority"],
                    "visibility_evidence": source["visibility_evidence"],
                    "admission_reason": reason,
                    "score": match["score"],
                    "matched_terms": match["matched_terms"],
                    "line": match["line"],
                    "excerpt": match["excerpt"],
                    "content_sha256": digest,
                }
            )

    if hydration_mismatch_paths:
        hits = []
        complete = False
        coverage["complete"] = False
        freshness = dict(freshness)
        freshness["status"] = "stale"
        freshness["hydration_mismatch_paths"] = sorted(
            set(hydration_mismatch_paths)
        )
        freshness["changed_paths"] = sorted(
            set(freshness.get("changed_paths", []))
            | set(hydration_mismatch_paths)
        )

    hits.sort(key=lambda hit: (-hit["score"], hit["path"]))
    total = len(hits)
    bounded = hits[:limit]

    note = (
        "Fresh declared corpus searched. Zero results are not proof of "
        "project-wide semantic absence."
        if complete
        else "Retrieval coverage is stale/tampered/unavailable; hydration is "
        "refused and zero results are not proof of absence."
    )

    return {
        "read_version": MANIFEST_VERSION,
        "mode": "story_retrieval",
        "query": query,
        "profile": profile,
        "limit": limit,
        "freshness": freshness,
        "complete": complete,
        "absence_is_proof": False,
        "coverage": coverage,
        "admission_rejections": admission_rejections,
        "count": len(bounded),
        "total_matches": total,
        "truncated": total > limit,
        "results": bounded,
        "note": note,
    }


def load_manifest(path):
    path = Path(path)
    if not path.is_file():
        return None, f"manifest not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return None, f"manifest unreadable: {exc}"
    return data, None


def query_receipt(
    manifest_path,
    base_dir,
    query: str,
    limit: int = DEFAULT_LIMIT,
    profile: str = AUTHORITATIVE_PROFILE,
) -> dict:
    manifest, error = load_manifest(manifest_path)
    if manifest is None:
        limit = max(1, min(int(limit), MAX_RESULTS))
        return {
            "read_version": MANIFEST_VERSION,
            "mode": "story_retrieval",
            "query": query,
            "profile": profile,
            "limit": limit,
            "freshness": {"status": "unavailable", "error": error},
            "complete": False,
            "absence_is_proof": False,
            "coverage": {
                "profile": profile,
                "indexed_source_count": 0,
                "source_classes": [],
                "complete": False,
            },
            "admission_rejections": 0,
            "count": 0,
            "total_matches": 0,
            "truncated": False,
            "results": [],
            "note": "Manifest unavailable; zero results are not proof of absence.",
        }
    return query_manifest(
        manifest, base_dir, query, limit=limit, profile=profile
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="story_retrieval.py",
        description="POST-EV2-6 project-wide story retrieval.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--base-dir", default=".")
    build.add_argument("--manifest", required=True)
    build.add_argument("--git-head", default=None)

    fresh = sub.add_parser("freshness")
    fresh.add_argument("--base-dir", default=".")
    fresh.add_argument("--manifest", required=True)

    query = sub.add_parser("query")
    query.add_argument("--base-dir", default=".")
    query.add_argument("--manifest", required=True)
    query.add_argument("--query", required=True)
    query.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    query.add_argument("--profile", choices=PROFILES, default=AUTHORITATIVE_PROFILE)

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "build":
        manifest = build_manifest(args.base_dir, git_head=args.git_head)
        Path(args.manifest).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": "built", "sources": len(manifest["sources"])}))
        return 0

    manifest, error = load_manifest(args.manifest)
    if manifest is None:
        print(json.dumps({"status": "unavailable", "error": error}))
        return 2

    if args.command == "freshness":
        receipt = check_freshness(manifest, args.base_dir)
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0 if receipt["status"] == "fresh" else 1

    receipt = query_manifest(
        manifest,
        args.base_dir,
        args.query,
        limit=args.limit,
        profile=args.profile,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
