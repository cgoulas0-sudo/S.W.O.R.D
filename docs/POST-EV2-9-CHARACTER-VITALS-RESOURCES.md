# POST-EV2-9 — Character vitals + resources runtime

POST-EV2-9 adds the smallest authoritative operational character-mechanics
capability RHC was missing: **one dedicated runtime owner** that carries the
bounded machine-readable mechanical definition/capacity plus the current
expendable state needed for character vitals/resources, with **one validated
controller-safe mutation route** and **one supported published read**, on the
existing RT01 SAVE / publish / mirror / confirm spine.

It creates no second save engine, no second controller/ownership ledger, and no
parallel persistence or mirror path.

> Architecture sentence: **POST-EV2-9 does not create a new save system. It
> creates the bounded durable character-vitals/resources mutation surface on top
> of the existing RT01 SAVE / publish / mirror / confirm spine, with controller
> authority resolved only from authoritative published Run truth.**

## Why this exists

RHC character sheets can describe Max HP, Hit Dice, spell slots and limited-use
features for humans, but `entity_state` deliberately excludes HP/resources and
there was no deterministic backend owner the future CCC, AI actions or POST-EV2-10
Rest could safely read/mutate. Without this Mission the frontend would have to
parse prose or invent a second resource ledger.

## Mental model

- **Character mechanics is what a tracked character can have and currently has.**
  It is the bounded normalized mechanical subset a runtime consumer needs, bound
  to a `character:<slug>` identity.
- **The player sheet stays the source of what a character can have.** The
  database does **not** infer a build from Markdown or D&D prose. It validates an
  explicitly supplied normalized mechanical snapshot. `characters/*.md` and
  `characters/CHARACTER_STATE_TEMPLATE.json` remain human/player-authoritative
  and are not promoted into a competing persistence path.
- **A tracked character has exactly one current controller:** CAMPAIGN MAINRUN or
  exactly one RUN #. Controller authority is **not stored**: it is resolved from
  authoritative **published** Run truth, exactly as EV2-10/EV2-11/EV2-13 do.
- **Definition/capacity and current expendable state live in the SAME record**, so
  the backend can validate `current <= capacity` and a later Rest gate can consume
  bounded recharge metadata without a second ledger.
- **Unknown is valid truth.** Every capability section carries an explicit
  `known | unknown | not_applicable` status, so an empty pool/counter list under a
  `known` section means "known to be none" and is never interchangeable with
  Unknown.
- **Player agency is human-owned.** The existence of a writable resource counter
  does not authorize the engine to spend a voluntary resource without an owning
  gameplay action/mechanic.

## Record shape

Each `character_mechanics` record mirrors `schemas/character_mechanics.schema.json`
and is exactly:

- `character_id` — required `character:<slug>` identity;
- `hp`, `hit_dice`, `spell_slots`, `resources` — four required capability
  sections, each with its own `status`.

Section semantics:

- `status: known` requires the section payload; its list may be empty (known to be
  none), and values are whole non-negative integers with `current <= maximum`.
- `status: unknown | not_applicable` forbids the payload; a present payload fails
  closed rather than being canonicalized.

Capability classes (bounded V1):

- **HP** — `current`, `maximum` (current <= maximum) and optional `temporary`
  (current state, deliberately not capacity-bounded);
- **Hit Dice** — one or more distinct pools of `{ pool_id, die_faces, current,
  maximum }` so multiclass / multiple die sizes are representable; `die_faces` is
  bounded to `4, 6, 8, 10, 12`;
- **spell slots** — distinct pools keyed by `pool_id` (never by `slot_level`, so
  multiple pools at the same level are representable) carrying `slot_level`
  (1..9), `current`, `maximum` and bounded `recharge_on`;
- **limited resources** — stable `resource_id`, human `label`, `current`,
  `maximum` and bounded `recharge_on`.

`recharge_on` is a unique subset of `short_rest` / `long_rest`; an empty list is
legal for a non-Rest-based generic tracked counter (POST-EV2-10 acts only on
Rest rules it owns). Stable local IDs (`pool_id`, `resource_id`) are lower-slug
and unique within a record. Records are canonically ordered (HP fixed; pools and
counters sorted by their stable IDs / level) so equivalent logical targets
compare stably and replay cannot drift on numeric formatting.

The record deliberately does **not** model class/subclass/feat/spell selection,
combat damage/healing, death saves, conditions/exhaustion/concentration, Rest
lifecycle, item-owned charges, or a full Markdown mirror.

## Durable mutation path

`public.mutate_character_mechanics(<lock_token>, <request>)` is the only way to
stage the engine-owned `character_mechanics` runtime namespace. It runs inside
the normal campaign save lifecycle:

