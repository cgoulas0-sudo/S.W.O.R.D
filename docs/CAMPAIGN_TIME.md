# Campaign Time

Rolling High Club's deterministic in-world **Campaign Clock**. It is infrastructure
for in-world time. It never reads wall-clock time, never counts chat/messages, and
never invents narrative outcomes.

The Campaign Clock is one engine-owned runtime state record keyed `campaign_clock`
inside the activated RT01 published-runtime spine. It is mutated only through the
validated `public.stage_campaign_clock(...)` route and published through the normal
guarded Save Gateway. There is no parallel persistence path.

## Two time representations, one state

The clock deliberately keeps two kinds of time together without pretending they are
equally precise:

- **Presentation time** — `day` (nullable, Unknown until established) plus a broad
  `phase`. This is what the DM can safely use for narration and broad sequencing.
- **Monotonic duration** — `elapsed_campaign_minutes`, an engine-only cursor from
  the RT02 Clock epoch that advances only when an in-world duration is actually
  established. It is **not** a minute-of-day clock and not reconstructed history.

The separation prevents a broad statement such as "afternoon" from becoming fake
precision such as 15:42.

## Runtime record

The engine-owned checkpoint record key is `campaign_clock`.

Required state (`schema_version` `1`):

```json
{
  "schema_version": 1,
  "day": null,
  "phase": "unknown",
  "elapsed_campaign_minutes": 0,
  "long_rests_completed": 0
}
```

- `day` — `null` (Unknown) until an RHC campaign day is actually established. When
  known, a non-negative integer coherent with `campaign_runtime.published_day`.
  Never coerced to `0` or `1` merely because a schema prefers a number.
- `phase` — exactly one broad phase: `unknown | dawn | morning | midday | afternoon
  | evening | night | late_night`.
- `elapsed_campaign_minutes` — non-negative monotonic cursor from the **RT02 epoch**,
  not minute-of-day and not reconstructed lifetime history.
- `long_rests_completed` — non-negative monotonic counter from the **RT02 epoch**,
  not a fabricated historical total.

## Safe advancement rules

- Explicit durations advance `elapsed_campaign_minutes` exactly; only in-world
  established duration is a valid source (travel, rests, rituals, downtime, spell
  durations, appointments, and other mechanically established durations).
- A completed Long Rest increments `long_rests_completed`; duration is added only if
  the duration itself is established.
- Day and phase observations advance only when the fiction/mechanics establish them.
- An established day never decreases and never erases back to Unknown.
- A known same-day phase never moves to an earlier known phase and never erases to
  Unknown.
- A later day may begin at any valid phase (for example dawn after night).
- If only a broad phase becomes known, update the phase and leave
  `elapsed_campaign_minutes` unchanged.
- If only an exact duration becomes known, advance the monotonic cursor and do not
  invent a new day/phase.
- If both are known, apply both in the same semantic time update.
- `elapsed_campaign_minutes` never decreases; `long_rests_completed` never decreases.
- Chat length and message count are never time sources. Wall-clock and system time
  are never time sources.

## Mutation and publication

1. Begin the normal RT01 campaign-save lifecycle (`public.begin_campaign_save(...)`).
2. Stage Clock state **only** through `public.stage_campaign_clock(<lock_token>,
   <clock>)`. The argument is the complete absolute target Clock; the transition is
   validated against the authoritative published Clock, so a replay re-stages the
   same value and cannot double-advance a cursor. The generic
   `stage_campaign_state`/`delete_staged_campaign_state` reject the `campaign_clock`
   key.
3. Publish through `public.publish_campaign_save(...)`. Publication **derives**
   `campaign_runtime.published_day` from the candidate Clock day; the Clock remains
   the semantic owner and the locator is derived metadata only. An Unknown (null)
   Clock day keeps `published_day` null.
4. Complete the existing runtime-published Git mirror/read-back/verifier
   confirmation handshake. Only the confirmed published generation is truth.

Abort preserves the previous published Clock and day.

## Read

Read the current published Clock through `public.dm_runtime_read('campaign_clock')`.
The context mode (`public.dm_runtime_read()`) returns the derived `runtime.day`.
Staged/future Clock state is never exposed through the service read facade.

