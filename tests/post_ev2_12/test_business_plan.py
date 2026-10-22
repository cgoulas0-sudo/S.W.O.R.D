import copy
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import business_plan  # noqa: E402
from business_plan import plan_businesses  # noqa: E402
from reputation_resolver import resolve_reputation  # noqa: E402

TEMPLATE_PATH = ROOT / "config" / "ECONOMY_TEMPLATE.json"

# A Reputation primitive config whose scale can represent the approved
# Natural-20 gain (+5) and the Natural-1 severity totals (-3/-4/-5).
REP_CONFIG = {
    "score_bounds": {"min": 0, "max": 100},
    "consequence_scale": {
        "gain": 5,
        "loss_minor": 3,
        "loss_moderate": 4,
        "loss_major": 5,
    },
    "high_standing": {
        "threshold": 80,
        "positive_gain_multiplier": 0.5,
        "rounding": "floor",
    },
    "tiers": [
        {"name": "wary", "min": 0, "max": 29},
        {"name": "neutral", "min": 30, "max": 59},
        {"name": "recognized", "min": 60, "max": 79},
        {"name": "institutional", "min": 80, "max": 94},
        {"name": "key_civic_link", "min": 95, "max": 99},
        {"name": "legendary", "min": 100, "max": 100},
    ],
}

# The exact approved fund policy declaration: 20/70/10 positive allocation,
# own-Recovery -> HQ-Recovery -> uncovered-loss waterfall, no automatic
# Development draw.
APPROVED_FUND_POLICY = {
    "enabled": True,
    "default_positive_profit_allocation": {
        "hq_share": 0.2,
        "development_share": 0.7,
        "recovery_share": 0.1,
    },
    "recovery_waterfall": ["own_recovery", "hq_recovery", "uncovered_loss"],
    "development_fund_auto_draw": False,
}


def rolled_card(**overrides):
    card = {
        "name": "Synthetic Foundry",
        "currency": "gp",
        "precision": 2,
        "rounding": "half_up",
        "revenue_mode": "rolled",
        "revenue_base": 1000,
        "facility_value": 50000,
        "fixed_daily_cost": 250,
        "funds_enabled": True,
        "parent": None,
        "subsidiaries": [],
        "economic_roll": {
            "die": "1d20",
            "bands": [
                {"min": 1, "max": 1, "outcome": "catastrophic"},
                {"min": 2, "max": 5, "multiplier": 0.35},
                {"min": 6, "max": 10, "multiplier": 0.75},
                {"min": 11, "max": 16, "multiplier": 1.00},
                {"min": 17, "max": 19, "multiplier": 1.35},
                {"min": 20, "max": 20, "multiplier": 1.75},
            ],
        },
        "repair": {
            "severity_die": "1d6",
            "severity_bands": [
                {
                    "min": 1,
                    "max": 2,
                    "severity": "minor",
                    "cost_percent_min": 5,
                    "cost_percent_max": 10,
                    "revenue_multiplier": 1.0,
                    "duration_die": None,
                },
                {
                    "min": 3,
                    "max": 4,
                    "severity": "moderate",
                    "cost_percent_min": 15,
                    "cost_percent_max": 25,
                    "revenue_multiplier": 0.70,
                    "duration_die": "1d3",
                },
                {
                    "min": 5,
                    "max": 5,
                    "severity": "serious",
                    "cost_percent_min": 30,
                    "cost_percent_max": 50,
                    "revenue_multiplier": 0.50,
                    "duration_die": "1d3",
                },
                {
                    "min": 6,
                    "max": 6,
                    "severity": "catastrophic",
                    "cost_percent_min": 60,
                    "cost_percent_max": 90,
                    "revenue_multiplier": 0.0,
                    "duration_die": "1d6",
                },
            ],
        },
        "reputation_consequences": {
            "economic_nat20": {"consequence_class": "gain", "direction": "positive"},
            "repair_nat1_severity": [
                {"min": 1, "max": 3, "consequence_class": "loss_minor", "direction": "negative"},
                {"min": 4, "max": 5, "consequence_class": "loss_moderate", "direction": "negative"},
                {"min": 6, "max": 6, "consequence_class": "loss_major", "direction": "negative"},
            ],
        },
        "internal_sources": [],
        "byproducts": [],
    }
    card.update(overrides)
    return card


