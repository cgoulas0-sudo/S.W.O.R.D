-- RT02 — Campaign Clock Foundation
-- Rolling High Club deterministic in-world time authority on the RT01 spine.
--
-- This migration adds the FIRST validated Clock mutation route without creating
-- any parallel persistence path. The Clock is one engine-owned runtime state
-- record keyed as `campaign_clock` inside the existing generation store, mutated
-- ONLY through this route and published through the existing guarded Save Gateway.
--
-- Clock record shape (schema_version 1):
--   {
--     "schema_version": 1,
--     "day": null | <non-negative integer>,
--     "phase": "unknown" | "dawn" | "morning" | "midday" | "afternoon"
--            | "evening" | "night" | "late_night",
--     "elapsed_campaign_minutes": <non-negative integer>,
--     "long_rests_completed": <non-negative integer>
--   }
--
-- Two time representations deliberately coexist without inferring each other:
--   * presentation day/phase (broad, may be partially unknown);
--   * monotonic `elapsed_campaign_minutes` (engine cursor from the RT02 epoch).
--
-- WHAT this migration changes:
--   1. `public.stage_campaign_clock(...)` — the ONLY validated Clock mutation
--      route. It validates Clock shape and monotonic/coherence invariants against
--      the authoritative published Clock, then stages the candidate value.
--   2. `public.stage_campaign_state(...)` / `delete_staged_campaign_state(...)`
--      now REJECT the `campaign_clock` key, closing the generic bypass.
--   3. `public.publish_campaign_save(...)` now DERIVES `published_day` from the
--      candidate Clock day so the locator never becomes a second day authority.
--
-- No new table, no new Git mirror, no scheduler/autosave, no campaign facts.
-- Unknown remains valid truth: an absent Clock or a null day is never coerced.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight.
--    A pre-RT02 active save's candidate generation may already contain a
--    `campaign_clock` staged through the (pre-RT02) generic staging route. The
--    RT02 publisher only derives `day` and would let that invalid candidate
--    publish. Mirroring RT01-C/D, refuse rather than guess.
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT02 migration refused: resolve the active campaign save before installing the Campaign Clock mutation route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Broad-phase ordering (internal). `unknown` has no order and is never used
--    as an ordering input because regression checks only compare known phases.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_phase_order(p_phase text)
returns integer
language sql
immutable
set search_path = ''
as $$
  select case p_phase
    when 'dawn' then 0
    when 'morning' then 1
    when 'midday' then 2
    when 'afternoon' then 3
    when 'evening' then 4
    when 'night' then 5
    when 'late_night' then 6
    else null
  end
$$;

