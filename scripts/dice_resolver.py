#!/usr/bin/env python3
"""POST-EV2-8 — Universal RHC dice resolver.

One small reusable random-resolution primitive. It owns random generation plus
declared roll arithmetic only. It never decides whether a roll is required, a
DC, success/failure, damage meaning, or canon mutation, and it never writes any
file, SQL, SAVE or campaign state.

Production randomness comes from Python's unseeded runtime RNG. A caller may
inject an explicit test-only RNG seam (``random.Random(seed)``); that seam must
never be used as production behavior.

Every accepted request is bounded by a finite work budget across the base
expression and the aggregate requested bonus/penalty dice. Oversized requests
fail closed before any RNG call or roll-list allocation.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys

NOTATION_RE = re.compile(r"^([0-9]+)[dD]([0-9]+)$")

MAX_DICE_PER_REQUEST = 1000

_REQUEST_KEYS = frozenset(
    {
        "notation",
        "modifiers",
        "bonus_dice",
        "penalty_dice",
        "advantage",
        "disadvantage",
    }
)
_DICE_ENTRY_KEYS = frozenset({"notation", "source"})
_MODIFIER_ENTRY_KEYS = frozenset({"value", "source"})


def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_empty_str(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty source string")
    return value


def _require_list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _require_known_keys(entry, allowed, name):
    if not isinstance(entry, dict):
        raise ValueError(f"{name} must be an object")
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f"{name} has unknown field(s): {sorted(unknown)}")
    return entry


def parse_notation(notation):
    """Parse a pure ``NdM`` dice expression into ``(count, sides)``."""
    if not isinstance(notation, str):
        raise ValueError("notation must be a string")
    match = NOTATION_RE.match(notation)
    if match is None:
        raise ValueError(f"invalid dice notation: {notation!r}")
    count = int(match.group(1))
    sides = int(match.group(2))
    if count < 1:
        raise ValueError("dice count must be at least 1")
    if count > MAX_DICE_PER_REQUEST:
        raise ValueError(
            f"dice count {count} exceeds the maximum of {MAX_DICE_PER_REQUEST} per request"
        )
    if sides < 2:
        raise ValueError("dice sides must be at least 2")
    return count, sides


def _roll(count, sides, rng):
    return [rng.randint(1, sides) for _ in range(count)]


def _source_list(raw, name):
    entries = _require_list(raw, name)
    sources = []
    for entry in entries:
        sources.append(_require_non_empty_str(entry, f"{name} source"))
    return sources


def _dice_entries(raw, name):
    entries = _require_list(raw, name)
    parsed = []
    for entry in entries:
        _require_known_keys(entry, _DICE_ENTRY_KEYS, f"{name} entry")
        notation = entry.get("notation")
        source = _require_non_empty_str(entry.get("source"), f"{name} source")
        count, sides = parse_notation(notation)
        parsed.append({"notation": notation, "source": source, "count": count, "sides": sides})
    return parsed


def _modifier_entries(raw):
    entries = _require_list(raw, "modifiers")
    parsed = []
    for entry in entries:
        _require_known_keys(entry, _MODIFIER_ENTRY_KEYS, "modifier entry")
        value = _require_int(entry.get("value"), "modifier value")
        source = _require_non_empty_str(entry.get("source"), "modifier source")
        parsed.append({"value": value, "source": source})
    return parsed


def resolve(request, rng=None):
    """Resolve one dice request into a structured result.

    ``rng`` is an explicit test-only seam. When omitted, the unseeded runtime
    RNG (the ``random`` module) is used and no seeding occurs anywhere.
    """
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    unknown = set(request) - _REQUEST_KEYS
    if unknown:
        raise ValueError(f"request has unknown field(s): {sorted(unknown)}")

    if "notation" not in request:
        raise ValueError("request requires a notation")
    count, sides = parse_notation(request["notation"])

    modifiers = _modifier_entries(request.get("modifiers", []))
    bonus_dice = _dice_entries(request.get("bonus_dice", []), "bonus_dice")
    penalty_dice = _dice_entries(request.get("penalty_dice", []), "penalty_dice")
    advantage_sources = _source_list(request.get("advantage", []), "advantage")
    disadvantage_sources = _source_list(request.get("disadvantage", []), "disadvantage")

    has_adv = bool(advantage_sources)
    has_dis = bool(disadvantage_sources)

    if (has_adv or has_dis) and not (count == 1 and sides == 20):
        raise ValueError("advantage/disadvantage is only valid on a single d20")

    if has_adv and has_dis:
        mode = "normal"
    elif has_adv:
        mode = "advantage"
    elif has_dis:
        mode = "disadvantage"
    else:
        mode = "normal"

    rolled_dice = 2 if mode in ("advantage", "disadvantage") else count
    total_dice = (
        rolled_dice
        + sum(entry["count"] for entry in bonus_dice)
        + sum(entry["count"] for entry in penalty_dice)
    )
    if total_dice > MAX_DICE_PER_REQUEST:
        raise ValueError(
            f"request resolves {total_dice} dice, exceeding the maximum of "
            f"{MAX_DICE_PER_REQUEST} per request"
        )

    if rng is None:
        rng = random

    if mode == "advantage":
        rolls = _roll(2, sides, rng)
        kept_rolls = [max(rolls)]
        dropped_rolls = [min(rolls)]
    elif mode == "disadvantage":
        rolls = _roll(2, sides, rng)
        kept_rolls = [min(rolls)]
        dropped_rolls = [max(rolls)]
    else:
        rolls = _roll(count, sides, rng)
        kept_rolls = list(rolls)
        dropped_rolls = []

    resolved_bonus = []
    for entry in bonus_dice:
        dice_rolls = _roll(entry["count"], entry["sides"], rng)
        resolved_bonus.append(
            {
                "notation": entry["notation"],
                "source": entry["source"],
                "rolls": dice_rolls,
                "total": sum(dice_rolls),
            }
        )

    resolved_penalty = []
    for entry in penalty_dice:
        dice_rolls = _roll(entry["count"], entry["sides"], rng)
        resolved_penalty.append(
            {
                "notation": entry["notation"],
                "source": entry["source"],
                "rolls": dice_rolls,
                "total": sum(dice_rolls),
            }
        )

    modifier_total = sum(entry["value"] for entry in modifiers)
    bonus_total = sum(entry["total"] for entry in resolved_bonus)
    penalty_total = sum(entry["total"] for entry in resolved_penalty)
    total = sum(kept_rolls) + modifier_total + bonus_total - penalty_total

    return {
        "notation": request["notation"],
        "dice_count": count,
        "sides": sides,
        "mode": mode,
        "advantage_sources": advantage_sources,
        "disadvantage_sources": disadvantage_sources,
        "rolls": rolls,
        "kept_rolls": kept_rolls,
        "dropped_rolls": dropped_rolls,
        "modifiers": modifiers,
        "modifier_total": modifier_total,
        "bonus_dice": resolved_bonus,
        "bonus_total": bonus_total,
        "penalty_dice": resolved_penalty,
        "penalty_total": penalty_total,
        "total": total,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve one RHC dice request from JSON (file or stdin)."
    )
    parser.add_argument(
        "request",
        nargs="?",
        help="path to a JSON request file; omit to read stdin",
    )
    args = parser.parse_args(argv)

    if args.request:
        with open(args.request, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.load(sys.stdin)

    try:
        result = resolve(payload)
    except ValueError as exc:
        print(f"dice resolver error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
