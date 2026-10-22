# EV2-13.1 — Timed Applied Status Continuity

EV2-13.1 adds the smallest durable runtime model for **one live time-dependent
`status_effect` application on a mutable target**, on the existing RT01 SAVE /
publish / mirror / confirm spine. It creates no second save engine, no second
controller/ownership ledger, no world-calendar representation, no scheduler and
no parallel persistence path: it is one engine-owned `applied_statuses` runtime
namespace plus one guarded mutation route, one pure due-threshold read, and the
smallest same-save exclusions required to keep controller and elapsed-anchor
semantics unambiguous.

> Architecture sentence: **EV2-13.1 owns the live timed application instance —
> identity, elapsed-time anchors, due-threshold derivation/acknowledgement and
> controller-safe mutation — while RT02's monotonic `elapsed_campaign_minutes`
> remains the only persisted elapsed-time authority and EV2-13.420 remains the
> only mechanical-duration arithmetic contract.**

## The core temporal continuity law

**World-calendar position may later move backward or forward. Experienced elapsed
campaign time never moves backward. Timed status ageing follows experienced
elapsed time only.**

A portal may place the party 400 years earlier (1372 DR -> 972 DR) or forward
(1372 DR -> 1772 DR). If only five experienced minutes passed, RT02 elapsed
advances by five minutes, the status ages five minutes, and there is **no
negative elapsed duration, reverse ageing, rollback, or 400-year automatic
expiry** inferred from calendar displacement. No applied-status field or
calculation derives age from Harptos / Dalereckoning / world-date subtraction.

## What this is / is not

- It **is** one bounded runtime namespace for timed applications, one validated
  mutation route, and one pure due-threshold read.
- It is **not** a world calendar or chronology engine. Harptos / Dalereckoning
  representation, the exact RHC timeline anchor, portal-driven world-date jumps,
  alternate realities and save slots are deferred.
- It is **not** a turn/initiative scheduler. `turn` remains a non-additive
  boundary, never an elapsed-duration unit.
- It is **not** a status-rules engine. Stacking / refresh / replace / ignore,
  concentration, D&D condition automation, saving throws, damage/resource
  consequences and automatic threshold consequences are later status-rules work.
- It is **not** persisted sub-minute time. Thresholds are whole campaign minutes
  and a sub-minute duration fails closed; there is no seconds remainder ledger.
- It **is not** `live_status`. That existing key is generic ordinary-save runtime
  context and is never applied-status authority.

## Application record shape

Each `applied_statuses` record is a stable runtime instance that references (and
never mints or mutates) a `status_effect:<slug>` **definition** identity:

```json
{
  "application_version": 1,
  "application_id": "AS01",
  "definition_id": "status_effect:test-chill",
  "target_entity_id": "character:test-hero",
  "source_entity_id": null,
  "applied_at_elapsed_minutes": 1000,
  "thresholds": [
    { "threshold_id": "T1", "due_at_elapsed_minutes": 2440 },
    { "threshold_id": "T2", "due_at_elapsed_minutes": 5320 }
  ],
  "acknowledged_thresholds": [
    { "threshold_id": "T1", "acknowledged_at_elapsed_minutes": 5500 }
  ],
  "ended_at_elapsed_minutes": null
}
```

- `application_id` — stable, unique runtime application identity. The namespace
  holds exactly one authoritative record per identity; a duplicate is an
  ambiguity and fails closed.
- `definition_id` — a reference to a persistent EV2-04.1 `status_effect`
  **definition**. The route never creates, mutates or removes a definition.
- `target_entity_id` — a `character:` / `creature:` mutable-actor identity, the
  same space EV2-08 `mutable_owner_entity_ids` uses.
- `source_entity_id` — optional known source identity. Unknown stays Unknown
  (stored as `null`); a source is never invented.
- `applied_at_elapsed_minutes` — the engine-derived absolute experienced-time
  anchor, stamped from authoritative published RT02 `elapsed_campaign_minutes`.
