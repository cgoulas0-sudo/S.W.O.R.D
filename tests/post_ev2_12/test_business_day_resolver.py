"""POST-EV2-12.2 proof suite -- deterministic Business Day Resolver.

Pure (no PostgreSQL) proof of ``scripts/business_resolver.py``: the Stage C
resolver consumes the POST-EV2-12.1 normalized plan plus the exact dice results
and resolves one deterministic Business day. Proven: fixed + every rolled band;
Nat-1 repair (mean-vs-selector percentage and duration); Nat-20 / Nat-1
Reputation delegation; inactive zero-work; active-effect lifecycle; internal
source ordering; byproduct stock; the 20/70/10 positive split and the own ->
HQ -> uncovered Recovery waterfall; generic hierarchy fail-closed; no hidden FX;
exact copper money and sub-copper conservation; and copy isolation / failure
atomicity.

Only synthetic data is used. No real RHC Business, money, or campaign state is
created or mutated.
"""

from __future__ import annotations

import copy
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "post_ev2_12"))

import business_resolver  # noqa: E402
import business_plan  # noqa: E402
from business_plan import plan_businesses  # noqa: E402
from test_business_plan import (  # noqa: E402
    APPROVED_FUND_POLICY,
    REP_CONFIG,
    economy,
    fixed_card,
    rolled_card,
)


# ---------------------------------------------------------------------------
# Plan / roll builders
# ---------------------------------------------------------------------------


def make_plan(businesses, state=None, *, reputation=REP_CONFIG, fund_policy=APPROVED_FUND_POLICY):
    econ = economy(businesses, reputation=reputation, fund_policy=fund_policy)
    result = plan_businesses(econ, {"businesses": state or {}})
    return result["plan"]


def build_rolls(business_id, *, economic=None, severity=None, duration=None,
                selector=None, narrative=None):
    rolls = {}
    if economic is not None:
        rolls["economic"] = {"notation": "1d20", "total": economic, "rolls": [economic]}
    if narrative is not None:
        rolls["narrative_event"] = {
            "notation": "1d20", "total": narrative, "rolls": [narrative]
        }
    if severity is not None:
        rolls["repair_severity"] = {"notation": "1d6", "total": severity, "rolls": [severity]}
    if duration is not None:
        rolls["repair_duration"] = {"notation": "1d3", "total": duration, "rolls": [duration]}
    if selector is not None:
        rolls["repair_percent_selector"] = {
            "notation": "1d6", "total": selector, "rolls": [selector]
        }
    return {business_id: rolls}


def resolve(businesses, rolls, state=None, **kwargs):
    plan = make_plan(businesses, state, **kwargs)
    return business_resolver.resolve_business_day(plan, rolls, day=kwargs.get("day"))


# ---------------------------------------------------------------------------
# Proof: fixed + every approved rolled economic band
# ---------------------------------------------------------------------------


def test_fixed_revenue_resolves_exactly():
    plan = make_plan({"ledger": fixed_card(funds_enabled=False)}, fund_policy=None)
    out = business_resolver.resolve_business_day(plan, {})
    res = out["mechanical_resolutions"][0]
    # 25 sp fixed revenue, 5 sp cost -> 20 sp net = 200 cp (fixed card is sp).
    assert res["revenue_mode"] == "fixed"
    assert res["revenue_copper"] == 250
    assert res["fixed_cost_copper"] == 50
    assert res["net_copper"] == 200


@pytest.mark.parametrize(
    "total,expected_multiplier",
    [
        (2, Decimal("0.35")),
        (6, Decimal("0.75")),
        (11, Decimal("1.00")),
        (17, Decimal("1.35")),
        (20, Decimal("1.75")),
    ],
)
def test_rolled_band_revenue(total, expected_multiplier):
    # revenue_base 1000 gp -> * multiplier. Disable fund accounting for a pure
    # revenue proof. Row 20 is a Nat-20 (critical) and triggers Reputation
    # delegation, so a current reputation score must be present.
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=total)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["economic_roll_total"] == total
    assert res["revenue_copper"] == int(Decimal(1000) * expected_multiplier * 100)
    assert res["outcome"] == "economic"


# ---------------------------------------------------------------------------
# Proof: Nat-1 repair (mean percentage vs configured selector, duration)
# ---------------------------------------------------------------------------


