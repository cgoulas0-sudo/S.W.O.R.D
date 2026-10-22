#!/usr/bin/env python3
"""Pure EV2-09A off-screen Run resolution helpers.

This module classifies the approved d20/d6 mechanic and builds a non-canonical
resolution proposal. It never writes campaign canon.
"""
from copy import deepcopy

OUTCOME_BANDS = (
    (1, 1, "critical_trigger"),
    (2, 5, "bad"),
    (6, 10, "below_average"),
    (11, 16, "normal"),
    (17, 19, "above_average"),
    (20, 20, "exceptional"),
)

SEVERITY_BANDS = (
    (1, 2, "minor"),
    (3, 4, "moderate"),
    (5, 5, "serious"),
    (6, 6, "catastrophic"),
)


def _require_int_roll(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    if not low <= value <= high:
        raise ValueError(f"{name} must be from {low} to {high}")
    return value


def classify_primary_roll(primary_roll):
    primary_roll = _require_int_roll("primary_roll", primary_roll, 1, 20)
    for low, high, label in OUTCOME_BANDS:
        if low <= primary_roll <= high:
            return label
    raise AssertionError("unreachable primary-roll band")


def classify_severity_roll(severity_roll):
    severity_roll = _require_int_roll("severity_roll", severity_roll, 1, 6)
    for low, high, label in SEVERITY_BANDS:
        if low <= severity_roll <= high:
            return label
    raise AssertionError("unreachable severity-roll band")


def classify_resolution(primary_roll, severity_roll=None):
    outcome_band = classify_primary_roll(primary_roll)

    if primary_roll == 1:
        if severity_roll is None:
            raise ValueError("severity_roll is required when primary_roll is 1")
        return outcome_band, classify_severity_roll(severity_roll)

    if severity_roll is not None:
        raise ValueError("severity_roll is only allowed when primary_roll is 1")

    return outcome_band, None


def _default_consequence(scenario_id, hook_id, outcome_band, severity_band):
    quality = severity_band or outcome_band
    return {
        "consequence_id": "PC01",
        "scope": "run_objective",
        "kind": "objective_result",
        "summary": (
            f"Apply the {quality.replace('_', ' ')} result to the Run objective "
            f"defined by Scenario {scenario_id} and Primary Hook {hook_id}."
        ),
        "related_entity_ids": [],
        "location_ids": [],
    }


def build_resolution_proposal(
    resolution_id,
    run,
    scenario,
    hook,
    primary_roll,
    severity_roll=None,
    proposed_consequences=None,
):
    """Build one non-canonical proposal from an off-screen Run.

    Concrete narrative/world consequences may be supplied by a future DM/LLM
    layer. When omitted, this function emits one bounded run-objective proposal
    that preserves the outcome quality without inventing campaign facts.
    """
    if run.get("execution_mode") != "off_screen":
        raise ValueError("EV2-09A resolves off-screen Runs only")
    if run.get("control_state") != "not_applicable":
        raise ValueError("off-screen Run control_state must be not_applicable")
    if scenario.get("scenario_id") != run.get("scenario_id"):
        raise ValueError("Run scenario_id does not match Scenario")
    if hook.get("hook_id") != scenario.get("primary_hook_id"):
        raise ValueError("Scenario primary_hook_id does not match Hook")

    outcome_band, severity_band = classify_resolution(primary_roll, severity_roll)
    consequences = deepcopy(proposed_consequences)
    if consequences is None:
        consequences = [
            _default_consequence(
                scenario["scenario_id"],
                hook["hook_id"],
                outcome_band,
                severity_band,
            )
        ]

    proposal = {
        "resolution_id": resolution_id,
        "run_id": run["run_id"],
        "scenario_id": scenario["scenario_id"],
        "primary_hook_id": hook["hook_id"],
        "campaign_anchor": deepcopy(run["campaign_anchor"]),
        "objective_context": {
            "scenario_objective": scenario["objective"],
            "hook_objective": hook["objective"],
        },
        "primary_roll": primary_roll,
        "outcome_band": outcome_band,
        "proposed_consequences": consequences,
    }
    if severity_band is not None:
        proposal["severity_roll"] = severity_roll
        proposal["severity_band"] = severity_band
    return proposal
