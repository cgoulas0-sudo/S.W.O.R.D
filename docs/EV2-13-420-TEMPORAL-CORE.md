# EV2-13.420 — Temporal Core Foundation

EV2-13.420 adds the smallest deterministic **mechanical-time contract** that
EV2-13.1 can safely consume, without introducing a second elapsed-time authority.
It is pure SQL: no table, no runtime key, no save route, no mirror path, no
scheduler, no status-instance record. RT02's persisted `campaign_clock` remains
the only place campaign elapsed time is stored.

> Architecture sentence: **EV2-13.420 owns deterministic mechanical-duration
> arithmetic only. It never persists time; RT02's absolute-target
> `stage_campaign_clock(...)` remains the only way `elapsed_campaign_minutes`
> advances.**

## What this is / is not

- It **is** one canonical exact duration converter plus one narrow whole-minute
  RT02 bridge.
- It is **not** a world calendar. Harptos / Dalereckoning dates, the exact RHC
  campaign timeline anchor, archive chronology, temporal jumps, save slots and
  alternate realities are explicitly deferred.
- It is **not** a status-instance or initiative engine. Applied status instances,
  turn-boundary anchors, expiry/threshold processing and stacking are EV2-13.1.
- It is **not** persisted time. No sub-minute remainder ledger is created; a
  duration that does not map exactly to whole campaign minutes fails closed.

## Mechanical time vs. world calendar

Mechanical time is elapsed duration: seconds, rounds, minutes, hours, days. It is
not a date. The human/DM owns campaign meaning and any later exact world-date
anchor; later world-calendar / intake work owns Harptos representation. This
Mission only fixes deterministic arithmetic so a future consumer cannot disagree
with itself about how long a duration is.

## Round vs. turn

Official D&D 2024/5.5e combat is organized into **rounds** and **turns**. A round
represents about six seconds and **contains** each participant's turn. A turn is
therefore a contextual boundary, never an additive elapsed-duration unit.

For deterministic RHC arithmetic, **one round maps to six elapsed seconds**. That
is an engine conversion convention derived from the round's duration; it is not a
claim that each participant's turn adds another six seconds. The duration
vocabulary is deliberately bounded to `second`, `round`, `minute`, `hour`, `day`;
`turn` is rejected as an elapsed-duration unit.

## The bounded API

Both functions are `IMMUTABLE`, mutate nothing, and are executable by
`service_role` only.

### `public.convert_mechanical_duration(p_amount, p_from_unit, p_to_unit) -> bigint`

The canonical exact conversion primitive. `p_amount` must be a whole,
non-negative number of `p_from_unit`; the result is the exact whole number of
`p_to_unit`. Because every unit is defined from one seconds table
(`second=1`, `round=6`, `minute=60`, `hour=3600`, `day=86400`), there is exactly
one correct answer per pair and no per-pair helper ladder to drift.

It fails closed on:

- null amount or unit;
- a negative amount;
- a non-integral amount (`1.5`);
- an unknown unit, or `turn`;
- a result that is not an exact whole number of the target unit
  (for example `7 seconds -> rounds`);
- a **final** result outside the representable `bigint` range.

Arithmetic is done in infinite-precision `numeric`, so only the **final**
requested result is range-checked. A wide seconds intermediate is never itself an
output-range failure: for example `bigint-max days -> days` succeeds because the
requested result is representable, even though its seconds intermediate is far
larger than `bigint`. Likewise a wide but valid result is not rejected merely
because it exceeds `integer`.

Canonical cases:

| call | result |
| --- | --- |
| `convert_mechanical_duration(1, 'round', 'second')` | `6` |
| `convert_mechanical_duration(10, 'round', 'minute')` | `1` |
| `convert_mechanical_duration(1, 'minute', 'round')` | `10` |
| `convert_mechanical_duration(1, 'hour', 'minute')` | `60` |
| `convert_mechanical_duration(1, 'day', 'hour')` | `24` |
| `convert_mechanical_duration(0, 'day', 'second')` | `0` |
| `convert_mechanical_duration(bigint_max, 'day', 'day')` | `bigint_max` (wide intermediate, representable result) |
| `convert_mechanical_duration(1, 'round', 'minute')` | fails closed (not a whole minute) |
| `convert_mechanical_duration(1, 'turn', 'second')` | fails closed (`turn` is not a duration) |

### `public.mechanical_duration_to_campaign_minutes(p_amount, p_unit) -> bigint`

The narrow bridge into RT02's elapsed-time world. It returns the exact whole
number of campaign minutes or fails closed. `10 rounds -> 1 minute` succeeds;
`1 round` (six seconds) fails closed rather than truncating to zero or inventing
hidden precision.

It is also bounded to the **actual storage range of RT02
`elapsed_campaign_minutes`**, which RT02 normalizes to a PostgreSQL `integer`
(int4): the maximum accepted value is `2147483647` and the first value above it
fails closed. A whole-minute result RT02 could not persist is never handed back as
a usable value.

It persists nothing. To advance the persisted cursor, a caller still stages an
**absolute** target through `public.stage_campaign_clock(...)` under RT02's
replay-safe law; there is no parallel persistence path.

## Proof

See `supabase/migrations/20260920000001_ev213420_temporal_core.sql`,
`tests/ev213420/conftest.py` and `tests/ev213420/test_temporal_core.py`. The proof
runs the complete forward migration chain on real PostgreSQL 15 and PostgreSQL 17
and covers round/turn distinction, exact canonical conversions, explicit zero
behavior, fail-closed null/negative/fractional/unknown-unit/non-whole input, the
RT02 whole-minute bridge and its int4 maximum/first-rejected boundaries,
wide-intermediate representability (`bigint-max days -> days`), clean
out-of-range final failure, the absence of new persistent state or mutation
authority, `service_role`-only execution, and pure immutable volatility.

## Deferred ownership

- **EV2-13.1** owns applied status instances, turn-boundary anchors,
  expiry/threshold processing, reapplication/stacking and controller-aware timed
  effect lifecycle.
- **Later world-calendar / intake work** owns Harptos/Dalereckoning representation
  and the exact RHC campaign timeline anchor.
- **Gate 36** consumes an already-proven timeline/calendar contract; it does not
  design calendar mechanics.
- **Future scheduler/autosave work** owns deferred events, scheduling consumers,
  travel/NPC/business timing.
- A finer-grained persisted sub-minute Campaign Clock is not authorized here; a
  real later consumer would need a separate Mission.