def test_nat1_repair_uses_arithmetic_mean_percentage():
    # Moderate severity (roll 3/4): cost percent range 15..25 -> mean 20%.
    # facility_value 50000 gp -> 10000 gp repair cost = 1000000 cp.
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=1, severity=3, duration=3)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["outcome"] == "catastrophic"
    assert res["severity"] == "moderate"
    assert res["repair"]["selected_percent"] == "20"
    assert res["repair"]["repair_cost_copper"] == 1_000_000
    # moderate has duration_die 1d3 -> remaining = roll - 1.
    assert res["repair"]["duration_roll"] == 3
    assert res["repair"]["remaining_resolution_days"] == 2
    effect = out["persistent_effects_applied"][0]
    assert effect["action"] == "created"
    assert effect["remaining_resolution_days"] == 2


def test_nat1_repair_ignores_configured_selector_and_uses_mean():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["percent_selector"] = "1d6"
    card = rolled_card(funds_enabled=False, repair=repair)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    # A selector die is declared and even supplied, but Stage C must not
    # reinterpret an arbitrary die total as a percentage: severity moderate
    # (15..25) uses its mean 20%, not the rolled 4.
    rolls = build_rolls("foundry", economic=1, severity=4, duration=4, selector=4)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["repair"]["selected_percent"] == "20"
    assert res["repair"]["repair_cost_copper"] == 1_000_000


def test_nat1_catastrophic_severity_has_1d6_duration():
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=1, severity=6, duration=6)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["severity"] == "catastrophic"
    assert res["repair"]["duration_roll"] == 6
    assert res["repair"]["remaining_resolution_days"] == 5


def test_nat1_catastrophic_revenue_multiplier_applies():
    # Catastrophic severity revenue_multiplier 0.0 -> zero revenue on trigger day.
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=1, severity=6, duration=6)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["revenue_copper"] == 0


# ---------------------------------------------------------------------------
# Proof: Nat-20 / Nat-1 Reputation delegation (never duplicated formula)
# ---------------------------------------------------------------------------


def test_nat20_reputation_gain_delegates_to_resolver():
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=20)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    # REP_CONFIG: economic_nat20 -> gain (+5). 50 -> 55.
    assert res["reputation"] == {
        "before": 50, "after": 55,
        "consequence_class": "gain", "direction": "positive",
    }
    assert out["businesses"]["foundry"]["reputation"] == 55


def test_nat1_reputation_loss_delegates_to_resolver():
    card = rolled_card(funds_enabled=False)
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"reputation": 50}}, fund_policy=None
    )
    # severity roll 6 -> loss_major (-5). 50 -> 45.
    rolls = build_rolls("foundry", economic=1, severity=6, duration=6)
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    assert res["reputation"]["after"] == 45
    assert res["reputation"]["direction"] == "negative"


# ---------------------------------------------------------------------------
# Proof: inactive Business does zero work
# ---------------------------------------------------------------------------


def test_inactive_business_resolves_nothing():
    plan = make_plan(
        {"foundry": rolled_card(funds_enabled=False)},
        state={"foundry": {"active": False}},
        fund_policy=None,
    )
    out = business_resolver.resolve_business_day(plan, {})
    assert out["mechanical_resolutions"] == []
    # State is carried through unchanged for the inactive Business.
    assert out["businesses"]["foundry"] == {"active": False}


# ---------------------------------------------------------------------------
# Proof: active-effect lifecycle (applies, then decrements / removes)
# ---------------------------------------------------------------------------


def test_active_effect_applies_and_decrements():
    state = {
        "foundry": {
            "active": True,
            "effects": [
                {
                    "effect_id": "fx-1",
                    "source": "repair",
                    "revenue_multiplier": Decimal("0.5"),
                    "remaining_resolution_days": 2,
                }
            ],
        }
    }
    plan = make_plan(
        {"foundry": rolled_card(funds_enabled=False)}, state=state, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=11)  # multiplier 1.0
    out = business_resolver.resolve_business_day(plan, rolls)
    res = out["mechanical_resolutions"][0]
    # revenue_base 1000 gp * 0.5 effect = 500 gp = 50000 cp.
    assert res["revenue_copper"] == 50_000
    assert res["effects_applied"][0]["effect_id"] == "fx-1"
    kept = out["businesses"]["foundry"]["effects"]
    assert kept[0]["remaining_resolution_days"] == 1


