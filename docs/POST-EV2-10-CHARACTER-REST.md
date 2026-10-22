# POST-EV2-10 — Character Rest / Long Rest lifecycle

POST-EV2-10 adds the smallest official D&D 5.5e per-character **Short Rest /
Long Rest lifecycle** RHC was missing: **one dedicated runtime owner** that says
whether one specific character actually started, continued, interrupted or
completed a valid Rest, with **one validated controller-safe mutation route** and
**one supported published read**, on the existing RT01 SAVE / publish / mirror /
confirm spine.

It creates no second save engine, no second controller/ownership ledger, no
second time source, no second RNG root and no parallel persistence or mirror
path.

> Architecture sentence: **POST-EV2-10 does not create a new save system. It
> creates the bounded durable per-character Rest lifecycle on top of the existing
> RT01 SAVE / publish / mirror / confirm spine, with RT02 elapsed time as the only
> time source, POST-EV2-8 as the only RNG root, POST-EV2-9 as the only HP /
> Hit-Dice / resource owner, and controller authority resolved only from
> authoritative published Run truth.**

## Why this exists

POST-EV2-9 now owns current HP / Hit Dice / spell-slot pools / limited-use
character resources, RT02 owns elapsed campaign time, POST-EV2-8 owns all
mechanically required RNG, and RT01 owns persistence. RHC still lacked the bounded
mechanic that says whether one specific character actually started, continued,
interrupted or completed a valid Rest and therefore which official Rest
consequences may fire.

## Mental model

- **One character owns one Rest attempt.** A shared camp scene may contain several
  independent Rest attempts, but there is never one shared mechanical Rest
  record. Interrupting one character's Rest does not alter another's.
- **Rest owns only the lifecycle.** It owns whether a character has an active Rest
  attempt, its authoritative elapsed-time anchors/interruption state, and the
  personal successful-Long-Rest timing needed for future eligibility. It never
  duplicates HP, Hit Dice, spell slots or feature charges.
- **Progress is derived, not ticked.** The record stores a start anchor and a
  required duration; completion is a legal transition once RT02 elapsed minutes
  have advanced to satisfy it. No minute-by-minute journal is persisted.
- **Time and randomness have single owners.** Every anchor is stamped from
  authoritative published RT02 `elapsed_campaign_minutes`; every required Hit
  Point Die roll comes from the shared POST-EV2-8 resolver. The route itself never
  advances the Clock or invents elapsed time.
- **Authority is proven, never stored.** Controller authority is resolved from
  authoritative **published** Run truth exactly as EV2-10/11/13/13.1 do.

## Record shape

Each `character_rests` record mirrors `schemas/character_rests.schema.json` and is
exactly:

- `character_id` — required `character:<slug>` identity;
- `schema_version` — `1`;
- `status` — `idle` | `active` | `completed` | `interrupted`;
- `rest_kind` — `null` | `short` | `long`;
- `started_at_elapsed_minutes` — engine-derived start anchor (null while idle);
- `required_minutes` — Short = 60; Long = 480 + 60 per interruption;
- `completed_at_elapsed_minutes` — engine-derived completion anchor;
- `last_long_rest_completed_at_elapsed_minutes` — personal last successful
  Long-Rest anchor, preserved across later attempts for the 16-hour rule;
- `interruptions` — bounded ordered `{ cause, at_elapsed_minutes }` (at most 1000
  entries, matching the schema) where `cause` is `initiative` | `spell` | `damage`
  | `exertion`;
- `short_benefit_granted` — true once Short-Rest benefits were granted to an
  active Long Rest after a rules-valid interruption at least 1 hour in.

Lifecycle: `idle -> active(short|long) -> completed | interrupted`. A Short Rest
interruption ends it as `interrupted` with no benefits; a Long Rest interruption
keeps it `active`, appends one interruption and adds 60 required minutes, so the
Long Rest resumes immediately.

## Official 5.5e rules enforced

- **Short Rest** — 1 hour; requires at least 1 HP to start; interruption by
  initiative, non-cantrip spell or damage gives no benefits. Benefits include
  optional Hit Point Die spending; each die recovers `die result + Constitution
  modifier`, minimum 1, and HP can never exceed the current maximum. Feature /
  resource recharge is metadata-driven from POST-EV2-9 `recharge_on`; there is no
  class-specific recharge switchboard.
- **Long Rest** — at least 8 hours; requires at least 1 HP to start; a creature
  must wait at least 16 hours after finishing a Long Rest before starting another.
  Interruption by initiative, non-cantrip spell, damage or 1 hour of physical
  exertion adds one required hour; if at least 1 hour elapsed first, Short Rest
  benefits are granted. Completion restores all lost HP, all spent Hit Point Dice,
  clears any current Temporary Hit Points, and restores only explicitly
  Long-Rest-recharging features.
- **Unsupported state fails closed.** Official Long Rest effects that RHC has no
  owner for (Exhaustion, condition/ability-score/HP-maximum reduction) are never
  invented. If a relevant `character_mechanics` section is `unknown`, the Rest
  route fails explicitly rather than pretending the state was fully resolved.

## Durable mutation path

`public.mutate_character_rest(<lock_token>, <request>)` is the only way to stage
the engine-owned `character_rests` runtime namespace. It runs inside the normal
campaign save lifecycle:

```
begin_campaign_save -> mutate_character_rest -> publish_campaign_save
                    -> existing runtime-published mirror / confirmation handshake
```

Request shape:

