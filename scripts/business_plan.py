#!/usr/bin/env python3
"""POST-EV2-12.1 — inert Business Card planner / preflight.

A small deterministic compiler for approved Business Cards. Given an explicitly
instantiated economy configuration plus the Business portion of current state,
it validates the completed authoring contract and returns a copy-isolated
normalized plan plus a conditional dice manifest for Stage C to consume later.

It is a planner, not a resolver. It:

- generates no random values and invokes no RNG;
- calculates no revenue, repair cost, purchase cost, byproduct quantity,
  allocation, balance or resulting Reputation;
- applies no duration effects and mutates no caller data;
- calls no SAVE/RT01 route, registers no Begin Day consumer, and writes no file
  or state;
- implements no Stage C resolution and no generic schema/rule engine.

The contract it completes makes every deterministic Stage C input explicit:
each Business declares its revenue base (or fixed revenue) and fixed daily cost,
its ``funds_enabled`` policy fact distinct from its current active/disabled
state, the approved fund policy, the bounded mutable state shape under
``live_status.businesses``, the explicit ``facility_value`` repair-cost basis a
rolled Business declares for the later catastrophic-repair resolution, and the
same-day internal source-cost chain (``internal_sources``) that Mission10 proves
is the real raw-material mechanic — not negotiated buyer-specific supplier
pricing. The planner validates and preserves ``facility_value`` exactly; it never
multiplies it by a repair percentage (that arithmetic belongs to Stage C).

The normalized plan carries the validated current Business state, the
validated fund policy, and the validated Reputation configuration (the same
shape the POST-EV2-11.9 ``scripts/reputation_resolver.py`` consumes) so Stage C
consumes one complete, copy-isolated contract; a Business whose current state
disables it emits no daily dice requests; and superseded negotiated-supplier
pricing surfaces fail closed rather than being silently dropped.

The only reusable mechanics it references are the existing owners:
``scripts/dice_resolver.py`` (POST-EV2-8) for dice-notation validation and
``scripts/reputation_resolver.py`` (POST-EV2-11.9) for Reputation
configuration/consequence compatibility. It copies neither.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from decimal import Decimal

import dice_resolver
import reputation_resolver

PLAN_VERSION = 4
MANIFEST_VERSION = 1

CURRENCIES = frozenset({"gp", "sp", "cp"})
ROUNDINGS = frozenset({"half_up", "half_even", "floor", "ceil"})
REVENUE_MODES = frozenset({"rolled", "fixed"})
DURATION_DICE = frozenset({"1d3", "1d6"})
ECONOMIC_DIE = "1d20"
SEVERITY_DIE = "1d6"
NARRATIVE_DIE = "1d20"

# The exact approved default positive-net fund allocation (20% HQ / 70% Business
# Development / 10% Business Recovery). The planner validates this declaration;
# it never allocates or moves money.
FUND_SHARES = (
    ("hq_share", Decimal("0.2")),
    ("development_share", Decimal("0.7")),
    ("recovery_share", Decimal("0.1")),
)
# The exact approved recovery waterfall: affected Business Recovery, then HQ
# Recovery, then uncovered loss. The Development Fund is never auto-drawn.
FUND_WATERFALL = ("own_recovery", "hq_recovery", "uncovered_loss")

# The exact approved economic 1d20 bands (POST-EV2-12 Stage B decision 5):
# (min, max, outcome, multiplier). Outcome 1 is the catastrophic/severity branch;
# every other band carries only its approved revenue multiplier.
ECONOMIC_BANDS = (
    (1, 1, "catastrophic", None),
    (2, 5, None, Decimal("0.35")),
    (6, 10, None, Decimal("0.75")),
    (11, 16, None, Decimal("1.00")),
    (17, 19, None, Decimal("1.35")),
    (20, 20, None, Decimal("1.75")),
)

# The exact approved Natural-1 repair severity schedule (decision 3):
# (min, max, severity, cost_percent_min, cost_percent_max, revenue_multiplier,
#  duration_die). Only the moderate/serious/catastrophic branches carry a
# required resolution-duration die; minor carries none.
REPAIR_BANDS = (
    (1, 2, "minor", Decimal("5"), Decimal("10"), Decimal("1.0"), None),
    (3, 4, "moderate", Decimal("15"), Decimal("25"), Decimal("0.70"), "1d3"),
    (5, 5, "serious", Decimal("30"), Decimal("50"), Decimal("0.50"), "1d3"),
    (6, 6, "catastrophic", Decimal("60"), Decimal("90"), Decimal("0.00"), "1d6"),
)

# The exact approved Natural-1 Reputation severity totals (decision 5), using
# the SAME severity d6 as the repair branch: (min, max, loss magnitude).
REPUTATION_NAT1_BANDS = ((1, 3, 3), (4, 5, 4), (6, 6, 5))
REPUTATION_NAT20_MAGNITUDE = 5


def _require_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a number")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{name} must be a finite number")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
    return value


def _as_decimal(value):
    """Exact decimal view of a declared number, without binary-float loss.

    An int or Decimal is already exact. A float is recovered from its shortest
    round-tripping representation (``str``) so a value authored as ``0.35``
    compares equal to the approved ``Decimal("0.35")`` rather than to the
    binary approximation beneath the float.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_str(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _require_notation(value, name):
    notation = _require_str(value, name)
    try:
        dice_resolver.parse_notation(notation)
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid dice notation: {exc}") from None
    return notation


def _require_band_cover(bands, low, high, name):
    """Require bands to cover ``[low, high]`` exactly once with no overlap/gap."""
    if not bands:
        raise ValueError(f"{name} must declare at least one band")
    seen = {}
    for index, band in enumerate(bands):
        _require_object(band, f"{name}[{index}]")
        bmin = _require_int(band.get("min"), f"{name}[{index}].min")
        bmax = _require_int(band.get("max"), f"{name}[{index}].max")
        if bmin > bmax:
            raise ValueError(f"{name}[{index}].min must not exceed .max")
        if bmin < low or bmax > high:
            raise ValueError(f"{name}[{index}] must stay within [{low}, {high}]")
        for outcome in range(bmin, bmax + 1):
            if outcome in seen:
                raise ValueError(
                    f"{name} outcomes overlap at {outcome} "
                    f"(bands {seen[outcome]} and {index})"
                )
            seen[outcome] = index
    for outcome in range(low, high + 1):
        if outcome not in seen:
            raise ValueError(f"{name} leaves reachable outcome {outcome} undefined")
    return seen


# --------------------------------------------------------------------------
# Fund policy
# --------------------------------------------------------------------------

def _validate_fund_policy(policy):
    """Validate the approved fund policy declaration, if one is present.

    The planner only confirms the declaration represents the approved
    20/70/10 positive allocation, the own-Recovery -> HQ-Recovery -> uncovered
    loss waterfall, and no automatic Development Fund draw. It never allocates
    or moves money.
    """
    if policy is None:
        return
    _require_object(policy, "fund_policy")

    allocation = policy.get("default_positive_profit_allocation")
    _require_object(
        allocation, "fund_policy.default_positive_profit_allocation"
    )
    expected_keys = {key for key, _share in FUND_SHARES}
    if set(allocation) != expected_keys:
        raise ValueError(
            "fund_policy.default_positive_profit_allocation must declare exactly "
            f"{sorted(expected_keys)}"
        )
    for key, expected in FUND_SHARES:
        declared = _as_decimal(
            _require_number(
                allocation.get(key),
                f"fund_policy.default_positive_profit_allocation.{key}",
            )
        )
        if declared != expected:
            raise ValueError(
                f"fund_policy.default_positive_profit_allocation.{key} must be "
                f"{expected}"
            )

    waterfall = _require_list(
        policy.get("recovery_waterfall"), "fund_policy.recovery_waterfall"
    )
    if tuple(waterfall) != FUND_WATERFALL:
        raise ValueError(
            "fund_policy.recovery_waterfall must be exactly "
            "own_recovery -> hq_recovery -> uncovered_loss"
        )

    if policy.get("development_fund_auto_draw") is not False:
        raise ValueError(
            "fund_policy.development_fund_auto_draw must be false"
        )


# --------------------------------------------------------------------------
# Internal source-cost chain
# --------------------------------------------------------------------------

def _validate_internal_sources(business_id, sources, business_ids):
    """Validate the same-day internal source-cost declarations for one Business.

    Later purchase cost equals the actual realized same-day sales/revenue of
    each linked source Business, so each link must name an existing Business
    and no link may repeat or reference the Business itself. Cycles across the
    whole graph are rejected separately.
    """
    name = f"{business_id}.internal_sources"
    _require_list(sources, name)
    seen = set()
    for index, source in enumerate(sources):
        label = f"{name}[{index}]"
        _require_str(source, label)
        if source == business_id:
            raise ValueError(f"{label} must not reference itself")
        if source not in business_ids:
            raise ValueError(f"{label} references unknown business {source!r}")
        if source in seen:
            raise ValueError(f"{label} duplicates internal source {source!r}")
        seen.add(source)


def _require_acyclic_internal_sources(businesses):
    white, gray, black = 0, 1, 2
    color = {business_id: white for business_id in businesses}

    def visit(business_id):
        color[business_id] = gray
        for source in businesses[business_id].get("internal_sources", []):
            if color[source] == gray:
                raise ValueError(
                    f"circular internal source dependency detected at {source!r}"
                )
            if color[source] == white:
                visit(source)
        color[business_id] = black

    for business_id in sorted(businesses):
        if color[business_id] == white:
            visit(business_id)


# --------------------------------------------------------------------------
# Business Card pieces
# --------------------------------------------------------------------------

def _validate_economic_roll(business_id, roll):
    name = f"{business_id}.economic_roll"
    roll = _require_object(roll, name)
    die = _require_notation(roll.get("die"), f"{name}.die")
    if die != ECONOMIC_DIE:
        raise ValueError(f"{name}.die must be {ECONOMIC_DIE}")
    bands = _require_list(roll.get("bands"), f"{name}.bands")
    _require_band_cover(bands, 1, 20, f"{name}.bands")

    expected_ranges = {(low, high) for low, high, _o, _m in ECONOMIC_BANDS}
    declared_ranges = {(band["min"], band["max"]) for band in bands}
    if declared_ranges != expected_ranges:
        raise ValueError(
            f"{name}.bands must declare exactly the approved economic 1d20 bands"
        )

    for index, band in enumerate(bands):
        label = f"{name}.bands[{index}]"
        _low, _high, outcome, multiplier = next(
            spec
            for spec in ECONOMIC_BANDS
            if spec[0] == band["min"] and spec[1] == band["max"]
        )
        if outcome == "catastrophic":
            if _require_str(band.get("outcome"), f"{label}.outcome") != "catastrophic":
                raise ValueError(f"{label}.outcome must be 'catastrophic'")
        else:
            declared = _as_decimal(
                _require_number(band.get("multiplier"), f"{label}.multiplier")
            )
            if declared != multiplier:
                raise ValueError(f"{label}.multiplier must be {multiplier}")


def _validate_repair(business_id, repair):
    name = f"{business_id}.repair"
    repair = _require_object(repair, name)
    die = _require_notation(repair.get("severity_die"), f"{name}.severity_die")
    if die != SEVERITY_DIE:
        raise ValueError(f"{name}.severity_die must be {SEVERITY_DIE}")
    bands = _require_list(repair.get("severity_bands"), f"{name}.severity_bands")
    _require_band_cover(bands, 1, 6, f"{name}.severity_bands")

    expected_ranges = {(low, high) for low, high, *_rest in REPAIR_BANDS}
    declared_ranges = {(band["min"], band["max"]) for band in bands}
    if declared_ranges != expected_ranges:
        raise ValueError(
            f"{name}.severity_bands must declare exactly the approved Natural-1 "
            "repair schedule"
        )

    for index, band in enumerate(bands):
        label = f"{name}.severity_bands[{index}]"
        _low, _high, severity, cmin, cmax, multiplier, duration = next(
            spec
            for spec in REPAIR_BANDS
            if spec[0] == band["min"] and spec[1] == band["max"]
        )
        if _require_str(band.get("severity"), f"{label}.severity") != severity:
            raise ValueError(f"{label}.severity must be {severity!r}")
        declared_min = _as_decimal(
            _require_number(band.get("cost_percent_min"), f"{label}.cost_percent_min")
        )
        declared_max = _as_decimal(
            _require_number(band.get("cost_percent_max"), f"{label}.cost_percent_max")
        )
        if declared_min != cmin or declared_max != cmax:
            raise ValueError(f"{label} cost percent must be {cmin}-{cmax}")
        declared_multiplier = _as_decimal(
            _require_number(band.get("revenue_multiplier"), f"{label}.revenue_multiplier")
        )
        if declared_multiplier != multiplier:
            raise ValueError(f"{label}.revenue_multiplier must be {multiplier}")
        declared_duration = band.get("duration_die")
        if declared_duration is not None:
            _require_notation(declared_duration, f"{label}.duration_die")
            if declared_duration not in DURATION_DICE:
                raise ValueError(
                    f"{label}.duration_die must be one of {sorted(DURATION_DICE)}"
                )
        if declared_duration != duration:
            raise ValueError(f"{label}.duration_die must be {duration!r}")

    selector = repair.get("percent_selector")
    if selector is not None:
        _require_notation(selector, f"{name}.percent_selector")


def _validate_consequence(label, entry, rep_cfg, direction):
    entry = _require_object(entry, label)
    if rep_cfg is None:
        raise ValueError(
            "economy.reputation config is required to declare Reputation consequences"
        )
    consequence_class = _require_str(entry.get("consequence_class"), f"{label}.consequence_class")
    if consequence_class not in rep_cfg["scale"]:
        raise ValueError(
            f"{label}.consequence_class {consequence_class!r} is not in the "
            "configured Reputation consequence_scale"
        )
    declared = _require_str(entry.get("direction"), f"{label}.direction")
    if declared != direction:
        raise ValueError(f"{label}.direction must be {direction!r}")
    return rep_cfg["scale"][consequence_class]


def _validate_reputation_consequences(business_id, consequences, rep_cfg):
    name = f"{business_id}.reputation_consequences"
    consequences = _require_object(consequences, name)

    nat20_magnitude = _validate_consequence(
        f"{name}.economic_nat20", consequences.get("economic_nat20"), rep_cfg, "positive"
    )
    if nat20_magnitude != REPUTATION_NAT20_MAGNITUDE:
        raise ValueError(
            f"{name}.economic_nat20 must resolve to "
            f"+{REPUTATION_NAT20_MAGNITUDE} through the configured consequence_scale"
        )

    nat1 = _require_list(consequences.get("repair_nat1_severity"), f"{name}.repair_nat1_severity")
    _require_band_cover(nat1, 1, 6, f"{name}.repair_nat1_severity")

    expected_ranges = {(low, high) for low, high, _m in REPUTATION_NAT1_BANDS}
    declared_ranges = {(band["min"], band["max"]) for band in nat1}
    if declared_ranges != expected_ranges:
        raise ValueError(
            f"{name}.repair_nat1_severity must declare exactly the approved "
            "Natural-1 severity totals"
        )

    for index, band in enumerate(nat1):
        label = f"{name}.repair_nat1_severity[{index}]"
        magnitude = _validate_consequence(label, band, rep_cfg, "negative")
        expected_magnitude = next(
            loss
            for low, high, loss in REPUTATION_NAT1_BANDS
            if low == band["min"] and high == band["max"]
        )
        if magnitude != expected_magnitude:
            raise ValueError(
                f"{label} must resolve to -{expected_magnitude} through the "
                "configured consequence_scale"
            )


def _validate_byproducts(business_id, byproducts):
    name = f"{business_id}.byproducts"
    _require_list(byproducts, name)
    for index, byproduct in enumerate(byproducts):
        label = f"{name}[{index}]"
        _require_object(byproduct, label)
        _require_str(byproduct.get("product"), f"{label}.product")
        source = _require_number(byproduct.get("source_quantity"), f"{label}.source_quantity")
        if source < 0:
            raise ValueError(f"{label}.source_quantity must be >= 0")
        waste = _require_number(byproduct.get("waste_ratio"), f"{label}.waste_ratio")
        if not 0 <= waste <= 1:
            raise ValueError(f"{label}.waste_ratio must be within [0, 1]")
        yield_ratio = _require_number(byproduct.get("yield"), f"{label}.yield")
        if not 0 <= yield_ratio <= 1:
            raise ValueError(f"{label}.yield must be within [0, 1]")
        _require_str(byproduct.get("disposition"), f"{label}.disposition")
        if byproduct.get("sold_on_production_day") is not False:
            raise ValueError(
                f"{label}.sold_on_production_day must be false; byproducts are "
                "not sold on the day of production"
            )


def _validate_narrative_event(business_id, event):
    if event is None:
        return
    name = f"{business_id}.narrative_event"
    event = _require_object(event, name)
    die = _require_notation(event.get("die"), f"{name}.die")
    if die != NARRATIVE_DIE:
        raise ValueError(f"{name}.die must be {NARRATIVE_DIE}")
    table = _require_object(event.get("table"), f"{name}.table")
    if not table:
        raise ValueError(f"{name}.table must be a non-empty object")


def _validate_card(business_id, card, business_ids, rep_cfg):
    _require_object(card, f"business_units[{business_id}]")
    if "supplier_agreements" in card:
        raise ValueError(
            f"{business_id}.supplier_agreements is a superseded negotiated-price "
            "surface; declare explicit internal_sources using same-day realized "
            "source-Business revenue instead"
        )
    _require_str(card.get("name"), f"{business_id}.name")
    currency = _require_str(card.get("currency"), f"{business_id}.currency")
    if currency not in CURRENCIES:
        raise ValueError(f"{business_id}.currency must be one of {sorted(CURRENCIES)}")
    precision = _require_int(card.get("precision"), f"{business_id}.precision")
    if precision < 0:
        raise ValueError(f"{business_id}.precision must be >= 0")
    rounding = _require_str(card.get("rounding"), f"{business_id}.rounding")
    if rounding not in ROUNDINGS:
        raise ValueError(f"{business_id}.rounding must be one of {sorted(ROUNDINGS)}")

    parent = card.get("parent")
    if parent is not None:
        _require_str(parent, f"{business_id}.parent")
        if parent == business_id:
            raise ValueError(f"{business_id}.parent must not reference itself")
        if parent not in business_ids:
            raise ValueError(f"{business_id}.parent references unknown business {parent!r}")

    subsidiaries = card.get("subsidiaries", [])
    _require_list(subsidiaries, f"{business_id}.subsidiaries")
    for index, subsidiary in enumerate(subsidiaries):
        _require_str(subsidiary, f"{business_id}.subsidiaries[{index}]")
        if subsidiary == business_id:
            raise ValueError(f"{business_id}.subsidiaries must not reference itself")
        if subsidiary not in business_ids:
            raise ValueError(
                f"{business_id}.subsidiaries[{index}] references unknown business "
                f"{subsidiary!r}"
            )

    mode = _require_str(card.get("revenue_mode"), f"{business_id}.revenue_mode")
    if mode not in REVENUE_MODES:
        raise ValueError(f"{business_id}.revenue_mode must be one of {sorted(REVENUE_MODES)}")

    if mode == "fixed":
        fixed = _require_number(card.get("fixed_revenue"), f"{business_id}.fixed_revenue")
        if fixed < 0:
            raise ValueError(f"{business_id}.fixed_revenue must be >= 0")
        for forbidden in (
            "revenue_base",
            "economic_roll",
            "repair",
            "reputation_consequences",
        ):
            if card.get(forbidden) is not None:
                raise ValueError(
                    f"{business_id}.{forbidden} is not valid for a fixed-revenue business"
                )
        # facility_value is the repair-only basis; a fixed Business owns no repair
        # mechanic, so reject the key by presence — an explicit null is still a
        # declared repair-cost basis and must fail closed rather than be dropped.
        if "facility_value" in card:
            raise ValueError(
                f"{business_id}.facility_value is not valid for a fixed-revenue business"
            )
    else:
        if card.get("fixed_revenue") is not None:
            raise ValueError(
                f"{business_id}.fixed_revenue is only valid for a fixed-revenue business"
            )
        revenue_base = _require_number(card.get("revenue_base"), f"{business_id}.revenue_base")
        if revenue_base < 0:
            raise ValueError(f"{business_id}.revenue_base must be >= 0")
        _validate_economic_roll(business_id, card.get("economic_roll"))
        _validate_repair(business_id, card.get("repair"))
        _validate_reputation_consequences(business_id, card.get("reputation_consequences"), rep_cfg)
        facility_value = _require_number(
            card.get("facility_value"), f"{business_id}.facility_value"
        )
        if facility_value < 0:
            raise ValueError(f"{business_id}.facility_value must be >= 0")

    fixed_daily_cost = _require_number(
        card.get("fixed_daily_cost"), f"{business_id}.fixed_daily_cost"
    )
    if fixed_daily_cost < 0:
        raise ValueError(f"{business_id}.fixed_daily_cost must be >= 0")

    funds_enabled = card.get("funds_enabled")
    if not isinstance(funds_enabled, bool):
        raise ValueError(f"{business_id}.funds_enabled must be a boolean")

    _validate_internal_sources(business_id, card.get("internal_sources", []), business_ids)
    _validate_byproducts(business_id, card.get("byproducts", []))
    _validate_narrative_event(business_id, card.get("narrative_event"))


# --------------------------------------------------------------------------
# Normalized plan + conditional manifest
# --------------------------------------------------------------------------

def _normalize_card(card):
    normalized = {
        "name": card["name"],
        "currency": card["currency"],
        "precision": card["precision"],
        "rounding": card["rounding"],
        "revenue_mode": card["revenue_mode"],
        "revenue_base": card.get("revenue_base"),
        "fixed_revenue": card.get("fixed_revenue"),
        "fixed_daily_cost": card["fixed_daily_cost"],
        "funds_enabled": card["funds_enabled"],
        "parent": card.get("parent"),
        "subsidiaries": list(card.get("subsidiaries", [])),
        "economic_roll": copy.deepcopy(card.get("economic_roll")),
        "repair": copy.deepcopy(card.get("repair")),
        "reputation_consequences": copy.deepcopy(card.get("reputation_consequences")),
        "narrative_event": copy.deepcopy(card.get("narrative_event")),
        "internal_sources": list(card.get("internal_sources", [])),
        "byproducts": copy.deepcopy(card.get("byproducts", [])),
    }
    # Only a rolled Business declares the repair-cost basis; a fixed Business
    # omits the key entirely rather than emitting a null repair-only field.
    if "facility_value" in card:
        normalized["facility_value"] = card["facility_value"]
    return normalized


def _request(business_id, purpose, notation, conditional):
    return {
        "business": business_id,
        "purpose": purpose,
        "notation": notation,
        "conditional": conditional,
    }


def _manifest_for(business_id, card):
    requests = []
    if card["revenue_mode"] == "rolled":
        requests.append(_request(business_id, "economic", ECONOMIC_DIE, False))
        repair = card["repair"]
        requests.append(_request(business_id, "repair_severity", SEVERITY_DIE, True))
        durations = sorted(
            {
                band["duration_die"]
                for band in repair["severity_bands"]
                if band.get("duration_die")
            }
        )
        for duration in durations:
            requests.append(_request(business_id, "repair_duration", duration, True))
        selector = repair.get("percent_selector")
        if selector:
            requests.append(_request(business_id, "repair_percent_selector", selector, True))
    event = card.get("narrative_event")
    if event is not None:
        requests.append(_request(business_id, "narrative_event", event["die"], False))
    return requests


def _validate_state_businesses(state, rep_cfg):
    """Validate the bounded Business portion of current state.

    The existing ``live_status.businesses`` owner is the only Business
    mutable-state owner. This confirms any declared entry can represent the
    Stage C inputs — active/disabled state (distinct from config
    ``funds_enabled``), a Business Reputation score, current fund balances,
    current stock/byproduct quantities, and Business-owned
    duration-in-resolution-days effects — without seeding real data.

    It returns a copy-isolated ``{"businesses": {...}}`` structure of the
    validated state so Stage C can consume the completed planner contract
    directly instead of rereading the caller's unvalidated input or inventing
    defaults.
    """
    businesses = state.get("businesses")
    if businesses is None:
        businesses = {}
    _require_object(businesses, "state.businesses")
    low = rep_cfg["min"] if rep_cfg is not None else 0
    high = rep_cfg["max"] if rep_cfg is not None else 100
    validated = {}
    for business_id, entry in businesses.items():
        _require_str(business_id, "state.businesses key")
        label = f"state.businesses[{business_id}]"
        _require_object(entry, label)

        if "active" in entry and not isinstance(entry["active"], bool):
            raise ValueError(f"{label}.active must be a boolean")

        if "reputation" in entry:
            score = _require_int(entry["reputation"], f"{label}.reputation")
            if score < low or score > high:
                raise ValueError(f"{label}.reputation must be within [{low}, {high}]")

        funds = entry.get("funds")
        if funds is not None:
            _require_object(funds, f"{label}.funds")
            for fund_name, amount in funds.items():
                _require_str(fund_name, f"{label}.funds key")
                value = _require_number(amount, f"{label}.funds[{fund_name}]")
                if value < 0:
                    raise ValueError(f"{label}.funds[{fund_name}] must be >= 0")

        stock = entry.get("stock")
        if stock is not None:
            _require_object(stock, f"{label}.stock")
            for product, quantity in stock.items():
                _require_str(product, f"{label}.stock key")
                value = _require_number(quantity, f"{label}.stock[{product}]")
                if value < 0:
                    raise ValueError(f"{label}.stock[{product}] must be >= 0")

        effects = entry.get("effects")
        if effects is not None:
            _require_list(effects, f"{label}.effects")
            for index, effect in enumerate(effects):
                elabel = f"{label}.effects[{index}]"
                _require_object(effect, elabel)
                _require_str(effect.get("effect_id"), f"{elabel}.effect_id")
                _require_str(effect.get("source"), f"{elabel}.source")
                multiplier = _require_number(
                    effect.get("revenue_multiplier"), f"{elabel}.revenue_multiplier"
                )
                if multiplier < 0:
                    raise ValueError(f"{elabel}.revenue_multiplier must be >= 0")
                remaining = _require_int(
                    effect.get("remaining_resolution_days"),
                    f"{elabel}.remaining_resolution_days",
                )
                if remaining < 0:
                    raise ValueError(
                        f"{elabel}.remaining_resolution_days must be >= 0"
                    )

        validated[business_id] = copy.deepcopy(entry)
    return {"businesses": validated}


def _business_is_active(validated_state, business_id):
    """Whether a Business resolves today.

    ``active`` is current operational state under ``live_status.businesses`` and
    is distinct from the configuration ``funds_enabled`` policy fact. A Business
    with no declared current state resolves by default; only an explicit
    ``active: false`` suppresses it.
    """
    entry = validated_state["businesses"].get(business_id)
    if entry is None:
        return True
    return entry.get("active", True)


def plan_businesses(economy, state=None):
    """Validate approved Business Cards and emit a normalized plan + manifest.

    ``economy`` is an explicitly instantiated economy configuration carrying
    ``business_units``, an optional ``fund_policy`` declaration, and an
    optional Reputation configuration. ``state`` is the Business portion of
    current state (``{"businesses": {...}}``). Both inputs are read only and
    never mutated. No RNG runs and no resolution is performed.

    The returned plan retains the validated fund policy (required whenever any
    Business declares ``funds_enabled: true``), the validated Reputation
    configuration (``economy.reputation`` after POST-EV2-11.9 validation, or
    ``None`` when no Reputation config is declared) in the shape the existing
    POST-EV2-11.9 resolver consumes, and a copy-isolated copy of the validated
    current Business state. A Business whose current state says ``active: false``
    contributes no requests to the manifest.
    """
    _require_object(economy, "economy")

    if "suppliers" in economy:
        raise ValueError(
            "economy.suppliers is a superseded negotiated-price registry; declare "
            "explicit internal_sources using same-day realized source-Business "
            "revenue instead"
        )

    businesses = economy.get("business_units")
    if businesses is None:
        businesses = {}
    _require_object(businesses, "business_units")

    rep_raw = economy.get("reputation")
    rep_cfg = reputation_resolver.validate_config(rep_raw) if rep_raw is not None else None

    if state is None:
        state = {}
    _require_object(state, "state")

    business_ids = set(businesses)

    normalized = {}
    any_funds_enabled = False
    for business_id in sorted(businesses):
        card = businesses[business_id]
        _validate_card(business_id, card, business_ids, rep_cfg)
        normalized[business_id] = _normalize_card(card)
        if card["funds_enabled"] is True:
            any_funds_enabled = True

    fund_policy = economy.get("fund_policy")
    if any_funds_enabled and fund_policy is None:
        raise ValueError(
            "fund_policy is required when any Business declares funds_enabled: true"
        )
    _validate_fund_policy(fund_policy)

    _require_acyclic_internal_sources(businesses)
    validated_state = _validate_state_businesses(state, rep_cfg)

    requests = []
    for business_id in sorted(businesses):
        if _business_is_active(validated_state, business_id):
            requests.extend(_manifest_for(business_id, businesses[business_id]))

    requests.sort(key=lambda item: (item["business"], item["purpose"], item["notation"]))
    plan = {
        "plan_version": PLAN_VERSION,
        "businesses": normalized,
        "fund_policy": copy.deepcopy(fund_policy),
        "reputation": copy.deepcopy(rep_raw),
        "state": validated_state,
    }
    manifest = {"manifest_version": MANIFEST_VERSION, "requests": requests}
    return {"plan": plan, "manifest": manifest}


def _load_config(path):
    # Parse JSON decimal literals as Decimal so an authored value such as a
    # multiplier, price or quantity is retained exactly as written instead of
    # being round-tripped through an inexact binary float.
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def _dumps_exact(value, indent=2, _level=0):
    """Serialize the plan deterministically, preserving Decimal values exactly.

    ``json.dumps`` cannot emit a ``Decimal`` as a JSON number (it either loses
    precision through ``float`` or quotes it as a string), so decimal-preserving
    output is produced directly. Objects are emitted with sorted keys.
    """
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
            raise ValueError("plan JSON numbers must be finite")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("plan JSON numbers must be finite")
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ",\n".join(
            " " * (indent * (_level + 1)) + _dumps_exact(item, indent, _level + 1)
            for item in value
        )
        return "[\n" + inner + "\n" + " " * (indent * _level) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ",\n".join(
            " " * (indent * (_level + 1))
            + json.dumps(key, ensure_ascii=False)
            + ": "
            + _dumps_exact(value[key], indent, _level + 1)
            for key in sorted(value)
        )
        return "{\n" + inner + "\n" + " " * (indent * _level) + "}"
    raise ValueError(f"unsupported plan JSON type: {type(value).__name__}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate approved Business Cards and emit a Stage B plan + dice manifest."
    )
    parser.add_argument("economy", help="path to the instantiated economy configuration JSON")
    parser.add_argument("--state", help="path to the Business portion of current state JSON")
    args = parser.parse_args(argv)

    try:
        economy = _load_config(args.economy)
        state = _load_config(args.state) if args.state else None
        result = plan_businesses(economy, state)
        rendered = _dumps_exact(result)
    except (ValueError, OSError) as exc:
        print(f"business plan error: {exc}", file=sys.stderr)
        return 2

    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