def fixed_card(**overrides):
    card = {
        "name": "Synthetic Ledger",
        "currency": "sp",
        "precision": 0,
        "rounding": "floor",
        "revenue_mode": "fixed",
        "fixed_revenue": 25,
        "fixed_daily_cost": 5,
        "funds_enabled": False,
        "internal_sources": [],
        "byproducts": [],
    }
    card.update(overrides)
    return card


_DEFAULT_FUND_POLICY = object()


def economy(businesses, reputation=REP_CONFIG, fund_policy=_DEFAULT_FUND_POLICY):
    econ = {
        "schema_version": 1,
        "status": "instantiated_for_test",
        "reputation": copy.deepcopy(reputation),
        "business_units": copy.deepcopy(businesses),
    }
    if fund_policy is _DEFAULT_FUND_POLICY:
        fund_policy = APPROVED_FUND_POLICY
    if fund_policy is not None:
        econ["fund_policy"] = copy.deepcopy(fund_policy)
    return econ


# An economy file whose authored decimal literal is not exactly representable as
# a binary float; the planner must retain the literal, not the float approximation.
AUTHORED_DECIMAL_ECONOMY = """
{
  "schema_version": 1,
  "reputation": null,
  "business_units": {
    "ledger": {
      "name": "Synthetic Ledger",
      "currency": "sp",
      "precision": 0,
      "rounding": "floor",
      "revenue_mode": "fixed",
      "fixed_revenue": 0.10000000000000001,
      "fixed_daily_cost": 1,
      "funds_enabled": false,
      "internal_sources": [],
      "byproducts": []
    }
  }
}
"""


def requests_for(result, business_id, purpose):
    return [
        req
        for req in result["manifest"]["requests"]
        if req["business"] == business_id and req["purpose"] == purpose
    ]


# --- Proof 1: two Business shapes share one generic planner -------------------


def test_two_business_shapes_share_one_planner():
    result = plan_businesses(
        economy({"foundry": rolled_card(), "ledger": fixed_card()})
    )
    assert set(result["plan"]["businesses"]) == {"foundry", "ledger"}
    assert result["plan"]["plan_version"] == 4
    assert result["manifest"]["manifest_version"] == 1


def test_rolled_business_carries_revenue_base_and_fixed_daily_cost():
    result = plan_businesses(economy({"foundry": rolled_card()}))
    foundry = result["plan"]["businesses"]["foundry"]
    assert foundry["revenue_base"] == 1000
    assert foundry["fixed_daily_cost"] == 250
    assert foundry["funds_enabled"] is True
    rolled = requests_for(result, "foundry", "economic")
    assert len(rolled) == 1
    assert rolled[0]["notation"] == "1d20"
    assert rolled[0]["conditional"] is False


# --- Proof 2: fixed-revenue Business emits no economic roll -------------------


def test_fixed_business_carries_fixed_revenue_and_fixed_daily_cost():
    result = plan_businesses(economy({"ledger": fixed_card()}))
    ledger = result["plan"]["businesses"]["ledger"]
    assert ledger["fixed_revenue"] == 25
    assert ledger["fixed_daily_cost"] == 5
    assert requests_for(result, "ledger", "economic") == []


def test_missing_fixed_daily_cost_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(fixed_daily_cost=None)}))


def test_negative_fixed_daily_cost_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(fixed_daily_cost=-1)}))


def test_missing_revenue_base_fails_closed_for_rolled():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(revenue_base=None)}))


# --- Proof: repair-cost basis (facility_value) --------------------------------


def test_rolled_business_requires_facility_value():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(facility_value=None)}))


def test_rolled_business_preserves_facility_value():
    result = plan_businesses(economy({"foundry": rolled_card(facility_value=50000)}))
    assert result["plan"]["businesses"]["foundry"]["facility_value"] == 50000


def test_negative_facility_value_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(facility_value=-1)}))


@pytest.mark.parametrize("value", [True, False, "50000"])
def test_non_number_facility_value_fails_closed(value):
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(facility_value=value)}))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_facility_value_fails_closed(value):
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(facility_value=value)}))


def test_facility_value_preserved_exactly():
    econ = economy({"foundry": rolled_card()})
    econ["business_units"]["foundry"]["facility_value"] = Decimal("12345.678901234567")
    result = plan_businesses(econ)
    assert result["plan"]["businesses"]["foundry"]["facility_value"] == Decimal(
        "12345.678901234567"
    )