```json
{
  "character_id": "character:<slug>",
  "controller": { "kind": "mainrun" }
              | { "kind": "run", "run_id": "R##" },
  "rest": { "status": "active", "rest_kind": "short",
            "started_at_elapsed_minutes": 1000, "required_minutes": 60,
            "completed_at_elapsed_minutes": null,
            "last_long_rest_completed_at_elapsed_minutes": null,
            "interruptions": [], "short_benefit_granted": false,
            "character_id": "character:<slug>", "schema_version": 1 },
  "hit_die_spending": [ { "pool_id": "fighter", "rolls": [4, 7] } ],
  "con_modifier": { "value": 3, "source": "<authoritative source>" }
}
```

`character_id`, `controller` and `rest` are required; `hit_die_spending` and
`con_modifier` are optional and only meaningful when a Short-Rest benefit is
granted (Long-Rest completion may not spend Hit Point Dice). The target is
**absolute**, so replaying one logical transition is idempotent.

The supported Hit Point Die rolls are produced by `scripts/character_rest.py`,
which calls the single shared resolver (`scripts/dice_resolver.py`) and never
touches raw `random.*`. A required Constitution modifier may be supplied only
with declared authoritative source provenance; Rest never stores or invents one.

Every supported Rest consequence is persisted only through POST-EV2-9's dedicated
`mutate_character_mechanics` owner. `mutate_character_rest` computes the resulting
HP / Hit Dice / resource values but never writes the `character_mechanics`
collection directly, so POST-EV2-9's operation marker and exhaustive-writer
contract remain true.

## Controller / authority law

Authority is proven for the target character against authoritative **published**
Run truth (the RT03 `runs` namespace), reusing the shared EV2-10 resolver:

- under a `mainrun` assertion, the character must currently be unclaimed by any
  published Run;
- under a `run` assertion, the character must be controlled by exactly that RUN #;
- a parked played Run that still claims the character fails closed;
- two Runs claiming one character fail closed;
- a malformed published `runs` batch or a duplicated authoritative Run identity
  fails closed rather than falling through to MAINRUN;
- `controller.kind` must be a JSON string exactly `mainrun` or `run`.

There is no stored controller authority, so a former/stale controller write fails
closed.

## Same-save ownership/mutation exclusion

Rest authority is proven against *published* Run truth, so Run-ownership changes
and Rest mutations are mutually exclusive within one save through the shared
POST-EV2-1 Patch 1B contract:

- `mutate_character_rest` fails closed when this save has already staged a
  different `runs` batch;
- once this save has staged a successful Rest mutation, every
  Run-ownership-writing doorway is refused — generic `runs` stage/delete and the
  dedicated RT04 `reconcile_run_resolution` route.

Closure keys on the explicit **Rest-staging operation fact**, not on final value
equality, so a value-equal replay still closes every doorway; the marker is bound
to the save's own database-minted lock token and never leaks into a later save.

No exclusion is invented between `character_rests` and `campaign_clock` /
`character_mechanics`: a legal Rest transaction may coexist with a Campaign Clock
change and a `character_mechanics` change in one save.

## Supported read

`public.dm_runtime_read_character_rest(<character_id>)` is the supported
`service_role`-only published read by exact character identity. It reads only the
current published generation, validates the whole published namespace through the
existing owner contract, and returns the RT01-D runtime metadata envelope plus the
single record, or `record: null` as truthful absence for an untracked character.
Staged/future Rest state is never exposed as runtime truth.

## Bypass closure

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes reject
the `character_rests` key through the existing POST-EV2-1 Patch 1A registry (the
same dedicated-key closure pattern as every other engine-owned domain). The HWB-02
ordinary-save allowlist is preserved unchanged. Both the mutation route and the
read are executable by `service_role` only.

## What this Mission deliberately does not build (Deferred Ownership)

- **Begin Day / Start-of-Day** — POST-EV2-11; it may consume Rest outcomes later
  but does not own Rest.
- **Combat Academy adaptation** — POST-EV2-12.
- **Conditions / Exhaustion / ability-score reduction** — a later status /
  character-mechanics concern. If current state required one of these official
  Long Rest effects and no owner exists, Rest reports/STOPs rather than faking
  completion.
- **Item-owned charges** — a future item mechanic.
- **CCC/frontend presentation and UI** — later; this gate exposes backend
  semantics only.
- **World interruption generation / scheduler** — future work. This gate resolves
  explicit interruption facts; it does not invent encounters while sleeping.
- **Real data intake/seeding** — INTAKE/BTH work.

## Proof

See `supabase/migrations/20260929000001_post_ev2_10_character_rest.sql`,
`tests/post_ev2_10/test_character_rest.py` and
`scripts/character_rest.py` (real PostgreSQL 15 and 17, full forward migration
chain, through the real save/publication/mirror-confirmation spine). Every
character is synthetic; no real RHC Rest state is published.

The suite proves: per-character independence; the at-least-1-HP start rule; the
60-minute Short Rest and 480 + 60-per-interruption Long Rest durations; the
personal 16-hour Long-Rest wait; every interruption cause and the no-benefit
Short Rest interruption; the Long Rest interruption granting Short Rest benefits
and adding required time; all-HP/all-Hit-Dice Long Rest restoration; metadata-
driven recharge only; unknown rest-sensitive state failing closed; shared-resolver
Hit Point Die spending with a sourced Constitution modifier and no raw RNG;
absolute replay idempotency (no double-spend / duplicate interruption hour); abort
residue; published-only, service-role-only reads; Patch 1A dedicated-domain
classification and generic bypass closure; the Patch 1B Run-ownership exclusion in
both orderings including value-equal replay; and coexistence of Rest with the
Campaign Clock and `character_mechanics` in one save.
