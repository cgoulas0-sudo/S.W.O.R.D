"""POST-EV2-12.2 proof suite -- Begin Day Business consumer.

Pure (no PostgreSQL) proof that ``scripts/business_resolver.BusinessDayConsumer``
is the single Business consumer wired to the POST-EV2-8 Begin Day dispatch seam:
it uses only ``dispatch.roll``, returns the four audit arrays plus exactly one
``businesses`` state patch, is deterministic across retries (no rerun / no
re-aliasing), treats narrative events as audit-only, and merges through the real
Begin Day conductor merge as exactly one live_status owner key.

Only synthetic data is used. No real RHC Business, money, or campaign state is
created or mutated.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "post_ev2_12"))

import begin_day  # noqa: E402
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
# Deterministic dispatch double (records every roll, asserts no hidden RNG)
# ---------------------------------------------------------------------------


class FakeDispatch:
    """Mirrors ``begin_day.DailyDispatchSeam`` but returns chosen deterministic totals."""

    def __init__(self, totals):
        self._totals = totals
        self.calls = []

    def roll(self, request, source):
        notation = request["notation"]
        self.calls.append((source, notation))
        total = self._totals[(source, notation)]
        return {"notation": notation, "total": total, "rolls": [total]}


def _totals_from_manifest(manifest, purpose_totals):
    totals = {}
    for req in manifest["requests"]:
        totals[(req["business"], req["notation"])] = purpose_totals.get(
            req["purpose"], 11
        )
    return totals


def _default_context(day=2):
    return {
        "day": day,
        "previous_day": day - 1,
        "previous_day_record_path": "finalized/prev.json",
        "phase": "active",
        "carryover_active_hooks": [],
    }


# ---------------------------------------------------------------------------
# Proof: exactly one Business consumer exists
# ---------------------------------------------------------------------------


def test_exactly_one_business_day_consumer():
    # Static scan: only one declared consumer_id matches the Business mission.
    scripts_dir = ROOT / "scripts"
    ids = []
    for path in scripts_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'consumer_id\s*=\s*"([^"]+)"', text):
            ids.append(match.group(1))
    business_ids = [cid for cid in ids if cid == "post-ev2-12-business-day"]
    assert business_ids == ["post-ev2-12-business-day"]
    # The Business consumer is importable and carries that id.
    consumer = business_resolver.BusinessDayConsumer(
        economy({"foundry": rolled_card(funds_enabled=False)}),
        {},
    )
    assert consumer.consumer_id == "post-ev2-12-business-day"


# ---------------------------------------------------------------------------
# Proof: consumer uses only dispatch.roll and returns the audit contract
# ---------------------------------------------------------------------------


def test_consumer_returns_audit_contract_and_one_patch():
    econ = economy(
        {"foundry": rolled_card(funds_enabled=False)},
        reputation=REP_CONFIG,
        fund_policy=None,
    )
    plan = plan_businesses(econ, {"businesses": {"foundry": {"reputation": 50}}})["plan"]
    manifest = plan_businesses(econ, {"businesses": {"foundry": {"reputation": 50}}})[
        "manifest"
    ]
    totals = _totals_from_manifest(
        manifest, {"economic": 11, "narrative_event": 7, "repair_severity": 3}
    )
    dispatch = FakeDispatch(totals)
    consumer = business_resolver.BusinessDayConsumer(
        econ, {"foundry": {"reputation": 50}}
    )
    result = consumer.resolve(_default_context(), dispatch)

    for key in (
        "rng_rolls",
        "mechanical_resolutions",
        "persistent_effects_applied",
        "notes",
    ):
        assert key in result and isinstance(result[key], list)
    assert "state_patch" in result
    assert set(result["state_patch"].keys()) == {"businesses"}
    # Every dispatch.roll call maps to a recorded rng_roll with the same total.
    assert len(result["rng_rolls"]) == len(dispatch.calls)
    for call, roll in zip(dispatch.calls, result["rng_rolls"]):
        assert call[0] == roll["source"]
        assert call[1] == roll["notation"]
        assert roll["total"] == totals[(call[0], call[1])]
    # The single resolved Business is present in the patch.
    assert "foundry" in result["state_patch"]["businesses"]


# ---------------------------------------------------------------------------
# Proof: determinism / retry -- re-running with the same rolls is idempotent
# ---------------------------------------------------------------------------


def test_consumer_is_deterministic_across_retries():
    econ = economy(
        {"foundry": rolled_card(funds_enabled=False)},
        reputation=REP_CONFIG,
        fund_policy=None,
    )
    plan = plan_businesses(econ, {"businesses": {"foundry": {"reputation": 50}}})[
        "manifest"
    ]
    totals = _totals_from_manifest(
        plan, {"economic": 1, "narrative_event": 7, "repair_severity": 3, "repair_duration": 3}
    )

    consumer_a = business_resolver.BusinessDayConsumer(
        econ, {"foundry": {"reputation": 50}}
    )
    dispatch_a = FakeDispatch(totals)
    result_a = consumer_a.resolve(_default_context(), dispatch_a)

    # Retry: a fresh consumer instance, identical inputs -> identical output.
    consumer_b = business_resolver.BusinessDayConsumer(
        econ, {"foundry": {"reputation": 50}}
    )
    dispatch_b = FakeDispatch(totals)
    result_b = consumer_b.resolve(_default_context(), dispatch_b)

    assert result_a == result_b
    # No extra rolls on the second run -- the consumer re-resolves from the same
    # dispatched totals and does not accumulate or rerun.
    assert dispatch_a.calls == dispatch_b.calls


# ---------------------------------------------------------------------------
# Proof: narrative event is audit-only
# ---------------------------------------------------------------------------


def test_consumer_narrative_event_is_audit_only():
    event = {"die": "1d20", "table": {"1": "flavor"}}
    econ = economy(
        {"foundry": rolled_card(funds_enabled=False, narrative_event=event)},
        reputation=REP_CONFIG,
        fund_policy=None,
    )
    plan = plan_businesses(econ, {"businesses": {"foundry": {"reputation": 50}}})[
        "manifest"
    ]
    # economic and narrative_event share the 1d20 notation, so the dispatch seam
    # returns one shared total for both; choose 11 (normal band, revenue 100000).
    totals = _totals_from_manifest(
        plan, {"economic": 11, "repair_severity": 3}
    )
    dispatch = FakeDispatch(totals)
    consumer = business_resolver.BusinessDayConsumer(
        econ, {"foundry": {"reputation": 50}}
    )
    result = consumer.resolve(_default_context(), dispatch)
    notes = [n for n in result["notes"] if n.get("note") == "narrative_event"]
    assert notes, "expected a narrative_event audit note"
    # Revenue is unaffected by the narrative roll.
    assert result["mechanical_resolutions"][0]["revenue_copper"] == 100_000


# ---------------------------------------------------------------------------
# Proof: exactly one live_status owner key via the real conductor merge
# ---------------------------------------------------------------------------


def test_consumer_merges_as_exactly_one_live_status_key():
    econ = economy(
        {"foundry": rolled_card(funds_enabled=False)},
        reputation=REP_CONFIG,
        fund_policy=None,
    )
    plan = plan_businesses(econ, {"businesses": {"foundry": {"reputation": 50}}})[
        "manifest"
    ]
    totals = _totals_from_manifest(
        plan, {"economic": 11, "narrative_event": 7, "repair_severity": 3}
    )
    dispatch = FakeDispatch(totals)
    consumer = business_resolver.BusinessDayConsumer(
        econ, {"foundry": {"reputation": 50}}
    )
    result = consumer.resolve(_default_context(), dispatch)

    candidate = {
        "day_resolution": {
            "rng_rolls": [],
            "mechanical_resolutions": [],
            "persistent_effects_applied": [],
            "notes": [],
        }
    }
    live_status = {"businesses": {}}  # an already-active live_status owner
    patched_keys = set()
    begin_day._merge_consumer_result(
        candidate["day_resolution"],
        consumer.consumer_id,
        result,
        [0],
        live_status,
        patched_keys,
    )
    # Exactly one top-level live_status key written by this consumer in a day.
    assert patched_keys == {"businesses"}
    assert live_status["businesses"] == result["state_patch"]["businesses"]


# ---------------------------------------------------------------------------
# Proof: the state patch round-trips through the Begin Day / SAVE JSON path
# ---------------------------------------------------------------------------


def test_consumer_state_patch_is_json_serializable():
    hq = fixed_card(
        name="HQ", parent=None, currency="gp", funds_enabled=True,
        fixed_revenue=0, fixed_daily_cost=0,
    )
    byproduct = {
        "product": "slag",
        "source_quantity": 100,
        "waste_ratio": Decimal("0.25"),
        "yield": Decimal("0.5"),
        "disposition": "stored",
        "sold_on_production_day": False,
    }
    child = rolled_card(
        name="Foundry", parent="hq", currency="gp", byproducts=[byproduct]
    )
    econ = economy({"hq": hq, "foundry": child}, reputation=REP_CONFIG)
    state = {
        "hq": {"funds": {"main": 0, "hq_recovery": 10000}},
        "foundry": {"reputation": 50, "funds": {"development": 0, "recovery": 0}},
    }
    manifest = plan_businesses(econ, {"businesses": state})["manifest"]
    totals = _totals_from_manifest(
        manifest,
        {"economic": 1, "repair_severity": 3, "repair_duration": 3},
    )
    dispatch = FakeDispatch(totals)
    consumer = business_resolver.BusinessDayConsumer(econ, state)
    result = consumer.resolve(_default_context(), dispatch)

    # The whole consumer result must serialize with the standard JSON path Begin
    # Day / SAVE uses; a raw Decimal anywhere would raise TypeError.
    json.dumps(result)
    foundry_funds = result["state_patch"]["businesses"]["foundry"]["funds"]
    main = result["state_patch"]["businesses"]["hq"]["funds"]["main"]
    assert not isinstance(main, Decimal)
    assert not isinstance(foundry_funds["development"], Decimal)
    # Byproduct quantity survives as an exact decimal number (100*0.25*0.5).
    assert result["state_patch"]["businesses"]["foundry"]["stock"]["slag"] == 12.5


def test_consumer_preserves_exact_fractional_money():
    hq = fixed_card(
        name="HQ", parent=None, currency="gp", funds_enabled=True,
        fixed_revenue=0, fixed_daily_cost=0,
    )
    child = rolled_card(name="Foundry", parent="hq", currency="gp")
    econ = economy({"hq": hq, "foundry": child}, reputation=REP_CONFIG)
    state = {
        "hq": {"funds": {"main": 0, "hq_recovery": 0}},
        "foundry": {
            "reputation": 50,
            "funds": {"development": 0, "recovery": Decimal("0.005")},
        },
    }
    manifest = plan_businesses(econ, {"businesses": state})["manifest"]
    totals = _totals_from_manifest(
        manifest, {"economic": 11, "repair_severity": 3}
    )
    dispatch = FakeDispatch(totals)
    consumer = business_resolver.BusinessDayConsumer(econ, state)
    result = consumer.resolve(_default_context(), dispatch)

    # net 75000 cp -> recovery = half_up(0.5 cp) + 7500 cp = 7501 cp = 75.01 gp.
    recovery = result["state_patch"]["businesses"]["foundry"]["funds"]["recovery"]
    assert Decimal(str(recovery)) == Decimal("75.01")
    # Exact money survives the standard JSON path unchanged.
    assert json.loads(json.dumps(result))["state_patch"]["businesses"]["foundry"][
        "funds"
    ]["recovery"] == recovery
