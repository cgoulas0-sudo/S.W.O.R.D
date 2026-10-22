# POST-EV2-12.1 — Business Contract Completion

POST-EV2-12.1 **completes and corrects** the inert Business Card + planner
contract that POST-EV2-12 Stage B shipped, so the later Business Day Resolver
receives every explicit static and current-state input it needs. It is still a
planner/contract patch only: no Business-day arithmetic, RNG execution,
Reputation mutation, Begin Day integration, SAVE/publication, or real RHC
Business.

The completed contract keeps one reusable, inert **Business Card schema** inside
the existing economy template, one empty `businesses` state slot inside the
existing `state/live_status.json` owner, and one small deterministic
**planner/validator** (`scripts/business_plan.py`) that turns configured
Businesses plus current Business state into a normalized plan and a **conditional
dice manifest**.

The planner **plans**; Stage C **resolves**. The planner rolls no dice, performs
no economic arithmetic, applies no Reputation, persists nothing, integrates no
Begin Day consumer, and creates no real campaign Business.

> Architecture sentence: **The Business Card declares the completed approved
> authoring contract; the planner compiles it into one explicit plan and the
> exact dice Stage C would later need; existing owners keep their mechanics, and
> Stage C owns actual Business-day resolution.**

## Why this exists

Stage B successfully separated planning from resolution, but its contract omitted
several revenue/cost/fund/current-state inputs Stage C needs and encoded
buyer-specific negotiated supplier pricing that does not match the Mission10
mechanic RHC outcomes follow. Building Stage C against that contract would force
the resolver to invent missing truth, so 12.1 completes the contract first.

## The completed contract

1. **Revenue inputs.** A rolled Business resolves revenue from explicit
   configured `revenue_base × economic_roll_multiplier × applicable active effect
   multiplier`. A fixed-revenue Business declares an explicit `fixed_revenue` and
   requests/uses no economic roll. Every Business that resolves operating
   economics declares its `fixed_daily_cost`, and every rolled Business declares
   its explicit `facility_value` repair-cost basis (the `facility_value × selected
   repair percentage` the later catastrophic-repair resolution needs).
2. **Active state is not funds-enabled.** Whether a Business resolves today
   (`active`) is a current operational-state fact under `live_status.businesses`.
   `funds_enabled` is a separate configuration/policy fact controlling Business
   fund accounting. An active support/cost centre may legitimately have funds
   disabled. The planner validates the two independently.
3. **Fund policy.** The approved default positive-net allocation is
   **20% HQ/Main, 70% Business Development, 10% Business Recovery**. Negative net
   or repair-obligation coverage follows **own Recovery → HQ Recovery → uncovered
   loss**, and the Development Fund is never auto-drawn. The planner validates
   the declaration only; it never allocates or moves money.
4. **Current Business state.** The existing `live_status.businesses` owner is the
   only Business mutable-state owner and is sufficient to represent the bounded
   inputs Stage C requires: active/disabled state, current fund balances, current
   stock/byproduct quantities, a Business Reputation score, and Business-owned
   duration-in-resolution-days effects. No real values are seeded.
5. **Same-day internal purchase cost.** For an explicitly linked internal source
   Business, later purchase cost equals the **actual realized same-day
   sales/revenue** of those source Businesses. Dependencies are explicit and
   acyclic so Stage C can resolve them deterministically. Mission10 proves this
   is the real raw-material mechanic, so Stage B's negotiated buyer-price /
   supplier-agreement surface is removed rather than kept as a second, competing
   semantic. External supplier/logistics pricing beyond this rule is deferred.
6. **Existing mechanics stay owned.** POST-EV2-8 remains the sole RNG owner;
   POST-EV2-11.9 remains the sole Reputation delta/tier owner. The Stage B
   repair, byproduct, currency and conditional-roll declarations remain valid,
   and authored decimal values remain exact.

## The Business Card schema

An instantiated economy configuration carries:

- `business_units` — a map of Business id → Business Card;
- `fund_policy` — the approved fund policy declaration (validated only);
- `reputation` — the shared Reputation primitive configuration (the same shape
  as `config/REPUTATION_TEMPLATE.json`), validated by the existing
  `reputation_resolver.validate_config` and retained in the normalized plan (or
  an explicit `None` when no config is declared) so the later resolver consumes
  the validated config without a second source read.

Each Business Card declares:

- `name`, `currency` (`gp`/`sp`/`cp`), `precision`, `rounding`
  (`half_up`/`half_even`/`floor`/`ceil`);
- `revenue_mode` (`rolled`/`fixed`), a `revenue_base` for rolled Businesses and a
  `fixed_revenue` for fixed Businesses;
