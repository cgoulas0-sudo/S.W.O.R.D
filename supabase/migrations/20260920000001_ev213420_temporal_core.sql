-- EV2-13.420 — Temporal Core Foundation
-- Rolling High Club deterministic mechanical-time contract on the existing
-- RT01/RT02 spine.
--
-- This migration adds the smallest pure mechanical-duration contract that
-- EV2-13.1 can safely consume. It creates NO table, runtime key, save route,
-- mirror path, scheduler, controller ledger, status-instance record or second
-- elapsed-time authority. Every function here is deterministic/pure and mutates
-- nothing.
--
-- ARCHITECTURE (the bounded contract):
--   * Mechanical time != world calendar. This is elapsed duration only; Harptos /
--     Dalereckoning / archive chronology / temporal jumps are deferred.
--   * Round != turn. A round represents about six seconds and CONTAINS the
--     participants' turns. A turn is not an additive elapsed-duration unit.
--   * Canonical engine arithmetic: one round maps to six elapsed seconds.
--   * Duration vocabulary is bounded to second, round, minute, hour, day.
--   * One canonical conversion primitive plus one narrow RT02 whole-minute
--     bridge; no ladder of per-pair helpers.
--   * No silent precision loss: a conversion that is not an exact whole number of
--     the target unit fails closed rather than truncating/rounding/inventing
--     hidden precision.
--   * No 32-bit overflow scar: arithmetic is wide enough (numeric intermediate,
--     bigint result) that representable valid conversions do not fail merely
--     because an int4 multiplication overflows; genuinely out-of-range results
--     fail cleanly instead of wrapping.
--   * RT02 remains the only persisted elapsed-time authority. This migration
--     never touches `campaign_clock`, `elapsed_campaign_minutes`,
--     `stage_campaign_clock` or `publish_campaign_save`, and introduces no
--     sub-minute remainder ledger.
--
-- WHAT this migration adds:
--   1. `public._rhc_mechanical_unit_seconds(text)` — internal bounded unit
--      vocabulary. `turn` is rejected explicitly, unknown units fail closed.
--   2. `public.convert_mechanical_duration(numeric, text, text)` — the canonical
--      exact duration-conversion primitive. Validates a whole, non-negative
--      amount, converts second/round/minute/hour/day exactly, and fails closed on
--      any non-whole result or out-of-range magnitude.
--   3. `public.mechanical_duration_to_campaign_minutes(numeric, text)` — the
--      narrow RT02 bridge. It yields a whole number of campaign minutes or fails
--      closed (for example one round is six seconds and cannot become a whole
--      campaign minute). It persists nothing; RT02's `stage_campaign_clock(...)`
--      absolute-target law remains the only way campaign minutes advance.
--
-- These functions are executable by `service_role` only and mutate no state.

-- ---------------------------------------------------------------------------
-- 0. Bound the elapsed-duration unit vocabulary (internal). All arithmetic in
--    this Mission is expressed from this single seconds table, so second/round/
--    minute/hour/day are the only legal units and every other token fails closed.
--    `turn` gets an explicit message because mistaking a turn for an additive
--    six-second duration is the exact regression scar this Mission exists to
--    prevent.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_mechanical_unit_seconds(p_unit text)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_unit is null then
    raise exception 'mechanical duration unit is required';
  end if;
  if p_unit = 'second' then
    return 1;
  elsif p_unit = 'round' then
    -- Official combat semantics: a round represents about six seconds and
    -- contains the participants' turns. This is an engine conversion convention,
    -- not a claim that each participant's turn adds another six seconds.
    return 6;
  elsif p_unit = 'minute' then
    return 60;
  elsif p_unit = 'hour' then
    return 3600;
  elsif p_unit = 'day' then
    return 86400;
  elsif p_unit = 'turn' then
    raise exception
      'turn is not an elapsed-duration unit; a turn occurs inside a roughly six-second round and is never an additive duration unit';
  else
    raise exception
      'unknown mechanical duration unit %; the elapsed-duration vocabulary is second, round, minute, hour, day',
      p_unit;
  end if;
end;
$$;

