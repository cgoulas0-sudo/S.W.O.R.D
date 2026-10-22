# POST-EV2-11 — Begin Day + Fresh-DM Boot

POST-EV2-11 adds the smallest safe **Start-of-Day orchestration** RHC was missing:
one command that opens exactly the next live campaign day, initializes only the
existing day-boundary owners, dispatches configured daily mechanics without
stealing their rule ownership, persists once through the existing RT01/RT02
spine, and returns a bounded **Fresh-Day DM Boot Packet**.

It creates **no new runtime key, mutation domain, Save Gateway, controller
ledger, time source, RNG root, Hook lifecycle or persistence/mirror path**, and
adds no same-save compatibility edge. Begin Day is a **conductor, not another
truth owner**.

> Architecture sentence: **Begin Day = current world + yesterday's finalized
> memory + today's initialization. It reads the exact previous finalized
> `canon/days/day_XXX.md`, changes only the day-boundary fields of the existing
> owners plus the RT02 Campaign Clock, dispatches only configured daily
> consumers through POST-EV2-8, publishes once through RT01 with RT02 as the only
> day authority, requires the existing mirror/verifier confirmation, and returns
> a derived boot packet that is never persisted as truth.**

## Why this exists

RHC already had Final Save / day archive, RT01 publication, RT02 Campaign Clock,
compact current-runtime reads, project/history retrieval, one RNG root, Rest,
Hooks and current-state owners — but no single safe day-opening command for a
fresh DM/AI. Begin Day closes that gap without inventing a new day owner.

## Live lifecycle

```
published Day N + finalized canon/days/day_N.md exists
  -> Begin Day N+1
  -> validate exact +1 and day-boundary owner coherence
  -> read the exact finalized Day N memory
  -> INITIALIZE today's live handoff (existing owners + RT02 Campaign Clock)
  -> dispatch only configured daily consumers in deterministic bounded order
  -> required randomness through POST-EV2-8
  -> publish ONCE through RT01 / RT02
  -> mirror / read-back / verifier confirm
  -> return Fresh-Day DM Boot Packet
```

**Retry:** if Day N+1 is already healthy/published, Begin Day rehydrates the
existing published result and never reruns daily mechanics or produces a second
set of rolls. Rehydration restores the **exact finalized previous-day memory**
(identity, path and content) in the boot packet; if that record cannot be proven,
the rehydration fails closed instead of returning a degraded packet.
**Historical intake** of already-played days is separate (POST-EV2-11.5) and
never invokes this live lifecycle.

## Read, then conduct

### Supported read (service-only)

`public.dm_begin_day_read()` is the one service-only, stable, published-only read
of the current day-boundary bundle:

```
{
  "read_version": 1,
  "mode": "begin_day",
  "runtime": { ... RT01-D metadata ... },
  "current": {
    "published_day", "campaign_clock", "daily_recap", "day_resolution",
    "live_status", "dm_meta", "narrative_hooks"
  },
  "coherence": {
    "coherent", "unknown_day", "clock_day",
    "owner_current_days", "issues"
  }
}
```

It never reads staged/future rows, adds no runtime key, and stages nothing.
`coherence.coherent` is false when the derived `published_day` disagrees with the
semantic `campaign_clock.day`, when a present owner's `current_day` disagrees
with the semantic Clock day, or when an **active** day-boundary owner (present,
non-empty published state) carries a `current_day` that is missing, malformed or
otherwise unparseable — an unverifiable owner day is incoherence, not implicit
agreement. Unknown (null) day remains valid truth and is reported as such; the
conductor fails closed on it.

### Conductor (`scripts/begin_day.py`)

`open_next_day(requested_day, *, runtime, finalized_store, consumers=(),
dispatch_rng=None, resolver=None)` returns the boot packet or raises
`BeginDayError`:

- requested day == published day → **rehydrate** (confirm mirror, restore the
  exact finalized previous-day memory, no mechanics);
- requested day == published day + 1 → **open** the next day;
- anything else (skip/backwards) → **fail closed**;
- previous day missing/unfinalized → **fail closed**;
- Unknown/incoherent current day → **fail closed**;
- unprovable exact confirmed generation (publish reported no exact generation,
  or a later publication moved the world) → **fail closed**.

`runtime` is the RT01/RT02 gateway seam. `SqlDayBoundaryRuntime` wires it to the
existing SQL routes (`begin_campaign_save`, `stage_campaign_state`,
`stage_campaign_clock`, `publish_campaign_save`, `abort_campaign_save`) plus the
POST-EV2-11 read; the existing runtime-published worker owns mirror confirmation.
The seam enforces the durable transaction boundary: under default (non-autocommit)
DB-API behavior it commits the client transaction when the gateway publication
succeeds and after the confirmation worker agrees, so a successful Begin Day is
only ever reported for a durably committed, mirror-confirmed generation — never
for uncommitted client state. The returned boot packet is pinned to the exact
confirmed published generation; any concurrent/later publication fails the
pin check closed instead of mixing generations.