def test_facility_value_survives_cli_serialization(tmp_path, capsys):
    econ = economy({"foundry": rolled_card()})
    econ["business_units"]["foundry"]["facility_value"] = Decimal("12345.678901234567")
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(business_plan._dumps_exact(econ), encoding="utf-8")
    assert business_plan.main([str(econ_path)]) == 0
    out = capsys.readouterr().out
    assert "12345.678901234567" in out
    emitted = json.loads(out, parse_float=Decimal)
    assert emitted["plan"]["businesses"]["foundry"]["facility_value"] == Decimal(
        "12345.678901234567"
    )


def test_fixed_business_without_repair_omits_facility_value():
    result = plan_businesses(economy({"ledger": fixed_card()}))
    assert "facility_value" not in result["plan"]["businesses"]["ledger"]


def test_fixed_business_rejects_facility_value():
    with pytest.raises(ValueError):
        plan_businesses(economy({"ledger": fixed_card(facility_value=1000)}))


def test_fixed_business_rejects_explicit_null_facility_value():
    # The repair-only key is rejected by presence; an explicit null is still a
    # declared repair-cost basis and must not be silently dropped.
    with pytest.raises(ValueError):
        plan_businesses(economy({"ledger": fixed_card(facility_value=None)}))


# --- Proof 3: active/disabled state is distinct from funds-enabled ------------


@pytest.mark.parametrize(
    "active,funds_enabled",
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_active_state_distinct_from_funds_enabled(active, funds_enabled):
    result = plan_businesses(
        economy({"foundry": rolled_card(funds_enabled=funds_enabled)}),
        {"businesses": {"foundry": {"active": active}}},
    )
    assert result["plan"]["businesses"]["foundry"]["funds_enabled"] is funds_enabled


def test_active_must_be_boolean():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card()}),
            {"businesses": {"foundry": {"active": "yes"}}},
        )


def test_funds_enabled_must_be_boolean():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(funds_enabled="yes")}))


def test_inactive_business_emits_no_daily_requests():
    result = plan_businesses(
        economy({"foundry": rolled_card()}),
        {"businesses": {"foundry": {"active": False}}},
    )
    assert result["manifest"]["requests"] == []
    assert requests_for(result, "foundry", "economic") == []
    assert requests_for(result, "foundry", "repair_severity") == []
    assert requests_for(result, "foundry", "narrative_event") == []


def test_inactive_business_does_not_suppress_other_active_businesses():
    economy_ = economy(
        {
            "foundry": rolled_card(),
            "couldry": rolled_card(internal_sources=["foundry"]),
        }
    )
    result = plan_businesses(
        economy_,
        {"businesses": {"foundry": {"active": False}, "couldry": {"active": True}}},
    )
    assert requests_for(result, "foundry", "economic") == []
    active = requests_for(result, "couldry", "economic")
    assert len(active) == 1
    assert active[0]["notation"] == "1d20"


def test_missing_active_state_defaults_to_resolving():
    result = plan_businesses(
        economy({"foundry": rolled_card()}),
        {"businesses": {"foundry": {"reputation": 50}}},
    )
    assert len(requests_for(result, "foundry", "economic")) == 1


def test_inactive_business_ignores_funds_enabled():
    # active:false suppresses daily rolls, funds_enabled is a distinct fact.
    result = plan_businesses(
        economy({"foundry": rolled_card(funds_enabled=True)}),
        {"businesses": {"foundry": {"active": False}}},
    )
    assert result["manifest"]["requests"] == []
    assert result["plan"]["businesses"]["foundry"]["funds_enabled"] is True


# --- Proof 4: fund policy declaration, zero allocation ------------------------


def test_fund_policy_represents_approved_allocation():
    result = plan_businesses(
        economy({"foundry": rolled_card()}, fund_policy=APPROVED_FUND_POLICY)
    )
    # The validated policy is retained in the normalized plan, and the planner
    # still performs zero allocation.
    retained = result["plan"]["fund_policy"]
    assert retained["default_positive_profit_allocation"] == {
        "hq_share": 0.2,
        "development_share": 0.7,
        "recovery_share": 0.1,
    }
    assert retained["recovery_waterfall"] == [
        "own_recovery",
        "hq_recovery",
        "uncovered_loss",
    ]
    assert retained["development_fund_auto_draw"] is False
    assert "funds" not in result["plan"]


def test_fund_policy_required_when_any_business_funds_enabled():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, fund_policy=None))


def test_fund_policy_optional_when_no_business_funds_enabled():
    result = plan_businesses(economy({"ledger": fixed_card()}, fund_policy=None))
    assert result["plan"]["fund_policy"] is None


