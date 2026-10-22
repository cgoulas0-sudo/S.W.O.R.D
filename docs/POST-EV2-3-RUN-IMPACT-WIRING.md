# POST-EV2-3 — Run impact wiring + knower-safe reconciliation

POST-EV2-3 wires the pieces RHC already owns — the published `runs`
Run/controller authority, EV2-14 owner-local knowledge, RT04 safe Run
reconciliation and the RT01 Save Gateway — so a Run can continue as a real
canonical path, mutate only legally-owned runtime domains, and never leak Run
knowledge into MAINRUN or another character automatically.

> Architecture sentence: **POST-EV2-3 does not create a new persistence
> authority. It creates one dedicated engine-owned `entity_knowledge` runtime
> mutation surface whose record belongs to the knower entity, with controller
> authority resolved only from authoritative published Run truth, and it extends
> POST-EV2-1 Patch 1A/1B by exactly one domain and its audited edges. No second
> Run registry, knowledge system, save engine, generic impact ledger or lock
> service is introduced.**

## Mental model

RHC already answers three independent knowledge questions (EV2-14):

1. **Is it true in the world?** — repository canon / `knowledge/facts.json`.
2. **Who knows/believes/suspects it?** — each knower's own knowledge record.
3. **May the human reader see it?** — the underlying information's
   `META`/`NON_META` exposure.

POST-EV2-3 adds the missing **runtime mutation route** for question 2 without
touching questions 1 or 3:

- **Knowledge belongs to the knower.** The record is stored once, keyed by the
  knower's own stable identity. It is never stored per Run and never duplicated
  per controller.
- **Mutation authority is controller-bound; knowledge lifecycle is not.** Only
  the entity's current controller (MAINRUN or exactly one RUN #, resolved from
  published `runs`) may write the record. Changing Run ownership changes only the
  controller; the record stays attached to the same entity.
- **No automatic propagation.** Fact existence, another entity's knowledge,
  party membership, MAINRUN presence, `dm_meta.run_claims`, BTH/player visibility
  or a Run resolution never grants or copies knowledge.

## Runtime domain

The engine-owned `entity_knowledge` runtime namespace is a JSON array holding
exactly one authoritative EV2-14 record per knower. It is the runtime
representation of the existing `schemas/knowledge.schema.json` contract — not a
second knowledge store, and EV2-14 semantics are consumed unchanged:

- `entity_id` is the knower, in the full EV2-14 identity space
  (`character:` / `location:` / `faction:` / `party:` / `creature:` / `item:`);
- `status` is `known` / `unknown` / `not_applicable`; a `known` record requires a
  non-empty `entries` array, and `unknown` / `not_applicable` forbid `entries`;
- every entry declares `topic` + `epistemic_status`
  (`confirmed | belief | suspicion`) and exactly one content mode:
  - a reusable **fact reference** (`fact_id`), which structurally forbids
    `value` and `visibility` because reader exposure is inherited from the
    referenced fact at read time and is never copied into the knower record;
  - or a concise **local assertion** (`value` plain scalar + `visibility`
    `meta | non_meta`), because the assertion itself is the underlying
    information;
- optional `note` / `source` are non-blank knower-local annotations;
- duplicate exact entries and duplicate topics within one record fail closed
  (a repeated topic is a contradiction, not two independent facts);
- exactly one record per knower; duplicate records for one entity are an
  ambiguity and fail closed.

## Mutation route

`public.mutate_entity_knowledge(<lock_token>, <request>)` is the ONLY way to
stage `entity_knowledge`. It runs INSIDE the normal campaign save lifecycle
(`begin_campaign_save` → mutate → `publish_campaign_save` → existing
mirror/confirmation handshake) and is executable by `service_role` only.

Request shape:

```json
{
  "entity_id": "character:madma",
  "controller": { "kind": "run", "run_id": "R01" },
  "knowledge": {
    "status": "known",
    "entries": [
      { "topic": "ritual_inscription_truth", "epistemic_status": "confirmed", "fact_id": "F012" },
      { "topic": "crystal_ball_private_theory", "epistemic_status": "belief", "value": "it listens", "visibility": "meta" }
    ]
  }
}
```

`entity_id` + `knowledge` form the absolute EV2-14 record. The target is
absolute, so replaying one logical update is idempotent and cannot drift.

### Controller law

Controller truth is resolved from authoritative published `runs` only, via the
shared EV2-10 published-Run resolver:

- under a MAINRUN assertion the knower must be unclaimed by any published Run;
- under a RUN # assertion the knower must be controlled by exactly that RUN #;
- a parked played Run that still claims the knower, two Runs claiming one
  knower, a malformed published `runs` batch, and a duplicated authoritative Run
  identity all fail closed rather than falling through to MAINRUN;
