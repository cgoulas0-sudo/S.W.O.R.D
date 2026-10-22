-- RT04 — Safe Run Reconciliation
-- Rolling High Club legality + translation layer in front of the existing RT01
-- Save Gateway / publication spine. RT04 is NOT a second save engine.
--
-- WHAT this migration changes:
--   1. `public.reconcile_run_resolution(p_lock_token, p_request)` — the ONLY
--      validated Run-reconciliation staging route. It runs INSIDE the normal
--      campaign save lifecycle (`begin_campaign_save` -> reconcile -> publish),
--      proves the source Run is still the current legal controller, translates
--      the accepted EV2-09A resolution into the bounded mutations the current
--      repository truth can express, and records a replay-proof consumption
--      marker. It never creates an alternate `reconcile_publish`, an independent
--      generation counter, a second database truth, a separate mirror path or a
--      parallel save lifecycle.
--   2. An engine-owned `run_reconciliations` consumption ledger inside the
--      existing generation store. It is staged only by this route; the generic
--      `stage_campaign_state` / `delete_staged_campaign_state` routes reject the
--      key (the same closure RT02 applies to `campaign_clock`) so the
--      idempotency proof cannot be bypassed or erased.
--
-- SOURCE TRUTH (never caller self-certified):
--   The source Run is resolved ONLY through the RT03 authoritative published
--   read `public.dm_runtime_read_run(...)`. Caller-supplied Run-shaped payload
--   is not source truth. The published `runs` batch decides whether the Run
--   still exists and what it currently owns. A resolution proposal identifies a
--   Run but never certifies it.
--
-- BOUNDED TRANSLATION (no whole-world replacement, no JSON Patch language):
--   Under current repository truth the only legal durable mutation surfaces for
--   an accepted reconciliation are the source Run's own EV2-08 record (its
--   `outcome_summary`, and its mutable ownership / control state for the
--   continuation-vs-collapse law) plus the consumption ledger. Accepted
--   consequences that target domains with no legal durable mutation surface yet
--   (entity state, inventory/custody, Hook mutation, location world changes,
--   knowledge, ...) are PRESERVED in the durable ledger and REPORTED with the
--   exact missing downstream owner (including their validated human-readable
--   `summary`, so the meaning of a consumed resolution is never lost). They are
--   never silently dropped and RT04 never invents those subsystems.
--
-- ONE RECONCILIATION PER SOURCE RUN PER SAVE (self-contradiction guard):
--   Within one active campaign save, one source `run_id` may be reconciled at
--   most once. A second distinct resolution for the same Run is refused even
--   though its `resolution_id` is fresh: it would reconstruct the source Run
--   from the PUBLISHED record instead of the already-staged reconciliation
--   result and could resurrect ownership the first reconciliation just
--   released. This is one backend save context contradicting its own staged
--   mutation — not a second player save; QuickSave remains a frozen-frame
--   operation and no concurrency machinery exists here. Chaining from the
--   published result of a PRIOR save remains legal (new save, new candidate).
--
-- CANDIDATE RUN OWNERSHIP LAW (validated before anything is staged):
--   The complete candidate `runs` batch this route is about to preserve or
--   publish is validated as a whole: no mutable entity may be claimed by more
--   than one Run in the candidate state, and a pre-staged sibling Run may not
--   claim an entity the source Run still owns in published reality (a staged
-- claim is never honored as an ownership transfer — `released_mutable_owners`
--   is subtractive-only). Contradictory candidates fail closed before any
--   write. Once a reconciliation is NEWLY staged in a save, the candidate
--   `runs` batch is engine-owned for the rest of that save: the generic staging
--   and deletion routes refuse the `runs` key so a later same-save mutation
--   cannot reintroduce overlap or erase the reconciled candidate before
--   publication. Historical receipts copied forward from published reality do
--   not trigger the closure — the guard detects only markers this save added
--   on top of the published ledger.
--
-- CONTINUATION VS COLLAPSE (Run is not auto-terminated by synchronization):
--   If the accepted reconciliation releases mutable owners and the Run still has
--   owners, the Run continues as their current continuation lane (control state
--   unchanged). If the Run ends with zero mutable owners, its mutable authority
--   is removed and a played Run collapses to `parked` (historical participation
--   is preserved; stale write authority is not). Off-screen Runs keep
--   `not_applicable` control state and simply lose released owners.
--
-- RT04 is not the future Hard Write Boundary patch: generic staging of the
-- `runs` batch remains the pre-existing RT01-B behavior. This route guarantees
-- that the *reconciliation* path itself fails closed and uses the gateway.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03 forward-only installation pattern.
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
      'RT04 migration refused: resolve the active campaign save before installing the Run reconciliation route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Outcome band classification (internal). Mirrors the EV2-09A approved