def test_active_effect_removed_when_expired():
    state = {
        "foundry": {
            "active": True,
            "effects": [
                {
                    "effect_id": "fx-2",
                    "source": "repair",
                    "revenue_multiplier": Decimal("0.5"),
                    "remaining_resolution_days": 1,
                }
            ],
        }
    }
    plan = make_plan(
        {"foundry": rolled_card(funds_enabled=False)}, state=state, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=11)
    out = business_resolver.resolve_business_day(plan, rolls)
    # Effect applied this day, then removed (remaining hit 0).
    assert out["businesses"]["foundry"]["effects"] == []
    actions = {e["action"] for e in out["persistent_effects_applied"]}
    assert "removed" in actions


# ---------------------------------------------------------------------------
# Proof: internal-source ordering / cost = source realized revenue
# ---------------------------------------------------------------------------


def test_internal_source_cost_uses_source_realized_revenue():
    # foundry sources from mine; mine revenue resolved first.
    mine = rolled_card(name="Mine", funds_enabled=False)
    foundry = rolled_card(name="Foundry", funds_enabled=False, internal_sources=["mine"])
    plan = make_plan(
        {"mine": mine, "foundry": foundry}, fund_policy=None
    )
    rolls = {
        "mine": build_rolls("mine", economic=11)["mine"],
        "foundry": build_rolls("foundry", economic=17)["foundry"],
    }
    out = business_resolver.resolve_business_day(plan, rolls)
    by_business = {r["business"]: r for r in out["mechanical_resolutions"]}
    mine_rev = by_business["mine"]["revenue_copper"]  # 1000 * 1.0 = 100000 cp
    foundry = by_business["foundry"]
    # foundry revenue 1000 * 1.35 = 135000 cp; internal cost = mine revenue.
    assert foundry["revenue_copper"] == 135_000
    assert foundry["internal_source_cost_copper"] == mine_rev
    assert foundry["net_copper"] == 135_000 - 250 * 100 - mine_rev


# ---------------------------------------------------------------------------
# Proof: byproduct stock (independent of revenue roll)
# ---------------------------------------------------------------------------


def test_byproduct_stock_added_independently_of_revenue():
    byproduct = {
        "product": "slag",
        "source_quantity": 100,
        "waste_ratio": Decimal("0.25"),
        "yield": Decimal("0.5"),
        "disposition": "stored",
        "sold_on_production_day": False,
    }
    card = rolled_card(funds_enabled=False, byproducts=[byproduct])
    plan = make_plan(
        {"foundry": card}, state={"foundry": {"stock": {"slag": 10}}}, fund_policy=None
    )
    rolls = build_rolls("foundry", economic=11)
    out = business_resolver.resolve_business_day(plan, rolls)
    # 100 * 0.25 * 0.5 = 12.5 added to existing 10 -> 22.5.
    assert out["businesses"]["foundry"]["stock"]["slag"] == Decimal("22.5")
    res = out["mechanical_resolutions"][0]
    assert res["byproducts"][0]["quantity"] == "12.5"


def test_byproduct_unsupported_disposition_fails_closed():
    # Stage C owns only storage; any other declared disposition fails closed
    # rather than being silently treated as storage or given invented semantics.
    byproduct = {
        "product": "slag",
        "source_quantity": 100,
        "waste_ratio": Decimal("0.25"),
        "yield": Decimal("0.5"),
        "disposition": "discarded",
        "sold_on_production_day": False,
    }
    card = rolled_card(funds_enabled=False, byproducts=[byproduct])
    plan = make_plan({"foundry": card}, fund_policy=None)
    rolls = build_rolls("foundry", economic=11)
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)


# ---------------------------------------------------------------------------
# Proof: 20/70/10 positive split + own -> HQ -> uncovered waterfall
# ---------------------------------------------------------------------------


def _hq_child_economy():
    hq = fixed_card(
        name="HQ", funds_enabled=True, parent=None,
        fixed_revenue=0, fixed_daily_cost=0, currency="gp",
    )
    child = rolled_card(
        name="Foundry", funds_enabled=True, parent="hq", currency="gp",
    )
    # Balances are money in the Business currency (gp). HQ recovery 10000 gp =
    # 1000000 cp; the child's recovery is a fractional 0.5 gp = 50 cp.
    return {"hq": hq, "foundry": child}, {
        "hq": {
            "reputation": 50,
            "funds": {"main": 0, "hq_recovery": 10000, "development": 0, "recovery": 0},
        },
        "foundry": {"reputation": 50, "funds": {"development": 0, "recovery": Decimal("0.5")}},
    }