def test_fund_policy_rejects_wrong_shares():
    policy = copy.deepcopy(APPROVED_FUND_POLICY)
    policy["default_positive_profit_allocation"]["hq_share"] = 0.5
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, fund_policy=policy))


def test_fund_policy_rejects_wrong_waterfall():
    policy = copy.deepcopy(APPROVED_FUND_POLICY)
    policy["recovery_waterfall"] = ["hq_recovery", "own_recovery", "uncovered_loss"]
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, fund_policy=policy))


def test_fund_policy_rejects_development_auto_draw():
    policy = copy.deepcopy(APPROVED_FUND_POLICY)
    policy["development_fund_auto_draw"] = True
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, fund_policy=policy))


def test_fund_policy_rejects_missing_allocation():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card()}, fund_policy={"enabled": True})
        )


# --- Proof 5: current Business-state contract --------------------------------


def test_state_contract_represents_balances_stock_and_effects():
    state = {
        "businesses": {
            "foundry": {
                "active": True,
                "reputation": 50,
                "funds": {"development": 123.45, "recovery": 67.8},
                "stock": {"slag": 12},
                "effects": [
                    {
                        "effect_id": "fx-1",
                        "source": "repair",
                        "revenue_multiplier": 0.5,
                        "remaining_resolution_days": 2,
                    }
                ],
            }
        }
    }
    result = plan_businesses(economy({"foundry": rolled_card()}), state)
    assert result["plan"]["businesses"]["foundry"]["name"] == "Synthetic Foundry"


def test_validated_state_carried_into_plan():
    state = {
        "businesses": {
            "foundry": {
                "active": True,
                "reputation": 50,
                "funds": {"development": 123.45, "recovery": 67.8},
                "stock": {"slag": 12},
                "effects": [
                    {
                        "effect_id": "fx-1",
                        "source": "repair",
                        "revenue_multiplier": 0.5,
                        "remaining_resolution_days": 2,
                    }
                ],
            }
        }
    }
    result = plan_businesses(economy({"foundry": rolled_card()}), state)
    plan_state = result["plan"]["state"]["businesses"]["foundry"]
    assert plan_state["active"] is True
    assert plan_state["reputation"] == 50
    assert plan_state["funds"] == {"development": 123.45, "recovery": 67.8}
    assert plan_state["stock"] == {"slag": 12}
    assert plan_state["effects"][0]["effect_id"] == "fx-1"
    assert plan_state["effects"][0]["remaining_resolution_days"] == 2


def test_plan_state_is_copy_isolated_from_input():
    state = {"businesses": {"foundry": {"active": True, "funds": {"development": 1}}}}
    result = plan_businesses(economy({"foundry": rolled_card()}), state)
    result["plan"]["state"]["businesses"]["foundry"]["funds"]["development"] = 999
    assert state["businesses"]["foundry"]["funds"]["development"] == 1


def test_empty_state_carries_empty_business_map():
    result = plan_businesses(economy({"foundry": rolled_card()}), {"businesses": {}})
    assert result["plan"]["state"] == {"businesses": {}}


def test_state_reputation_bounds_fail_closed():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card()}),
            {"businesses": {"foundry": {"reputation": 101}}},
        )


def test_state_negative_fund_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card()}),
            {"businesses": {"foundry": {"funds": {"recovery": -1}}}},
        )


def test_state_negative_remaining_days_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card()}),
            {
                "businesses": {
                    "foundry": {
                        "effects": [
                            {
                                "effect_id": "fx",
                                "source": "repair",
                                "revenue_multiplier": 1,
                                "remaining_resolution_days": -1,
                            }
                        ]
                    }
                }
            },
        )


# --- Proof 6: same-day internal source-cost chain -----------------------------


def test_internal_sources_validate():
    businesses = {
        "transport": fixed_card(internal_sources=["farm", "fishery"]),
        "farm": rolled_card(),
        "fishery": rolled_card(),
    }
    result = plan_businesses(economy(businesses))
    assert result["plan"]["businesses"]["transport"]["internal_sources"] == [
        "farm",
        "fishery",
    ]


def test_dangling_internal_source_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"transport": fixed_card(internal_sources=["ghost"])})
        )


def test_self_internal_source_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"transport": fixed_card(internal_sources=["transport"])})
        )


def test_cyclic_internal_sources_fail_closed():
    businesses = {
        "a": fixed_card(internal_sources=["b"]),
        "b": fixed_card(internal_sources=["a"]),
    }
    with pytest.raises(ValueError):
        plan_businesses(economy(businesses))


