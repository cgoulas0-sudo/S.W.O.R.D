# EV2-09A — Off-screen Run resolution → proposed consequences

EV2-09A adds the smallest non-canonical resolution layer on top of the EV2-08 Run record foundation.

## Mental model

`Run -> Scenario -> Primary Hook -> off-screen resolution proposal`

The Run remains the occurrence branch. The Scenario and its Primary Hook provide the narrative purpose. The resolution proposal records the quality of what happened off-screen and a bounded set of proposed consequences. It does **not** write campaign canon.

## Approved resolution mechanic

Primary d20 bands are fixed:

- `1` = `critical_trigger`
- `2-5` = `bad`
- `6-10` = `below_average`
- `11-16` = `normal`
- `17-19` = `above_average`
- `20` = `exceptional`

Only when the primary roll is `1`, a second d6 is required:

- `1-2` = `minor`
- `3-4` = `moderate`
- `5` = `serious`
- `6` = `catastrophic`

A severity roll is forbidden for every non-1 primary result.

## Objective-driven meaning

EV2-09A does not add a redundant `loot` / `discovery` / `rescue` purpose field.

Purpose comes from:

1. the source Run's `scenario_id`;
2. that Scenario's `primary_hook_id`;
3. the Scenario and Hook objectives.

The proposal stores a non-authoritative `objective_context` snapshot so the outcome remains understandable as a Run-local historical proposal. Callers resolving a real Run must supply Scenario/Hook source records from the Run's branch/anchor context, not silently substitute unrelated later intent.

The helper can emit a neutral `run_objective` consequence when no concrete consequence is supplied. This deliberately preserves outcome quality without inventing campaign facts. Future DM/LLM presentation may turn that quality into better loot, stronger findings, rescue quality, and so on, but that later layer does not gain canon authority.

## Proposal contract

A resolution proposal has:

- stable `RP<number>` identity;
- source `run_id`, `scenario_id`, and `primary_hook_id`;
- the source Run's exact `campaign_anchor`;
- the Scenario/Hook objective snapshot;
- the exact primary roll and derived outcome band;
- severity roll/band only on primary `1`;
- one or more bounded proposed consequences.

Each proposed consequence has a local stable `PC<number>` identity, a scope, a broad semantic kind, a non-blank summary, and optional bounded entity/location references.

Allowed scopes are:

- `run_objective`
- `participant`
- `location`
- `related_entity`

Any referenced entity/location must already be inside the source Run, Scenario, or Primary Hook context. Participant-scoped proposals may target actual Run participants only.

## Character-death safety

The automatic resolution vocabulary contains no `death` consequence kind.

No dice result, including `1` followed by severity `6`, can automatically kill a Character. Catastrophic output may propose injury, capture, loss, setback, world change, or another DM-reviewed consequence. Character death remains explicit DM authority outside this automatic mechanic.

## Canon boundary

A resolution proposal is **not canon**.

The schema has no canonical-write field, no owner mutation command, and no merge state. EV2-09A never:

- mutates entity/state/inventory/Hook/location owners;
- resolves stale ownership or Run A -> Run B handoff conflicts;
- applies consequences exactly once;
- performs all-or-nothing reconciliation;
- closes/synchronizes a Run into shared canon.

Those behaviors belong to EV2-09B.

## Validation

`validate_run_resolutions.py` checks:

- referenced Run/Scenario/Hook resolution;
- off-screen Run mode;
- source Run anchor is an actual commit reachable from canonical `main`;
- exact anchor and objective-context preservation;
- exact d20/d6 band classification;
- strict IDs and duplicate consequence IDs;
- consequence reference boundedness;
- participant-scope ownership;
- schema/JSON safety.

All EV2-09A fixtures are synthetic.
