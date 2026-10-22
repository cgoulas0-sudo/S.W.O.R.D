#!/usr/bin/env python3
"""Read-only validation of the committed canonical root campaign JSON files.

Usage:
    python scripts/validate_canonical_root_json.py [<canonical-root-path> ...]

With no arguments it validates the exact six canonical root documents:

    state/daily_recap.json
    state/day_resolution.json
    state/dm_meta.json
    state/live_status.json
    knowledge/facts.json
    npc/npc_state.json

The public CLI is bound to those six **exact repository-relative paths**. A
supplied path is validated only when it resolves to one of the six; any other
path (including a file that merely shares a basename, such as
``/tmp/live_status.json``) is rejected without receiving a root contract. A
repository-relative argument resolves from the repository root, not the
caller's current working directory, so CWD never changes acceptance.

This is a *read-only* check. It never writes, normalizes, infers, or generates
campaign content; it only reads the committed bytes, parses them, and reports.
It exists to stop a malformed or off-vocabulary root document from silently
escaping review, not to become a second campaign-truth or game-schema owner.

It deliberately reuses the strict JSON parse hooks from
``scripts/validate_entities.py`` (duplicate-key rejection and rejection of
non-finite numbers, both bare ``NaN``/``Infinity`` tokens and ordinary
overflows like ``1e400``) instead of maintaining a second parser.

The only semantic contracts applied are bounded and owner-declared:

* every root document must parse as a JSON **object**;
* ``knowledge/facts.json`` must use the META/NON_META visibility vocabulary
  (``meta`` | ``non_meta``) for ``default_visibility`` and for each fact's
  ``visibility``, and each fact's ``source_status`` must be one of the values
  the file itself declares in ``fact_schema.source_status``;
* ``npc/npc_state.json`` must use the vocabularies the NPC owner template
  (``npc/NPC_STATE_TEMPLATE.json``) declares for ``current_combat_state``,
  relationship ``trend`` and ``last_update_source``;
* ``state/dm_meta.json`` is META by domain default and must not declare any
  other visibility.

Per-entity state/knowledge schemas are intentionally NOT applied to these root
documents: they describe Entity V2 records, not root document shapes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import (  # noqa: E402  (reuse the strict JSON parse hooks)
    _parse_float_reject_overflow,
    _reject_duplicate_keys,
    _reject_non_json_constants,
)

CANONICAL_ROOT_FILES = (
    "state/daily_recap.json",
    "state/day_resolution.json",
    "state/dm_meta.json",
    "state/live_status.json",
    "knowledge/facts.json",
    "npc/npc_state.json",
)

NPC_STATE_TEMPLATE = "npc/NPC_STATE_TEMPLATE.json"

VISIBILITY_VALUES = ("meta", "non_meta")

# Recognized canonical root documents -> bounded contract id, keyed by the
# **exact repository-relative path** (never by basename). ``None`` means "root
# object only"; a string selects one owner-declared vocabulary contract below.
_CONTRACTS = {
    "state/daily_recap.json": None,
    "state/day_resolution.json": None,
    "state/live_status.json": None,
    "state/dm_meta.json": "dm_meta",
    "knowledge/facts.json": "facts",
    "npc/npc_state.json": "npc",
}

USAGE = "usage: validate_canonical_root_json.py [<canonical-root-path> ...]"


def _parse_strict(text):
    """Parse JSON with the shared strict hooks (duplicate keys, non-finite)."""
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constants,
        parse_float=_parse_float_reject_overflow,
    )


def load_npc_vocabulary(root=ROOT):
    """Return the owner-declared NPC vocabularies from the NPC state template."""
    template = json.loads((Path(root) / NPC_STATE_TEMPLATE).read_text(encoding="utf-8"))
    return {
        "combat_states": frozenset(template.get("allowed_current_combat_states", ())),
        "relationship_trends": frozenset(template.get("allowed_relationship_trends", ())),
        "update_sources": frozenset(template.get("allowed_update_sources", ())),
    }


def _check_facts(document):
    errors = []
    default_visibility = document.get("default_visibility")
    if default_visibility not in VISIBILITY_VALUES:
        errors.append(
            "default_visibility must be one of "
            f"{VISIBILITY_VALUES!r}, got {default_visibility!r}"
        )

    source_statuses = _declared_source_statuses(document)
    facts = document.get("facts")
    if facts is None:
        facts = []
    if not isinstance(facts, list):
        errors.append(f"facts must be a list, got {type(facts).__name__}")
        return errors

    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            errors.append(f"facts[{index}] must be an object")
            continue
        visibility = fact.get("visibility")
        if visibility is not None and visibility not in VISIBILITY_VALUES:
            errors.append(
                f"facts[{index}].visibility must be one of "
                f"{VISIBILITY_VALUES!r}, got {visibility!r}"
            )
        source_status = fact.get("source_status")
        if source_status is not None and source_status not in source_statuses:
            errors.append(
                f"facts[{index}].source_status {source_status!r} is not declared in "
                "fact_schema.source_status"
            )
    return errors


def _declared_source_statuses(document):
    """Parse the file's own ``fact_schema.source_status`` vocabulary."""
    schema = document.get("fact_schema")
    declared = schema.get("source_status") if isinstance(schema, dict) else None
    if not isinstance(declared, str):
        return frozenset()
    return frozenset(part.strip() for part in declared.split("|") if part.strip())