- `thresholds[].due_at_elapsed_minutes` — absolute elapsed-time due anchors in
  whole campaign minutes, derived once from the application anchor plus an
  EV2-13.420-normalized duration. They are **absolute anchors**, never
  remaining-duration countdowns.
- `acknowledged_thresholds` — explicit acknowledgement state that distinguishes
  “due but unprocessed” from “already acknowledged”, stamped with the
  authoritative elapsed cursor at acknowledgement. Acknowledgement performs **no**
  automatic gameplay consequence.
- `ended_at_elapsed_minutes` — explicit end/removal lifecycle, stamped from the
  authoritative elapsed cursor. Ending is terminal.

The record deliberately contains **no** world-calendar/date field anywhere.

## Mutation route

`public.mutate_applied_status(<lock_token>, <request>)` is the **only** way to
stage `applied_statuses`. It runs inside the normal campaign save lifecycle:

```
begin_campaign_save -> mutate_applied_status -> publish_campaign_save
                    -> existing runtime-published mirror / confirmation handshake
```

Request shape:

```json
{
  "application_id": "AS01",
  "controller": { "kind": "mainrun" }
              | { "kind": "run", "run_id": "R01" },
  "definition": {
    "definition_id": "status_effect:test-chill",
    "target_entity_id": "character:test-hero",
    "source_entity_id": null,
    "thresholds": [
      { "threshold_id": "T1", "amount": 1, "unit": "day" }
    ]
  },
  "acknowledge": ["T1"],
  "end": false
}
```

- `application_id` and `controller` are always required. `definition` is required
  when the application does not yet exist and, when supplied on an existing
  application, must exactly reproduce the immutable timing definition (a replay).
  `acknowledge` and `end` are optional and additive.
- Durations are **relative** whole durations. The engine normalizes them through
  EV2-13.420's `mechanical_duration_to_campaign_minutes(...)`; it never
  duplicates time arithmetic and never trusts a caller-supplied absolute anchor,
  acknowledgement anchor, end anchor, world date or elapsed minute.
- The timing definition is **immutable after creation**. Re-sending it is an
  idempotent replay; changing it fails closed, because reapplication / refresh /
  stacking policy is explicitly deferred.
- A future threshold cannot be pre-acknowledged: due detection and
  acknowledgement are separate, and acknowledgement requires the threshold to be
  due at the authoritative current elapsed cursor.

## Controller / handoff law

One application record is **global to the target in the single campaign reality**.
It is never copied into MAINRUN and RUN-local versions.

If the target moves `CAMPAIGN MAINRUN -> RUN #A -> RUN #B -> CAMPAIGN MAINRUN`, the
same application remains one runtime record. After each published handoff, only
the target's **current authoritative controller** — resolved from published Run
truth through the shared EV2-10 resolver — may mutate, acknowledge or end it:

- under a `mainrun` assertion the target must currently be unclaimed by any
  published Run;
- under a `run` assertion the target must be controlled by exactly that RUN #;
- a parked played Run that still claims the target fails closed (it is not a
  current controller, and its stale claim means MAINRUN is not provably the
  controller either);
- two Runs claiming one target, a malformed published `runs` batch, and a
  duplicated authoritative Run identity all fail closed rather than falling
  through to MAINRUN;
- there is no stored `controller` field inside the record, so stored controller
  and published Run truth can never disagree. A former/stale controller write
  fails closed.

## Timing / catch-up law

A forward experienced-time jump does **not** tick once per minute.

- application anchor `1000`; thresholds due at `2440` and `5320`; published Clock
  jumps from `1100` to `5500`. `public.read_timed_applied_status(...)`
  deterministically exposes **both** still-unacknowledged thresholds as due,
  computed from the current elapsed cursor in one read.
- once a threshold is acknowledged through the guarded route, a later read never
  re-presents it as unprocessed; later thresholds stay discoverable.