def test_negotiated_supplier_price_is_not_part_of_plan():
    # The rejected Stage B negotiated-price surface is dropped, not preserved.
    result = plan_businesses(economy({"foundry": rolled_card()}))
    assert "suppliers" not in result["plan"]
    assert "supplier_agreements" not in result["plan"]["businesses"]["foundry"]


def test_card_supplier_agreements_fail_closed():
    card = rolled_card()
    card["supplier_agreements"] = [
        {"supplier": "some-supplier", "product": "ore", "quantity": 1}
    ]
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": card}))


def test_card_empty_supplier_agreements_fail_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(supplier_agreements=[])}))


def test_economy_suppliers_registry_fails_closed():
    econ = economy({"foundry": rolled_card()})
    econ["suppliers"] = {"some-supplier": {"supplied_by": None}}
    with pytest.raises(ValueError):
        plan_businesses(econ)


def test_explicit_internal_sources_remain_authoritative():
    businesses = {
        "transport": fixed_card(internal_sources=["farm"]),
        "farm": rolled_card(),
    }
    result = plan_businesses(economy(businesses))
    assert result["plan"]["businesses"]["transport"]["internal_sources"] == ["farm"]


# --- Proof 7: existing repair/byproduct/Reputation/currency contract intact ---


def test_economic_manifest_rolled_vs_fixed():
    result = plan_businesses(
        economy({"foundry": rolled_card(), "ledger": fixed_card()})
    )
    rolled = requests_for(result, "foundry", "economic")
    assert len(rolled) == 1
    assert rolled[0]["notation"] == "1d20"
    assert rolled[0]["conditional"] is False
    assert requests_for(result, "ledger", "economic") == []


def test_nat1_manifest_severity_and_durations():
    result = plan_businesses(economy({"foundry": rolled_card()}))
    severity = requests_for(result, "foundry", "repair_severity")
    assert len(severity) == 1
    assert severity[0]["notation"] == "1d6"
    assert severity[0]["conditional"] is True

    durations = {req["notation"] for req in requests_for(result, "foundry", "repair_duration")}
    assert durations == {"1d3", "1d6"}

    # No duplicate Reputation roll and no unconfigured percentage selector.
    purposes = {req["purpose"] for req in result["manifest"]["requests"]}
    assert "reputation" not in purposes
    assert "repair_percent_selector" not in purposes


def test_percent_selector_only_when_configured():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["percent_selector"] = "1d6"
    result = plan_businesses(economy({"foundry": rolled_card(repair=repair)}))
    selector = requests_for(result, "foundry", "repair_percent_selector")
    assert len(selector) == 1
    assert selector[0]["notation"] == "1d6"
    assert selector[0]["conditional"] is True


def test_reputation_declarations_representable_and_not_applied():
    card = rolled_card()
    result = plan_businesses(economy({"foundry": card}))
    # The planner validates compatibility, preserves the declarations, and
    # produces no resolved Reputation.
    serialized = json.dumps(result, default=str)
    assert "resulting_score" not in serialized
    assert "applied_delta" not in serialized

    foundry = result["plan"]["businesses"]["foundry"]
    # Validated declarations are preserved, not reduced to booleans.
    assert foundry["economic_roll"]["die"] == "1d20"
    assert len(foundry["economic_roll"]["bands"]) == 6
    assert foundry["repair"]["severity_die"] == "1d6"
    assert foundry["repair"]["severity_bands"][1]["duration_die"] == "1d3"
    assert foundry["reputation_consequences"]["economic_nat20"] == {
        "consequence_class": "gain",
        "direction": "positive",
    }
    assert [b["consequence_class"] for b in foundry["reputation_consequences"]["repair_nat1_severity"]] == [
        "loss_minor",
        "loss_moderate",
        "loss_major",
    ]
    assert "has_economic_roll" not in foundry


def test_unknown_reputation_class_fails_closed():
    consequences = copy.deepcopy(rolled_card()["reputation_consequences"])
    consequences["economic_nat20"]["consequence_class"] = "not_in_scale"
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"foundry": rolled_card(reputation_consequences=consequences)})
        )


def test_missing_reputation_config_fails_closed_for_rolled():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, reputation=None))


