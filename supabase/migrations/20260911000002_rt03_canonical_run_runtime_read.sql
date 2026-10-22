-- RT03 — Canonical Run Runtime Read (09B-ID canary)
-- Rolling High Club read-only Run resolution on the RT01 published-runtime spine.
--
-- WHAT this migration changes:
--   1. `public.dm_runtime_read_run(<run_id>)` — the supported service-facing
--      canonical Run read. One exact EV2-08-valid Run from the current
--      published generation, returned inside the same RT01-D runtime
--      metadata envelope used by every other supported read.
--   2. Internal-only EV2-08 Run shape/coherence validation helpers beneath it.
--
-- Run namespace rule (deterministic, system-owned):
--   The ONLY system-owned Run records in a published generation are the JSON
--   object entries of the published state key `runs`, whose value must be a
--   JSON array. Identity matching is exact: an entry is a candidate for
--   `<run_id>` only when it is an object whose string `run_id` field equals
--   `<run_id>` exactly. Any other runtime JSON that merely contains a
--   run_id-looking value is discovery noise, never Run authority.
--
-- Resolution rules (all fail closed):
--   * malformed `run_id` (not `R` + >= 2 digits, absolute end) -> refuse;
--   * a published `runs` value that is not a JSON array -> refuse;
--   * more than one candidate claiming one identity -> refuse (no first-match);
--   * a matching candidate that violates EV2-08 (including a played Run whose
--     control_state is absent or invalid) -> refuse;
--   * a matching candidate whose mutable owners are also claimed by another
--     published Run entry -> refuse (EV2-08 Run-batch unique mutable ownership);
--   * exactly zero candidates -> truthful absence: `run: null` with coherent
--     runtime metadata. No default Run is ever fabricated.
--
-- RT03 is read-only: it stages nothing, mutates nothing, seeds nothing, owns
-- no Clock arithmetic, performs no Git/repository resolution, and returns
-- minimum trusted Run context (the record itself, never a hydrated graph).
-- EV2-08 remains the Run contract; EV2-09A proposals remain non-canonical.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT01-D/RT02 forward-only installation pattern.
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
      'RT03 migration refused: resolve the active campaign save before installing the canonical Run read';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Absolute-end identity matching (internal). PostgreSQL `$` also matches
--    before a trailing newline; the EV2-08 patterns reject any trailing
--    character (`(?![\s\S])`), so the newline case is cancelled explicitly.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_full_id_match(
  p_value text,
  p_pattern text
)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select p_value is not null
     and p_value ~ p_pattern
     and p_value !~ E'\n$'
$$;

