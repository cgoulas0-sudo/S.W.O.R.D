# EV2-13 — Save-Gateway-integrated mutable entity state

EV2-13 adds the smallest coherent durable current-state surface for a **mutable
entity** and one validated mutation route on the existing RT01 SAVE / publish /
mirror / confirm spine. It creates no second save engine, no second
controller/ownership ledger, and no parallel persistence or mirror path: it is
one engine-owned `entity_state` runtime namespace plus one guarded, atomic
route that consumes the existing EV2-08/RT03 Run-ownership law.

> Architecture sentence: **EV2-13 does not create a new save system. It creates
> the bounded durable entity-state mutation surface on top of the existing RT01
> SAVE / publish / mirror / confirm spine, with controller authority resolved
> only from authoritative published Run truth.**

## Mental model

- **Entity state is what is true for a mutable entity now.** It is the smallest
  current-state fact set, bound to a `character:` / `creature:` mutable-actor
  identity — the same identity space EV2-08 `mutable_owner_entity_ids` uses.
- **A mutable entity has exactly one current controller:** CAMPAIGN MAINRUN or
  exactly one RUN #. Controller authority is **not stored** as a competing
  ownership ledger: it is resolved from authoritative **published** Run truth,
  exactly as EV2-10/EV2-11 do. Caller prose is never authority.
- **The former controller is historical/reference-only.** A handoff is an atomic
  candidate transition of Run ownership; the old Run may keep historical
  participation but never retains mutable authority, and its later writes fail
  closed because published Run truth no longer grants it authority.
- **Entity state is not a history/event subsystem, not a relationship ledger,
  and not applied status instances.** Time-dependent applied status instances and
  timing/threshold processing are **EV2-13.1**, now implemented as the separate
  engine-owned `applied_statuses` namespace on the same RT01 spine (see
  `docs/EV2-13-1-TIMED-STATUS-CONTINUITY.md`). The two are deliberately distinct:
  `entity_state` is bounded current-state facts, while a timed application is a
  stable elapsed-time instance with its own anchors and lifecycle.

## Record shape

Each `entity_state` record mirrors the repository `state.schema.json` box and is
exactly:

- `entity_id` — required `character:` / `creature:` mutable-entity identity;
- `status` — required, one of `known`, `unknown`, `not_applicable`;
- `entries` — present **only** when `status` is `known`: a required, non-empty,
  unique array of `{ attribute, status, value }`, where each entry's own `status`
  is independently `known` / `unknown` / `not_applicable` and `value` is a plain
  scalar (string/number/boolean) present only when that entry is `known`.

When `status` is `unknown` or `not_applicable`, `entries` must be **absent**; a
present `entries` (even empty) or any invented field fails closed rather than
being canonicalized. Entries are unique under JSON value equality, so a
numerically equal duplicate (`1` and `1.0`) is one fact, not two. The record
deliberately does **not** model HP, resources, conditions, relationships, or
applied status instances.

## One authoritative record per mutable entity

`entity_state` is a JSON array with exactly one record per `entity_id`. A second
record for the same identity is an ambiguity and fails closed. The complete
existing candidate namespace is validated before anything is staged, so
malformed or duplicate unrelated truth fails closed and is never repaired by
overwrite.

## Durable mutation path

`public.mutate_entity_state(<lock_token>, <request>)` is the only way to stage
the engine-owned `entity_state` runtime namespace. It runs inside the normal
campaign save lifecycle:

```
begin_campaign_save -> mutate_entity_state -> publish_campaign_save
                    -> existing runtime-published mirror / confirmation handshake
```

Request shape:

```json
{
  "entity_id": "character:<slug>",
  "controller": { "kind": "mainrun" }
              | { "kind": "run", "run_id": "R##" },
  "state": {
    "status": "known",
    "entries": [ { "attribute": "...", "status": "known", "value": ... } ]
  }
}
```

The target is an **absolute** replacement for one entity's state, so replaying
one logical update is idempotent and cannot drift. `entity_id`, `controller` and
`state` are required; extra fields fail closed.