def test_positive_net_split_conserves_exactly_at_copper():
    businesses, state = _hq_child_economy()
    # foundry revenue 1000 gp * 1.0 (roll 11) = 100000 cp; cost 250 gp = 25000 cp
    # -> net 75000 cp. Split 20/70/10 = 15000 / 52500 / 7500.
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=11)["foundry"]}
    out = business_resolver.resolve_business_day(plan, rolls)
    res = [r for r in out["mechanical_resolutions"] if r["business"] == "foundry"][0]
    split = res["fund_split"]
    assert split["hq_main_copper"] + split["development_copper"] + split["recovery_copper"] == 75000
    assert split["development_copper"] == 52500
    assert split["recovery_copper"] == 7500
    # The HQ main balance is money in gp: 15000 cp -> 150 gp.
    assert out["businesses"]["hq"]["funds"]["main"] == Decimal("150")


@pytest.mark.parametrize("net,expected_sum", [(1000, 1000), (1003, 1003), (7, 7), (250000, 250000)])
def test_split_exact_largest_remainder_conservation(net, expected_sum):
    parts = business_resolver._split_exact(net, business_resolver.POSITIVE_SHARES)
    assert sum(parts) == expected_sum
    assert len(parts) == 3


def test_deficit_waterfall_own_then_hq_then_uncovered():
    businesses, state = _hq_child_economy()
    # foundry Nat-1 minor severity (roll 1/2) cost percent 5..10 -> mean 7.5% of
    # 50000 gp = 3750 gp = 375000 cp repair. Revenue (minor mult 1.0) 100000 cp -
    # 25000 cost = 75000 net positive -> split first, then repair obligation.
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=1, severity=1, duration=2)["foundry"]}
    out = business_resolver.resolve_business_day(plan, rolls, day=2)
    res = [r for r in out["mechanical_resolutions"] if r["business"] == "foundry"][0]
    foundry_funds = out["businesses"]["foundry"]["funds"]
    # Positive net 75000 cp split: own recovery 0.5 gp (50 cp) + 7500 cp = 7550 cp,
    # then the 375000 cp repair obligation draws own recovery fully (7550), then
    # the HQ recovery (367450), leaving the rest of the HQ recovery intact.
    assert foundry_funds["recovery"] == 0
    assert out["businesses"]["hq"]["funds"]["hq_recovery"] == Decimal("6325.5")
    assert res["uncovered_loss_copper"] == 0


def test_deficit_waterfall_uncovered_when_hq_insufficient():
    businesses, state = _hq_child_economy()
    # Shrink HQ recovery so the obligation cannot be fully covered: 10 gp = 1000 cp.
    state["hq"]["funds"]["hq_recovery"] = Decimal("10")
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=1, severity=6, duration=6)["foundry"]}
    out = business_resolver.resolve_business_day(plan, rolls, day=2)
    res = [r for r in out["mechanical_resolutions"] if r["business"] == "foundry"][0]
    # catastrophic repair cost 60..90 -> mean 75% of 50000 gp = 37500 gp = 3750000 cp.
    # foundry net is -25000 (revenue 0, 250 gp cost) -> obligation 3775000 cp.
    # own recovery 0.5 gp = 50 cp + HQ hq_recovery 10 gp = 1000 cp drawn; remainder
    # is uncovered.
    assert res["uncovered_loss_copper"] == 3_775_000 - 50 - 1000


# ---------------------------------------------------------------------------
# Proof: balance conversion is not fractional-copper truncation
# ---------------------------------------------------------------------------


def test_balancing_converts_currency_not_fractional_copper():
    assert business_resolver._balance_to_copper(Decimal("0.5"), "sp", "floor") == 5
    assert business_resolver._balance_to_copper(Decimal("0.05"), "sp", "floor") == 0
    assert business_resolver._balance_to_copper(Decimal("0.25"), "gp", "half_up") == 25
    assert business_resolver._copper_to_currency(755, "gp") == Decimal("7.55")
    assert business_resolver._copper_to_currency(755, "cp") == Decimal("755")


# ---------------------------------------------------------------------------
# Proof: exact JSON money preservation (never silently altered; else fail closed)
# ---------------------------------------------------------------------------


