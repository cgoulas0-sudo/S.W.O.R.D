# POST-EV2-4A — Temporal / timespace travel continuity

POST-EV2-4A adds the smallest authoritative runtime contract that lets a play
lane — the CAMPAIGN MAINRUN or one valid published RUN # — hold its own current
world-calendar and timespace placement inside the one canonical campaign
reality, so portals, planar travel, magic and DM-authored effects can move a lane
centuries backward or forward (or into a partly-known or Unknown timespace)
without being confused with Campaign Day identity, RT02 experienced elapsed time,
EV2-13 mutable state, EV2-13.1 status ageing or EV2-14 knowledge.

> Architecture sentence: **POST-EV2-4A does not create a new persistence
> authority, a world calendar or an alternate-reality system. It creates one
> dedicated, engine-owned `temporal_positions` runtime mutation surface holding
> the current world-calendar/timespace placement of a play lane, with RUN lane
> authority resolved only from authoritative published Run truth, and it extends
> POST-EV2-1 Patch 1A/1B by exactly one domain and its audited edges.**

## Time is layered (unchanged)

RHC already layers time deliberately:

- **Campaign Day ID** is archive/gameplay sequence identity, not chronology.
- **RT02 `campaign_clock`** owns persisted experienced elapsed time;
  `elapsed_campaign_minutes` is monotonic and is not a minute-of-day clock or a
  world date.
- **EV2-13.420** owns deterministic mechanical-duration arithmetic only.
- **EV2-13.1** ages live timed statuses only from RT02 elapsed time.
- **`temporal_positions`** (this Mission) owns only the *current lane placement*
  in world-calendar/timespace coordinates.

The separations are consumed unchanged. A world-date jump is **not** elapsed-time
mutation: RT02 never moves backward, a future jump does not add the intervening
calendar years to experienced time, and a past jump does not rejuvenate travelers
or statuses.

## Runtime domain

The engine-owned `temporal_positions` runtime namespace is a JSON array holding
exactly one authoritative position per play lane. It is not a second chronology
engine and not a per-era copy of entity state.

### Lane

- `mainrun` — the normal CAMPAIGN MAINRUN lane; always valid and independent of
  published Run truth.
- `run:<R##>` — one valid published RUN # lane.

MAINRUN and a valid published RUN # may therefore be in different eras/timespaces
at the same campaign moment without forking reality, and their positions never
overwrite one another.

### Position record

```json
{
  "lane": "mainrun",
  "chronology": { "year": 1490, "month": 7, "day": 12, "hour": 9, "minute": 30 },
  "timespace": { "status": "known", "ref": "material-plane" }
}
```

- `chronology` is a bounded object carrying any subset of the integer components
  `year` (signed) and `month` / `day` / `hour` / `minute` (non-negative). A missing
  component is truthful **Unknown**; the engine never invents finer precision, so a
  partial destination stays partial and an empty `chronology` is a wholly Unknown
  local chronology.
- `timespace` is `{"status":"unknown"}` or
  `{"status":"known","ref":"<lower-slug>"}` — a known/Unknown plane or timespace
  reference. No setting-specific plane catalog is encoded.
- There is **no engine default position**: absence of a lane record is truthful
  Unknown, never an invented default date.

No calendar-specific range or month-length rule is enforced. Harptos /
Dalereckoning representation, the exact RHC timeline anchor and non-trivial
month/day calendar adapters remain a later consumer-driven gate.

## Mutation route

`public.mutate_temporal_position(<lock_token>, <request>)` is the ONLY way to
stage `temporal_positions`. It runs INSIDE the normal campaign save lifecycle
(`begin_campaign_save` → mutate → `publish_campaign_save` → existing
mirror/confirmation handshake) and is executable by `service_role` only.

Absolute request:

```json
{
  "controller": { "kind": "mainrun" },
  "target": {
    "chronology": { "year": 1490, "month": 7 },
    "timespace": { "status": "unknown" }
  }
}
```

Relative request:

```json
{
  "controller": { "kind": "run", "run_id": "R01" },
  "relative_year_displacement": -400,
  "relative_from": {
    "chronology": { "year": 1490, "month": 7, "day": 12, "hour": 9, "minute": 30 },
    "timespace": { "status": "known", "ref": "material-plane" }
  },
  "timespace": { "status": "known", "ref": "feywild" }
}
```

`controller` and exactly one of `target` / `relative_year_displacement` are
required. The absolute target is ABSOLUTE, not a delta, so replaying one logical
update is idempotent and cannot drift.

### Supported relative displacement

The only supported relative arithmetic is a signed whole-**year** displacement.
A relative request MUST include `relative_from`, the exact source position
(`chronology` + `timespace`) from which the jump was authorized. The engine
derives one stable absolute target from that pinned source instead of adding the
delta to the latest candidate on every invocation.