## Mechanical time boundary (EV2-13.420)

RT02 owns persisted elapsed time. A separate, pure **mechanical-time contract**
(`EV2-13.420`) owns deterministic duration arithmetic and nothing else:

- `public.convert_mechanical_duration(amount, from_unit, to_unit)` converts
  exactly among `second`, `round`, `minute`, `hour` and `day` (one round maps to
  six elapsed seconds). A `turn` is never an additive duration unit.
- `public.mechanical_duration_to_campaign_minutes(amount, unit)` is the only
  bridge into this Clock: it yields a whole number of campaign minutes or fails
  closed, bounded to the integer range this Clock actually stores
  (`0..2147483647`). A sub-minute duration such as one round (six seconds) never
  truncates, rounds, or creates hidden precision, and a whole-minute value larger
  than the Clock can persist fails closed rather than being returned unusable.

Neither function persists anything. Campaign minutes still advance only by staging
an absolute target through `stage_campaign_clock(...)`; there is no sub-minute
remainder ledger and no second elapsed-time authority. Turn-boundary expiry rules
belong to EV2-13.1, not to this Clock. See `docs/EV2-13-420-TEMPORAL-CORE.md`.

## Timed applied status continuity (EV2-13.1)

EV2-13.1 consumes this Clock as the **only** experienced-elapsed-time source for
timed applied statuses; see `docs/EV2-13-1-TIMED-STATUS-CONTINUITY.md`.

- A live application's `applied_at` anchor and every acknowledgement/end anchor
  are derived from the published `elapsed_campaign_minutes`, never from caller
  input.
- Age and threshold due-ness are whole-minute elapsed differences; a forward
  elapsed jump exposes every still-unacknowledged crossed threshold from the
  current cursor with no per-minute ticker.
- Missing/Unknown Clock truth fails closed rather than defaulting to elapsed `0`.
- **World-calendar position is not elapsed time.** A later backwards or forwards
  world-date placement changes no elapsed anchor and cannot reverse status ageing,
  produce negative elapsed duration, or infer automatic calendar-based expiry.
  World-calendar/timespace placement is now a separate owner (POST-EV2-4A, below);
  this Clock is never mutated backwards to express a date jump.

## Lane temporal / timespace placement (POST-EV2-4A)

World-calendar and timespace placement is a separate lane-scoped owner and is
**not** part of this Clock. POST-EV2-4A adds the engine-owned `temporal_positions`
runtime namespace, mutated only through `public.mutate_temporal_position(...)` on
the same RT01 spine:

- each play lane (CAMPAIGN MAINRUN or one valid published RUN #) holds its own
  current chronology + timespace position, so two lanes may be in different eras
  or timespaces at the same campaign moment without forking reality;
- a position carries an exact, partial or Unknown local chronology and a
  known/Unknown timespace reference; missing components stay Unknown and no finer
  precision is invented;
- a supported relative whole-year displacement preserves already-known finer
  components; unsupported day/month arithmetic and a relative jump from an
  Unknown year fail closed;
- a temporal placement never mutates Campaign Day, `elapsed_campaign_minutes`,
  `long_rests_completed`, entity state, applied statuses or knowledge. A backward
  date jump is not negative experienced time and a forward jump adds no
  intervening calendar years to elapsed time.

See `docs/POST-EV2-4A-TEMPORAL-TIMESPACE-CONTINUITY.md`.

## Ownership and boundaries

- `campaign_clock` is the semantic Campaign Clock authority.
- `campaign_runtime.published_day` is derived locator/checkpoint metadata only.
- Unknown is valid truth; RT02 does not backfill, infer, or invent current day,
  phase, elapsed minutes, or Long Rest count.
- The counters begin at the RT02 epoch; there is no reconstruction of earlier
  campaign time.
- **Deferred (not owned by the Clock):** Autosave, the Deferred Event Scheduler,
  Rest recovery/resource consequences, turn-boundary/initiative effect ticking
  (EV2-13.1 owns elapsed-time status ageing and threshold continuity, not turn
  semantics), business/economy/day-tick consumers, NPC schedules, and
  current-campaign time backfill. These are separate gates.
