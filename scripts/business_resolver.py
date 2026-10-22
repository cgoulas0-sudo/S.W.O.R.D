#!/usr/bin/env python3
"""POST-EV2-12.2 -- Business Day Resolver + Begin Day Business consumer.

Stage C from the POST-EV2-12 Business / Economy contract. It consumes the
Stage B / POST-EV2-12.1 normalized plan (``scripts/business_plan.py``) plus the
exact dice rolls the existing POST-EV2-8 resolver (``scripts/dice_resolver.py``)
produced through the Begin Day dispatch seam, and resolves one deterministic
Business day for the complete configured Business set.

It is the resolution owner. It:

- performs the approved Business-day arithmetic exactly in copper (1 gp = 10 sp =
  100 cp), rounding only below 1 cp with each Card's declared rounding mode;
- consumes the validated Reputation config carried in the plan and delegates every
  Reputation consequence to ``scripts/reputation_resolver.py`` (POST-EV2-11.9);
  it never re-derives that formula;
- resolves the same-day internal-source cost graph (each source Business's actual
  realized revenue) deterministically over the acyclic dependency graph;
- routes positive net through the approved 20% HQ/Main, 70% Business Development,
  10% Business Recovery split, and deficit / repair obligations through the
  approved own-Recovery -> HQ-Recovery -> uncovered-loss waterfall, never drawing
  the Development Fund automatically;
- refuses any hidden FX: a money transfer that crosses an incompatible currency
  with no established conversion mechanic fails closed;
- routes each Business's funds to its own corporation root/HQ by following the
  declared parent chain (no hard-coded company name; multiple independent
  corporation roots may coexist) and fails closed on a cycle, a broken parent
  chain or a missing required root balance;
- treats existing fund balances as money in the Business currency, converts them
  to the exact copper view before any obligation arithmetic (rounding only below
  1 cp with the Card's rounding mode), and applies only the byproduct disposition
  it owns (``stored``), failing closed on any other declared disposition;
- normalizes resolver-only Decimals to exact JSON-safe numbers at the consumer
  output boundary and fails closed if a value cannot round-trip exactly;
- applies and decrements existing Business-owned duration effects only after they
  actually affect a resolved Business day, and creates a new repair effect only on
  a triggered Nat-1 with a duration die;
- produces the four Begin Day consumer audit arrays (``rng_rolls`` is built by the
  consumer from the dispatch seam) plus exactly one ``businesses`` state patch.

It creates no new runtime mutation domain, no same-save compatibility edge, no
save / SQL / runtime authority, no new planner, config, state, RNG, Reputation or
logistics surface, and no second Business consumer. It is pure: it never mutates
its caller's plan, rolls or state.
"""

from __future__ import annotations

import copy
import sys
from collections import deque
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import business_plan
import reputation_resolver

# The existing generic owners / resolvers are read-only to this Mission; this
# module imports them but modifies neither their behavior nor their files.
import dice_resolver  # noqa: F401  (the single shared RNG root, POST-EV2-8)

ROUNDING_MAP = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "floor": ROUND_FLOOR,
    "ceil": ROUND_CEILING,
}

# Money is exact. Each Card declares its currency; copper is the smallest unit.
COPPER_FACTOR = {"gp": 100, "sp": 10, "cp": 1}

# The approved positive-net fund allocation: 20% HQ/Main, 70% Business
# Development, 10% Business Recovery. The Development Fund is never auto-drawn; a
# deficit / repair obligation covers own Recovery -> HQ Recovery -> uncovered loss.
POSITIVE_SHARES = (Decimal("0.2"), Decimal("0.7"), Decimal("0.1"))


class BusinessResolutionError(Exception):
    """A fail-closed Business-day resolution / authority failure."""