On first application, current position must equal `relative_from`. On a retry
after a lost RPC response or uncertain publication, current may already equal the
derived target; that is treated as the same idempotent operation and does not
apply the displacement again. If current matches neither source nor target, the
request is stale/ambiguous and fails closed.

Already-known finer components (month/day/hour/minute) and the source timespace
are preserved deterministically unless an explicit target `timespace` override
is supplied. An Unknown source year fails closed rather than inventing a
destination, and day/month/calendar offsets are not part of the contract.

### Controller / lane law

- `controller.kind` must be a JSON string exactly `mainrun` or `run`; a null,
  missing, number, boolean, array, object or unknown-string kind fails closed
  before any authority branch.
- A MAINRUN assertion needs no Run proof and is independent of a same-save `runs`
  change or Campaign Clock change.
- A RUN # assertion requires the exact Run identity in authoritative PUBLISHED
  Run truth and rejects a parked played Run; a missing/malformed/duplicate/
  non-authoritative published Run batch fails closed through the shared reader.
- `dm_meta.run_claims` is coordination metadata only and never grants temporal
  authority.

## Patch 1A / 1B integration

- **Patch 1A:** `temporal_positions` is registered `dedicated` with the exhaustive
  writer set `[mutate_temporal_position]`. The generic `stage_campaign_state` /
  `delete_staged_campaign_state` routes fail closed for the key.
- **Patch 1B:** the shared compatibility contract gains the
  `mutate_temporal_position` operation (blocked by a same-save `runs` change) and
  a trailing `temporal_positions` edge on `stage_runs` / `delete_runs` /
  `reconcile_runs`. Same-save closure keys on the explicit RUN-scoped
  temporal-staging operation fact (bound to the save's own database-minted lock
  token), so a value-equal replay still closes every Run-ownership doorway and
  never leaks into a later save.
- A **MAINRUN** placement deliberately does not set that operation fact and is
  therefore not blocked by, and does not block, a same-save `runs` or Campaign
  Clock change.

## What this Mission changes

| Surface | Change |
| --- | --- |
| `supabase/migrations/20260925000001_post_ev2_4a_temporal_timespace_continuity.sql` | created — `mutate_temporal_position`, Patch 1A `temporal_positions` domain, Patch 1B temporal edges |
| `docs/POST-EV2-4A-TEMPORAL-TIMESPACE-CONTINUITY.md` | created (this document) |
| `tests/post_ev2_4a/test_temporal_timespace_continuity.py` | created (focused proof) |
| `docs/CAMPAIGN_TIME.md` | documents that world-calendar/timespace placement is now a separate lane-scoped owner |
| `supabase/README.md` | documents the route and the migration frontier |
| `.github/workflows/rt01-runtime.yml` | runs `tests/post_ev2_4a/**` on PostgreSQL 15/17 |
| `CHANGELOG.md` / `ENGINE_CHANGELOG.md` | continuity at closeout |
| `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py` | frozen policy-edge snapshot updated to the new frontier |
| `tests/post_ev2_2/test_hot_run_registry.py` | frozen migration/blocker snapshot updated to the new frontier |

No world calendar, alternate reality identity, second Save Gateway, Run registry,
controller ledger, clock or chronology persistence engine is introduced. RT02
remains elapsed-time authority, EV2-13.420 remains mechanical-duration authority,
EV2-13.1 remains timed-status authority, EV2-14 remains knowledge authority, and
published `runs` remains RUN identity/controller truth.

## Deferred ownership (must not be absorbed here)

- **POST-EV2-4B** owns alternate reality / alternate-history identity.
- Existing future selective-context/RAG gates own era-appropriate retrieval and
  future-knowledge leakage prevention at hydration time.
- **EV2-07** remains Scenario/Encounter prepared-content authority; 4A does not
  rewrite prepared content by era.
- Hook/location/world mutation semantics remain with their own owners.
- Disposable non-canon prequel/sequel brainstorm realities remain with their
  existing separate future gate.
- Full calendar adapters for non-trivial month/day arithmetic belong to a later
  consumer-driven gate.

## Proof

`tests/post_ev2_4a/test_temporal_timespace_continuity.py` proves on real
PostgreSQL 15 and 17 with disposable schemas and synthetic data only: Patch 1A
classification and generic bypass closure; truthful Unknown (no invented default);
an exact MAINRUN destination with byte-for-byte unchanged Campaign Day / RT02
time; partial and Unknown destinations that invent nothing; backward/forward
placement that leaves elapsed time, day, entity state, applied statuses and
knowledge untouched; supported relative whole-year preservation and fail-closed
unsupported arithmetic / Unknown year; independent MAINRUN and RUN # lanes that
never overwrite one another; published-Run authority, parked/malformed/duplicate
rejection and `run_claims` non-authority; same-save RUN-scoped exclusion in both
orderings while MAINRUN placement does neither; replay idempotency; publication
integrity and failure isolation; and service-role-only execution.