- a non-mutable knower (`location:` / `faction:` / `party:` / `item:`) can never
  be claimed by a published Run, so MAINRUN is its controller and a Run
  assertion for it fails closed;
- `dm_meta.run_claims` is coordination metadata only and never authorizes a
  write.

### Patch 1A / 1B integration

- **Patch 1A:** `entity_knowledge` is registered `dedicated` with the exhaustive
  writer set `[mutate_entity_knowledge]`. The generic `stage_campaign_state` /
  `delete_staged_campaign_state` routes fail closed for the key.
- **Patch 1B:** the shared compatibility contract gains the
  `mutate_entity_knowledge` operation (blocked by a same-save `runs` change) and
  a trailing `entity_knowledge` edge on `stage_runs` / `delete_runs` /
  `reconcile_runs`. Same-save closure keys on the explicit knowledge-staging
  operation fact (bound to the save's own database-minted lock token), so a
  value-equal replay still closes every Run-ownership doorway and never leaks
  into a later save.

## Handoff law

1. the entity has one authoritative EV2-14 knowledge record;
2. the current controller is resolved from published Run truth;
3. the legal controller submits an absolute EV2-14-valid record during an active
   save;
4. validation + same-save compatibility run before staging;
5. RT01 publishes atomically;
6. mirror/confirmation + published-generation read-back prove success;
7. a later MAINRUN ↔ RUN handoff changes the controller only; the record remains
   attached to the same entity;
8. no handoff step copies knowledge to any other entity.

Rejoining MAINRUN therefore carries the returning character's own knowledge
because the entity carries it; it teaches nobody else.

## RT04 boundary

RT04 continues to PRESERVE unsupported consequences (Hook/location/world/Hook
progress and knowledge) in `run_reconciliations` with their validated summary and
missing downstream owner. A free-form `discovery` consequence is evidence/
candidate description only; it is never sufficient structured authority to mint
an EV2-14 knowledge record. POST-EV2-3 does not change RT04's reconciliation
mapping.

## What this Mission changes

| Surface | Change |
| --- | --- |
| `supabase/migrations/20260924000001_post_ev2_3_knower_safe_run_impact.sql` | created — `mutate_entity_knowledge`, Patch 1A `entity_knowledge` domain, Patch 1B knowledge edges |
| `docs/POST-EV2-3-RUN-IMPACT-WIRING.md` | created (this document) |
| `tests/post_ev2_3/test_run_impact_wiring.py` | created (focused proof) |
| `supabase/README.md` | documents the route and the migration frontier |
| `.github/workflows/rt01-runtime.yml` | runs `tests/post_ev2_3/**` on PostgreSQL 15/17 |
| `CHANGELOG.md` / `ENGINE_CHANGELOG.md` | continuity at closeout |
| `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py` | frozen policy-edge snapshot updated to the new frontier |
| `tests/post_ev2_2/test_hot_run_registry.py` | frozen migration/blocker snapshot updated to the new frontier |

No new Run registry, controller ledger, knowledge store, lock service, Hook or
location mutation route, or second Save Gateway is introduced. EV2-14 schemas/docs
and the EV2-09A resolution schema are unchanged.

## Deferred ownership (must not be absorbed here)

- POST-EV2-5 / POST-EV2-6 own selective context / retrieval, including which
  absent-Run knowledge is loaded into a MAINRUN scene packet.
- POST-EV2-7 owns COLD historical Run archive/retrieval.
- Future Hook/location mutation gates own durable Hook progress/finalization and
  location/world-state mutation semantics; RT04 keeps preserving them meanwhile.
- POST-EV2-8 owns disposable non-canon brainstorm realities.
- Real campaign knowledge/data intake remains outside this gate.
- A later writable shared domain defines its own collision semantics; no generic
  lock layer is pre-built here.

## Proof

`tests/post_ev2_3/test_run_impact_wiring.py` proves on real PostgreSQL 15 and 17
with disposable schemas and synthetic data only: Patch 1A classification and
generic bypass closure; happy-path publication through RT01; EV2-14 negative
shapes (invalid epistemic status/visibility, fact-reference visibility
duplication, structured value, blank topic, duplicate topics/records); MAINRUN and
RUN controller law; `run_claims` non-authority; different/stale/parked/ambiguous/
malformed Run rejection; both same-save orderings; handoff without propagation;
BTH/fact-existence non-propagation; RT04 preservation and no prose-to-knowledge
promotion; generation/mirror/read-back integrity and failure isolation; and
service-role-only execution.