def test_json_number_preserves_exact_decimal_or_fails_closed():
    # A value that round-trips through its shortest float spelling is preserved
    # exactly (its JSON text reconstructs the same Decimal).
    for value in (Decimal("7.55"), Decimal("150"), Decimal("0.005"), Decimal("-0.1")):
        normalized = business_resolver._json_number(value)
        assert Decimal(str(normalized)) == value
    # A value that cannot round-trip exactly as a JSON number fails closed rather
    # than being silently altered.
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver._json_number(Decimal("123456789012345678.55"))


def test_json_number_rejects_non_finite():
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver._json_number(Decimal("NaN"))


# ---------------------------------------------------------------------------
# Proof: root-owned balances use the root card's rounding, not the child's
# ---------------------------------------------------------------------------


def _shared_root_economy(child_a_rounding, child_b_rounding):
    hq = fixed_card(
        name="HQ", parent=None, currency="gp", funds_enabled=True,
        fixed_revenue=0, fixed_daily_cost=0, rounding="floor",
    )
    a = rolled_card(
        name="A", parent="hq", currency="gp", revenue_base=1000,
        rounding=child_a_rounding,
    )
    b = rolled_card(
        name="B", parent="hq", currency="gp", revenue_base=300,
        rounding=child_b_rounding,
    )
    state = {
        # Sub-copper root balance: floor(0.005 gp = 0.5 cp) -> 0 cp.
        "hq": {"funds": {"main": Decimal("0.005"), "hq_recovery": 0}},
        "a": {"funds": {"development": 0, "recovery": 0}},
        "b": {"funds": {"development": 0, "recovery": 0}},
    }
    return {"hq": hq, "a": a, "b": b}, state


@pytest.mark.parametrize(
    "child_a_rounding,child_b_rounding",
    [("half_up", "floor"), ("floor", "half_up"), ("ceil", "half_even")],
)
def test_root_owned_balances_use_root_rounding(child_a_rounding, child_b_rounding):
    businesses, state = _shared_root_economy(child_a_rounding, child_b_rounding)
    plan = make_plan(businesses, state)
    rolls = {
        "a": build_rolls("a", economic=11)["a"],  # 20% share = 15000 cp
        "b": build_rolls("b", economic=11)["b"],  # 20% share = 1000 cp
    }
    out = business_resolver.resolve_business_day(plan, rolls)
    # HQ main is root-owned: floor(0.5 cp) = 0, + 15000 + 1000 = 16000 cp = 160 gp,
    # the same for every child-rounding combination (never the child's rule).
    assert out["businesses"]["hq"]["funds"]["main"] == Decimal("160")


def test_child_owned_balance_uses_child_rounding():
    businesses, state = _hq_child_economy()
    # Sub-copper fractional child recovery (gp); the child's own half_up rounding
    # (not the root's floor) governs it.
    state["foundry"]["funds"]["recovery"] = Decimal("0.005")
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=11)["foundry"]}
    out = business_resolver.resolve_business_day(plan, rolls)
    # net 75000 -> recovery += 7500; half_up(0.5 cp) = 1 -> 7501 cp = 75.01 gp.
    assert out["businesses"]["foundry"]["funds"]["recovery"] == Decimal("75.01")


# ---------------------------------------------------------------------------
# Proof: generic hierarchy fail-closed / corporation-local roots
# ---------------------------------------------------------------------------


def test_multiple_independent_corporation_roots_route_to_own_root():
    # Two independent corporations; each Business routes funds to its own root.
    hq_a = fixed_card(
        name="HQ-A", parent=None, currency="gp", funds_enabled=True,
        fixed_revenue=0, fixed_daily_cost=0,
    )
    hq_b = fixed_card(
        name="HQ-B", parent=None, currency="gp", funds_enabled=True,
        fixed_revenue=0, fixed_daily_cost=0,
    )
    child_a = rolled_card(name="A-Foundry", parent="hq_a", currency="gp")
    child_b = rolled_card(name="B-Foundry", parent="hq_b", currency="gp")
    businesses = {"hq_a": hq_a, "child_a": child_a, "hq_b": hq_b, "child_b": child_b}
    state = {
        "hq_a": {"funds": {"main": 0, "hq_recovery": 0}},
        "child_a": {"reputation": 50, "funds": {"development": 0, "recovery": 0}},
        "hq_b": {"funds": {"main": 0, "hq_recovery": 0}},
        "child_b": {"reputation": 50, "funds": {"development": 0, "recovery": 0}},
    }
    plan = make_plan(businesses, state)
    rolls = {
        "child_a": build_rolls("child_a", economic=11)["child_a"],
        "child_b": build_rolls("child_b", economic=11)["child_b"],
    }
    out = business_resolver.resolve_business_day(plan, rolls)
    # Each child's 75000 cp net sends its 15000 cp (150 gp) 20% share to its own
    # root; the two corporations never mix funds.
    assert out["businesses"]["hq_a"]["funds"]["main"] == Decimal("150")
    assert out["businesses"]["hq_b"]["funds"]["main"] == Decimal("150")


