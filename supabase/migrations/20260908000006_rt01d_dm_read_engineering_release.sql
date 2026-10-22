-- RT01-D -- published DM read facade + guarded engineering release
--
-- This migration finishes the inert RT01 published-runtime foundation. It does
-- not activate SQL as the live RHC authority and it does not populate campaign
-- state. Reads remain published-generation-only; engineering releases clone the
-- current world without changing campaign state or day.

-- A pre-D save has no operation marker. Refuse the upgrade rather than guessing
-- whether an in-flight candidate is an ordinary save or an engineering release.
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT01-D migration refused: resolve the active campaign save before installing engineering-release lifecycle metadata';
  end if;
end;
$$;

alter table public.campaign_runtime
  add column if not exists staging_save_kind text,
  add column if not exists staging_engineering_git_ref text,
  add column if not exists staging_base_published_day integer,
  add column if not exists published_engineering_git_ref text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_staging_save_kind_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_staging_save_kind_check
      check (staging_save_kind is null or staging_save_kind in ('campaign_save', 'engineering_release'));
  end if;

  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_engineering_ref_shape_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_engineering_ref_shape_check
      check (
        (staging_engineering_git_ref is null or staging_engineering_git_ref ~ '^[0-9a-f]{40}$')
        and (published_engineering_git_ref is null or published_engineering_git_ref ~ '^[0-9a-f]{40}$')
      );
  end if;

  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_staging_kind_coherence_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_staging_kind_coherence_check
      check (
        save_in_progress = (staging_save_kind is not null)
        and (
          (staging_save_kind = 'engineering_release' and staging_engineering_git_ref is not null)
          or
          (staging_save_kind is distinct from 'engineering_release' and staging_engineering_git_ref is null)
        )
      );
  end if;
end;
$$;