def test_byproduct_and_currency_declarations():
    byproduct = {
        "product": "slag",
        "source_quantity": 100,
        "waste_ratio": 0.25,
        "yield": 0.5,
        "disposition": "stored",
        "sold_on_production_day": False,
    }
    result = plan_businesses(economy({"foundry": rolled_card(byproducts=[byproduct])}))
    stored = result["plan"]["businesses"]["foundry"]["byproducts"][0]
    assert stored["source_quantity"] == 100
    assert "quantity" not in stored  # no arithmetic performed


def test_byproduct_sold_on_production_day_fails_closed():
    byproduct = {
        "product": "slag",
        "source_quantity": 100,
        "waste_ratio": 0.25,
        "yield": 0.5,
        "disposition": "stored",
        "sold_on_production_day": True,
    }
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(byproducts=[byproduct])}))


@pytest.mark.parametrize("currency", ["gold", "GP", "", None])
def test_invalid_currency_fails_closed(currency):
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(currency=currency)}))


def test_invalid_rounding_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(rounding="banker")}))


def test_negative_precision_fails_closed():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(precision=-1)}))


# --- Proof 8: purity / inertness ---------------------------------------------


def test_inputs_not_mutated():
    econ = economy({"foundry": rolled_card()})
    state = {"businesses": {"foundry": {"reputation": 50}}}
    econ_snapshot = json.dumps(econ, sort_keys=True)
    state_snapshot = json.dumps(state, sort_keys=True)

    plan_businesses(econ, state)

    assert json.dumps(econ, sort_keys=True) == econ_snapshot
    assert json.dumps(state, sort_keys=True) == state_snapshot


def test_plan_is_copy_isolated_from_input():
    econ = economy({"foundry": rolled_card(byproducts=[
        {"product": "slag", "source_quantity": 1, "waste_ratio": 0.0, "yield": 0.0,
         "disposition": "stored", "sold_on_production_day": False}
    ])})
    result = plan_businesses(econ)
    result["plan"]["businesses"]["foundry"]["byproducts"][0]["product"] = "changed"
    assert econ["business_units"]["foundry"]["byproducts"][0]["product"] == "slag"


def test_empty_template_and_state_create_no_business():
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    result = plan_businesses(template, {"businesses": {}})
    assert result["plan"]["businesses"] == {}
    assert result["manifest"]["requests"] == []


def test_planner_performs_no_rng(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("planner must not invoke RNG")

    monkeypatch.setattr(random, "randint", _boom)
    monkeypatch.setattr(random, "Random", _boom)
    result = plan_businesses(economy({"foundry": rolled_card()}))
    assert requests_for(result, "foundry", "economic")


# --- Malformed roll tables fail closed ---------------------------------------


def test_economic_band_gap_fails_closed():
    roll = copy.deepcopy(rolled_card()["economic_roll"])
    roll["bands"] = [b for b in roll["bands"] if b["min"] != 11]
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(economic_roll=roll)}))


def test_economic_band_overlap_fails_closed():
    roll = copy.deepcopy(rolled_card()["economic_roll"])
    roll["bands"][1]["min"] = 1
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(economic_roll=roll)}))


def test_repair_band_gap_fails_closed():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["severity_bands"] = [b for b in repair["severity_bands"] if b["min"] != 5]
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(repair=repair)}))


def test_fixed_business_rejects_economic_roll():
    with pytest.raises(ValueError):
        plan_businesses(
            economy({"ledger": fixed_card(economic_roll=rolled_card()["economic_roll"])})
        )


def test_fixed_business_rejects_revenue_base():
    with pytest.raises(ValueError):
        plan_businesses(economy({"ledger": fixed_card(revenue_base=10)}))


def test_rolled_business_rejects_fixed_revenue():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(fixed_revenue=10)}))


def test_parent_reference_must_exist():
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(parent="missing")}))


# --- Exact approved contract enforcement -------------------------------------


def test_economic_roll_rejects_nonapproved_partition():
    roll = copy.deepcopy(rolled_card()["economic_roll"])
    for band in roll["bands"]:
        if band["min"] == 6:
            band["max"] = 11
        elif band["min"] == 11:
            band["min"] = 12
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(economic_roll=roll)}))


def test_economic_roll_rejects_wrong_multiplier():
    roll = copy.deepcopy(rolled_card()["economic_roll"])
    roll["bands"][1]["multiplier"] = 0.5
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(economic_roll=roll)}))


def test_repair_rejects_nonapproved_severity_partition():
    repair = copy.deepcopy(rolled_card()["repair"])
    original = repair["severity_bands"]
    repair["severity_bands"] = [
        original[0],
        {**original[1], "max": 5},
        original[3],
    ]
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(repair=repair)}))


