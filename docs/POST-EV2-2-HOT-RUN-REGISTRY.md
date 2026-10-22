# POST-EV2-2 — HOT Run registry + reservations

POST-EV2-2 establishes the **smallest operational convention** that lets a fresh
DM/AI answer one question: *which Run is active now, who is in it, and what
stable-ID things is it currently concerned with?* It does this by **reusing the
engine that already exists** — the published `runs` array and the existing
DM-only `dm_meta` runtime key — without creating another registry, save engine,
lock service, ownership ledger or mutation route.

> Architecture sentence: **`runs` remains the only authoritative Run/controller
> registry. `dm_meta.run_claims` is one optional coordination field inside the
> existing DM-only `dm_meta` domain, keyed by Run ID and holding stable target
> IDs only. The existing RT01 Save Gateway stages, publishes, mirrors and reads
> both unchanged; no new runtime key, SQL migration, dedicated mutation route,
> lock mechanism or Patch 1A/1B policy is introduced.**

## Why this exists

The engine already has every required persistence piece:

- `runs` is an already-admitted **generic** runtime key that carries the
  authoritative EV2-08 Run records (stable `run_id`, execution/control state,
  participants, `mutable_owner_entity_ids`, locations and campaign anchor).
- RT03 (`public.dm_runtime_read_run`) already resolves canonical published Run
  truth and treats `runs` as Run authority.
- `dm_meta` is an already-admitted **generic** runtime key and is the committed,
  hidden, durable DM-only handoff surface.
- RT01 `begin` / `stage` / `publish` / `mirror` / `confirm` already persist
  generic runtime state safely, and `dm_runtime_read` / `dm_quick_context`
  already provide the SQL-first DM read boundary.
- POST-EV2-1 Patch 1A owns generic/dedicated runtime-key admission; Patch 1B
  owns same-save compatibility. Neither needs to change.

POST-EV2-2 adds no persistence authority. It defines a convention over data the
runtime already publishes.

## Reservation shape

The repository-owned `dm_meta` shape gains **one optional/current field**:

`run_claims`

Canonical shape:

```json
{
  "run_claims": {
    "R01": ["H04", "location:aethel-guard"],
    "R02": ["S03"]
  }
}
```

Rules:

- object keys are **existing Run IDs** (`R##`);
- values are arrays of **stable semantic IDs only**;
- valid target identity families for this Mission are existing RHC IDs:
  - entity IDs such as `character:`, `creature:`, `location:`, `faction:`,
    `party:`, `item:`;
  - Hook IDs `H##`;
  - Scenario IDs `S##`;
  - Encounter IDs `E##`;
- no repository paths, filenames, prose scopes, permissions, impact modes or
  caller-defined lock semantics;
- absence of a Run key means **no current reservation note for that Run**;
- `run_claims: {}` means **no current Run reservations**.

A claim is **DM coordination metadata only**. It does not grant write authority
and does not change controller ownership.

## HOT view

No persisted HOT registry is created.

A DM/AI derives the HOT picture from the two already-published runtime values:

1. authoritative `runs`;
2. `dm_meta.run_claims`.

A Run is operationally relevant when **any** of the following is true:

- it is a played Run with `control_state = active`;
- it currently owns one or more `mutable_owner_entity_ids`;
- it has a current `dm_meta.run_claims[run_id]` entry.

A parked zero-owner Run with no claim remains historical Run truth but need not
be treated as HOT. An off-screen zero-owner Run with no claim likewise remains
historical truth without becoming HOT merely because its Run record exists.

This is a **read/interpretation convention over existing data**, not a new
persistence authority. Historical Runs are never archived, rewritten or deleted
by a claim change; clearing a claim changes only the reservation note.

## Using the existing save lifecycle

No new mutation route exists. A claim is added, changed or removed by ordinary
**absolute** `dm_meta` staging through the existing Save Gateway:

1. `begin_campaign_save` derives the candidate from published state;
2. `stage_campaign_state(lock_token, 'dm_meta', <full dm_meta value>)` replaces
   the candidate `dm_meta` value (the claim field is part of that value);
