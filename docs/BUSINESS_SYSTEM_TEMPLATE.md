# Rolling High Club — Business / Economy System Template

This document explains how to instantiate a reusable business/economy mechanic in RHC without importing any Mission 10 company or values.

## Files

- Static economic rules and configured business units: create a named file from `config/ECONOMY_TEMPLATE.json`.
- Static organization/workforce structure: create a named file from `config/ORGANIZATION_TEMPLATE.json` when needed.
- Current money, assets, persistent production effects and obligations: `state/live_status.json` or a later explicitly approved dedicated state file.
- Current-day rolls/resolutions that must survive handoff: `state/day_resolution.json`.
- Permanent historical consequences: the relevant `canon/days/day_XXX.md` after Final Save.

## Activation Rule

A business mechanic does not exist merely because these templates exist.

Before first use, the Dungeon Master must establish:

1. the business/organization itself;
2. the currency and economic units;
3. any income, costs, production, logistics or reputation rules;
4. any RNG table and resolution method;
5. the initial current state.

Only then should named configuration/state files be created.

## Static vs Mutable Boundary

Keep formulas, durable business-unit definitions and rules in configuration. Keep current balances, damage, active effects, deployment, inventory and obligations in mutable state.

Never rewrite static configuration merely to make a current result come out differently. If the Dungeon Master changes a rule, record that as an explicit rule change before resolving future results.

## Blank-Template Safety

Mission 10's Robbert Inc. values, workforce, managers, facilities, company names, revenue tables and current assets are not part of these RHC templates and must not be inferred from them.

## Business Cards (POST-EV2-12.1)

An instantiated economy configuration may declare Business Cards in its
`business_units` map. Both remain inert until a named configuration is
explicitly instantiated.

Each Business Card declares, for the completed approved Business contract:

- currency (`gp`/`sp`/`cp`), decimal `precision` and explicit `rounding` policy;
- an explicit `revenue_mode` of `rolled` or `fixed`, with a `revenue_base` only
  for rolled businesses and a `fixed_revenue` only for fixed businesses;
- a `fixed_daily_cost` for every Business that resolves operating economics;
- a `facility_value` for every rolled Business: the facility value the later
  catastrophic-repair resolver derives repair cost from (facility value x the
  selected repair percentage). The planner validates and preserves it exactly and
  performs no repair arithmetic; fixed Businesses carry no repair mechanic and
  declare no `facility_value` — the key is rejected by presence (including an
  explicit null) and omitted entirely from the normalized fixed plan;
- a `funds_enabled` configuration/policy flag, distinct from the current
  active/disabled state that lives in `live_status.businesses`;
- for rolled businesses, an `economic_roll` `1d20` band table, a `repair`
  Natural-1 severity `1d6` branch (with optional configured `percent_selector`),
  and `reputation_consequences` for the Natural-20 gain and Natural-1 severity
  totals;
- optional `parent`/`subsidiaries` declared links (no parent aggregation);
- `internal_sources` naming the explicitly linked Businesses whose actual
  realized same-day sales/revenue become this Business's raw-material cost;
- `byproducts` declaring their base source quantity, waste ratio, yield and
  disposition, and an optional separate `narrative_event` `1d20`.

The economy configuration may also declare a `fund_policy` block: the approved
default positive-net allocation is 20% HQ / 70% Business Development / 10%
Business Recovery, deficits and repair obligations cover own Recovery -> HQ
Recovery -> uncovered loss, and the Development Fund is never auto-drawn.

`scripts/business_plan.py` is the planner/validator. It reads configured
Businesses plus the Business portion of current state (`live_status.businesses`)
and returns a copy-isolated normalized plan and a conditional dice manifest. The
normalized plan retains the validated `fund_policy`, the validated Reputation
configuration (in the shape the existing POST-EV2-11.9 resolver consumes, or an
explicit `None` when no config is declared), and the validated current Business
state, so Stage C consumes the completed contract without a second source read.
The planner rolls no dice, performs no economic arithmetic, applies no Reputation
and writes no state; Stage C owns actual Business-day resolution. See
`docs/POST-EV2-12-BUSINESS-ECONOMY.md`.