revoke all on function public._rhc_full_id_match(text, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. String identity-array validation (internal). Mirrors the EV2-08 schema:
--    JSON array, unique items, every item a string inside the given identity
--    pattern, with an optional minimum length.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_require_string_id_array(
  p_arr jsonb,
  p_label text,
  p_pattern text,
  p_min_items integer
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_count integer;
  v_distinct integer;
  v_item jsonb;
begin
  if p_arr is null or jsonb_typeof(p_arr) is distinct from 'array' then
    raise exception 'Run % must be a JSON array', p_label;
  end if;
  v_count := jsonb_array_length(p_arr);
  if v_count < greatest(0, coalesce(p_min_items, 0)) then
    raise exception 'Run % requires at least % item(s)', p_label, p_min_items;
  end if;
  select count(*), count(distinct item)
    into v_count, v_distinct
    from jsonb_array_elements(p_arr) item;
  if v_distinct < v_count then
    raise exception 'Run % must not contain duplicate entries', p_label;
  end if;
  for v_item in select * from jsonb_array_elements(p_arr) loop
    if not public._rhc_full_id_match(v_item #>> '{}', p_pattern) then
      raise exception 'Run % contains an entry outside its EV2-08 identity pattern', p_label;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_require_string_id_array(jsonb, text, text, integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. EV2-08 Run record validation (internal). Shape, identity patterns,
--    execution/control coherence and record-internal ownership semantics only.
--    Cross-domain resolution (Scenario/Encounter existence, anchor Git
--    reachability) stays owned by the repository EV2-08 validator; the runtime
--    read never fetches Git or repository files.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_run_record(p_run jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_mode text;
  v_state text;
  v_anchor jsonb;
begin
  if p_run is null or jsonb_typeof(p_run) is distinct from 'object' then
    raise exception 'Run must be a JSON object';
  end if;

  if not p_run ?& array[
    'run_id', 'execution_mode', 'control_state', 'scenario_id',
    'occurred_encounter_ids', 'participant_entity_ids',
    'mutable_owner_entity_ids', 'location_ids', 'campaign_anchor'
  ] then
    raise exception 'Run is missing a required EV2-08 field';
  end if;

  if (
    p_run - 'run_id' - 'execution_mode' - 'control_state' - 'scenario_id'
        - 'occurred_encounter_ids' - 'party_id' - 'participant_entity_ids'
        - 'mutable_owner_entity_ids' - 'location_ids' - 'campaign_anchor'
        - 'outcome_summary'
  ) <> '{}'::jsonb then
    raise exception 'Run contains fields outside the EV2-08 contract';
  end if;

  if not public._rhc_full_id_match(p_run ->> 'run_id', '^R[0-9]{2,}$') then
    raise exception 'Run run_id must be R followed by at least two digits';
  end if;

  v_mode := p_run ->> 'execution_mode';
  if v_mode is null or v_mode not in ('played', 'off_screen') then
    raise exception 'Run execution_mode must be played or off_screen';
  end if;

  v_state := p_run ->> 'control_state';
  -- Null-safe on purpose: `v_state not in (...)` silently evaluates to SQL
  -- NULL for a JSON-null control state, which would let an invalid played
  -- Run slip through as trusted context.
  if v_mode = 'played'
     and (v_state is null or v_state not in ('active', 'parked')) then
    raise exception 'played Run control_state must be active or parked';
  end if;
  if v_mode = 'off_screen' and v_state is distinct from 'not_applicable' then
    raise exception 'off_screen Run control_state must be not_applicable';
  end if;

  if not public._rhc_full_id_match(p_run ->> 'scenario_id', '^S[0-9]{2,}$') then
    raise exception 'Run scenario_id must be S followed by at least two digits';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'occurred_encounter_ids', 'occurred_encounter_ids', '^E[0-9]{2,}$', 0);

  if p_run ? 'party_id'
     and not public._rhc_full_id_match(
       p_run ->> 'party_id', '^party:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'Run party_id must be party: followed by a slug';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'participant_entity_ids', 'participant_entity_ids',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$', 1);

  perform public._rhc_require_string_id_array(
    p_run -> 'mutable_owner_entity_ids', 'mutable_owner_entity_ids',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$', 0);

  if not ((p_run -> 'mutable_owner_entity_ids')
            <@ (p_run -> 'participant_entity_ids')) then
    raise exception 'Run mutable owner must also appear in participant_entity_ids';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'location_ids', 'location_ids',
    '^location:[a-z0-9]+(-[a-z0-9]+)*$', 0);

  v_anchor := p_run -> 'campaign_anchor';
  if v_anchor is null or jsonb_typeof(v_anchor) is distinct from 'object' then
    raise exception 'Run campaign_anchor must be a JSON object';
  end if;
  if not v_anchor ?& array['base_commit', 'campaign_time'] then
    raise exception 'Run campaign_anchor requires base_commit and campaign_time';
  end if;
  if (v_anchor - 'base_commit' - 'campaign_time') <> '{}'::jsonb then
    raise exception 'Run campaign_anchor contains fields outside the EV2-08 contract';
  end if;
  if not public._rhc_full_id_match(v_anchor ->> 'base_commit', '^[0-9a-f]{40}$') then
    raise exception 'Run campaign_anchor.base_commit must be an exact 40-character lowercase hex commit';
  end if;
  if jsonb_typeof(v_anchor -> 'campaign_time') is distinct from 'string'
     or (v_anchor ->> 'campaign_time') !~ '\S' then
    raise exception 'Run campaign_anchor.campaign_time must be a non-blank label';
  end if;

  if p_run ? 'outcome_summary'
     and (jsonb_typeof(p_run -> 'outcome_summary') is distinct from 'string'
          or (p_run ->> 'outcome_summary') !~ '\S') then
    raise exception 'Run outcome_summary must be a non-blank string';
  end if;

  return true;
end;
$$;

revoke all on function public._rhc_validate_run_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Supported service-facing canonical Run read. Published-generation-only,
--    metadata-bearing, exact identity, fail-closed. Returns truthful absence
--    as `run: null` without fabricating a default Run.
-- ---------------------------------------------------------------------------
create or replace function public.dm_runtime_read_run(p_run_id text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_id text;
  v_runs jsonb;
  v_matches jsonb;
  v_count integer;
  v_run jsonb;
  v_owners jsonb;
  v_other jsonb;
  v_other_owners jsonb;
  v_conflict text;
begin
  v_id := coalesce(p_run_id, '');
  if not public._rhc_full_id_match(v_id, '^R[0-9]{2,}$') then
    raise exception 'run_id must be R followed by at least two digits';
  end if;

  select csg.value into v_runs
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'runs'
   where cr.id = 1;

  if found and v_runs is not null then
    if jsonb_typeof(v_runs) is distinct from 'array' then
      raise exception 'published runs state is unreadable; refusing to treat it as Run authority';
    end if;

    select coalesce(jsonb_agg(item), '[]'::jsonb), count(*)
      into v_matches, v_count
      from jsonb_array_elements(v_runs) item
     where jsonb_typeof(item) = 'object'
       and item ->> 'run_id' = v_id;

    if v_count > 1 then
      raise exception 'duplicate authoritative Run claims for %; failing closed', v_id;
    end if;
    if v_count = 1 then
      v_run := v_matches -> 0;
      perform public._rhc_validate_run_record(v_run);

      -- EV2-08 Run-batch law: across the published Run batch an actor may
      -- appear in at most one `mutable_owner_entity_ids` list. The requested
      -- Run is trusted only when no other published Run entry claims one of
      -- its mutable owners. A zero-claim Run cannot conflict, so the
      -- namespace is only read for the uniqueness proof when the requested
      -- Run claims owners; an unreadable owner list where overlap is still
      -- possible fails closed.
      v_owners := v_run -> 'mutable_owner_entity_ids';
      if jsonb_array_length(v_owners) > 0 then
        -- Only entries claiming a string Run identity participate in the
        -- uniqueness proof; namespace noise without one cannot hold a
        -- controller token (same rule as identity matching).
        for v_other in
          select item
            from jsonb_array_elements(v_runs) item
           where jsonb_typeof(item) = 'object'
             and jsonb_typeof(item -> 'run_id') = 'string'
             and (item ->> 'run_id') is distinct from v_id
        loop
          v_other_owners := v_other -> 'mutable_owner_entity_ids';
          if v_other_owners is null
             or jsonb_typeof(v_other_owners) is distinct from 'array' then
            raise exception
              'published Run % has an unreadable mutable_owner_entity_ids list; mutable-owner uniqueness cannot be proven',
              v_other ->> 'run_id';
          end if;
          select oo #>> '{}'
            into v_conflict
            from jsonb_array_elements(v_other_owners) oo
           where v_owners ? (oo #>> '{}')
           limit 1;
          if found then
            raise exception
              'mutable owner % is claimed by both % and %; EV2-08 allows at most one mutable-owner claim per actor across the published Run batch',
              v_conflict, v_id, v_other ->> 'run_id';
          end if;
        end loop;
      end if;
    end if;
  end if;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'run',
    'run_id', v_id,
    'runtime', public._rhc_dm_runtime_metadata(),
    'run', v_run
  );
end;
$$;

revoke all on function public.dm_runtime_read_run(text)
  from public, anon, authenticated;
grant execute on function public.dm_runtime_read_run(text) to service_role;

comment on function public.dm_runtime_read_run(text) is
  'RT03: supported service-facing canonical Run read. Resolves one exact EV2-08-valid Run from the current published generation inside the RT01-D runtime metadata envelope. Truthful absence returns run: null; malformed identity, unreadable namespace, duplicate claims, an EV2-08-invalid match (including a played Run with an absent or invalid control state) or a cross-Run mutable-owner conflict fail closed.';
comment on function public._rhc_validate_run_record(jsonb) is
  'RT03 internal EV2-08 Run shape/coherence validation. Internal-only: not executable by service consumers, so Run data is reachable only through the metadata-bearing supported read.';
