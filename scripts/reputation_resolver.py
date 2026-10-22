#!/usr/bin/env python3
"""POST-EV2-11.9 — Reusable deterministic Business Reputation primitive.

One small reusable mechanic for a Business-owned 0-100 standing score. It
validates an existing score, an explicit consequence classification, and
configuration; applies the configured bounded change with high-standing positive
asymmetry; derives the resulting tier; and returns a mechanical result for a
later owner to persist.

It is a pure mechanic. It:
- creates no RNG root and invokes no randomness;
- persists nothing and integrates with no Business economy, Incorporation,
  Begin Day, or runtime mutation domain;
- never duplicates personal Reputation state;
- never infers Business association of a person (that is caller-owned context).

The Business owns its Reputation score. Owners/workers inherit contextual
association with the relevant Business Reputation; they do not receive
duplicated personal Reputation state. Tiers describe default public/institutional
standing, eligibility and access only — never automatic NPC behavior,
relationships, knowledge, obedience, or spawned entities.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal

ALLOWED_REQUEST_KEYS = frozenset({"current_score", "consequence_class", "direction"})
POSITIVE = "positive"
NEGATIVE = "negative"
ALLOWED_DIRECTIONS = frozenset({POSITIVE, NEGATIVE})
ALLOWED_ROUNDING = frozenset({"floor"})

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "config",
    "REPUTATION_TEMPLATE.json",
)


def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a number")
    return value


def _require_str(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def validate_config(config):
    """Validate and normalize a Reputation configuration.

    Fails closed on any malformed config: bad bounds, missing/overlapping/gapped
    tier coverage, an invalid positive-gain multiplier, or an unsupported
    rounding mode. Returns a normalized structure; never mutates ``config``.
    """
    if not isinstance(config, dict):
        raise ValueError("config must be an object")

    bounds = config.get("score_bounds")
    if not isinstance(bounds, dict):
        raise ValueError("config.score_bounds must be an object")
    low = _require_int(bounds.get("min"), "score_bounds.min")
    high = _require_int(bounds.get("max"), "score_bounds.max")
    if not (low < high):
        raise ValueError("score_bounds.min must be strictly less than score_bounds.max")

    scale = config.get("consequence_scale")
    if not isinstance(scale, dict) or not scale:
        raise ValueError("config.consequence_scale must be a non-empty object")
    normalized_scale = {}
    for key, value in scale.items():
        if not isinstance(key, str) or not key:
            raise ValueError("consequence_scale keys must be non-empty strings")
        magnitude = _require_int(value, f"consequence_scale[{key}]")
        if magnitude < 1:
            raise ValueError(f"consequence_scale[{key}] must be >= 1")
        normalized_scale[key] = magnitude

    hs = config.get("high_standing")
    if not isinstance(hs, dict):
        raise ValueError("config.high_standing must be an object")
    threshold = _require_int(hs.get("threshold"), "high_standing.threshold")
    if not (low < threshold <= high):
        raise ValueError("high_standing.threshold must satisfy min < threshold <= max")
    multiplier = _require_number(
        hs.get("positive_gain_multiplier"), "high_standing.positive_gain_multiplier"
    )
    if not (0 < multiplier < 1):
        raise ValueError("high_standing.positive_gain_multiplier must be in (0, 1)")
    rounding = _require_str(hs.get("rounding"), "high_standing.rounding")
    if rounding not in ALLOWED_ROUNDING:
        raise ValueError("high_standing.rounding must be 'floor'")

    tiers = config.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("config.tiers must be a non-empty list")
    parsed_tiers = []
    for tier in tiers:
        if not isinstance(tier, dict):
            raise ValueError("each tier must be an object")
        name = _require_str(tier.get("name"), "tier.name")
        tmin = _require_int(tier.get("min"), "tier.min")
        tmax = _require_int(tier.get("max"), "tier.max")
        if tmin < low or tmax > high:
            raise ValueError("tier bounds must stay within score_bounds")
        if tmin > tmax:
            raise ValueError("tier.min must not exceed tier.max")
        parsed_tiers.append((name, tmin, tmax))
    parsed_tiers.sort(key=lambda item: item[1])
    if parsed_tiers[0][1] != low:
        raise ValueError("tiers must start at score_bounds.min")
    if parsed_tiers[-1][2] != high:
        raise ValueError("tiers must end at score_bounds.max")
    for index in range(len(parsed_tiers) - 1):
        if parsed_tiers[index][2] + 1 != parsed_tiers[index + 1][1]:
            raise ValueError("tiers must be contiguous with no gap or overlap")

    return {
        "min": low,
        "max": high,
        "scale": normalized_scale,
        "threshold": threshold,
        "multiplier": multiplier,
        "rounding": rounding,
        "tiers": parsed_tiers,
    }


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _floor_scaled_magnitude(magnitude, multiplier):
    """Exact ``floor(magnitude * multiplier)`` with decimal-safe semantics.

    A configured multiplier parsed as a binary float can sit just below the
    mathematically exact product (for example ``100 * 0.29`` evaluates to
    ``28.999999999999996``), so flooring the float product would silently drop a
    whole Reputation point. Recover the intended decimal value from the
    multiplier's shortest representation and floor the exact product instead.

    Flooring is done with exact integer-ratio arithmetic rather than Decimal
    multiplication: the default Decimal context precision (28 significant
    digits) rounds any product wider than that, so a valid configured magnitude
    large enough to exceed it would silently lose whole points. Converting the
    multiplier to its exact ``numerator / denominator`` and integer-dividing
    ``magnitude * numerator`` by ``denominator`` is exact at any magnitude.
    """
    if isinstance(multiplier, Decimal):
        exact = multiplier
    elif isinstance(multiplier, int):
        exact = Decimal(multiplier)
    else:
        exact = Decimal(str(multiplier))
    numerator, denominator = exact.as_integer_ratio()
    return (magnitude * numerator) // denominator


def _tier_for(score, tiers):
    for name, tmin, tmax in tiers:
        if tmin <= score <= tmax:
            return name
    raise ValueError(f"no tier covers score {score!r}")


def resolve_reputation(request, config):
    """Resolve one explicit Reputation consequence into a mechanical result.

    ``request`` is ``{current_score, consequence_class, direction}``. The
    consequence class names a configured magnitude; ``direction`` selects the
    sign. A positive gain applied while the current score is above the configured
    high-standing threshold is reduced by the configured multiplier with floor
    rounding. Negative changes are never reduced by the positive asymmetry.
    Returns the bounded resulting score, the derived tier, and the applied delta.

    Fails closed on any malformed input, unknown class, out-of-range score, or
    invalid config. Never mutates ``request`` or ``config``.
    """
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    unknown = set(request) - ALLOWED_REQUEST_KEYS
    if unknown:
        raise ValueError(f"request has unknown field(s): {sorted(unknown)}")

    cfg = validate_config(config)

    if "current_score" not in request:
        raise ValueError("request.current_score is required")
    current = _require_int(request["current_score"], "current_score")
    if current < cfg["min"] or current > cfg["max"]:
        raise ValueError("current_score out of bounds")

    if "consequence_class" not in request:
        raise ValueError("request.consequence_class is required")
    consequence_class = _require_str(request["consequence_class"], "consequence_class")
    if consequence_class not in cfg["scale"]:
        raise ValueError(f"unknown consequence class: {consequence_class!r}")

    if "direction" not in request:
        raise ValueError("request.direction is required")
    direction = _require_str(request["direction"], "direction")
    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError("direction must be 'positive' or 'negative'")

    magnitude = cfg["scale"][consequence_class]
    sign = 1 if direction == POSITIVE else -1

    # High-standing positive asymmetry: a positive gain above the configured
    # threshold is reduced by the multiplier with floor rounding. Negative
    # changes are never reduced by this asymmetry.
    asymmetry = direction == POSITIVE and current > cfg["threshold"]
    if asymmetry:
        applied_magnitude = _floor_scaled_magnitude(magnitude, cfg["multiplier"])
        if applied_magnitude < 0:
            applied_magnitude = 0
    else:
        applied_magnitude = magnitude

    delta = sign * applied_magnitude
    raw = current + delta
    resulting = _clamp(raw, cfg["min"], cfg["max"])
    bounded = raw != resulting

    tier = _tier_for(resulting, cfg["tiers"])

    return {
        "current_score": current,
        "consequence_class": consequence_class,
        "direction": direction,
        "magnitude": magnitude,
        "high_standing_asymmetry_applied": asymmetry,
        "applied_delta": delta,
        "resulting_score": resulting,
        "tier": tier,
        "bounded": bounded,
    }


def load_config(path):
    # Parse JSON decimal literals as Decimal so a configured multiplier is
    # retained exactly as written. Parsing through binary float first loses
    # high-precision digits, and recovering the multiplier with
    # ``Decimal(str(float))`` only yields the float's shortest round-tripping
    # representation rather than the configured literal, so exact floor
    # semantics begin at parse time, not only during multiplication.
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve one RHC Business Reputation consequence from JSON."
    )
    parser.add_argument(
        "request", nargs="?", help="path to a JSON request file; omit to read stdin"
    )
    parser.add_argument(
        "--config",
        default=_DEFAULT_CONFIG_PATH,
        help="path to the reputation config template JSON",
    )
    args = parser.parse_args(argv)

    try:
        if args.request:
            with open(args.request, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = json.load(sys.stdin)
        config = load_config(args.config)
        result = resolve_reputation(payload, config)
    except (ValueError, OSError) as exc:
        print(f"reputation resolver error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