## Controller / authority law

Authority is proven for the target entity against authoritative **published** Run
truth (the RT03 `runs` namespace), reusing the shared EV2-10 resolver:

- under a `mainrun` assertion, the entity must currently be unclaimed by any
  published Run;
- under a `run` assertion, the entity must be controlled by exactly that RUN #;
- a **parked** played Run that still claims the entity fails closed — it is not a
  current controller, and its stale claim means MAINRUN is not provably the
  controller either;
- two Runs claiming one entity fail closed;
- a malformed published `runs` batch (non-object entry, missing string `run_id`,
  an EV2-08-invalid record) or a duplicated authoritative Run identity fails
  closed rather than falling through to MAINRUN.

`controller.kind` must be a JSON string exactly `mainrun` or `run`; a null,
missing, number, boolean, array, object, or unknown-string kind fails closed
before any authority branch, so a malformed assertion can never be interpreted
as MAINRUN by fallthrough.

## Handoff law

A handoff (MAINRUN -> RUN, RUN -> MAINRUN, or RUN A -> RUN B) is an atomic
candidate transition of Run ownership staged and published through the existing
RT01 spine. After the handoff:

- the new controller is the **only** controller that can author the entity's
  state;
- the former controller's write fails closed (published Run truth no longer
  grants it authority);
- exactly one authoritative `entity_state` record exists for the entity.

No new ownership ledger is introduced. Entity state records do not carry an
independent controller authority, so there is no way for a stored controller and
published Run truth to disagree.

## Same-save ownership/mutation exclusion

Entity-state authority is proven against *published* Run truth, so Run-ownership
changes and entity-state mutations are mutually exclusive within one save:

- `mutate_entity_state` fails closed when this save has already staged a
  different `runs` batch;
- once this save has staged a successful entity-state mutation, every
  Run-ownership-writing doorway is refused for the rest of the save — the generic
  `runs` key and the dedicated RT04 `reconcile_run_resolution` route alike.

Closure keys on the explicit **entity-state-staging operation fact**, not on final
value equality, so a value-equal replay (or a mutate-away-and-back) still closes
every doorway. The marker is bound to the save's own database-minted lock token
and never leaks into a later save. Use separate saves for an ownership handoff
and a mutable entity-state change.

## Bypass closure

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes reject
the `entity_state` key (the same dedicated-key closure pattern as
`campaign_clock`, `run_reconciliations`, `inventory`, `item_custody` and
`item_admissions`), so a caller/model cannot bypass the validated route with a
raw generic runtime write. The HWB-02 ordinary-save allowlist is preserved
unchanged. The route is executable by `service_role` only.

## What EV2-13 deliberately does not build

- **Time-dependent applied status instances / timing / thresholds** — EV2-13.1,
  now implemented as the separate `applied_statuses` namespace
  (`docs/EV2-13-1-TIMED-STATUS-CONTINUITY.md`); `entity_state` stays bounded
  current-state facts and carries no status-instance record.
- **Relationship definitions/lifecycle** — EV2-05.
- **Alternate realities / save slots, inventory/resource-pool expansion, RAG,
  scheduler/autosave, and broader entity schema** — later gates.
- **A new controller/ownership ledger or second persistence/mirror path** — never;
  published Run truth remains the only controller authority.
- **HP / resources / conditions / goals / relationships inside the state box** —
  the box stays the bounded independent-attribute state surface.
- **Inventory mechanics redesign, Hook/Scenario/Run redesign, bulk migration, or
  automatic D&D resolution** — out of scope.

## Proof

See `supabase/migrations/20260919000002_ev213_mutable_entity_state.sql`,
`tests/ev213/test_mutable_entity_state.py` and
`tests/ev213/test_handoff_and_controller_safety.py` (real PostgreSQL, full
forward migration chain, through the real save/publication/mirror-confirmation
spine). No real RHC entity state is published; every entity is synthetic.