revoke all on function public._rhc_mechanical_unit_seconds(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 1. Canonical exact duration-conversion primitive.
--
--    `p_amount` is a whole, non-negative number of `p_from_unit`; the result is
--    the exact whole number of `p_to_unit`. Because every unit is defined from a
--    single seconds table, there is exactly one correct answer per pair and no
--    per-pair ladder to drift. A result that is not a whole number of the target
--    unit fails closed rather than silently truncating or rounding.
--
--    Arithmetic is done in infinite-precision `numeric`, so neither a wide
--    seconds intermediate nor a wide but valid same-unit value fails merely
--    because it exceeds bigint. Only the FINAL requested result is range-checked:
--    it must fit in a bigint or the call fails cleanly. Intermediate magnitude is
--    never itself an output-range failure (for example bigint-max days -> days
--    stays representable even though its seconds intermediate is far larger).
-- ---------------------------------------------------------------------------
create or replace function public.convert_mechanical_duration(
  p_amount numeric,
  p_from_unit text,
  p_to_unit text
)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_from_seconds bigint;
  v_to_seconds bigint;
  v_total_seconds numeric;
  v_result numeric;
  v_bigint_max constant numeric := 9223372036854775807;
begin
  if p_amount is null then
    raise exception 'mechanical duration amount is required';
  end if;
  -- Untrusted caller input: reject non-integral and negative magnitudes instead
  -- of coercing them into a valid-looking time.
  if p_amount <> trunc(p_amount) then
    raise exception
      'mechanical duration amount must be a whole number of units, got %',
      p_amount;
  end if;
  if p_amount < 0 then
    raise exception
      'mechanical duration amount must be non-negative, got %',
      p_amount;
  end if;

  v_from_seconds := public._rhc_mechanical_unit_seconds(p_from_unit);
  v_to_seconds := public._rhc_mechanical_unit_seconds(p_to_unit);

  v_total_seconds := p_amount * v_from_seconds;

  if mod(v_total_seconds, v_to_seconds) <> 0 then
    raise exception
      'mechanical duration % % is not an exact whole number of %; refusing silent truncation',
      p_amount, p_from_unit, p_to_unit;
  end if;

  v_result := v_total_seconds / v_to_seconds;
  if v_result > v_bigint_max then
    raise exception
      'mechanical duration % % is out of representable range when expressed in %',
      p_amount, p_from_unit, p_to_unit;
  end if;

  return v_result::bigint;
end;
$$;

revoke all on function public.convert_mechanical_duration(numeric, text, text)
  from public, anon, authenticated;
grant execute on function public.convert_mechanical_duration(numeric, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- 2. Narrow RT02 whole-minute bridge.
--
--    This is the only bridge from a mechanical duration into RT02's elapsed-time
--    world. It succeeds only when the duration is an exact whole number of
--    campaign minutes; a sub-minute result (for example one round = six seconds)
--    fails closed. It persists nothing and invents no sub-minute remainder: a
--    consumer that needs an exact expiry boundary must express it as its own
--    turn-boundary rule, not as hidden Campaign Clock precision.
--
--    It is additionally bounded to the ACTUAL storage range of RT02
--    `elapsed_campaign_minutes`, which RT02 normalizes to a PostgreSQL `integer`
--    (int4). A whole-minute value RT02 cannot persist (above 2147483647) fails
--    closed here rather than being handed back as an unusable result.
-- ---------------------------------------------------------------------------
create or replace function public.mechanical_duration_to_campaign_minutes(
  p_amount numeric,
  p_unit text
)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_minutes bigint;
  v_rt02_minutes_max constant bigint := 2147483647;
begin
  v_minutes := public.convert_mechanical_duration(p_amount, p_unit, 'minute');
  if v_minutes > v_rt02_minutes_max then
    raise exception
      'mechanical duration % % maps to % campaign minutes, above the RT02 elapsed_campaign_minutes range (0..%); a duration RT02 cannot persist fails closed',
      p_amount, p_unit, v_minutes, v_rt02_minutes_max;
  end if;
  return v_minutes;
end;
$$;

revoke all on function public.mechanical_duration_to_campaign_minutes(numeric, text)
  from public, anon, authenticated;
grant execute on function public.mechanical_duration_to_campaign_minutes(numeric, text)
  to service_role;

comment on function public._rhc_mechanical_unit_seconds(text) is
  'EV2-13.420 internal bounded elapsed-duration unit vocabulary expressed from one seconds table: second=1, round=6, minute=60, hour=3600, day=86400. `turn` is explicitly refused as an additive duration unit and unknown units fail closed. Internal-only.';
comment on function public.convert_mechanical_duration(numeric, text, text) is
  'EV2-13.420 canonical deterministic mechanical-duration conversion. Converts an exact whole non-negative amount among second, round, minute, hour and day using infinite-precision numeric arithmetic, failing closed on non-integral/negative input, on any non-whole result, and only when the FINAL requested result is out of bigint range. A wide seconds intermediate or wide valid same-unit value is never rejected merely for exceeding bigint. Pure: mutates nothing and owns no persistence.';
comment on function public.mechanical_duration_to_campaign_minutes(numeric, text) is
  'EV2-13.420 narrow RT02 bridge. Returns the exact whole number of campaign minutes for a mechanical duration or fails closed; a sub-minute result such as one round (six seconds) never truncates or invents hidden Campaign Clock precision. Bounded to the actual RT02 elapsed_campaign_minutes PostgreSQL integer range (0..2147483647): a whole-minute value RT02 cannot persist fails closed. Pure: persists nothing, leaving stage_campaign_clock as the only way elapsed_campaign_minutes advances.';