def test_parent_cycle_fails_closed():
    a = rolled_card(name="A", parent="b", currency="gp")
    b = rolled_card(name="B", parent="a", currency="gp")
    plan = make_plan({"a": a, "b": b})
    rolls = {
        "a": build_rolls("a", economic=11)["a"],
        "b": build_rolls("b", economic=11)["b"],
    }
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)


def test_broken_parent_chain_fails_closed():
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver._root_of({"a": {"parent": "missing"}}, "a")


def test_missing_hq_fund_balances_fail_closed():
    businesses, state = _hq_child_economy()
    # Remove the HQ main / hq_recovery balances.
    state["hq"]["funds"] = {}
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=11)["foundry"]}
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)


# ---------------------------------------------------------------------------
# Proof: no hidden FX
# ---------------------------------------------------------------------------


def test_internal_source_cross_currency_fails_closed():
    mine = rolled_card(name="Mine", currency="gp", funds_enabled=False)
    foundry = rolled_card(
        name="Foundry", currency="cp", funds_enabled=False, internal_sources=["mine"]
    )
    plan = make_plan({"mine": mine, "foundry": foundry}, fund_policy=None)
    rolls = {
        "mine": build_rolls("mine", economic=11)["mine"],
        "foundry": build_rolls("foundry", economic=11)["foundry"],
    }
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)


def test_fund_routing_cross_currency_fails_closed():
    businesses, state = _hq_child_economy()
    # Make the child a different currency than HQ.
    businesses["foundry"]["currency"] = "cp"
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=11)["foundry"]}
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)


def test_exact_copper_conversion_sub_copper_rounding():
    # 20.25 gp = 2025 cp exactly (no sub-copper). 20.25 sp = 202.5 cp -> rounded.
    card = fixed_card(
        funds_enabled=False, currency="sp", fixed_revenue=Decimal("20.25"),
        fixed_daily_cost=0,
    )
    plan = make_plan({"ledger": card}, fund_policy=None)
    out = business_resolver.resolve_business_day(plan, {})
    # floor rounding -> 202 cp (0.5 cp dropped, exactly below 1 cp).
    assert out["mechanical_resolutions"][0]["revenue_copper"] == 202


# ---------------------------------------------------------------------------
# Proof: narrative event is audit-only (no invented economics)
# ---------------------------------------------------------------------------


def test_narrative_event_is_audit_only():
    event = {"die": "1d20", "table": {"1": "flavor"}}
    card = rolled_card(funds_enabled=False, narrative_event=event)
    plan = make_plan({"foundry": card}, fund_policy=None)
    rolls = build_rolls("foundry", economic=11, narrative=7)
    out = business_resolver.resolve_business_day(plan, rolls)
    note = out["notes"][0]
    assert note["note"] == "narrative_event"
    # Revenue is unaffected by the narrative roll.
    assert out["mechanical_resolutions"][0]["revenue_copper"] == 100_000


# ---------------------------------------------------------------------------
# Proof: copy isolation / failure atomicity
# ---------------------------------------------------------------------------


def test_inputs_not_mutated_by_resolver():
    plan = make_plan({"foundry": rolled_card(funds_enabled=False)}, fund_policy=None)
    plan_snapshot = copy.deepcopy(plan)
    rolls = build_rolls("foundry", economic=11)
    rolls_snapshot = copy.deepcopy(rolls)
    business_resolver.resolve_business_day(plan, rolls)
    assert plan == plan_snapshot
    assert rolls == rolls_snapshot


def test_resolver_failure_does_not_partially_mutate():
    businesses, state = _hq_child_economy()
    state["hq"]["funds"] = {}  # forces fail-closed mid-resolution
    plan = make_plan(businesses, state)
    rolls = {"foundry": build_rolls("foundry", economic=11)["foundry"]}
    before = copy.deepcopy(plan)
    with pytest.raises(business_resolver.BusinessResolutionError):
        business_resolver.resolve_business_day(plan, rolls)
    # The plan argument is untouched after a failure.
    assert plan == before