- due-ness is derived from the current elapsed cursor. There is no per-minute
  scheduler/ticker and no write amplification.

## Read surface

`public.read_timed_applied_status(<application_id>)` is the service-only pure
read. It reads only the published `applied_statuses` namespace and the published
Clock, returns the application with a derived `age_elapsed_minutes`, and exposes
`due_thresholds` and `pending_thresholds` derived from elapsed minutes. A
truthful absence returns `application: null`. It mutates nothing.

## Same-save exclusions

Status mutation is mutually exclusive, in the same campaign save and in **both
orderings**, with:

- **Run-ownership mutation** — authority is proven against published Run truth,
  so a same-save `runs` change would invalidate it; and once applied status is
  staged, every Run-ownership-writing doorway is refused (generic `runs`
  stage/delete and the dedicated RT04 `reconcile_run_resolution` route).
- **Campaign Clock mutation** — timing anchors are derived from the published
  Clock, so a same-save `campaign_clock` change would invalidate them; and once
  applied status is staged, `stage_campaign_clock` is refused.

Closure keys on the explicit **applied-status-staging operation fact**, not on
final value equality, so a value-equal replay (or a mutate-away-and-back) still
closes every doorway. The marker is bound to the save's own database-minted lock
token and never leaks into a later save. Perform the handoff or Clock advance
first, publish/confirm it, then mutate/acknowledge the status against the new
published truth in a later save.

## Bypass closure

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes reject
the `applied_statuses` key (the same dedicated-key closure pattern as
`campaign_clock`, `run_reconciliations`, `inventory`, `item_custody`,
`item_admissions` and `entity_state`). The HWB-02 ordinary-save allowlist is
preserved unchanged, and `live_status` cannot become applied-status authority.
Both the mutation route and the read are executable by `service_role` only.

## What EV2-13.1 deliberately does not build

- **World calendar** — Harptos / Dalereckoning representation, world-date
  placement, the exact RHC timeline anchor, portal-driven chronology changes —
  later world-calendar / temporal-jump / INTAKE-01 work.
- **Turn-boundary semantics** — start/end of turn, initiative boundaries. `turn`
  stays non-additive.
- **Stacking / refresh / replace / ignore, concentration, D&D condition
  automation, saving throws, damage/resource effects, automatic threshold
  consequences** — later status-rules work.
- **Alternate realities / save slots / prequel-sequel branches** — POST-EV2 Full
  Run Instance / Save-Slot Architecture.
- **Generic deferred events, NPC/business/travel scheduling, autosave** — later
  scheduler work.
- **Persisted sub-minute elapsed state** — only if a real consumer proves whole
  minutes insufficient; a separate Mission.
- **A new controller/ownership ledger, a second persistence/mirror path, or
  per-Run status copies** — never; published Run truth is the only controller
  authority and RT01 is the only save spine.
- **Real RHC status application** — BUILD proof is synthetic only.

## Proof

See `supabase/migrations/20260920000002_ev2131_timed_status_continuity.sql`,
`tests/ev2131/test_timed_status_instances.py`,
`tests/ev2131/test_temporal_continuity.py` and
`tests/ev2131/test_controller_handoff.py`. The proof runs the complete forward
migration chain on real PostgreSQL 15 and PostgreSQL 17, through the real
save/publication/mirror-confirmation spine, with synthetic applications only. It
covers authoritative elapsed anchoring, missing-Clock fail-closed, unique
replay-safe identity, definition/application separation, mutable-actor target
restriction, EV2-13.420 duration normalization, engine-derived
acknowledgement/end anchors, definition immutability, forward-jump catch-up of
every crossed threshold, acknowledgement without replay, calendar-field absence
and backwards-date impossibility, generic/gateway bypass closure, controller
handoffs and stale-controller rejection, same-save Run/Clock exclusion in both
orderings, and publication integrity. No real RHC status is published.