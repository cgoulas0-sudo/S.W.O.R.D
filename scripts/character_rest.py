#!/usr/bin/env python3
"""POST-EV2-10 -- Character Rest Hit Point Die spending helper.

Short Rest Hit Point Die spending is the only Rest step that requires a random
roll. This module never generates randomness itself: every required Hit Point Die
roll is produced by RHC's single shared resolver, ``scripts/dice_resolver.py``
(POST-EV2-8). It owns no rule beyond "ask the one RNG root for the declared
``NdM`` expression and expose the individual die results", and it writes no file,
SQL or campaign state.

Production randomness comes from the resolver's unseeded runtime RNG. A caller
may inject an explicit test-only ``rng`` seam (``random.Random(seed)``) which is
forwarded to the resolver; that seam must never be used as production behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dice_resolver  # noqa: E402  (single shared RNG root)

HIT_DIE_FACES = (4, 6, 8, 10, 12)


def _require_positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def roll_hit_die_spending(entries, rng=None):
    """Resolve declared Hit Point Die spending through the shared resolver.

    ``entries`` is a bounded list of ``{"pool_id", "die_faces", "count"}``. For
    each entry the whole pool expenditure is resolved as one ``count``d``faces``
    expression through ``dice_resolver.resolve`` and the individual kept rolls are
    returned, so the SQL route can validate each die against the pool and add the
    sourced Constitution modifier. No raw RNG is ever used here.
    """
    if not isinstance(entries, list):
        raise ValueError("hit die spending entries must be a list")
    spending = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("hit die spending entry must be an object")
        unknown = set(entry) - {"pool_id", "die_faces", "count"}
        if unknown:
            raise ValueError(f"hit die spending entry has unknown field(s): {sorted(unknown)}")
        pool_id = entry.get("pool_id")
        if not isinstance(pool_id, str) or not pool_id.strip():
            raise ValueError("hit die spending pool_id must be a non-empty string")
        if pool_id in seen:
            raise ValueError(f"hit die spending declares pool {pool_id} more than once")
        seen.add(pool_id)
        faces = entry.get("die_faces")
        if faces not in HIT_DIE_FACES:
            raise ValueError("hit die spending die_faces must be one of 4, 6, 8, 10 or 12")
        count = _require_positive_int(entry.get("count"), "hit die spending count")
        result = dice_resolver.resolve({"notation": f"{count}d{faces}"}, rng=rng)
        spending.append({"pool_id": pool_id, "rolls": list(result["kept_rolls"])})
    return spending


def build_request(character_id, controller, rest, spending_entries=None, con_modifier=None, rng=None):
    """Build the SQL-ready ``mutate_character_rest`` request.

    ``spending_entries`` (when present) are resolved through the shared resolver;
    a sourced ``con_modifier`` is carried through unchanged (Rest never invents or
    stores a Constitution modifier).
    """
    request = {
        "character_id": character_id,
        "controller": controller,
        "rest": rest,
    }
    if spending_entries:
        request["hit_die_spending"] = roll_hit_die_spending(spending_entries, rng=rng)
        if con_modifier is None:
            raise ValueError("Hit Point Die spending requires a sourced con_modifier")
        request["con_modifier"] = con_modifier
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Resolve declared Hit Point Die spending through the shared RHC dice "
            "resolver (POST-EV2-8). Reads JSON from a file argument or stdin and "
            "prints the SQL-ready hit_die_spending list."
        )
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
        spending = roll_hit_die_spending(payload.get("spending", []))
    except ValueError as exc:
        print(f"character rest error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"hit_die_spending": spending}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