--    resolution mechanic exactly.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_band_for_roll(p_roll integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_roll = 1 then 'critical_trigger'
    when p_roll between 2 and 5 then 'bad'
    when p_roll between 6 and 10 then 'below_average'
    when p_roll between 11 and 16 then 'normal'
    when p_roll between 17 and 19 then 'above_average'
    when p_roll = 20 then 'exceptional'
    else null
  end
$$;

revoke all on function public._rhc_band_for_roll(integer)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_band_for_severity(p_roll integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_roll between 1 and 2 then 'minor'
    when p_roll between 3 and 4 then 'moderate'
    when p_roll = 5 then 'serious'
    when p_roll = 6 then 'catastrophic'
    else null
  end
$$;

revoke all on function public._rhc_band_for_severity(integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Generic string-identity array validation (internal). JSON array, unique
--    items, every item a string inside the given identity pattern.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_require_entity_id_array(
  p_arr jsonb,
  p_label text,
  p_pattern text
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
    raise exception '% must be a JSON array', p_label;
  end if;
  select count(*), count(distinct item)
    into v_count, v_distinct
    from jsonb_array_elements(p_arr) item;
  if v_distinct < v_count then
    raise exception '% must not contain duplicate entries', p_label;
  end if;
  for v_item in select * from jsonb_array_elements(p_arr) loop
    if not public._rhc_full_id_match(v_item #>> '{}', p_pattern) then
      raise exception '% contains an entry outside its EV2-09A identity pattern', p_label;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_require_entity_id_array(jsonb, text, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Released mutable-owner validation (internal). Optional; when present it
--    must be a JSON array of unique character/creature identities.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_released_owners(p_arr jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_arr is null or jsonb_typeof(p_arr) = 'null' then
    return true;
  end if;
  perform public._rhc_require_entity_id_array(
    p_arr, 'released_mutable_owners',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$');
  return true;
end;
$$;

revoke all on function public._rhc_validate_released_owners(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. EV2-09A proposal contract validation (internal, SQL-level). Shape, exact
--    identity patterns, exact band/severity classification, bounded consequence
--    vocabulary and references. Cross-domain Scenario/Hook content resolution
--    (git-anchored) remains owned by the repository EV2-09A validator; this
--    helper enforces the full EV2-09A *schema/mechanics* contract so a malformed
--    or self-inconsistent proposal can never reach the save boundary.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_resolution_proposal(p_proposal jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_required text[] := array[
    'resolution_id', 'run_id', 'scenario_id', 'primary_hook_id',
    'campaign_anchor', 'objective_context', 'primary_roll',
    'outcome_band', 'proposed_consequences'
  ];
  v_anchor jsonb;
  v_obj_ctx jsonb;
  v_roll integer;
  v_band text;
  v_sev_roll integer;
  v_sev_band text;
  v_consequences jsonb;
  v_c jsonb;
  v_cid text;
  v_scope text;
  v_kind text;
  v_seen text[] := '{}';
begin
  if p_proposal is null or jsonb_typeof(p_proposal) is distinct from 'object' then
    raise exception 'resolution must be a JSON object';
  end if;
  if not p_proposal ?& v_required then
    raise exception 'resolution is missing a required EV2-09A field';
  end if;
  if (
    p_proposal - 'resolution_id' - 'run_id' - 'scenario_id' - 'primary_hook_id'
        - 'campaign_anchor' - 'objective_context' - 'primary_roll'
        - 'outcome_band' - 'severity_roll' - 'severity_band'
        - 'proposed_consequences'
  ) <> '{}'::jsonb then
    raise exception 'resolution contains fields outside the EV2-09A contract';
  end if;

  if not public._rhc_full_id_match(p_proposal ->> 'resolution_id', '^RP[0-9]{2,}$') then
    raise exception 'resolution_id must be RP followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'run_id', '^R[0-9]{2,}$') then
    raise exception 'resolution run_id must be R followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'scenario_id', '^S[0-9]{2,}$') then
    raise exception 'resolution scenario_id must be S followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'primary_hook_id', '^H[0-9]{2,}$') then
    raise exception 'resolution primary_hook_id must be H followed by at least two digits';
  end if;

  v_anchor := p_proposal -> 'campaign_anchor';
  if v_anchor is null or jsonb_typeof(v_anchor) is distinct from 'object' then
    raise exception 'resolution campaign_anchor must be a JSON object';
  end if;
  if not v_anchor ?& array['base_commit', 'campaign_time'] then
    raise exception 'resolution campaign_anchor requires base_commit and campaign_time';
  end if;
  if (v_anchor - 'base_commit' - 'campaign_time') <> '{}'::jsonb then
    raise exception 'resolution campaign_anchor contains fields outside the EV2-09A contract';
  end if;
  if not public._rhc_full_id_match(v_anchor ->> 'base_commit', '^[0-9a-f]{40}$') then
    raise exception 'resolution campaign_anchor.base_commit must be an exact 40-character lowercase hex commit';
  end if;
  if jsonb_typeof(v_anchor -> 'campaign_time') is distinct from 'string'
     or (v_anchor ->> 'campaign_time') !~ '\S' then
    raise exception 'resolution campaign_anchor.campaign_time must be a non-blank label';
  end if;

  v_obj_ctx := p_proposal -> 'objective_context';
  if v_obj_ctx is null or jsonb_typeof(v_obj_ctx) is distinct from 'object' then
    raise exception 'resolution objective_context must be a JSON object';
  end if;
  if not v_obj_ctx ?& array['scenario_objective', 'hook_objective'] then
    raise exception 'resolution objective_context requires scenario_objective and hook_objective';
  end if;
  if (v_obj_ctx - 'scenario_objective' - 'hook_objective') <> '{}'::jsonb then
    raise exception 'resolution objective_context contains fields outside the EV2-09A contract';
  end if;
  if jsonb_typeof(v_obj_ctx -> 'scenario_objective') is distinct from 'string'
     or (v_obj_ctx ->> 'scenario_objective') !~ '\S' then
    raise exception 'resolution objective_context.scenario_objective must be a non-blank string';
  end if;
  if jsonb_typeof(v_obj_ctx -> 'hook_objective') is distinct from 'string'
     or (v_obj_ctx ->> 'hook_objective') !~ '\S' then
    raise exception 'resolution objective_context.hook_objective must be a non-blank string';
  end if;

  if jsonb_typeof(p_proposal -> 'primary_roll') is distinct from 'number'
     or (p_proposal ->> 'primary_roll') !~ '^[0-9]+$'
     or (p_proposal ->> 'primary_roll')::integer not between 1 and 20 then
    raise exception 'resolution primary_roll must be an integer between 1 and 20';
  end if;
  v_roll := (p_proposal ->> 'primary_roll')::integer;
  v_band := public._rhc_band_for_roll(v_roll);
  if (p_proposal ->> 'outcome_band') is distinct from v_band then
    raise exception 'resolution outcome_band must be % for primary_roll %', v_band, v_roll;
  end if;

  if v_roll = 1 then
    if jsonb_typeof(p_proposal -> 'severity_roll') is distinct from 'number'
       or (p_proposal ->> 'severity_roll') !~ '^[0-9]+$'
       or (p_proposal ->> 'severity_roll')::integer not between 1 and 6 then
      raise exception 'primary_roll 1 requires severity_roll between 1 and 6';
    end if;
    v_sev_roll := (p_proposal ->> 'severity_roll')::integer;
    v_sev_band := public._rhc_band_for_severity(v_sev_roll);
    if (p_proposal ->> 'severity_band') is distinct from v_sev_band then
      raise exception 'resolution severity_band must be % for severity_roll %', v_sev_band, v_sev_roll;
    end if;
  else
    if p_proposal ? 'severity_roll' or p_proposal ? 'severity_band' then
      raise exception 'severity is forbidden when primary_roll is not 1';
    end if;
  end if;

  v_consequences := p_proposal -> 'proposed_consequences';
  if jsonb_typeof(v_consequences) is distinct from 'array'
     or jsonb_array_length(v_consequences) < 1 then
    raise exception 'resolution proposed_consequences must be a non-empty array';
  end if;

  for v_c in select * from jsonb_array_elements(v_consequences) loop
    if jsonb_typeof(v_c) is distinct from 'object' then
      raise exception 'proposed consequence must be a JSON object';
    end if;
    if not v_c ?& array['consequence_id', 'scope', 'kind', 'summary', 'related_entity_ids', 'location_ids'] then
      raise exception 'proposed consequence is missing a required EV2-09A field';
    end if;
    if (v_c - 'consequence_id' - 'scope' - 'kind' - 'summary' - 'related_entity_ids' - 'location_ids') <> '{}'::jsonb then
      raise exception 'proposed consequence contains fields outside the EV2-09A contract';
    end if;

    v_cid := v_c ->> 'consequence_id';
    if not public._rhc_full_id_match(v_cid, '^PC[0-9]{2,}$') then
      raise exception 'consequence_id must be PC followed by at least two digits';
    end if;
    if array_position(v_seen, v_cid) is not null then
      raise exception 'duplicate consequence_id % within resolution', v_cid;
    end if;
    v_seen := array_append(v_seen, v_cid);

    v_scope := v_c ->> 'scope';
    if v_scope not in ('run_objective', 'participant', 'location', 'related_entity') then
      raise exception 'consequence scope must be run_objective, participant, location or related_entity';
    end if;
    v_kind := v_c ->> 'kind';
    if v_kind not in (
      'objective_result', 'gain', 'loss', 'injury', 'capture', 'discovery', 'setback', 'world_change'
    ) then
      raise exception 'consequence kind is outside the EV2-09A vocabulary';
    end if;

    if jsonb_typeof(v_c -> 'summary') is distinct from 'string'
       or (v_c ->> 'summary') !~ '\S' then
      raise exception 'consequence summary must be a non-blank string';
    end if;

    perform public._rhc_require_entity_id_array(
      v_c -> 'related_entity_ids', 'related_entity_ids',
      '^(character|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$');
    perform public._rhc_require_entity_id_array(
      v_c -> 'location_ids', 'location_ids',
      '^location:[a-z0-9]+(-[a-z0-9]+)*$');

    if v_scope = 'participant' and jsonb_array_length(v_c -> 'related_entity_ids') < 1 then
      raise exception 'participant-scoped consequence requires at least one related entity';
    end if;
    if v_scope = 'location' and jsonb_array_length(v_c -> 'location_ids') < 1 then
      raise exception 'location-scoped consequence requires at least one location';
    end if;
    if v_scope = 'related_entity' and jsonb_array_length(v_c -> 'related_entity_ids') < 1 then
      raise exception 'related_entity-scoped consequence requires at least one related entity';
    end if;
  end loop;

  return true;
end;
$$;

revoke all on function public._rhc_validate_resolution_proposal(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4b. Candidate Run ownership validation (internal, RT04). Proves the complete
--     candidate `runs` batch is globally exclusive before it may be preserved
--     or published: no mutable entity may be claimed by more than one Run in
--     the candidate state. Only JSON object entries carrying a string `run_id`
--     participate as Run records (same participation rule as the RT03
--     identity read); an owner list that exists but is unreadable fails closed
--     rather than silently skipping a possible overlap.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_candidate_run_ownership(
  p_runs jsonb
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entry jsonb;
  v_owners jsonb;
  v_owner text;
  v_seen jsonb := '{}'::jsonb;
begin
  if p_runs is null or jsonb_typeof(p_runs) is distinct from 'array' then
    raise exception 'candidate runs batch must be a JSON array';
  end if;
  for v_entry in select * from jsonb_array_elements(p_runs) loop
    continue when jsonb_typeof(v_entry) is distinct from 'object'
       or jsonb_typeof(v_entry -> 'run_id') is distinct from 'string';

    v_owners := v_entry -> 'mutable_owner_entity_ids';
    continue when v_owners is null or jsonb_typeof(v_owners) = 'null';
    if jsonb_typeof(v_owners) is distinct from 'array' then
      raise exception
        'candidate Run % has an unreadable mutable_owner_entity_ids; candidate ownership cannot be proven exclusive',
        v_entry ->> 'run_id';
    end if;

    for v_owner in select o #>> '{}' from jsonb_array_elements(v_owners) o loop
      if v_seen ? v_owner then
        raise exception
          'candidate Run ownership is contradictory: mutable entity % is claimed by more than one Run (% and %); reconciliation fails closed before publication',
          v_owner, v_seen ->> v_owner, v_entry ->> 'run_id';
      end if;
      v_seen := jsonb_set(v_seen, array[v_owner], to_jsonb(v_entry ->> 'run_id'));
    end loop;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_candidate_run_ownership(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4c. Current-save reconciliation detector (internal, RT04). A save's staging
--     generation starts as a copy of published reality, so a historical
--     `run_reconciliations` receipt can legitimately be present in staged state
--     before this save has reconciled anything. The generic-`runs` closure must
--     therefore not key on the ledger's mere existence: it fires only when this
--     save carries at least one reconciliation marker that is ABSENT from the
--     published ledger, i.e. newly staged during the current active save. An
--     unreadable ledger fails closed. If there is no published reconciliation
--     ledger at all, any staged marker is by definition new in this save.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_reconciliation_new_in_save(
  p_staging_generation bigint,
  p_published_generation bigint
)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_stg jsonb;
  v_pub jsonb;
  v_key text;
  v_marker jsonb;
begin
  select value into v_stg
    from public.campaign_state_generations
   where generation = p_staging_generation
     and key = 'run_reconciliations';
  if v_stg is null then
    return false;
  end if;
  if jsonb_typeof(v_stg) is distinct from 'object' then
    raise exception 'staged run_reconciliations ledger is unreadable; runs mutation cannot be proven safe';
  end if;
  if p_published_generation is null then
    return true;
  end if;
  select value into v_pub
    from public.campaign_state_generations
   where generation = p_published_generation
     and key = 'run_reconciliations';
  if v_pub is null then
    return true;
  end if;
  if jsonb_typeof(v_pub) is distinct from 'object' then
    raise exception 'published run_reconciliations ledger is unreadable; runs mutation cannot be proven safe';
  end if;
  for v_key, v_marker in select key, value from jsonb_each(v_stg) loop
    if not (v_pub ? v_key) then
      return true;
    end if;
  end loop;
  return false;
end;
$$;

revoke all on function public._rhc_reconciliation_new_in_save(bigint, bigint)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. The validated Run-reconciliation staging route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> reconcile_run_resolution(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape (EV2-09A proposal is NOT modified; this is an RT04 wrapper):
--      {
--        "resolution": { <full EV2-09A proposal object> },
--        "released_mutable_owners": [ "<character|creature>:<slug>", ... ]  // optional
--      }
--
--    Fail-closed guarantees:
--      * reconciliation only runs inside an active campaign save (not an
--        engineering release) -> gateway bypass is impossible;
--      * the source Run is resolved through the RT03 published read only;
--      * a proposal that is malformed, lineage-incoherent, or already consumed
--        is refused before any write;
--      * a consequence targeting a mutable entity the Run no longer controls is
--        stale authority and fails closed;
--      * released owners must currently be owned by the Run;
--      * one source run_id may be reconciled at most once per active save: a
--        second distinct resolution for the same Run is refused so the save can
--        never contradict its own earlier staged reconciliation;
--      * the complete candidate Run ownership state is validated before any
--        staging: no mutable entity claimed by two Runs, and no pre-staged
--        sibling claim converted into an ownership transfer;
--      * after a reconciliation is newly staged in this save, the generic
--        routes refuse further
--        same-save `runs` staging/deletion so the validated candidate cannot be
--        contradicted again before publish;
--      * zero partial writes: all validation happens before any staging, and
--        the caller's single transaction plus the existing gateway laws make the
--        accepted reconciliation all-or-nothing.
-- ---------------------------------------------------------------------------
create or replace function public.reconcile_run_resolution(
  p_lock_token text,
  p_request jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_resolution jsonb;
  v_released jsonb;
  v_rid text;
  v_run_id text;
  v_ledger_pub jsonb;
  v_ledger_stg jsonb;
  v_read jsonb;
  v_run jsonb;
  v_owners jsonb;
  v_new_owners jsonb;
  v_mode text;
  v_state text;
  v_new_state text;
  v_band text;
  v_summary text;
  v_preserved jsonb;
  v_c jsonb;
  v_scope text;
  v_kind text;
  v_t jsonb;
  v_missing text;
  v_count integer;
  v_runs_stg jsonb;
  v_runs_pub jsonb;
  v_runs_base jsonb;
  v_new_runs jsonb;
  v_new_run jsonb;
  v_marker jsonb;
  v_new_ledger jsonb;
  v_other jsonb;
  v_other_owners jsonb;
  v_prior_rid text;
  v_key text;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Request shape (bounded RT04 contract).
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'reconciliation request must be a JSON object';
  end if;
  if not p_request ? 'resolution' then
    raise exception 'reconciliation request requires a resolution proposal';
  end if;
  if (p_request - 'resolution' - 'released_mutable_owners') <> '{}'::jsonb then
    raise exception 'reconciliation request contains fields outside the RT04 contract';
  end if;
  v_resolution := p_request -> 'resolution';
  perform public._rhc_validate_resolution_proposal(v_resolution);
  v_rid := v_resolution ->> 'resolution_id';
  v_run_id := v_resolution ->> 'run_id';

  v_released := p_request -> 'released_mutable_owners';
  if v_released is null or jsonb_typeof(v_released) = 'null' then
    v_released := '[]'::jsonb;
  end if;
  perform public._rhc_validate_released_owners(v_released);

  -- Idempotency: an accepted resolution is consumed exactly once. The engine
  -- owned ledger is checked in the published generation AND in this save's
  -- candidate, so replay across saves and repeated calls within one save both
  -- fail closed.
  select csg.value into v_ledger_pub
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation
     and csg.key = 'run_reconciliations';
  if v_ledger_pub is not null and jsonb_typeof(v_ledger_pub) is distinct from 'object' then
    raise exception 'published run_reconciliations ledger is unreadable; reconciliation cannot be proven safe';
  end if;
  if v_ledger_pub is not null and v_ledger_pub ? v_rid then
    raise exception 'resolution % has already been reconciled; replay is forbidden', v_rid;
  end if;
  select csg.value into v_ledger_stg
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'run_reconciliations';
  if v_ledger_stg is not null and jsonb_typeof(v_ledger_stg) is distinct from 'object' then
    raise exception 'staged run_reconciliations ledger is unreadable; reconciliation cannot be proven safe';
  end if;
  if v_ledger_stg is not null and v_ledger_stg ? v_rid then
    raise exception 'resolution % has already been reconciled in this save; replay is forbidden', v_rid;
  end if;

  -- One reconciliation per source Run per save: a second DISTINCT resolution
  -- for the same run_id inside this active save is refused even though its
  -- resolution_id is fresh. It would resolve the source Run from the published
  -- generation instead of the already-staged reconciliation result and could
  -- resurrect ownership the first reconciliation released. Only markers this
  -- save added on top of the published ledger count as same-save history: the
  -- candidate starts as a copy of the published ledger, so a Run reconciled in
  -- a PRIOR save may still be chained legally in a fresh save.
  v_prior_rid := null;
  if v_ledger_stg is not null then
    for v_key, v_marker in select key, value from jsonb_each(v_ledger_stg) loop
      if (v_marker ->> 'run_id') = v_run_id
         and (v_ledger_pub is null or not (v_ledger_pub ? v_key)) then
        v_prior_rid := v_key;
        exit;
      end if;
    end loop;
  end if;
  if v_prior_rid is not null then
    raise exception
      'source Run % has already been reconciled in this save as %; a second same-Run reconciliation would reuse stale published ownership and is forbidden',
      v_run_id, v_prior_rid;
  end if;

  -- Authoritative source Run: RT03 published read only. Caller-supplied Run
  -- truth is never consulted. Absence, duplicate claims, EV2-08-invalid matches
  -- and cross-Run mutable-owner conflicts all fail closed inside the read.
  v_read := public.dm_runtime_read_run(v_run_id);
  v_run := v_read -> 'run';
  if v_run is null or jsonb_typeof(v_run) is distinct from 'object' then
    raise exception 'source Run % does not exist in published reality; reconciliation fails closed', v_run_id;
  end if;

  -- Lineage: the proposal must speak for THIS Run under THIS anchor.
  if (v_run ->> 'run_id') is distinct from v_run_id then
    raise exception 'resolution run lineage is incoherent';
  end if;
  if (v_resolution ->> 'scenario_id') is distinct from (v_run ->> 'scenario_id') then
    raise exception 'resolution scenario_id does not match the source Run scenario';
  end if;
  if (v_resolution -> 'campaign_anchor') is distinct from (v_run -> 'campaign_anchor') then
    raise exception 'resolution campaign_anchor does not exactly match the source Run campaign_anchor';
  end if;

  v_owners := v_run -> 'mutable_owner_entity_ids';
  if jsonb_typeof(v_owners) is distinct from 'array' then
    raise exception 'source Run mutable_owner_entity_ids is unreadable; reconciliation fails closed';
  end if;

  -- Released owners must currently be owned by the Run; releasing an entity the
  -- Run no longer controls would be stale authority.
  for v_t in select * from jsonb_array_elements(v_released) loop
    if not (v_owners ? (v_t #>> '{}')) then
      raise exception 'source Run does not own released mutable entity %; releasing it would be stale authority', v_t #>> '{}';
    end if;
  end loop;

  -- Remaining owners after the accepted release.
  select coalesce(jsonb_agg(o), '[]'::jsonb)
    into v_new_owners
    from jsonb_array_elements(v_owners) o
   where not (v_released ? (o #>> '{}'));

  -- Consequence legality + preservation. The only consequence applied as a
  -- durable mutation is the run_objective / objective_result translation into
  -- the Run outcome summary. Every other accepted consequence is checked for
  -- ownership legality and then preserved + reported against its missing
  -- downstream owner; it is never silently dropped and never invents a surface.
  v_preserved := '[]'::jsonb;
  for v_c in select * from jsonb_array_elements(v_resolution -> 'proposed_consequences') loop
    v_scope := v_c ->> 'scope';
    v_kind := v_c ->> 'kind';

    if v_scope = 'run_objective' and v_kind = 'objective_result' then
      continue;
    end if;

    -- Ownership legality: a character/creature target the Run is attempting to
    -- mutate must still be a current mutable owner. Stale authority fails closed.
    if jsonb_typeof(v_c -> 'related_entity_ids') = 'array' then
      for v_t in select * from jsonb_array_elements(v_c -> 'related_entity_ids') loop
        if (v_t #>> '{}') ~ '^(character|creature):'
           and not (v_owners ? (v_t #>> '{}')) then
          raise exception 'consequence % targets mutable entity % which the source Run no longer controls; stale authority fails closed', v_c ->> 'consequence_id', v_t #>> '{}';
        end if;
      end loop;
    end if;

    v_missing := case
      when v_scope = 'participant' then 'no legal durable entity-state mutation surface exists yet'
      when v_scope = 'location' then 'no legal durable location-state mutation surface exists yet'
      when v_scope = 'related_entity' then 'no legal durable related-entity mutation surface exists yet'
      else 'no legal durable surface to apply ' || v_kind || ' to the Run objective exists yet'
    end;

    v_preserved := v_preserved || jsonb_build_object(
      'consequence_id', v_c ->> 'consequence_id',
      'scope', v_scope,
      'kind', v_kind,
      'summary', v_c ->> 'summary',
      'target_entity_ids', v_c -> 'related_entity_ids',
      'target_location_ids', v_c -> 'location_ids',
      'missing_downstream_owner', v_missing
    );
  end loop;

  -- Continuation vs collapse. A Run is never auto-terminated merely because it
  -- synchronized: it continues while it still has owners; with zero owners a
  -- played Run collapses to parked (historical participation preserved, stale
  -- mutable authority removed) and an off-screen Run keeps not_applicable.
  v_mode := v_run ->> 'execution_mode';
  v_state := v_run ->> 'control_state';
  if jsonb_array_length(v_new_owners) = 0 and v_mode = 'played' then
    v_new_state := 'parked';
  else
    v_new_state := v_state;
  end if;

  -- Deterministic objective-result translation into the EV2-08 outcome summary.
  -- Built only from authoritative proposal fields; no campaign fact is invented.
  -- Trailing periods/spaces on the objective snapshots are trimmed so the
  -- mechanical summary reads cleanly regardless of the snapshot wording.
  v_band := v_resolution ->> 'outcome_band';
  v_summary := 'Resolution ' || v_rid || ' accepted: ' || v_band
    || ' objective result. Scenario objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,scenario_objective}'), ' '), '.')
    || '. Hook objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,hook_objective}'), ' '), '.')
    || '.';

  -- Build the updated runs batch. The base is this save's candidate `runs`
  -- (preserving any other staged Run work) else the published `runs`; the source
  -- Run entry is always rebuilt from the authoritative published record plus the
  -- bounded reconciliation translation.
  select csg.value into v_runs_stg
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'runs';
  if v_runs_stg is not null then
    v_runs_base := v_runs_stg;
  else
    select csg.value into v_runs_pub
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'runs';
    v_runs_base := v_runs_pub;
  end if;
  if v_runs_base is null or jsonb_typeof(v_runs_base) is distinct from 'array' then
    raise exception 'published runs namespace is unreadable; reconciliation cannot stage a bounded Run update';
  end if;

  select count(*)
    into v_count
    from jsonb_array_elements(v_runs_base) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'run_id') = v_run_id;
  if v_count <> 1 then
    raise exception 'source Run % is ambiguous or absent in the runs batch; reconciliation fails closed', v_run_id;
  end if;

  v_new_run := v_run
    || jsonb_build_object(
         'mutable_owner_entity_ids', v_new_owners,
         'control_state', v_new_state,
         'outcome_summary', v_summary
       );

  select coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'run_id') = v_run_id
           then v_new_run
           else e
      end
    ), '[]'::jsonb)
    into v_new_runs
    from jsonb_array_elements(v_runs_base) e;

  -- Candidate Run ownership law, proven before anything is staged:
  --   1. the complete candidate batch must be globally exclusive — no mutable
  --      entity claimed by more than one Run;
  perform public._rhc_validate_candidate_run_ownership(v_new_runs);

  --   2. a pre-staged sibling Run must not claim an entity the source Run
  --      currently owns in published reality. Keeping the owner would already
  --      have failed rule 1; releasing it must not silently become an
  --      R01 -> R02 ownership transfer, because released_mutable_owners is
  --      subtractive-only and a pre-staged claim is never honored as one.
  --      Contradiction fails closed before publication either way.
  for v_other in
    select e from jsonb_array_elements(v_new_runs) e
     where jsonb_typeof(e) = 'object'
       and jsonb_typeof(e -> 'run_id') = 'string'
       and (e ->> 'run_id') is distinct from v_run_id
  loop
    v_other_owners := v_other -> 'mutable_owner_entity_ids';
    continue when v_other_owners is null
       or jsonb_typeof(v_other_owners) is distinct from 'array';
    for v_t in select * from jsonb_array_elements(v_other_owners) loop
      if (v_owners ? (v_t #>> '{}')) then
        raise exception
          'pre-staged Run % claims mutable entity % which the source Run % still owns in published reality; released_mutable_owners cannot transfer ownership and reconciliation fails closed',
          v_other ->> 'run_id', v_t #>> '{}', v_run_id;
      end if;
    end loop;
  end loop;

  -- Consumption ledger + bounded run update are staged together, atomically,
  -- inside the caller's active save transaction.
  v_marker := jsonb_build_object(
    'run_id', v_run_id,
    'published_generation', r.published_generation,
    'applied_outcome_summary', v_summary,
    'released_mutable_owners', v_released,
    'run_state_after', jsonb_build_object(
      'control_state', v_new_state,
      'mutable_owner_entity_ids', v_new_owners
    ),
    'preserved_consequences', v_preserved
  );
  v_new_ledger := coalesce(v_ledger_stg, '{}'::jsonb)
    || jsonb_build_object(v_rid, v_marker);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'run_reconciliations', v_new_ledger, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'runs', v_new_runs, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  return jsonb_build_object(
    'reconciliation_version', 1,
    'resolution_id', v_rid,
    'run_id', v_run_id,
    'runtime', public._rhc_dm_runtime_metadata(),
    'applied', jsonb_build_object(
      'outcome_summary', v_summary,
      'released_mutable_owners', v_released,
      'run_state_after', jsonb_build_object(
        'control_state', v_new_state,
        'mutable_owner_entity_ids', v_new_owners
      )
    ),
    'preserved_consequences', v_preserved
  );
end;
$$;

revoke all on function public.reconcile_run_resolution(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.reconcile_run_resolution(text, jsonb) to service_role;

comment on function public.reconcile_run_resolution(text, jsonb) is
  'RT04: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet (with their validated summary), and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. All-or-nothing through the existing gateway.';

-- ---------------------------------------------------------------------------
-- 6. Close the generic `run_reconciliations` bypass. The consumption ledger is
--    engine-owned reconciliation proof: it can never be staged or deleted
--    through the generic routes, otherwise replay could be forged or erased.
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
  if p_key = 'run_reconciliations' then
    raise exception 'run_reconciliations is engine-owned and can only be staged through reconcile_run_resolution';
  end if;
  if p_key = 'runs'
     and public._rhc_reconciliation_new_in_save(r.staging_generation, r.published_generation) then
    raise exception
      'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; a later generic runs mutation could reintroduce duplicate mutable ownership or erase the reconciled candidate; abort this save and start a new one';
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
  if p_key = 'run_reconciliations' then
    raise exception 'run_reconciliations is engine-owned and cannot be deleted';
  end if;
  if p_key = 'runs'
     and public._rhc_reconciliation_new_in_save(r.staging_generation, r.published_generation) then
    raise exception
      'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; deleting it would erase the reconciled candidate while the consumption ledger claims it was applied; abort this save and start a new one';
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

comment on function public.stage_campaign_state(text, text, jsonb) is
  'RT01-B/RT02/RT04: generic runtime-state staging. Engine-owned campaign_clock and run_reconciliations keys are rejected here and must use their validated routes. Once a reconciliation is newly staged in the current save (absent from the published reconciliation ledger), the runs key is refused for the rest of the save so the validated candidate Run ownership cannot be contradicted before publication; historical receipts copied forward from published reality do not trigger the closure.';