def _check_npc(document, vocabulary):
    errors = []
    npcs = document.get("npcs")
    if npcs is None:
        npcs = {}
    if not isinstance(npcs, dict):
        errors.append(f"npcs must be an object, got {type(npcs).__name__}")
        return errors

    combat_states = vocabulary.get("combat_states", frozenset())
    trends = vocabulary.get("relationship_trends", frozenset())
    update_sources = vocabulary.get("update_sources", frozenset())

    for npc_id, entry in npcs.items():
        if not isinstance(entry, dict):
            errors.append(f"npcs[{npc_id!r}] must be an object")
            continue

        live_state = entry.get("live_state")
        if isinstance(live_state, dict):
            combat_state = live_state.get("current_combat_state")
            if combat_state is not None and combat_state not in combat_states:
                errors.append(
                    f"npcs[{npc_id!r}].live_state.current_combat_state "
                    f"{combat_state!r} is not in the owner-declared vocabulary"
                )

        relationships = entry.get("relationships")
        if isinstance(relationships, dict):
            for target, relationship in relationships.items():
                if not isinstance(relationship, dict):
                    continue
                trend = relationship.get("trend")
                if trend is not None and trend not in trends:
                    errors.append(
                        f"npcs[{npc_id!r}].relationships[{target!r}].trend "
                        f"{trend!r} is not in the owner-declared vocabulary"
                    )

        continuity = entry.get("continuity")
        if isinstance(continuity, dict):
            update_source = continuity.get("last_update_source")
            if update_source is not None and update_source not in update_sources:
                errors.append(
                    f"npcs[{npc_id!r}].continuity.last_update_source "
                    f"{update_source!r} is not in the owner-declared vocabulary"
                )
    return errors


def _check_dm_meta(document):
    errors = []
    visibility = document.get("visibility")
    if visibility is not None and visibility != "meta":
        errors.append(
            f"visibility must be 'meta' (dm_meta is META by domain default), "
            f"got {visibility!r}"
        )
    return errors


def canonical_relative_path(path, root=ROOT):
    """Map a path to the exact canonical repository-relative id, or ``None``.

    A repository-relative input (e.g. ``state/live_status.json``) is resolved
    against the repository ``root``, never against the caller's current working
    directory; an absolute input is resolved as given. Acceptance then requires
    the resolved location to equal one of the six canonical files under
    ``root`` -- never a basename match, so ``/tmp/live_status.json`` receives no
    contract. The caller's CWD can never change which canonical paths are
    accepted.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    for relative in CANONICAL_ROOT_FILES:
        if (Path(root) / relative).resolve() == resolved:
            return relative
    return None


def validate_document(relative, document, vocabulary):
    """Return bounded contract errors for one already-parsed canonical document.

    This internal/test API is keyed by the exact canonical repository-relative
    path; it never guesses a contract from a basename.
    """
    if not isinstance(document, dict):
        return [f"root document must be a JSON object, got {type(document).__name__}"]

    if relative not in _CONTRACTS:
        return [f"{relative!r} is not a recognized canonical root document"]

    contract = _CONTRACTS[relative]
    if contract == "facts":
        return _check_facts(document)
    if contract == "npc":
        return _check_npc(document, vocabulary)
    if contract == "dm_meta":
        return _check_dm_meta(document)
    return []


def validate_text(relative, text, vocabulary):
    """Parse + validate canonical document text (internal/test API)."""
    try:
        document = _parse_strict(text)
    except json.JSONDecodeError as exc:
        return [f"{relative}: invalid JSON: {exc}"]
    except ValueError as exc:
        return [f"{relative}: invalid JSON: {exc}"]
    return [f"{relative}: {error}" for error in validate_document(relative, document, vocabulary)]


def validate_repository_file(relative, vocabulary, root=ROOT):
    """Validate one of the exact six canonical root files (read-only)."""
    try:
        text = (Path(root) / relative).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{relative}: invalid UTF-8: {exc}"]
    except OSError as exc:
        return [f"{relative}: cannot read: {exc}"]
    return validate_text(relative, text, vocabulary)


def main(argv):
    if any(arg in ("-h", "--help") for arg in argv):
        print(USAGE)
        return 0

    vocabulary = load_npc_vocabulary(ROOT)

    errors = []
    if argv:
        targets = []
        for arg in argv:
            relative = canonical_relative_path(arg, ROOT)
            if relative is None:
                errors.append(f"{arg}: not one of the canonical root paths")
            else:
                targets.append(relative)
    else:
        targets = list(CANONICAL_ROOT_FILES)

    for relative in targets:
        errors.extend(validate_repository_file(relative, vocabulary, ROOT))

    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} canonical root JSON error(s).", file=sys.stderr)
        return 1

    print(f"OK: {len(targets)} canonical root JSON document(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