def _dec(value):
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # noqa: SIM108 - explicit bool guard
        raise ValueError("expected a number, got bool")
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def _fmt_qty(value):
    """Clean, human-stable decimal string with no trailing zeros."""
    s = format(Decimal(str(value)), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _to_copper(amount, currency):
    """Exact copper view of a Card-declared money amount in its currency."""
    if currency not in COPPER_FACTOR:
        raise BusinessResolutionError(f"unknown currency: {currency!r}")
    return _dec(amount) * COPPER_FACTOR[currency]


def _round_copper(value, rounding):
    """Quantize a copper Decimal to the nearest whole copper."""
    if rounding not in ROUNDING_MAP:
        raise BusinessResolutionError(f"unknown rounding mode: {rounding!r}")
    return int(value.quantize(Decimal(1), rounding=ROUNDING_MAP[rounding]))


def _copper_to_currency(copper, currency):
    """Exact Business-currency view of an integer copper amount."""
    if currency not in COPPER_FACTOR:
        raise BusinessResolutionError(f"unknown currency: {currency!r}")
    return Decimal(copper) / COPPER_FACTOR[currency]


def _balance_to_copper(value, currency, rounding):
    """Exact copper view of an existing Business-currency fund balance.

    A stored balance is money in the Business currency, so it is converted to the
    copper view before any obligation arithmetic; rounding happens only below
    1 cp using the Card's declared rounding mode.
    """
    return _round_copper(_to_copper(value, currency), rounding)


def _json_number(value):
    """Normalize a resolver-only Decimal to a JSON-safe number without loss.

    The Begin Day / SAVE JSON path serializes with ``json.dumps``, which cannot
    emit a ``Decimal``. An integral value becomes an exact ``int``. A fractional
    value becomes a ``float`` only when its shortest round-tripping spelling
    reproduces the exact Decimal; otherwise the value cannot be preserved as a
    JSON-safe number, so resolution fails closed rather than silently altering
    money.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise BusinessResolutionError(
                f"cannot serialize a non-finite Decimal: {value!r}"
            )
        if value == value.to_integral_value():
            return int(value)
        candidate = float(value)
        if Decimal(str(candidate)) != value:
            raise BusinessResolutionError(
                f"Decimal {value!r} cannot be represented exactly as a JSON "
                "number without losing value"
            )
        return candidate
    return value


def _json_safe(value):
    """Recursively make a consumer result JSON-serializable (Decimals -> numbers)."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return _json_number(value)


def _split_exact(total, fractions):
    """Largest-remainder apportionment of an exact integer copper ``total``.

    Distributes a whole-copper total across the given exact fractional shares so
    the pieces sum to ``total`` exactly with no gameplay preference for any
    bucket; leftover copper goes to the largest fractional remainder.
    """
    total = int(total)
    quotas = [Decimal(total) * fraction for fraction in fractions]
    floors = [int(q.to_integral_value(ROUND_FLOOR)) for q in quotas]
    used = sum(floors)
    remainder = total - used
    order = sorted(
        range(len(quotas)),
        key=lambda index: (quotas[index] - floors[index], -index),
        reverse=True,
    )
    result = floors[:]
    for index in range(remainder):
        result[order[index % len(order)]] += 1
    return result


def _topo_order(businesses):
    """Deterministic topo order so each Business's realized revenue is available.

    A Business depends on every Business it names as an internal source. The
    planner has already proven the graph acyclic; the guard here is fail-closed.
    """
    indegree = {business_id: 0 for business_id in businesses}
    dependents = {business_id: [] for business_id in businesses}
    for business_id, card in businesses.items():
        for source in card.get("internal_sources", []) or []:
            if source in businesses:
                dependents[source].append(business_id)
                indegree[business_id] += 1
    queue = deque(sorted(b for b, d in indegree.items() if d == 0))
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in sorted(dependents[node]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(businesses):
        raise BusinessResolutionError("internal source graph is not acyclic")
    return order


def _root_of(businesses, business_id):
    """Follow a Business's declared parent chain to its own corporation root.

    The root is the ancestor that declares no parent. Multiple independent
    corporation roots may coexist; each Business routes its funds to its own
    root. A cycle (including a self-cycle) or a parent that does not exist fails
    closed rather than silently collapsing or inventing a hierarchy.
    """
    seen = set()
    current = business_id
    while True:
        if current in seen:
            raise BusinessResolutionError(
                f"parent hierarchy cycle detected at {current!r}"
            )
        seen.add(current)
        parent = businesses[current].get("parent")
        if parent is None:
            return current
        if parent not in businesses:
            raise BusinessResolutionError(
                f"{current!r} parent {parent!r} is unknown"
            )
        current = parent


def _find_economic_band(card, total):
    for band in card["economic_roll"]["bands"]:
        if band["min"] <= total <= band["max"]:
            return band
    raise BusinessResolutionError(f"economic roll {total} matches no band")


def _is_catastrophic(total):
    return total == 1


def _find_severity_band(card, total):
    for band in card["repair"]["severity_bands"]:
        if band["min"] <= total <= band["max"]:
            return band
    raise BusinessResolutionError(f"repair severity roll {total} matches no band")


def _find_nat1_reputation_band(card, total):
    bands = card["reputation_consequences"]["repair_nat1_severity"]
    for band in bands:
        if band["min"] <= total <= band["max"]:
            return band
    raise BusinessResolutionError(
        f"Nat-1 reputation severity roll {total} matches no band"
    )


def _roll_record(result):
    return {
        "notation": result["notation"],
        "total": result["total"],
        "rolls": list(result["rolls"]),
    }


def _active_effects(state_entry):
    """Active (remaining > 0) Business-owned duration effects."""
    effects = state_entry.get("effects") or []
    return [effect for effect in effects if effect.get("remaining_resolution_days", 0) > 0]


def _effect_multiplier(active):
    multiplier = Decimal(1)
    for effect in active:
        multiplier *= _dec(effect["revenue_multiplier"])
    return multiplier


def resolve_business_day(plan, rolls, *, day=None):
    """Resolve one deterministic Business day from a normalized plan + rolls.

    ``plan`` is the POST-EV2-12.1 normalized plan (``plan_businesses`` output).
    ``rolls`` maps business id -> the dice results the Begin Day dispatch seam
    produced, keyed by purpose (``economic``, ``narrative_event``,
    ``repair_severity``, ``repair_duration``).

    Returns ``{"businesses", "mechanical_resolutions", "persistent_effects_applied",
    "notes"}``. ``businesses`` is the updated ``live_status.businesses`` map for the
    consumer's single ``state_patch``. Never mutates ``plan`` or ``rolls``.
    """
    businesses = plan["businesses"]
    state = plan["state"]["businesses"]
    reputation_config = plan.get("reputation")

    # The returned state is a deep copy; the input plan / state is never mutated.
    new_state = copy.deepcopy(state)

    order = _topo_order(businesses)

    # First pass: realized revenue (integer copper) for every active Business, so
    # internal-source costs can reference it deterministically.
    realized_revenue = {}

    mechanical_resolutions = []
    persistent_effects_applied = []
    notes = []

    for business_id in order:
        card = businesses[business_id]
        state_entry = state.get(business_id, {})
        if state_entry.get("active", True) is False:
            # Inactive: no rolls, no economics, no effect decrement. State copied.
            continue

        currency = card["currency"]
        rounding = card["rounding"]
        active = _active_effects(state_entry)
        effect_mult = _effect_multiplier(active)
        created_effects = []

        entry_rolls = rolls.get(business_id, {})
        revenue_mode = card["revenue_mode"]

        resolution = {
            "business": business_id,
            "name": card["name"],
            "currency": currency,
            "revenue_mode": revenue_mode,
            "active": True,
            "effects_applied": [
                {
                    "effect_id": effect["effect_id"],
                    "revenue_multiplier": effect["revenue_multiplier"],
                }
                for effect in active
            ],
        }

        # --- Revenue --------------------------------------------------------
        if revenue_mode == "rolled":
            econ = entry_rolls.get("economic")
            if econ is None:
                raise BusinessResolutionError(
                    f"{business_id} is active and rolled but has no economic roll"
                )
            econ_total = econ["total"]
            resolution["economic_roll_total"] = econ_total
            if _is_catastrophic(econ_total):
                resolution["outcome"] = "catastrophic"
                severity = entry_rolls.get("repair_severity")
                if severity is None:
                    raise BusinessResolutionError(
                        f"{business_id} Nat-1 has no repair severity roll"
                    )
                severity_band = _find_severity_band(card, severity["total"])
                daily_multiplier = _dec(severity_band["revenue_multiplier"])
                resolution["severity"] = severity_band["severity"]
            else:
                econ_band = _find_economic_band(card, econ_total)
                daily_multiplier = _dec(econ_band["multiplier"])
                resolution["outcome"] = "economic"
        else:
            daily_multiplier = Decimal(1)
            resolution["economic_roll_total"] = None
            resolution["outcome"] = "fixed"

        revenue_base_copper = _to_copper(
            card["revenue_base"] if revenue_mode == "rolled" else card["fixed_revenue"],
            currency,
        )
        revenue_gross = revenue_base_copper * daily_multiplier * effect_mult
        revenue_int = _round_copper(revenue_gross, rounding)
        resolution["revenue_copper"] = revenue_int
        realized_revenue[business_id] = revenue_int

        # --- Internal-source cost (same-day realized source revenue) ----------
        internal_cost = 0
        internal_breakdown = []
        for source in card.get("internal_sources", []) or []:
            if source not in businesses:
                raise BusinessResolutionError(
                    f"{business_id} internal source {source!r} is unknown"
                )
            if source not in realized_revenue:
                raise BusinessResolutionError(
                    f"{business_id} internal source {source!r} did not resolve"
                )
            if businesses[source]["currency"] != currency:
                raise BusinessResolutionError(
                    f"{business_id} internal source {source!r} crosses currencies "
                    "with no FX mechanic"
                )
            source_revenue = realized_revenue[source]
            internal_cost += source_revenue
            internal_breakdown.append({"source": source, "cost_copper": source_revenue})
        resolution["internal_source_cost_copper"] = internal_cost
        resolution["internal_sources"] = internal_breakdown

        fixed_cost_int = _round_copper(
            _to_copper(card["fixed_daily_cost"], currency), rounding
        )
        resolution["fixed_cost_copper"] = fixed_cost_int

        net = revenue_int - fixed_cost_int - internal_cost
        resolution["net_copper"] = net

        # --- Byproduct stock (independent of the revenue roll) ----------------
        byproduct_entries = []
        for byproduct in card.get("byproducts", []) or []:
            product = byproduct["product"]
            disposition = byproduct["disposition"]
            # Stage C owns only storage. Any other declared disposition is
            # deferred to a later owner and fails closed rather than being
            # silently treated as storage or given invented semantics here.
            if disposition != "stored":
                raise BusinessResolutionError(
                    f"{business_id} byproduct {product!r} declares disposition "
                    f"{disposition!r}; Stage C owns only 'stored'"
                )
            quantity = (
                _dec(byproduct["source_quantity"])
                * _dec(byproduct["waste_ratio"])
                * _dec(byproduct["yield"])
            )
            stock = new_state.setdefault(business_id, {}).setdefault("stock", {})
            stock[product] = _dec(stock.get(product, 0)) + quantity
            byproduct_entries.append(
                {
                    "product": product,
                    "disposition": disposition,
                    "quantity": _fmt_qty(quantity),
                }
            )
        resolution["byproducts"] = byproduct_entries

        # --- Repair (Nat-1 only) -------------------------------------------
        repair_info = None
        repair_cost = 0
        if revenue_mode == "rolled" and _is_catastrophic(econ_total):
            severity_band = _find_severity_band(card, entry_rolls["repair_severity"]["total"])
            # Stage C uses the arithmetic mean of the approved severity cost
            # range as the selected repair percentage. A future authored/random
            # selector mechanic remains a later owner; Stage C must not
            # reinterpret an arbitrary selector die total as a percentage.
            selected_percent = (
                _dec(severity_band["cost_percent_min"])
                + _dec(severity_band["cost_percent_max"])
            ) / 2
            facility_copper = _to_copper(card["facility_value"], currency)
            repair_cost = _round_copper(
                facility_copper * selected_percent / Decimal(100), rounding
            )
            repair_info = {
                "severity": severity_band["severity"],
                "selected_percent": str(selected_percent),
                "repair_cost_copper": repair_cost,
            }
            duration_die = severity_band.get("duration_die")
            if duration_die is not None:
                duration_roll = entry_rolls["repair_duration"]["total"]
                remaining = duration_roll - 1
                repair_info["duration_roll"] = duration_roll
                repair_info["remaining_resolution_days"] = remaining
                if remaining > 0:
                    effect_id = "repair:%s:%s" % (
                        business_id,
                        day if day is not None else "x",
                    )
                    created = {
                        "effect_id": effect_id,
                        "source": "repair",
                        "revenue_multiplier": _dec(severity_band["revenue_multiplier"]),
                        "remaining_resolution_days": remaining,
                    }
                    created_effects.append(created)
                    persistent_effects_applied.append(
                        {
                            "business": business_id,
                            "effect_id": effect_id,
                            "action": "created",
                            "source": "repair",
                            "revenue_multiplier": str(
                                severity_band["revenue_multiplier"]
                            ),
                            "remaining_resolution_days": remaining,
                        }
                    )
            resolution["repair"] = repair_info

        # --- Reputation (Nat-20 gain / Nat-1 severity loss) ------------------
        reputation_before = state_entry.get("reputation")
        reputation_after = reputation_before
        if reputation_config is not None and revenue_mode == "rolled":
            if econ_total == 20:
                consequence = card["reputation_consequences"]["economic_nat20"]
                if reputation_before is None:
                    raise BusinessResolutionError(
                        f"{business_id} Nat-20 with no current reputation score"
                    )
                outcome = reputation_resolver.resolve_reputation(
                    {
                        "current_score": reputation_before,
                        "consequence_class": consequence["consequence_class"],
                        "direction": consequence["direction"],
                    },
                    reputation_config,
                )
                reputation_after = outcome["resulting_score"]
                resolution["reputation"] = {
                    "before": reputation_before,
                    "after": reputation_after,
                    "consequence_class": consequence["consequence_class"],
                    "direction": consequence["direction"],
                }
            elif _is_catastrophic(econ_total):
                nat1_band = _find_nat1_reputation_band(
                    card, entry_rolls["repair_severity"]["total"]
                )
                if reputation_before is None:
                    raise BusinessResolutionError(
                        f"{business_id} Nat-1 with no current reputation score"
                    )
                outcome = reputation_resolver.resolve_reputation(
                    {
                        "current_score": reputation_before,
                        "consequence_class": nat1_band["consequence_class"],
                        "direction": nat1_band["direction"],
                    },
                    reputation_config,
                )
                reputation_after = outcome["resulting_score"]
                resolution["reputation"] = {
                    "before": reputation_before,
                    "after": reputation_after,
                    "consequence_class": nat1_band["consequence_class"],
                    "direction": nat1_band["direction"],
                }
        if reputation_after is not None:
            new_state.setdefault(business_id, {})["reputation"] = reputation_after

        # --- Fund accounting (only when funds_enabled) -----------------------
        if card["funds_enabled"]:
            # Each Business routes funds to its own corporation root/HQ; multiple
            # independent corporation roots may coexist. The parent chain, its
            # cycles and the required root balances are fail-closed.
            hq = _root_of(businesses, business_id)
            root_card = businesses[hq]
            if root_card["currency"] != currency:
                raise BusinessResolutionError(
                    "fund routing crosses currencies with no FX mechanic"
                )
            # Child-owned balances use the child's declared rounding; the root's
            # own main/hq_recovery balances use the root Card's declared rounding
            # so the outcome never depends on which child was processed.
            root_rounding = root_card["rounding"]
            funds = new_state.setdefault(business_id, {}).setdefault("funds", {})
            # Existing balances are money in the Business currency; convert to
            # the exact copper view before obligation arithmetic so no gp/sp
            # balance is mistaken for fractional copper.
            if net > 0:
                hq_funds = new_state.setdefault(hq, {}).setdefault("funds", {})
                if "main" not in hq_funds:
                    raise BusinessResolutionError(
                        "the corporation root (HQ) fund balance 'main' is required"
                    )
                split = _split_exact(net, POSITIVE_SHARES)
                funds["development"] = _copper_to_currency(
                    _balance_to_copper(
                        funds.get("development", 0), currency, rounding
                    )
                    + split[1],
                    currency,
                )
                funds["recovery"] = _copper_to_currency(
                    _balance_to_copper(funds.get("recovery", 0), currency, rounding)
                    + split[2],
                    currency,
                )
                hq_funds["main"] = _copper_to_currency(
                    _balance_to_copper(
                        hq_funds.get("main", 0), currency, root_rounding
                    )
                    + split[0],
                    currency,
                )
                resolution["fund_split"] = {
                    "hq_main_copper": split[0],
                    "development_copper": split[1],
                    "recovery_copper": split[2],
                }
            # Deficit / repair waterfall: own Recovery -> HQ Recovery -> uncovered.
            obligation = max(0, -net) + repair_cost
            resolution["obligation_copper"] = obligation
            if obligation > 0:
                own_recovery_copper = _balance_to_copper(
                    funds.get("recovery", 0), currency, rounding
                )
                take = min(obligation, own_recovery_copper)
                funds["recovery"] = _copper_to_currency(
                    own_recovery_copper - take, currency
                )
                obligation -= take
                if obligation > 0:
                    hq_funds = new_state.setdefault(hq, {}).setdefault("funds", {})
                    if "hq_recovery" not in hq_funds:
                        raise BusinessResolutionError(
                            "the corporation root (HQ) fund balance "
                            "'hq_recovery' is required"
                        )
                    hq_recovery_copper = _balance_to_copper(
                        hq_funds["hq_recovery"], currency, root_rounding
                    )
                    take2 = min(obligation, hq_recovery_copper)
                    hq_funds["hq_recovery"] = _copper_to_currency(
                        hq_recovery_copper - take2, currency
                    )
                    obligation -= take2
                uncovered = obligation
                resolution["uncovered_loss_copper"] = uncovered
                if uncovered:
                    notes.append(
                        {
                            "business": business_id,
                            "note": "uncovered_loss",
                            "copper": uncovered,
                        }
                    )

        # --- Narrative event: audit only, no invented economics ---------------
        narrative = entry_rolls.get("narrative_event")
        if narrative is not None:
            notes.append(
                {
                    "business": business_id,
                    "note": "narrative_event",
                    "roll_total": narrative["total"],
                }
            )
            resolution["narrative_event_total"] = narrative["total"]

        # --- Effect lifecycle: decrement / remove after a resolved day -------
        # Build the final effect list from the original effects plus any repair
        # effect created today (which applies starting the NEXT day, never the
        # trigger day), decrementing only those that actually affected today.
        original_effects = state_entry.get("effects") or []
        final_effects = []
        for effect in original_effects:
            if effect.get("remaining_resolution_days", 0) > 0:
                new_remaining = effect["remaining_resolution_days"] - 1
                if new_remaining > 0:
                    final_effects.append(
                        {**effect, "remaining_resolution_days": new_remaining}
                    )
                    persistent_effects_applied.append(
                        {
                            "business": business_id,
                            "effect_id": effect["effect_id"],
                            "action": "decremented",
                            "remaining_resolution_days": new_remaining,
                        }
                    )
                else:
                    persistent_effects_applied.append(
                        {
                            "business": business_id,
                            "effect_id": effect["effect_id"],
                            "action": "removed",
                        }
                    )
        final_effects.extend(created_effects)
        if original_effects or created_effects:
            new_state.setdefault(business_id, {})["effects"] = final_effects

        mechanical_resolutions.append(resolution)

    return {
        "businesses": new_state,
        "mechanical_resolutions": mechanical_resolutions,
        "persistent_effects_applied": persistent_effects_applied,
        "notes": notes,
    }


class BusinessDayConsumer:
    """The exactly-one Begin Day Business consumer for POST-EV2-12.2.

    It covers the complete configured Business set. It uses only ``dispatch.roll``
    (the POST-EV2-8 seam), executes unconditional economic / narrative rolls
    first, then only the triggered conditional (Nat-1) rolls, calls the
    deterministic resolver, and returns the four audit arrays plus exactly one
    ``businesses`` state patch. It must not be modified to touch ``begin_day.py``
    or to spawn per-Business consumers.
    """

    consumer_id = "post-ev2-12-business-day"

    def __init__(self, economy, state):
        # The consumer holds its own copy of the economy and the current Business
        # state so a retry rehydration (which never reruns the consumer) cannot
        # alias or mutate the caller's input.
        self._economy = copy.deepcopy(economy)
        self._state = copy.deepcopy(state)

    def resolve(self, context, dispatch):
        planned = business_plan.plan_businesses(
            self._economy, {"businesses": self._state}
        )
        plan = planned["plan"]
        manifest = planned["manifest"]
        businesses = plan["businesses"]
        state = plan["state"]["businesses"]
        day = context.get("day")

        by_business = {}
        for request in manifest["requests"]:
            by_business.setdefault(request["business"], []).append(request)

        def is_active(business_id):
            return state.get(business_id, {}).get("active", True)

        rolls = {}
        rng_rolls = []

        # Pass 1 -- unconditional economic + narrative rolls only.
        for business_id in sorted(by_business):
            if not is_active(business_id):
                continue
            for request in by_business[business_id]:
                if request["conditional"]:
                    continue
                if request["purpose"] in ("economic", "narrative_event"):
                    resolved = dispatch.roll(
                        {"notation": request["notation"]}, source=business_id
                    )
                    rolls.setdefault(business_id, {})[request["purpose"]] = _roll_record(
                        resolved
                    )
                    rng_rolls.append(
                        {
                            "notation": request["notation"],
                            "total": resolved["total"],
                            "source": business_id,
                        }
                    )

        # Pass 2 -- triggered conditional (Nat-1) rolls only.
        for business_id in sorted(by_business):
            if not is_active(business_id):
                continue
            card = businesses[business_id]
            if card["revenue_mode"] != "rolled":
                continue
            economic = rolls.get(business_id, {}).get("economic")
            if economic is None or economic["total"] != 1:
                continue
            severity_request = next(
                r for r in by_business[business_id] if r["purpose"] == "repair_severity"
            )
            severity_resolved = dispatch.roll(
                {"notation": severity_request["notation"]}, source=business_id
            )
            rolls[business_id]["repair_severity"] = _roll_record(severity_resolved)
            rng_rolls.append(
                {
                    "notation": severity_request["notation"],
                    "total": severity_resolved["total"],
                    "source": business_id,
                }
            )
            severity_band = _find_severity_band(card, severity_resolved["total"])
            if severity_band.get("duration_die") is not None:
                duration_request = next(
                    r
                    for r in by_business[business_id]
                    if r["purpose"] == "repair_duration"
                    and r["notation"] == severity_band["duration_die"]
                )
                duration_resolved = dispatch.roll(
                    {"notation": duration_request["notation"]}, source=business_id
                )
                rolls[business_id]["repair_duration"] = _roll_record(duration_resolved)
                rng_rolls.append(
                    {
                        "notation": duration_request["notation"],
                        "total": duration_resolved["total"],
                        "source": business_id,
                    }
                )

        resolved = resolve_business_day(plan, rolls, day=day)

        # Normalize every resolver-only Decimal at this output boundary so the
        # existing Begin Day / SAVE JSON path (``json.dumps``) can serialize the
        # audit arrays and the single ``businesses`` state patch.
        return _json_safe(
            {
                "rng_rolls": rng_rolls,
                "mechanical_resolutions": resolved["mechanical_resolutions"],
                "persistent_effects_applied": resolved[
                    "persistent_effects_applied"
                ],
                "notes": resolved["notes"],
                "state_patch": {"businesses": resolved["businesses"]},
            }
        )


if __name__ == "__main__":  # pragma: no cover - library entry point
    sys.exit(0)
