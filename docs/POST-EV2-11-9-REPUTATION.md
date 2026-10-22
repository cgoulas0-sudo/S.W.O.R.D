# POST-EV2-11.9 — Reputation Mechanic

POST-EV2-11.9 adds one reusable deterministic **Reputation primitive** for a
Business-owned 0–100 standing score. A fresh caller can deterministically resolve
a valid Reputation consequence and receive the bounded resulting score plus the
derived tier; malformed or unsupported input fails closed. It is a pure mechanic
and creates no Business economy, Incorporation, Begin Day integration, RNG, NPC
override, or persistence owner.

> Architecture sentence: **The Business owns Reputation; people inherit
> contextual association, not duplicated Reputation state. Resolution is
> deterministic, creates no RNG root, and persists nothing here — a later owner
> persists the returned result.**

## Why this exists

Business / Economy needs Reputation as an already-defined primitive instead of
embedding social-standing semantics inside the economy resolver. This Mission
extracts that primitive so POST-EV2-12 (Business / Economy) and any later
consumer can call it without re-deriving standing math.

## What it does

`scripts/reputation_resolver.py` exposes `resolve_reputation(request, config)`:

- **validates** an existing score, an explicit consequence classification, and
  configuration;
- **applies** the configured bounded change with high-standing positive
  asymmetry;
- **derives** the resulting tier;
- **returns** a mechanical result (`current_score`, `consequence_class`,
  `direction`, `magnitude`, `high_standing_asymmetry_applied`, `applied_delta`,
  `resulting_score`, `tier`, `bounded`) for a later owner to persist.

It creates no RNG root, persists nothing, and never mutates caller inputs.

## Request contract

```json
{
  "current_score": 50,
  "consequence_class": "major",
  "direction": "positive"
}
```

- `current_score` — integer within `config.score_bounds` (reference 0–100).
  Missing or out-of-range input fails closed; a missing score is **never**
  synthesized as zero.
- `consequence_class` — one of the configured `consequence_scale` keys
  (`minor`, `meaningful`, `major`, `city_defining`). Unknown classes fail closed.
- `direction` — `"positive"` or `"negative"`. The class names the magnitude;
  direction selects the sign.

## Port / Reference semantics

- bounded score 0–100 (configurable);
- explicit consequence scale: minor ±1, meaningful ±2, major ±5,
  city-defining ±10 (magnitude from config, sign from `direction`);
- classification follows established scope/consequence, **never** a desired final
  score;
- positive gains above the configured `high_standing.threshold` use the
  configured `positive_gain_multiplier` (reference 0.5) with floor rounding;
- reference tiers: 0–29 wary, 30–59 neutral, 60–79 recognized, 80–94
  institutional, 95–99 key civic link, 100 legendary recognition/increased
  attention;
- tiers describe default standing/access only.

## Configuration (`config/REPUTATION_TEMPLATE.json`)

The template is **inert until explicitly instantiated** for a specific Business.
Its validation rules (enforced by `validate_config`) are:

- `score_bounds.min` strictly less than `score_bounds.max`;
- `consequence_scale` is a non-empty object of non-empty keys to integer
  magnitudes ≥ 1;
- `high_standing.threshold` satisfies `min < threshold <= max`;
- `high_standing.positive_gain_multiplier` is a number in `(0, 1)`;
- `high_standing.rounding` is `"floor"`;
- `tiers` form a single contiguous, non-overlapping, gap-free cover of
  `[min, max]` — exactly one tier per score.

Any malformed config (bad bounds, missing/overlapping/gapped coverage, invalid
multiplier, unsupported rounding) fails closed before resolution.

## Association semantics (documented, never persisted/duplicated)

The Business owns its Reputation score. Owners/workers **inherit contextual
association** with the relevant Business Reputation; they do **not** receive
duplicated personal Reputation state. A person associated with multiple
Businesses uses the contextually relevant Business Reputation; unrelated scores
are not averaged. This resolver **does not infer or persist** association — that
remains caller-owned context for the later Business / Economy Mission.

## Hard boundaries (this Mission owns none of these)

No Business economy. No Incorporation. No Begin Day wiring. No persistence domain.
No SQL. No RNG. No automatic events. No NPC mutation. No personal/faction
Reputation ledger. No UI. No real campaign data.

## Deferred ownership

Business / Economy owns: Business definitions/state and economic resolution;
Business consequences that call Reputation; Begin Day Business-consumer
integration; durable Business Reputation persistence through existing
runtime/save authority; owner/worker association data; Incorporations,
multi-Business ownership, and any consolidated Incorporation-level Reputation. A
later social/faction Mission owns any independent personal/faction standing
system.

## Proof

See `scripts/reputation_resolver.py` and
`tests/post_ev2_11_9/test_reputation.py`. The suite proves: every configured
consequence class resolves its exact signed delta; 0/100 bounds clamp; positive
above-threshold asymmetry and floor behavior are correct; negative changes are
not reduced by the positive asymmetry; every boundary score derives exactly one
correct tier; malformed/out-of-range current score, unknown consequence class,
and malformed config all fail closed; caller/config inputs are not mutated; no
RNG is required or invoked; fixtures remain generic/template-portable; and
association semantics are documented but not persisted/duplicated.
