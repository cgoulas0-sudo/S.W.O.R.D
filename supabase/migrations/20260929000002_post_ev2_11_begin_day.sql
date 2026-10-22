-- POST-EV2-11 -- Begin Day + Fresh-DM Boot
-- Rolling High Club smallest safe day-opening read surface on the RT01 spine.
--
-- Architecture sentence: POST-EV2-11 adds NO new runtime key, mutation domain,
-- same-save compatibility edge, Save Gateway, controller ledger or mirror path.
-- Begin Day is a conductor: it reuses the existing RT02 Campaign Clock
-- (stage_campaign_clock) and the existing generic day-boundary owners
-- (daily_recap, day_resolution, live_status, dm_meta) plus the Hook owner
-- (narrative_hooks) through the ordinary RT01 Save Gateway. This migration adds
-- exactly ONE read-only, service_role-only published read that lets the
-- conductor see the current published day-boundary bundle and decide, before any
-- mutation, whether the published world is coherent enough to open the next day.
--
-- WHAT this migration changes:
--   1. `public.dm_begin_day_read()` -- the supported service-only published read
--      of the current day-boundary bundle plus a bounded coherence verdict.
--   2. Nothing else. No new runtime key is admitted, so POST-EV2-1 Patch 1A and
--      Patch 1B are intentionally untouched. No generic route is re-declared.
--
-- The read is `stable`, reads ONLY the current published generation, validates
-- shapes defensively, and never treats staged/future rows as authority. It never
-- mutates, stages or publishes anything.

-- ---------------------------------------------------------------------------
-- 1. Published day-boundary read + coherence verdict (service_role only).
--
--    Planes:
--      * campaign_runtime.published_day is derived checkpoint metadata from the
--        RT02 Campaign Clock and is the locator only.
--      * campaign_clock.day is the semantic day authority.
--      * daily_recap / day_resolution / live_status / dm_meta / narrative_hooks
--        each carry a current day-boundary field while active.
--
--    Coherence fails when the derived locator disagrees with the semantic Clock
--    day, when a present owner's `current_day` disagrees with the semantic
--    Clock day, or when an ACTIVE day-boundary owner (present, non-empty
--    published state) carries a current_day that is missing, malformed or
--    otherwise unparseable. An unverifiable owner day is incoherence, not
--    implicit agreement: Begin Day fails closed on it. Unknown (null) Clock day
--    remains valid truth: the read reports it and leaves the caller to fail
--    closed for a Begin Day attempt.
-- ---------------------------------------------------------------------------
create or replace function public.dm_begin_day_read()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_runtime jsonb;
  v_published_day integer;
  v_clock jsonb;
  v_daily jsonb;
  v_day jsonb;
  v_live jsonb;
  v_meta jsonb;
  v_hooks jsonb;
  v_clock_day integer;
  v_owner_days jsonb := '{}'::jsonb;
  v_issues jsonb := '[]'::jsonb;
  v_owner text;
  v_value jsonb;
  v_owner_day integer;
  v_owners constant text[] := array[
    'daily_recap', 'day_resolution', 'live_status', 'dm_meta', 'narrative_hooks'
  ];
begin
  v_runtime := public._rhc_dm_runtime_metadata();

  select cr.published_day into v_published_day
    from public.campaign_runtime cr
   where cr.id = 1;

  select csg.value into v_clock
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'campaign_clock';
  select csg.value into v_daily
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'daily_recap';
  select csg.value into v_day
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'day_resolution';
  select csg.value into v_live
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'live_status';
  select csg.value into v_meta
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'dm_meta';
  select csg.value into v_hooks
    from public.campaign_state_generations csg
   where csg.generation = (select published_generation from public.campaign_runtime where id = 1)
     and csg.key = 'narrative_hooks';

  -- Clock day, defensive: a non-object or malformed clock is reported, never
  -- trusted, and never coerced to a number.
  if v_clock is not null and jsonb_typeof(v_clock) <> 'object' then
    v_issues := v_issues || to_jsonb('campaign_clock is not a JSON object'::text);
    v_clock := null;
  elsif jsonb_typeof(v_clock -> 'day') = 'number'
        and (v_clock ->> 'day') ~ '^[0-9]+$' then
    v_clock_day := (v_clock ->> 'day')::integer;
  end if;

  if v_published_day is not null
     and v_clock_day is not null
     and v_published_day <> v_clock_day then
    v_issues := v_issues || to_jsonb(
      'campaign_runtime.published_day disagrees with campaign_clock.day'::text);
  end if;

  foreach v_owner in array v_owners loop
    v_value := case v_owner
      when 'daily_recap' then v_daily
      when 'day_resolution' then v_day
      when 'live_status' then v_live
      when 'dm_meta' then v_meta
      when 'narrative_hooks' then v_hooks
    end;

    if v_value is not null and jsonb_typeof(v_value) <> 'object' then
      v_issues := v_issues || to_jsonb(v_owner || ' is not a JSON object'::text);
      v_owner_days := v_owner_days || jsonb_build_object(v_owner, null);
    else
      -- An active day-boundary owner (present, non-empty published state) is
      -- expected to participate in day coherence. A current_day that is
      -- missing, a JSON null, a string, a non-integer number or otherwise
      -- unparseable is NOT implicit agreement with the Clock day: report it as
      -- incoherence so Begin Day fails closed (P1-04).
      if v_value is not null
         and v_value <> '{}'::jsonb
         and (
           jsonb_typeof(v_value -> 'current_day') is distinct from 'number'
           or (v_value ->> 'current_day') !~ '^[0-9]+$'
         ) then
        v_issues := v_issues || to_jsonb(
          v_owner || ' is an active day-boundary owner whose current_day is missing or unparseable'::text);
      end if;
      if jsonb_typeof(v_value -> 'current_day') = 'number'
         and (v_value ->> 'current_day') ~ '^[0-9]+$' then
        v_owner_day := (v_value ->> 'current_day')::integer;
      else
        v_owner_day := null;
      end if;
      v_owner_days := v_owner_days || jsonb_build_object(v_owner, v_owner_day);

      if v_owner_day is not null
         and v_clock_day is not null
         and v_owner_day <> v_clock_day then
        v_issues := v_issues || to_jsonb(
          v_owner || '.current_day disagrees with campaign_clock.day'::text);
      end if;
    end if;
  end loop;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'begin_day',
    'runtime', v_runtime,
    'current', jsonb_build_object(
      'published_day', v_published_day,
      'campaign_clock', v_clock,
      'daily_recap', coalesce(v_daily, '{}'::jsonb),
      'day_resolution', coalesce(v_day, '{}'::jsonb),
      'live_status', coalesce(v_live, '{}'::jsonb),
      'dm_meta', coalesce(v_meta, '{}'::jsonb),
      'narrative_hooks', coalesce(v_hooks, '{}'::jsonb)
    ),
    'coherence', jsonb_build_object(
      'coherent', jsonb_array_length(v_issues) = 0,
      'unknown_day', v_clock_day is null,
      'clock_day', v_clock_day,
      'owner_current_days', v_owner_days,
      'issues', v_issues
    )
  );
end;
$$;

revoke all on function public.dm_begin_day_read()
  from public, anon, authenticated;
grant execute on function public.dm_begin_day_read() to service_role;

comment on function public.dm_begin_day_read() is
  'POST-EV2-11: service-only published read of the current day-boundary bundle (RT02 campaign_clock + the generic day-boundary owners + narrative_hooks) with a bounded coherence verdict. Read-only, stable, published-generation-only. Adds no runtime key, mutation route, Patch 1A/1B policy or mirror path; staged/future state is never read as authority.';