revoke all on function public._rhc_phase_order(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Clock shape validation + canonical normalization (internal).
--    Returns the canonical Clock object or raises on any invalid field.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_campaign_clock(p_clock jsonb)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_day integer;
  v_phase text;
  v_elapsed integer;
  v_rests integer;
begin
  if p_clock is null or jsonb_typeof(p_clock) <> 'object' then
    raise exception 'campaign_clock must be a JSON object';
  end if;
  if (p_clock ->> 'schema_version') is distinct from '1' then
    raise exception 'campaign_clock schema_version must be 1';
  end if;

  -- day: null (Unknown) or a non-negative integer. Never coerced to 0/1.
  if jsonb_typeof(p_clock -> 'day') = 'null' then
    v_day := null;
  elsif jsonb_typeof(p_clock -> 'day') = 'number'
        and (p_clock ->> 'day') ~ '^[0-9]+$' then
    v_day := (p_clock ->> 'day')::integer;
  else
    raise exception 'campaign_clock day must be null or a non-negative integer';
  end if;

  -- phase: exactly one enumerated broad phase.
  v_phase := p_clock ->> 'phase';
  if v_phase is null then
    raise exception 'campaign_clock phase is required';
  end if;
  if v_phase not in (
    'unknown','dawn','morning','midday','afternoon','evening','night','late_night'
  ) then
    raise exception 'campaign_clock phase must be an enumerated broad phase';
  end if;

  -- elapsed_campaign_minutes: non-negative integer engine cursor.
  if jsonb_typeof(p_clock -> 'elapsed_campaign_minutes') = 'number'
     and (p_clock ->> 'elapsed_campaign_minutes') ~ '^[0-9]+$' then
    v_elapsed := (p_clock ->> 'elapsed_campaign_minutes')::integer;
  else
    raise exception 'campaign_clock elapsed_campaign_minutes must be a non-negative integer';
  end if;

  -- long_rests_completed: non-negative integer engine counter.
  if jsonb_typeof(p_clock -> 'long_rests_completed') = 'number'
     and (p_clock ->> 'long_rests_completed') ~ '^[0-9]+$' then
    v_rests := (p_clock ->> 'long_rests_completed')::integer;
  else
    raise exception 'campaign_clock long_rests_completed must be a non-negative integer';
  end if;

  return jsonb_build_object(
    'schema_version', 1,
    'day', v_day,
    'phase', v_phase,
    'elapsed_campaign_minutes', v_elapsed,
    'long_rests_completed', v_rests
  );
end;
$$;

revoke all on function public._rhc_normalize_campaign_clock(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Validated Clock mutation route (the ONLY way to stage `campaign_clock`).
--
--    The caller supplies the complete TARGET Clock state. The target is
--    absolute, not a delta, so replaying one logical update re-stages the same
--    value and cannot double-advance the monotonic cursors. The transition is
--    validated against the authoritative PUBLISHED Clock (not the candidate),
--    so a partial in-save edit can never relax a published invariant.
-- ---------------------------------------------------------------------------
create or replace function public.stage_campaign_clock(
  p_lock_token text,
  p_clock jsonb
)
returns public.campaign_state_generations
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  out_row public.campaign_state_generations%rowtype;
  v_target jsonb;
  v_base jsonb;
  v_tday integer;
  v_bday integer;
  v_tphase text;
  v_bphase text;
  v_telapsed integer;
  v_belapsed integer;
  v_trests integer;
  v_brests integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  v_target := public._rhc_normalize_campaign_clock(p_clock);

  -- Authoritative base Clock: the published generation's value, else the
  -- truthful Unknown default. No historical time is invented.
  select csg.value into v_base
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation
     and csg.key = 'campaign_clock';
  if v_base is null then
    v_base := jsonb_build_object(
      'schema_version', 1,
      'day', null,
      'phase', 'unknown',
      'elapsed_campaign_minutes', 0,
      'long_rests_completed', 0
    );
  end if;
  v_base := public._rhc_normalize_campaign_clock(v_base);

  v_tday := case when jsonb_typeof(v_target -> 'day') = 'number'
                 then (v_target ->> 'day')::integer else null end;
  v_bday := case when jsonb_typeof(v_base -> 'day') = 'number'
                 then (v_base ->> 'day')::integer else null end;
  v_tphase := v_target ->> 'phase';
  v_bphase := v_base ->> 'phase';
  v_telapsed := (v_target ->> 'elapsed_campaign_minutes')::integer;
  v_belapsed := (v_base ->> 'elapsed_campaign_minutes')::integer;
  v_trests := (v_target ->> 'long_rests_completed')::integer;
  v_brests := (v_base ->> 'long_rests_completed')::integer;

  -- Established day never decreases and never erases to Unknown.
  if v_bday is not null then
    if v_tday is null then
      raise exception 'campaign_clock day cannot be unset once established';
    end if;
    if v_tday < v_bday then
      raise exception 'campaign_clock day cannot move backwards';
    end if;
  end if;

  -- A known same-day phase never moves to an earlier known phase and never
  -- erases to Unknown. A later day may begin at any valid phase.
  if v_tday is not null and v_tday = v_bday and v_bphase <> 'unknown' then
    if v_tphase = 'unknown' then
      raise exception 'campaign_clock phase cannot become unknown on the established day';
    end if;
    if public._rhc_phase_order(v_tphase) < public._rhc_phase_order(v_bphase) then
      raise exception 'campaign_clock phase cannot move backwards within the same day';
    end if;
  end if;

  -- Monotonic engine cursors never decrease.
  if v_telapsed < v_belapsed then
    raise exception 'campaign_clock elapsed_campaign_minutes cannot decrease';
  end if;
  if v_trests < v_brests then
    raise exception 'campaign_clock long_rests_completed cannot decrease';
  end if;

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'campaign_clock', v_target, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now()
  returning * into out_row;

  return out_row;
end;
$$;

revoke all on function public.stage_campaign_clock(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.stage_campaign_clock(text, jsonb) to service_role;

-- ---------------------------------------------------------------------------
-- 4. Close the generic `campaign_clock` bypass. The generic stage/delete must
--    never accept an engine-owned Clock record, malformed or otherwise.
-- ---------------------------------------------------------------------------
create or replace function public.stage_campaign_state(
  p_lock_token text,
  p_key text,
  p_value jsonb
)
returns public.campaign_state_generations
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  out_row public.campaign_state_generations%rowtype;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
  end if;
  if p_key = 'campaign_clock' then
    raise exception 'campaign_clock must be staged through stage_campaign_clock';
  end if;
  if p_value is null then
    raise exception 'campaign state value is required';
  end if;

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, p_key, p_value, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now()
  returning * into out_row;
  return out_row;
end;
$$;

revoke all on function public.stage_campaign_state(text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.stage_campaign_state(text, text, jsonb) to service_role;

create or replace function public.delete_staged_campaign_state(
  p_lock_token text,
  p_key text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_deleted integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
  end if;
  if p_key = 'campaign_clock' then
    raise exception 'campaign_clock is engine-owned and cannot be deleted';
  end if;

  delete from public.campaign_state_generations
   where generation = r.staging_generation
     and key = p_key;
  get diagnostics v_deleted = row_count;
  return v_deleted > 0;
end;
$$;

revoke all on function public.delete_staged_campaign_state(text, text)
  from public, anon, authenticated;
grant execute on function public.delete_staged_campaign_state(text, text) to service_role;

-- ---------------------------------------------------------------------------
-- 5. Publication coherence. `published_day` is DERIVED from the candidate Clock
--    day so the locator can never become an independent second day authority.
--    An absent Clock or a null day keeps `published_day` null (Unknown).
-- ---------------------------------------------------------------------------
create or replace function public.publish_campaign_save(
  p_lock_token text
)
returns public.campaign_runtime
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  out_row public.campaign_runtime%rowtype;
  v_mirror_token uuid;
  v_published_day integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;
  if r.staging_save_kind not in ('campaign_save', 'engineering_release') then
    raise exception 'active campaign save is missing a valid save kind';
  end if;

  -- Derive the published day locator from the candidate Clock day. Because every
  -- Clock value is validated at stage time and copy-forwarded by BEGIN, a Clock
  -- present here is well-formed; the regex guard is defense-in-depth only.
  select case
           when jsonb_typeof(csg.value -> 'day') = 'number'
            and (csg.value ->> 'day') ~ '^[0-9]+$'
           then (csg.value ->> 'day')::integer
           else null
         end
    into v_published_day
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'campaign_clock';

  if r.staging_save_kind = 'engineering_release' then
    if r.staging_engineering_git_ref is null then
      raise exception 'engineering release is missing its bound engineering target';
    end if;
    if r.published_day is distinct from r.staging_base_published_day then
      raise exception 'engineering_release may not change published day';
    end if;
    if v_published_day is distinct from r.published_day then
      raise exception 'engineering_release may not change the campaign clock day';
    end if;
    if exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
      ) missing_from_candidate
    ) or exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
      ) added_to_candidate
    ) then
      raise exception 'engineering_release may not change campaign state';
    end if;
  end if;

  v_mirror_token := gen_random_uuid();
  update public.campaign_runtime
     set published_generation = r.staging_generation,
         published_git_ref = null,
         runtime_mirror_token = v_mirror_token,
         runtime_mirror_base_git_ref = null,
         runtime_published_confirmed = false,
         runtime_published_confirmed_at = null,
         published_engineering_git_ref = r.staging_engineering_git_ref,
         published_day = v_published_day,
         save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null,
         staging_save_kind = null,
         staging_engineering_git_ref = null,
         staging_base_published_day = null,
         updated_at = now()
   where id = 1
   returning * into out_row;
  return out_row;
end;
$$;

revoke all on function public.publish_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.publish_campaign_save(text) to service_role;

comment on function public.stage_campaign_clock(text, jsonb) is
  'RT02: the only validated Clock mutation route. Stages an absolute target Clock after shape + monotonic/coherence validation against the authoritative published Clock. Replay-safe by construction.';
comment on function public.stage_campaign_state(text, text, jsonb) is
  'RT01-B/RT02: generic runtime-state staging. The engine-owned campaign_clock key is rejected here and must use stage_campaign_clock.';
