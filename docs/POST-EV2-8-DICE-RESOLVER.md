# POST-EV2-8 — Universal D&D Dice Resolver

`scripts/dice_resolver.py` is RHC's single shared random-resolution primitive. It
owns random generation plus declared roll arithmetic only. It decides no
meaning: not whether a roll is required, not the ability/skill/save, not a DC,
not success/failure, not damage meaning, and not any canon or state mutation.

It is one RNG root. Future mechanics, AI/tool callers and frontend/backend
adapters consume this resolver rather than calling raw `random.*` or inventing
their own RNG.

## Contract

The core callable is:

```python
resolve(request, rng=None) -> dict
```

The request is a machine-readable object:

```json
{
  "notation": "1d20",
  "modifiers": [{"value": 3, "source": "proficiency"}],
  "bonus_dice": [{"notation": "1d4", "source": "bless"}],
  "penalty_dice": [{"notation": "1d4", "source": "bane"}],
  "advantage": ["flanking"],
  "disadvantage": ["prone"]
}
```

- `notation` is a pure `NdM` dice expression (`1d20`, `2d6`, `1d100`); it never
  carries an inline numeric modifier.
- `modifiers` are positive or negative static adjustments; each declares a
  non-empty `source`.
- `bonus_dice` / `penalty_dice` are added/subtracted dice expressions; each
  declares a non-empty `source` and exposes its individual rolled components.
- `advantage` / `disadvantage` are lists of explicit non-empty source strings.

Only the declared keys are accepted; an unknown field fails closed.

The result is structured data:

```json
{
  "notation": "1d20",
  "dice_count": 1,
  "sides": 20,
  "mode": "advantage",
  "advantage_sources": ["flanking"],
  "disadvantage_sources": [],
  "rolls": [7, 15],
  "kept_rolls": [15],
  "dropped_rolls": [7],
  "modifiers": [{"value": 3, "source": "proficiency"}],
  "modifier_total": 3,
  "bonus_dice": [{"notation": "1d4", "source": "bless", "rolls": [2], "total": 2}],
  "bonus_total": 2,
  "penalty_dice": [],
  "penalty_total": 0,
  "total": 20
}
```

`total = sum(kept_rolls) + modifier_total + bonus_total - penalty_total`.

## Advantage / Disadvantage

Advantage/disadvantage follows D&D composition and is valid only on a single
`d20`:

- same-state sources do not stack — any number of Advantage sources still rolls
  two dice and keeps the highest;
- any number of Disadvantage sources still rolls two dice and keeps the lowest;
- at least one Advantage source **and** at least one Disadvantage source cancel
  to one normal `d20`. All declared sources are preserved in the result.

## Randomness and the test seam

Production uses Python's **unseeded runtime RNG**. `rng` is an explicit
test-only seam (`random.Random(seed)`); it must never be used as production
behavior. The resolver never seeds anything itself.

## CLI

The thin tool surface reads the same JSON request (from a file argument or
stdin), calls the same `resolve`, and prints the same structured result. It
duplicates no resolution logic:

```text
python scripts/dice_resolver.py request.json
```

## Boundary

The resolver performs **no** file, SQL, SAVE, canon or campaign-state mutation.
Rolling never writes `day_resolution` by itself. Existing owners keep their
semantics: `state/day_resolution.json` + SAVE own durable mechanical outcomes,
`scripts/offscreen_resolution.py` owns off-screen Run consequence
classification, Combat owns attack/save/damage/initiative consequences, and the
DM/rules own whether a roll is required and any DC. Wiring those systems onto
this resolver is deferred to a later gate.