3. `publish_campaign_save` advances the published generation once;
4. the mirror/confirm handshake completes as for any other save.

Because `begin` copies the published generation forward, saving only `dm_meta`
carries the existing `runs` array forward unchanged. Clearing `run_claims` can
therefore never delete or alter the historical Run record.

## Authority and boundary

- Published `runs` owns Run identity, control state and mutable actor ownership.
- Existing entity/Hook/Scenario/Encounter IDs own identity.
- `dm_meta.run_claims` owns only the current DM coordination note that a Run is
  concerned with a stable target ID.
- Claim presence never grants mutation authority.
- RT01 remains the only save/publish/mirror/confirm spine.
- `dm_meta` remains the existing DM-only generic notepad/handoff surface;
  `run_claims` is nested coordination metadata, **not** a new runtime domain.
- Stable IDs are references; they do not imply permissions.
- POST-EV2-3 owns the meaning of collisions, impact scope and any future
  write-permission semantics.

## What this Mission changes

| Surface | Change |
| --- | --- |
| `docs/POST-EV2-2-HOT-RUN-REGISTRY.md` | created (this document) |
| `tests/post_ev2_2/test_hot_run_registry.py` | created (focused proof) |
| `state/dm_meta.json` | adds `run_claims: {}` (empty coordination state only) |
| `state/README.md` | documents the `run_claims` field |
| `.github/workflows/rt01-runtime.yml` | runs `tests/post_ev2_2/**` in the existing PostgreSQL 15/17 job |

No SQL migration, no new runtime key, no new SQL function, no controller ledger
and no lock service are introduced. EV2-08 Run schema is unchanged. Patch 1A and
Patch 1B are unchanged.

## Deferred ownership (must not be absorbed here)

POST-EV2-3 owns:

- what an overlap between Run claims means;
- whether a target is full-control, bounded-influence or no-touch;
- canonical path/write-scope identity if repository-path coordination is ever
  needed;
- blocking/conflict semantics and any future authoritative lock/permission
  mechanism.

Historical note (superseded by POST-EV2-7 closeout): this document originally deferred historical Run archive/selective retrieval to POST-EV2-7. POST-EV2-7 later closed zero-code after RT04 + POST-EV2-2 + RT03 + POST-EV2-5 were verified to already satisfy the intended capability; no separate archive lifecycle/owner was added.

POST-EV2-8 owns alternate realities/save-slot concepts.

Real campaign Run/claim intake remains locked until the factory gates are
complete.

## Proof

`tests/post_ev2_2/test_hot_run_registry.py` proves, on real PostgreSQL 15 and 17
with disposable schemas and synthetic data only:

1. `state/dm_meta.json` remains uninitialized/Unknown-safe and adds
   `run_claims: {}` only as empty coordination state;
2. the existing `runs` schema is unchanged (source-pinned) and `runs` /
   `dm_meta` remain the authoritative published runtime values;
3. Patch 1A still classifies `runs` and `dm_meta` as `generic` and no new
   runtime key exists (`run_claims` is `forbidden`);
4. Patch 1B compatibility operations/edges are unchanged;
5. through the real Save Gateway, a synthetic `dm_meta` value containing
   `run_claims` stages and publishes as ordinary existing `dm_meta`;
6. the same published generation may contain synthetic authoritative `runs` and
   `dm_meta.run_claims` without creating a second owner/controller store;
7. RT03 still resolves Run ownership exclusively from published `runs`;
   changing `dm_meta.run_claims` does not change controller authority;
8. a claim can be added, changed and removed by ordinary absolute `dm_meta`
   staging using the existing save lifecycle;
9. clearing `run_claims` does not delete or alter the historical Run record;
10. synthetic examples prove the HOT interpretation: active/owned Run and
    claimed Run are relevant; parked zero-owner/no-claim and off-screen
    zero-owner/no-claim Runs are not HOT;
11. stable-ID examples cover entity, Hook, Scenario and Encounter references;
    no raw path/write-permission fields are introduced;
12. no SQL migration, new runtime key, new SQL function, controller ledger or
    lock service exists in the diff.