def test_repair_rejects_missing_required_duration_branch():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["severity_bands"][1]["duration_die"] = None
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(repair=repair)}))


def test_repair_rejects_wrong_cost_range():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["severity_bands"][0]["cost_percent_max"] = 12
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(repair=repair)}))


def test_repair_rejects_wrong_revenue_multiplier():
    repair = copy.deepcopy(rolled_card()["repair"])
    repair["severity_bands"][1]["revenue_multiplier"] = 0.5
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(repair=repair)}))


def test_reputation_nat20_must_resolve_to_plus_five():
    rep = copy.deepcopy(REP_CONFIG)
    rep["consequence_scale"]["gain"] = 2
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, reputation=rep))


def test_reputation_nat1_totals_must_match_approved():
    rep = copy.deepcopy(REP_CONFIG)
    rep["consequence_scale"]["loss_moderate"] = 2
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card()}, reputation=rep))


def test_plan_preserves_economic_repair_narrative_declarations():
    event = {"die": "1d20", "table": {"1": "flavor"}}
    card = rolled_card(narrative_event=event, internal_sources=[])
    result = plan_businesses(economy({"foundry": card}))
    foundry = result["plan"]["businesses"]["foundry"]
    assert foundry["economic_roll"] == card["economic_roll"]
    assert foundry["repair"] == card["repair"]
    assert foundry["reputation_consequences"] == card["reputation_consequences"]
    assert foundry["narrative_event"] == event


# --- Exact decimal preservation ----------------------------------------------


def test_authored_decimal_preserved_in_plan():
    econ = economy({"ledger": fixed_card()})
    econ["business_units"]["ledger"]["fixed_revenue"] = Decimal("0.10000000000000001")
    result = plan_businesses(econ)
    assert result["plan"]["businesses"]["ledger"]["fixed_revenue"] == Decimal(
        "0.10000000000000001"
    )


def test_authored_decimal_revenue_base_preserved():
    econ = economy({"foundry": rolled_card()})
    econ["business_units"]["foundry"]["revenue_base"] = Decimal("1000.00000000000001")
    result = plan_businesses(econ)
    assert result["plan"]["businesses"]["foundry"]["revenue_base"] == Decimal(
        "1000.00000000000001"
    )


def test_exact_serializer_preserves_decimal_token():
    text = business_plan._dumps_exact({"amount": Decimal("0.10000000000000001")})
    assert "0.10000000000000001" in text
    assert json.loads(text, parse_float=Decimal)["amount"] == Decimal(
        "0.10000000000000001"
    )


def test_cli_reads_authored_decimal_exactly(tmp_path, capsys):
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(AUTHORED_DECIMAL_ECONOMY, encoding="utf-8")
    assert business_plan.main([str(econ_path)]) == 0
    out = capsys.readouterr().out
    assert "0.10000000000000001" in out
    emitted = json.loads(out, parse_float=Decimal)
    assert emitted["plan"]["businesses"]["ledger"]["fixed_revenue"] == Decimal(
        "0.10000000000000001"
    )


# --- Narrative event ----------------------------------------------------------


def test_narrative_event_manifest():
    event = {"die": "1d20", "table": {"1": "flavor"}}
    result = plan_businesses(economy({"foundry": rolled_card(narrative_event=event)}))
    narrative = requests_for(result, "foundry", "narrative_event")
    assert len(narrative) == 1
    assert narrative[0]["notation"] == "1d20"
    assert narrative[0]["conditional"] is False


# --- CLI shares the API contract ---------------------------------------------


def test_cli_roundtrip(tmp_path, capsys):
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(json.dumps(economy({"foundry": rolled_card()})), encoding="utf-8")

    code = business_plan.main([str(econ_path)])
    assert code == 0
    emitted = json.loads(capsys.readouterr().out)
    assert set(emitted["plan"]["businesses"]) == {"foundry"}


def test_cli_invalid_config_exits_nonzero(tmp_path, capsys):
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(json.dumps(economy({"foundry": rolled_card(rounding="x")})), encoding="utf-8")
    code = business_plan.main([str(econ_path)])
    assert code == 2
    assert "error" in capsys.readouterr().err


# --- Non-finite declarations fail cleanly ------------------------------------


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_fixed_revenue_fails_closed(value):
    with pytest.raises(ValueError):
        plan_businesses(economy({"ledger": fixed_card(fixed_revenue=value)}))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_revenue_base_fails_closed(value):
    with pytest.raises(ValueError):
        plan_businesses(economy({"foundry": rolled_card(revenue_base=value)}))