- a `fixed_daily_cost` for every Business;
- a `facility_value` for every rolled Business — the explicit static repair-cost
  basis (a finite non-negative monetary value in the Card's declared currency)
  that the later resolver multiplies by the selected repair percentage; the
  planner validates and preserves it exactly and performs no repair arithmetic; a
  fixed-revenue Business carries no repair mechanic, so it declares no
  `facility_value` — the key is rejected by presence (including an explicit null)
  and the normalized fixed plan omits the key entirely, so an unowned basis fails
  closed rather than leaking into plan output;
- `funds_enabled` — the fund-accounting policy fact, distinct from current
  `active` state;
- optional `parent` and `subsidiaries` declared links;
- for rolled Businesses: `economic_roll` (a `1d20` band table), `repair` (the
  Natural-1 `1d6` severity branch with optional `percent_selector`), and
  `reputation_consequences` (the Natural-20 gain and Natural-1 severity totals,
  each referencing a configured Reputation `consequence_class` + `direction`);
- optional `internal_sources` (the same-day internal raw-material cost links),
  `byproducts`, and `narrative_event`.

`config/ECONOMY_TEMPLATE.json` ships the schema inert, with an empty
`business_units` map and the approved `fund_policy` values. It creates no
company, balance or Business.

## The planner contract

`plan_businesses(economy, state=None)` returns `{"plan": ..., "manifest": ...}`
or raises `ValueError`.

It may confirm:

- required fields for the completed contract are present and internally coherent;
- referenced Businesses exist, and `internal_sources` links are dangling-free,
  self-free and acyclic;
- the declared economic, repair and Reputation tables match the approved rules
  exactly — the approved bands with no overlap, gap or unapproved band;
- rolled vs fixed-revenue mode is explicit and carries the right revenue input;
- every Business declares a fixed daily cost and a boolean `funds_enabled`;
- a declared `fund_policy` represents exactly the approved 20/70/10 allocation,
  the own-Recovery → HQ-Recovery → uncovered-loss waterfall, and no automatic
  Development draw;
- whenever any Business declares `funds_enabled: true`, an approved
  `fund_policy` is present — a missing policy fails closed;
- the superseded Stage B `suppliers` registry / `supplier_agreements` negotiated
  pricing surfaces fail closed rather than being silently dropped;
- Reputation consequence declarations resolve to the exact approved outcomes
  (Natural-20 `+5`; Natural-1 severity totals `-3/-4/-5`) through the configured
  consequence scale;
- byproduct basis/disposition and currency policy are explicit;
- the returned plan is copy-isolated and preserves the validated economic,
  repair, Reputation and narrative declarations (not reduced to booleans), and it
  also retains the validated `fund_policy`, the validated Reputation
  configuration (the shape the existing POST-EV2-11.9 resolver consumes, or an
  explicit `None` when no config is declared), and a copy-isolated copy of the
  validated current Business state so Stage C needs no second, unvalidated read;
- authored decimal values are retained exactly, without binary-float precision
  loss;
- every rolled Business declares a finite non-negative `facility_value` (the
  repair-cost basis) that is copy-preserved into the normalized plan; a missing,
  negative, boolean, non-number or non-finite basis fails closed; and
- the normalized contract is plan version **4** (manifest version stays **1**).

The conditional manifest contains only declared requests:

- one economic `1d20` for each rolled Business;
- one conditional Natural-1 severity `1d6`;
- the conditional repair-duration `1d3`/`1d6` dice the approved branch requires;
- an explicitly configured `percent_selector` die, when one exists;
- a separately configured narrative-event `1d20`.

A Business whose current state says `active: false` resolves nothing today, so it
contributes **no** requests (economic, repair or narrative) to the manifest; this
is distinct from its `funds_enabled` configuration fact.

The planner must **not** generate random values, calculate revenue, repair cost,
purchase cost, byproduct quantity, allocation, balances or resulting Reputation;
apply duration effects; mutate current state; call SAVE/RT01; register a Begin
Day consumer; or grow into a generic schema/rule engine.

## State

`state/live_status.json` keeps one empty top-level `businesses: {}` field inside
the existing live-status owner. Each declared Business state entry may carry:

- `active` — whether the Business resolves today (current operational state);
- `reputation` — the Business Reputation score, validated against the configured
  bounds;
- `funds` — current Development/Recovery (and HQ Main/Recovery) balances;
- `stock` — current stock/byproduct quantities;
- `effects` — Business-owned duration-in-resolution-days effects, each with a
  `revenue_multiplier` and `remaining_resolution_days`.

This is a state-shape declaration only: it is not populated by this Mission and
creates no company or balance. Whatever entries are declared here are validated
and carried into the returned plan's `state` map, copy-isolated, so Stage C
consumes the validated current state instead of rereading the caller's input.

## Mutation domain / compatibility

POST-EV2-12.1 adds **no** runtime mutation domain and **no** same-save
compatibility edge. No Patch 1A registry or Patch 1B dispatcher change is
required.

## Deferred ownership

POST-EV2-12.2 owns actual Business-day arithmetic, consumption of the validated
manifest through the existing POST-EV2-8 RNG owner, Reputation consequence
application, state-patch production and Begin Day consumer integration. A future
Fleet/Logistics gate owns transport capacity, routing and voyage scheduling; a
future explicit external-supplier gate owns pricing beyond the proven same-day
internal source rule; parent Reputation aggregation is a separately approved
later gate.

## Proof

See `tests/post_ev2_12/test_business_plan.py`. The suite proves a rolled and a
fixed-revenue Business share one generic planner with explicit revenue base /
fixed revenue and fixed daily cost; a rolled Business carries an explicit
facility-value repair-cost basis that is preserved exactly while a missing,
negative, boolean, non-number or non-finite basis fails closed and a fixed
Business declares none; active/disabled state is distinct from
`funds_enabled` and every combination validates; the fund policy represents the
approved 20/70/10 allocation and waterfall with zero allocation; the
`live_status.businesses` contract represents synthetic balances, stock and
duration effects without seeding real data; explicit internal source-cost links
validate while dangling/cyclic links fail and no negotiated buyer price is
treated as the approved rule; the repair/byproduct/Reputation/currency/
conditional-manifest contract is intact; the validated Reputation configuration
is carried into the plan copy-isolated and exactly (consumable by the existing
POST-EV2-11.9 resolver, with an explicit `None` for a fixed-only economy that
declares no config) without resolving any Reputation; authored decimals survive
normalization and CLI serialization; inputs are never mutated and the inert
template plus empty state create no Business; and no RNG runs.