## What Begin Day changes — and what it never does

**Changes only day-boundary fields** of the existing owners:

- `campaign_clock` — day set to N+1 through `stage_campaign_clock`; elapsed
  minutes, broad phase and `long_rests_completed` are carried forward exactly,
  never invented.
- `daily_recap` — status `active`, `current_day` N+1, cleared current summary,
  `previous_day_record` pointed at the **exact** finalized Day N path that was
  actually read (any legal `day_<digits>.md` width — leading zeroes legal, no
  digit-count ceiling — is accepted by numeric day identity, and a numeric day
  with more than one legal file fails closed as ambiguous), and
  an immutable `carryover_active_hooks_at_start` snapshot taken from the Hook
  owner.
- `day_resolution` — status `active`, `current_day` N+1, cleared current buckets.
- `narrative_hooks` — `day_status` active and `current_day` N+1; active/dormant
  hooks preserved; the current-day closure bucket cleared. It never becomes a
  second Hook ledger.
- `live_status` / `dm_meta` — `current_day` N+1 only, and only when already
  active; unrelated content is carried forward untouched.

**Never:** creates a competing open-day Markdown file; grants/completes/infers
Rest or sleep; changes Campaign Day outside RT02; invents elapsed duration,
phase, chronology or temporal position; rerolls or re-applies daily mechanics on
retry; uses a HOT Run as the previous-day history source; uses broad retrieval to
rediscover the known previous-day record; absorbs Business/Combat/Rest rules; or
persists the boot packet as truth.

## Daily consumers (bounded extension seam)

A daily consumer is any object with a stable `consumer_id` and
`resolve(context, dispatch)`. Begin Day:

- orders consumers deterministically by `consumer_id`, rejects duplicates, and
  bounds the count (`MAX_DAILY_CONSUMERS`) and produced effects
  (`MAX_DAILY_EFFECTS`);
- passes a declared **dispatch seam** (`DailyDispatchSeam`), the only path to
  randomness, which calls the single shared resolver `scripts/dice_resolver.py`
  (POST-EV2-8). No raw `random.*` is ever used by a consumer or the conductor;
- merges the consumer's own `rng_rolls` / `mechanical_resolutions` /
  `persistent_effects_applied` / `notes` declarations into `day_resolution`,
  stamping the owning `consumer_id`, without owning the mechanic's rules.

A consumer may also return one optional **`state_patch`** beside those four
audit arrays: a flat object of top-level **`live_status`** keys to replace. Begin
Day *transports* the declared current-state change through the same RT01
publication path; it never interprets the mechanic. This channel is deliberately
narrow:

- **`live_status` only, and only when already active.** A patch returned while
  `live_status` is absent/empty fails closed; Begin Day never initializes an
  owner on a consumer's behalf, and never routes the patch to another owner or a
  dedicated namespace.
- **Top-level keys by replacement, no deep merge.** Each named key's value
  replaces that key wholesale; unmentioned keys are carried forward untouched.
  The patch is bounded (`_MAX_STATE_PATCH_KEYS`) and every value is deep-copied
  so the consumer cannot alias the staged candidate.
- **Conductor/schema fields are protected.** A patch may never overwrite
  `current_day` (the day-boundary field Begin Day owns) or `schema_version`; one
  `live_status` key may be written by only one consumer per day, so conflicting
  writes fail closed.
- **No replay.** On retry, consumers are never rerun, so the patch is neither
  recomputed nor reapplied; the already-published `live_status` truth is what the
  rehydrated boot packet reads back.

Unknown unrelated result fields are still refused. A refused patch aborts the
candidate before publication, so a bad or conflicting patch never partially
publishes.

**Production may have zero configured consumers.** With zero consumers there is
zero RNG and zero invented daily event. POST-EV2-12 Business can later attach as
a consumer without moving its rules into Begin Day.

## Fresh-Day DM Boot Packet

Derived read output, never persisted:

```
{
  "packet_version": 1,
  "mode": "fresh_day_boot" | "rehydrated_day_boot",
  "day": <N+1>,
  "previous_day": { "day": N, "finalized_record_path", "finalized_record" },
  "current_context": { published_day, published_generation, runtime,
                       campaign_clock, daily_recap, day_resolution,
                       narrative_hooks, live_status, dm_meta },
  "today_mechanics": { rng_rolls, mechanical_resolutions,
                       persistent_effects_applied, notes }
}
```