```
begin_campaign_save -> mutate_character_mechanics -> publish_campaign_save
                    -> existing runtime-published mirror / confirmation handshake
```

Request shape:

```json
{
  "character_id": "character:<slug>",
  "controller": { "kind": "mainrun" }
              | { "kind": "run", "run_id": "R##" },
  "mechanics": {
    "hp": { "status": "known", "current": 28, "maximum": 28 },
    "hit_dice": { "status": "known", "pools": [ ... ] },
    "spell_slots": { "status": "not_applicable" },
    "resources": { "status": "known", "items": [ ... ] }
  }
}
```

The target is an **absolute** replacement for one character's record, so
replaying one logical update is idempotent and cannot drift. `character_id`,
`controller` and `mechanics` are required; extra fields fail closed. A
level/build change may replace capacity and current values atomically in one
absolute target; the route validates the new snapshot rather than treating
capacity metadata as permanently immutable.

## Controller / authority law

Authority is proven for the target character against authoritative **published**
Run truth (the RT03 `runs` namespace), reusing the shared EV2-10 resolver:

- under a `mainrun` assertion, the character must currently be unclaimed by any
  published Run;
- under a `run` assertion, the character must be controlled by exactly that RUN #;
- a **parked** played Run that still claims the character fails closed;
- two Runs claiming one character fail closed;
- a malformed published `runs` batch or a duplicated authoritative Run identity
  fails closed rather than falling through to MAINRUN;
- `controller.kind` must be a JSON string exactly `mainrun` or `run`; a null,
  missing, number, boolean, array, object or unknown-string kind fails closed
  before any authority branch.

There is no stored controller authority, so a former/stale controller write
fails closed because published Run truth no longer grants it authority.

## Same-save ownership/mutation exclusion

Character-mechanics authority is proven against *published* Run truth, so
Run-ownership changes and character-mechanics mutations are mutually exclusive
within one save through the shared POST-EV2-1 Patch 1B contract:

- `mutate_character_mechanics` fails closed when this save has already staged a
  different `runs` batch;
- once this save has staged a successful character-mechanics mutation, every
  Run-ownership-writing doorway is refused for the rest of the save — generic
  `runs` stage/delete and the dedicated RT04 `reconcile_run_resolution` route.

Closure keys on the explicit **character-mechanics-staging operation fact**, not
on final value equality, so a value-equal replay still closes every doorway; the
marker is bound to the save's own database-minted lock token and never leaks into
a later save. No compatibility edge with `campaign_clock`, `inventory`,
`item_custody`, `entity_state`, `applied_statuses`, `entity_knowledge` or
`temporal_positions` was invented. Use separate saves for an ownership handoff and
a character-mechanics change.

## Supported read

`public.dm_runtime_read_character_mechanics(<character_id>)` is the supported
`service_role`-only published read by exact character identity. It reads only the
current published generation, validates the whole published namespace through the
existing collection contract, and returns the RT01-D runtime metadata envelope
plus the single record, or `record: null` as truthful absence for an untracked
character. The read never consumes staged/future state as authority, and the
frontend must never query raw `campaign_state_generations` or parse Markdown.

## Bypass closure

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes reject
the `character_mechanics` key through the existing POST-EV2-1 Patch 1A registry
(the same dedicated-key closure pattern as every other engine-owned domain). The
HWB-02 ordinary-save allowlist is preserved unchanged. Both the mutation route and
the read are executable by `service_role` only.

## What this Mission deliberately does not build (Deferred Ownership)

- **Rest / Long Rest lifecycle** (eligibility, interruption/completion and
  application of official Rest consequences) — POST-EV2-10.
- **Semantic relative operations** (take damage, heal, spend a slot/feature use,
  regain a resource, death saves, action economy) — later combat/gameplay gates.
- **Item-owned mutable charges** — a future item-mechanics owner.
- **Conditions/exhaustion/concentration** — status/condition work.
- **CCC/frontend presentation and UI** — later; Gate 9 provides backend
  read/write capability only.
- **Real character normalization/import/seeding** — explicit intake/setup work
  with authoritative source evidence; no real RHC record is seeded by BUILD proof.
- **Character-sheet derivation, leveling/build calculators and D&D rules
  compilers** — separate future capabilities if needed.

## Proof

See `supabase/migrations/20260928000001_post_ev2_9_character_vitals_resources.sql`
and `tests/post_ev2_9/test_character_vitals_resources.py` (real PostgreSQL 15 and
17, full forward migration chain, through the real save/publication/
mirror-confirmation spine). No real RHC character-mechanics state is published;
every character is synthetic.