NON_FINITE_DECLARATION_ECONOMY = """
{
  "business_units": {
    "ledger": {
      "name": "Synthetic Ledger",
      "currency": "sp",
      "precision": 0,
      "rounding": "floor",
      "revenue_mode": "fixed",
      "fixed_revenue": NaN,
      "fixed_daily_cost": 1,
      "funds_enabled": false,
      "internal_sources": [],
      "byproducts": []
    }
  }
}
"""


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_cli_non_finite_declaration_exits_cleanly(tmp_path, capsys, token):
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(
        NON_FINITE_DECLARATION_ECONOMY.replace("NaN", token), encoding="utf-8"
    )
    code = business_plan.main([str(econ_path)])
    assert code == 2
    assert "error" in capsys.readouterr().err


def test_cli_non_finite_nested_value_exits_cleanly(tmp_path, capsys):
    card = rolled_card(narrative_event={"die": "1d20", "table": {"1": float("nan")}})
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(json.dumps(economy({"foundry": card})), encoding="utf-8")
    code = business_plan.main([str(econ_path)])
    assert code == 2
    assert "error" in capsys.readouterr().err


# --- Proof: validated Reputation config carried into the normalized plan ------


def test_plan_version_four_and_manifest_one():
    result = plan_businesses(economy({"foundry": rolled_card()}))
    assert result["plan"]["plan_version"] == 4
    assert result["manifest"]["manifest_version"] == 1


def test_plan_carries_validated_reputation_config():
    # The validated Reputation configuration is retained, not discarded.
    result = plan_businesses(economy({"foundry": rolled_card()}))
    assert result["plan"]["reputation"] == REP_CONFIG


def test_carried_reputation_config_is_resolver_consumable():
    # The retained config is exactly what the existing POST-EV2-11.9 resolver
    # consumes, so Stage C needs no second, unvalidated source read.
    result = plan_businesses(economy({"foundry": rolled_card()}))
    resolved = resolve_reputation(
        {"current_score": 50, "consequence_class": "gain", "direction": "positive"},
        result["plan"]["reputation"],
    )
    assert resolved["resulting_score"] == 55
    assert resolved["tier"] == "neutral"


def test_plan_reputation_config_copy_isolated_from_input():
    econ = economy({"foundry": rolled_card()})
    result = plan_businesses(econ)
    result["plan"]["reputation"]["consequence_scale"]["gain"] = 999
    result["plan"]["reputation"]["tiers"][0]["name"] = "changed"
    assert econ["reputation"]["consequence_scale"]["gain"] == 5
    assert econ["reputation"]["tiers"][0]["name"] == "wary"


def test_plan_reputation_config_carries_exact_numeric_values():
    econ = economy({"foundry": rolled_card()})
    exact = Decimal("0.12345678901234567890123456789")
    econ["reputation"]["high_standing"]["positive_gain_multiplier"] = exact
    result = plan_businesses(econ)
    carried = result["plan"]["reputation"]["high_standing"]["positive_gain_multiplier"]
    assert carried == exact
    assert isinstance(carried, Decimal)


def test_fixed_only_economy_without_reputation_config_is_explicit_none():
    result = plan_businesses(economy({"ledger": fixed_card()}, reputation=None))
    assert result["plan"]["reputation"] is None


def test_plan_carries_no_reputation_resolution():
    result = plan_businesses(economy({"foundry": rolled_card()}))
    serialized = json.dumps(result, default=str)
    assert "resulting_score" not in serialized
    assert "applied_delta" not in serialized
    assert "resulting_score" not in result["plan"]["reputation"]
    assert "applied_delta" not in result["plan"]["reputation"]


def test_carried_reputation_config_survives_cli_serialization(tmp_path, capsys):
    econ = economy({"foundry": rolled_card()})
    exact = Decimal("0.12345678901234567890123456789")
    econ["reputation"]["high_standing"]["positive_gain_multiplier"] = exact
    econ_path = tmp_path / "economy.json"
    econ_path.write_text(business_plan._dumps_exact(econ), encoding="utf-8")
    assert business_plan.main([str(econ_path)]) == 0
    emitted = json.loads(capsys.readouterr().out, parse_float=Decimal)
    assert emitted["plan"]["reputation"]["high_standing"]["positive_gain_multiplier"] == exact
    assert emitted["plan"]["plan_version"] == 4