It contains the **full** previous finalized-day record, compact today's
authoritative published context, and today's resolved mechanics. Older history is
on demand through POST-EV2-6 and is deliberately **not** part of the default boot
payload.

`previous_day.finalized_record_path` is the **exact** path that was read. The
reader resolves a finalized day by **numeric day identity** across every legal
`canon/days/day_<positive integer>.md` spelling (leading zeroes are legal and
there is no digit-count ceiling), so the path returned and persisted is the one
that actually exists on disk — a legal unpadded archive is never reported or
persisted as a fabricated padded pointer, and vice versa. If more than one legal
file resolves to the same numeric day, Begin Day **fails closed as ambiguous**
rather than silently choosing one.

## Authority and boundary

- RT02 owns Campaign Day and elapsed-time facts; RT01 owns publication.
- Finalized prior-day history belongs to `canon/days/day_XXX.md`.
- `daily_recap` owns only the current active-day handoff; `narrative_hooks` owns
  Hook lifecycle; each daily mechanic owns its own rules.
- POST-EV2-8 owns RNG; POST-EV2-10 owns Rest and is independent; POST-EV2-6 owns
  older/project-wide retrieval; RT04/POST-EV2-2 own Run reconciliation/HOT.
- Begin Day adds no runtime state key, mutation domain, Patch 1A registry entry,
  Patch 1B compatibility edge, or patch-1A/1B change. Reuse, never duplicate.

## Deferred ownership

- **POST-EV2-11.5** — historical played-day backfill / bulk finalized-history intake.
- **POST-EV2-12** — Business/Economy templates + resolution; may attach later as a daily consumer.
- **POST-EV2-10** — Rest / Long Rest.
- **Combat gates** — combat semantics.
- **RT04 / POST-EV2-2** — Run reconciliation / HOT semantics.
- **POST-EV2-6** — older / project-wide story retrieval.
- **POST-EV2-4A** — temporal / timespace placement.
- **CCC / frontend** — UI.
- **Future scheduler / deferred events** — separate owner.

## Proof

See `supabase/migrations/20260929000002_post_ev2_11_begin_day.sql`,
`scripts/begin_day.py` and `tests/post_ev2_11/test_begin_day.py` (pure
orchestration proof plus real PostgreSQL 15 and 17 with the full forward
migration chain and one end-to-end publication through the RT01/RT02 spine).
Every character/day is synthetic; no real RHC day is opened and no real
`canon/days/day_XXX.md` is created or edited by BUILD proof.

The suite proves: only the next day opens; skip/backwards fails closed; a
missing/unfinalized previous day fails closed; an Unknown/incoherent current day
fails closed; an active day-boundary owner with a missing/malformed/unparseable
`current_day` fails closed (and empty/absent owners do not participate); the day
changes only through RT02 with no invented elapsed/phase/Rest; day-boundary
owners reconcile without rewriting unrelated entities; the carryover Hook
snapshot derives from the Hook owner; the previous day's closed bucket does not
leak; zero consumers means zero RNG; a synthetic consumer uses the shared
resolver via the declared seam with no raw RNG; consumer order is
deterministic/bounded; retry never creates a second RNG/consequence set and
restores the exact finalized previous-day memory (a degraded rehydration fails
closed); abort leaves Day N published truth unchanged (including under default
transactional DB-API behavior); a mirror confirmation failure is not reported as
success; publication is durable before any success is reported (a successful
Begin Day survives a caller rollback on the same connection); the boot packet is
derived, complete and pinned to the exact confirmed published generation (a
concurrent/later publication fails closed instead of mixing generations); every
legal finalized-day width is resolved by numeric day identity and a numeric day
with more than one legal file fails closed as ambiguous; the
exact previous-day record needs no POST-EV2-6 search; older history stays
delegated; HOT Run truth is not used as day history; Rest/resources do not
change; no real RHC data is seeded; and the POST-EV2-11 published read is
service-role-only.

The optional `live_status` consumer `state_patch` is proven separately in
`tests/post_ev2_11/test_consumer_state_patch.py`: an authorized patch round-trips
through real PostgreSQL 15/17 and the RT01/RT02 spine with exact confirmed
read-back while every unmentioned `live_status` key is preserved; an
inactive/absent `live_status`, an empty/oversized patch, a protected
`current_day`/`schema_version` key, a malformed patch and a conflicting
cross-consumer key all fail closed without partial publication; a refused patch
leaves Day N published truth unchanged; and rehydration reads the published
patch back without rerunning the consumer. The patch is isolated from the
consumer/published/staged mutable data through deep copies.