-- Ordinary saves retain the RT01-C contract and one-parent mirror shape. The
-- operation marker only lets shared stage/publish functions distinguish them
-- from engineering releases.
create or replace function public.begin_campaign_save(
  p_ttl_minutes integer default 30
)
returns table (
  published_generation bigint,
  staging_generation bigint,
  lock_token text,
  lock_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_next bigint;
  v_ttl integer;
  v_token text;
  v_now timestamptz;
begin
  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  v_now := clock_timestamp();

  if r.published_generation > 0 then
    if r.runtime_mirror_token is null then
      raise exception 'published generation % predates the RT01-C mirror contract; repair its mirror before a new save',
        r.published_generation;
    end if;
    if not r.runtime_published_confirmed then
      raise exception 'published generation % has a pending runtime-published mirror; repair it before a new save',
        r.published_generation;
    end if;
  end if;

  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;
  if r.save_in_progress and r.staging_save_kind = 'engineering_release' then
    raise exception 'expired engineering release must be resumed with the same engineering target';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  delete from public.campaign_state_generations where generation = v_next;
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  select v_next, csg.key, csg.value, now(), now()
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  update public.campaign_runtime
     set save_in_progress = true,
         staging_generation = v_next,
         lock_token = v_token,
         save_started_at = v_now,
         lock_expires_at = v_now + make_interval(mins => v_ttl),
         staging_save_kind = 'campaign_save',
         staging_engineering_git_ref = null,
         staging_base_published_day = null
   where id = 1;

  return query
  select cr.published_generation,
         cr.staging_generation,
         cr.lock_token,
         cr.lock_expires_at
    from public.campaign_runtime cr
   where cr.id = 1;
end;
$$;

revoke all on function public.begin_campaign_save(integer)
  from public, anon, authenticated;
grant execute on function public.begin_campaign_save(integer) to service_role;

-- Bind the exact approved-main target when the release begins. PostgreSQL owns
-- retry stability; the external worker separately proves reachability from the
-- fetched origin/main and validates the bounded engineering path set.
create or replace function public.begin_engineering_release(
  p_engineering_git_ref text,
  p_ttl_minutes integer default 30
)
returns table (
  published_generation bigint,
  published_git_ref text,
  published_day integer,
  staging_generation bigint,
  lock_token text,
  engineering_git_ref text,
  lock_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_next bigint;
  v_ttl integer;
  v_token text;
  v_now timestamptz;
begin
  if p_engineering_git_ref is null or p_engineering_git_ref !~ '^[0-9a-f]{40}$' then
    raise exception 'engineering release target must be an exact full commit SHA';
  end if;

  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  v_now := clock_timestamp();
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or not r.runtime_published_confirmed
     or r.published_git_ref is null
     or r.last_confirmed_generation is distinct from r.published_generation
     or r.last_confirmed_git_ref is distinct from r.published_git_ref then
    raise exception 'engineering release requires a fully confirmed current published checkpoint';
  end if;

  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;
  if r.save_in_progress and (
    r.staging_save_kind is distinct from 'engineering_release'
    or r.staging_engineering_git_ref is distinct from p_engineering_git_ref
  ) then
    raise exception 'engineering release retry must preserve the bound engineering target';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  delete from public.campaign_state_generations where generation = v_next;
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  select v_next, csg.key, csg.value, now(), now()
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  update public.campaign_runtime
     set save_in_progress = true,
         staging_generation = v_next,
         lock_token = v_token,
         save_started_at = v_now,
         lock_expires_at = v_now + make_interval(mins => v_ttl),
         staging_save_kind = 'engineering_release',
         staging_engineering_git_ref = p_engineering_git_ref,
         staging_base_published_day = r.published_day
   where id = 1;

  return query
  select cr.published_generation,
         cr.published_git_ref,
         cr.published_day,
         cr.staging_generation,
         cr.lock_token,
         cr.staging_engineering_git_ref,
         cr.lock_expires_at
    from public.campaign_runtime cr
   where cr.id = 1;
end;
$$;

revoke all on function public.begin_engineering_release(text, integer)
  from public, anon, authenticated;
grant execute on function public.begin_engineering_release(text, integer) to service_role;

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

create or replace function public.abort_campaign_save(
  p_lock_token text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
begin
  r := public._rhc_require_active_save(p_lock_token);
  delete from public.campaign_state_generations
   where generation = r.staging_generation;

  update public.campaign_runtime
     set save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null,
         staging_save_kind = null,
         staging_engineering_git_ref = null,
         staging_base_published_day = null
   where id = 1;
end;
$$;

revoke all on function public.abort_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.abort_campaign_save(text) to service_role;

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
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;
  if r.staging_save_kind not in ('campaign_save', 'engineering_release') then
    raise exception 'active campaign save is missing a valid save kind';
  end if;

  if r.staging_save_kind = 'engineering_release' then
    if r.staging_engineering_git_ref is null then
      raise exception 'engineering release is missing its bound engineering target';
    end if;
    if r.published_day is distinct from r.staging_base_published_day then
      raise exception 'engineering_release may not change published day';
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

create or replace function public.get_pending_runtime_mirror()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_state jsonb;
begin
  select * into r from public.campaign_runtime where id = 1;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or r.runtime_published_confirmed then
    raise exception 'no runtime-published mirror is pending';
  end if;

  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  return jsonb_build_object(
    'schema_version', 1,
    'generation', r.published_generation,
    'published_day', r.published_day,
    'mirror_token', r.runtime_mirror_token::text,
    'last_confirmed_git_ref', r.last_confirmed_git_ref,
    'mirror_base_git_ref', r.runtime_mirror_base_git_ref,
    'engineering_git_ref', r.published_engineering_git_ref,
    'state', v_state
  );
end;
$$;

revoke all on function public.get_pending_runtime_mirror()
  from public, anon, authenticated;
grant execute on function public.get_pending_runtime_mirror()
  to service_role, rhc_mirror_verifier;

-- One coherent metadata block is used by context and targeted reads. A pending
-- SQL generation is current even though git_ref is null; the previous confirmed
-- ref is explicitly labelled current/stale rather than aliased to that generation.
create or replace function public._rhc_dm_runtime_metadata()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'generation', cr.published_generation,
    'git_ref', cr.published_git_ref,
    'day', cr.published_day,
    'mirror_confirmed', cr.runtime_published_confirmed,
    'mirror_confirmed_at', cr.runtime_published_confirmed_at,
    'last_confirmed_generation', cr.last_confirmed_generation,
    'last_confirmed_git_ref', cr.last_confirmed_git_ref,
    'fallback_freshness', case
      when cr.last_confirmed_git_ref is null then 'unavailable'
      when cr.runtime_published_confirmed
       and cr.last_confirmed_generation = cr.published_generation then 'current'
      else 'stale'
    end
  )
  from public.campaign_runtime cr
  where cr.id = 1
$$;

revoke all on function public._rhc_dm_runtime_metadata()
  from public, anon, authenticated, service_role;

-- Compact known index entries without expanding description/body/secret fields.
create or replace function public._rhc_compact_dm_index_array(
  p_items jsonb,
  p_limit integer
)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select coalesce(jsonb_agg(q.compact order by q.ordinality), '[]'::jsonb)
  from (
    select e.ordinality,
           jsonb_strip_nulls(jsonb_build_object(
             'id', e.item -> 'id',
             'title', e.item -> 'title',
             'label', e.item -> 'label',
             'summary', e.item -> 'summary',
             'status', e.item -> 'status',
             'visibility', e.item -> 'visibility',
             'priority', e.item -> 'priority',
             'influence', e.item -> 'influence',
             'current_day_update', e.item -> 'current_day_update',
             'source', e.item -> 'source'
           )) as compact
      from jsonb_array_elements(
        case when jsonb_typeof(p_items) = 'array' then p_items else '[]'::jsonb end
      ) with ordinality as e(item, ordinality)
     where jsonb_typeof(e.item) = 'object'
     order by e.ordinality
     limit greatest(0, least(coalesce(p_limit, 0), 100))
  ) q
$$;

revoke all on function public._rhc_compact_dm_index_array(jsonb, integer)
  from public, anon, authenticated, service_role;

create or replace function public.dm_quick_context()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_state jsonb;
  v_daily jsonb;
  v_live jsonb;
  v_day jsonb;
  v_meta jsonb;
  v_hooks jsonb;
  v_next_scene jsonb;
begin
  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation;

  v_daily := coalesce(v_state -> 'daily_recap', '{}'::jsonb);
  v_live := coalesce(v_state -> 'live_status', '{}'::jsonb);
  v_day := coalesce(v_state -> 'day_resolution', '{}'::jsonb);
  v_meta := coalesce(v_state -> 'dm_meta', '{}'::jsonb);
  v_hooks := coalesce(v_state -> 'narrative_hooks', '{}'::jsonb);
  v_next_scene := case
    when jsonb_typeof(v_daily #> '{current_summary,next_scene_handoff}') = 'array'
      then jsonb_path_query_array(v_daily #> '{current_summary,next_scene_handoff}', '$[0 to 19]')
    else '[]'::jsonb
  end;

  return jsonb_build_object(
    'context_version', 1,
    'runtime', public._rhc_dm_runtime_metadata(),
    'scene', jsonb_build_object(
      'status', coalesce(v_daily -> 'status', '"unknown"'::jsonb),
      'next_scene_handoff', v_next_scene,
      'hooks', jsonb_build_object(
        'day_status', coalesce(v_hooks -> 'day_status', '"unknown"'::jsonb),
        'active', public._rhc_compact_dm_index_array(v_hooks -> 'active_hooks', 20),
        'dormant', public._rhc_compact_dm_index_array(v_hooks -> 'dormant_hooks', 20),
        'closed_today', public._rhc_compact_dm_index_array(v_hooks -> 'closed_hooks_today', 20)
      )
    ),
    'world', jsonb_build_object(
      'status', coalesce(v_live -> 'status', '"unknown"'::jsonb),
      'current_day', v_live -> 'current_day',
      'party_state', coalesce(v_live -> 'party_state', '{}'::jsonb),
      'campaign_resources', coalesce(v_live -> 'campaign_resources', '{}'::jsonb),
      'organizations', coalesce(v_live -> 'organizations', '{}'::jsonb),
      'assets', coalesce(v_live -> 'assets', '{}'::jsonb),
      'persistent_effects', case
        when jsonb_typeof(v_live -> 'persistent_effects') = 'array'
          then jsonb_path_query_array(v_live -> 'persistent_effects', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'financial_obligations', coalesce(v_live -> 'financial_obligations', '{}'::jsonb)
    ),
    'today', jsonb_build_object(
      'status', coalesce(v_day -> 'status', '"unknown"'::jsonb),
      'current_day', v_day -> 'current_day',
      'rng_rolls', case
        when jsonb_typeof(v_day -> 'rng_rolls') = 'array'
          then jsonb_path_query_array(v_day -> 'rng_rolls', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'mechanical_resolutions', case
        when jsonb_typeof(v_day -> 'mechanical_resolutions') = 'array'
          then jsonb_path_query_array(v_day -> 'mechanical_resolutions', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'persistent_effects_applied', case
        when jsonb_typeof(v_day -> 'persistent_effects_applied') = 'array'
          then jsonb_path_query_array(v_day -> 'persistent_effects_applied', '$[0 to 49]')
        else '[]'::jsonb
      end
    ),
    'dm_index', jsonb_build_object(
      'status', coalesce(v_meta -> 'status', '"unknown"'::jsonb),
      'committed_hidden_truths', public._rhc_compact_dm_index_array(v_meta -> 'committed_hidden_truths', 50),
      'durable_dm_plans', public._rhc_compact_dm_index_array(v_meta -> 'durable_dm_plans', 50),
      'ghost_seeds', public._rhc_compact_dm_index_array(v_meta -> 'ghost_seeds', 50),
      'unresolved_reveal_conditions', public._rhc_compact_dm_index_array(v_meta -> 'unresolved_reveal_conditions', 50)
    )
  );
end;
$$;

create or replace function public.dm_runtime_lookup(
  p_query text,
  p_limit integer default 20
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_query text;
  v_limit integer;
  v_results jsonb;
begin
  v_query := btrim(coalesce(p_query, ''));
  if v_query = '' then
    raise exception 'runtime lookup query is required';
  end if;
  if char_length(v_query) > 200 then
    raise exception 'runtime lookup query exceeds 200 characters';
  end if;
  v_limit := greatest(1, least(coalesce(p_limit, 20), 100));

  select coalesce(jsonb_agg(q.result order by q.score desc, q.key), '[]'::jsonb)
    into v_results
    from (
      select csg.key,
             case
               when lower(csg.key) = lower(v_query) then 100
               when lower(csg.key) like lower(v_query) || '%' then 80
               when position(lower(v_query) in lower(csg.key)) > 0 then 60
               else 20
             end as score,
             jsonb_build_object(
               'key', csg.key,
               'value', csg.value
             ) as result
        from public.campaign_state_generations csg
        join public.campaign_runtime cr
          on cr.id = 1
         and csg.generation = cr.published_generation
       where position(lower(v_query) in lower(csg.key || ' ' || csg.value::text)) > 0
       order by score desc, csg.key
       limit v_limit
    ) q;
  return v_results;
end;
$$;

create or replace function public.dm_runtime_read(
  p_query text default null,
  p_limit integer default 20
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_context jsonb;
begin
  if p_query is null or btrim(p_query) = '' then
    v_context := public.dm_quick_context();
    return jsonb_build_object(
      'read_version', 1,
      'mode', 'context',
      'runtime', v_context -> 'runtime',
      'context', v_context - 'runtime'
    );
  end if;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'lookup',
    'runtime', public._rhc_dm_runtime_metadata(),
    'query', btrim(p_query),
    'results', public.dm_runtime_lookup(p_query, p_limit)
  );
end;
$$;

revoke all on function public.dm_quick_context()
  from public, anon, authenticated;
revoke all on function public.dm_runtime_lookup(text, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.dm_runtime_read(text, integer)
  from public, anon, authenticated;
grant execute on function public.dm_quick_context() to service_role;
grant execute on function public.dm_runtime_read(text, integer) to service_role;

-- RT01-A/B allowed service tooling to inspect the raw generation store before a
-- consumer facade existed. RT01-D makes that facade the service read boundary,
-- so staging/future generations must no longer be directly readable.
revoke select on table public.campaign_state_generations from service_role;

comment on column public.campaign_runtime.published_engineering_git_ref is
  'Exact approved origin/main commit bound to the current engineering_release generation; null for ordinary campaign saves.';
comment on function public.begin_engineering_release(text, integer) is
  'Begins a state/day-preserving engineering release from a fully confirmed runtime checkpoint and durably binds one exact target SHA.';
comment on function public.dm_runtime_read(text, integer) is
  'Unified service-only published-runtime facade: compact context for a blank query, bounded targeted lookup otherwise, with coherent checkpoint/fallback metadata in both modes.';
