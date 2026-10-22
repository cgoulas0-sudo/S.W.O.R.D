-- EV2-13.1 — Timed Applied Status Continuity
-- Rolling High Club validated runtime model for one live time-dependent
-- `status_effect` application on a mutable target, on the existing RT01 SAVE /
-- publish / mirror / confirm spine.
--
-- This migration is NOT a second save engine, NOT a second controller/ownership
-- ledger and NOT a new persistence/mirror path. It creates ONE engine-owned
-- runtime namespace `applied_statuses`, ONE validated mutation route, ONE pure
-- due-threshold read and the smallest same-save exclusions required to keep the
-- controller/elapsed-anchor semantics unambiguous.
--
-- Architecture sentence:
--   EV2-13.1 owns the live timed application instance — identity, elapsed-time
--   anchors, due-threshold derivation/acknowledgement and controller-safe
--   mutation — while RT02's monotonic `elapsed_campaign_minutes` remains the only
--   persisted elapsed-time authority and EV2-13.420 remains the only
--   mechanical-duration arithmetic contract.
--
-- Core invariance (the reason the whole Mission exists):
--   World-calendar position may later move backward or forward. Experienced
--   elapsed campaign time never moves backward. Timed status ageing follows
--   experienced elapsed time only.
--
-- WHAT this migration changes:
--   1. The engine-owned `applied_statuses` runtime namespace is a JSON array
--      holding exactly one application record per stable application identity.
--      A record references a `status_effect:` DEFINITION identity (EV2-04.1),
--      never mints or mutates it; it is bound to one mutable target actor
--      (`character:` / `creature:`), an optional known source identity, an
--      engine-derived application anchor from authoritative PUBLISHED RT02
--      `elapsed_campaign_minutes`, bounded absolute elapsed-time threshold
--      anchors in whole campaign minutes, explicit acknowledgement state and an
--      explicit end anchor. It stores elapsed anchors only — never world dates.
--   2. `public.mutate_applied_status(p_lock_token, p_request)` is the ONLY way to
--      stage `applied_statuses`. It runs INSIDE the normal campaign save
--      lifecycle, proves the caller's asserted controller (MAINRUN or exactly one
--      RUN #) against authoritative PUBLISHED Run truth for the target mutable
--      actor, derives every timing anchor from the authoritative published Clock,
--      normalizes relative human-facing durations through EV2-13.420, and stages
--      exactly one application record per identity.
--   3. `public.read_timed_applied_status(p_application_id)` is the service-only
--      pure read that deterministically exposes every still-unacknowledged
--      threshold whose absolute due anchor is now <= current elapsed time. A
--      forward elapsed-time jump needs no per-minute ticking: due-ness is derived
--      from the current elapsed cursor, never from an incremental loop.
--   4. The generic `stage_campaign_state` / `delete_staged_campaign_state` routes
--      reject the `applied_statuses` key (the same dedicated-key closure pattern
--      as `campaign_clock`, `run_reconciliations`, `inventory`, `item_custody`,
--      `item_admissions` and `entity_state`), so a caller/model cannot bypass the
--      validated route with a raw generic runtime write. The HWB-02 ordinary-save
--      allowlist is preserved unchanged. Legacy `live_status` stays generic
--      ordinary-save state and is never applied-status authority.
--   5. Status mutation and Run-ownership mutation are mutually exclusive within
--      one save, and status mutation and Campaign Clock mutation are mutually
--      exclusive within one save, in BOTH orderings. Closure keys on the explicit
--      applied-status staging operation fact, not on final value equality, and
--      the marker is bound to the save's own database-minted lock token so it
--      never leaks into a later save.
--
-- TIMING MODEL:
--   * The application anchor (`applied_at_elapsed_minutes`) is the authoritative
--     published `elapsed_campaign_minutes` at the first accepted mutation — never
--     caller-supplied.
--   * A threshold is described by a relative whole-duration (`threshold_id`,
--     `amount`, `unit`). Its absolute due anchor is the application anchor plus
--     the exact whole-minute result of EV2-13.420's
--     `mechanical_duration_to_campaign_minutes`. No duplicate time arithmetic is
--     introduced; a sub-minute duration such as one round fails closed.
--   * A threshold becomes due purely because `due_at <= current elapsed`. There is
--     no per-minute scheduler/ticker.
--   * Acknowledgement and end anchors are stamped from the current authoritative
--     published elapsed cursor, never from caller input. Acknowledging a due
--     threshold is terminal for that threshold (idempotent on replay) and leaves
--     later thresholds discoverable; it performs NO automatic gameplay
--     consequence.
--   * The whole timing definition (definition identity, target, source, threshold
--     due anchors) is immutable after creation. Re-sending it is an idempotent
--     replay; changing it fails closed, because reapplication/refresh/stacking
--     policy is explicitly deferred to later status-rules work.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * One application record is global to the target in the single campaign
--     reality. It is never copied into MAINRUN and RUN-local versions.
--   * Only the target's current authoritative controller — resolved from
--     PUBLISHED Run truth — may mutate/acknowledge/end the application. A
--     former/stale controller write fails closed because published Run truth no
--     longer grants it authority. There is no stored controller field.
--
-- DEFERRED (not built here): world-calendar / Harptos / Dalereckoning
-- representation or mutation, world-date jumps, turn/initiative-boundary
-- scheduler semantics (`turn` is never an additive duration), stacking /
-- refresh / replace / ignore policy, concentration, D&D condition automation,
-- saving throws, damage/resources, automatic gameplay consequences, alternate
-- realities / save slots, sub-minute persisted remainder and any generic
-- scheduler/autosave. `live_status` is not repurposed.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13
--    forward-only install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'EV2-13.1 migration refused: resolve the active campaign save before installing the timed applied-status route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Authoritative elapsed cursor (internal). Reads the published campaign
--    Clock's monotonic `elapsed_campaign_minutes`. Missing/Unknown Clock truth
--    FAILS CLOSED rather than defaulting to elapsed 0: status ageing must never
--    invent timeline position from an absent Clock.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_published_clock_elapsed()
returns integer
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_clock jsonb;
  v_elapsed integer;
begin
  select csg.value into v_clock
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation
   where csg.key = 'campaign_clock';
  if v_clock is null or jsonb_typeof(v_clock) is distinct from 'object' then
    raise exception
      'published campaign_clock is unavailable; timed applied-status elapsed anchoring cannot be derived and never defaults to zero';
  end if;
  if jsonb_typeof(v_clock -> 'elapsed_campaign_minutes') is distinct from 'number'
     or (v_clock ->> 'elapsed_campaign_minutes') !~ '^[0-9]+$' then
    raise exception
      'published campaign_clock elapsed_campaign_minutes is unreadable; timed applied-status timing fails closed';
  end if;
  v_elapsed := (v_clock ->> 'elapsed_campaign_minutes')::integer;
  return v_elapsed;
end;
$$;

revoke all on function public._rhc_published_clock_elapsed()
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Canonical timing definition normalization (internal). Accepts the bounded
--    relative-duration definition and the (engine-derived) application anchor,
--    and returns the canonical definition with absolute whole-minute due
--    anchors. Human-facing durations are normalized through EV2-13.420; no
--    duplicate time arithmetic is introduced. A sub-minute or malformed
--    duration, a forged threshold id, or an anchor beyond the RT02 integer range
--    fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_applied_status_definition(
  p_definition jsonb,
  p_applied_at integer
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_definition_id text;
  v_target text;
  v_source jsonb;
  v_thresholds jsonb;
  v_entry jsonb;
  v_out jsonb := '[]'::jsonb;
  v_tid text;
  v_amount jsonb;
  v_unit text;
  v_minutes bigint;
  v_due bigint;
  v_seen text[] := '{}';
  v_rt02_max constant bigint := 2147483647;
begin
  if p_definition is null or jsonb_typeof(p_definition) is distinct from 'object' then
    raise exception 'applied-status definition must be a JSON object';
  end if;
  if (p_definition - 'definition_id' - 'target_entity_id' - 'source_entity_id'
        - 'thresholds') <> '{}'::jsonb then
    raise exception
      'applied-status definition contains fields outside the EV2-13.1 contract (definition_id, target_entity_id, source_entity_id, thresholds)';
  end if;
  if not (p_definition ?& array['definition_id', 'target_entity_id', 'thresholds']) then
    raise exception
      'applied-status definition requires definition_id, target_entity_id and thresholds';
  end if;

  -- Definition identity: a reference to an EV2-04.1 persistent status_effect.
  -- The runtime references definitions; it never mints or mutates their identity.
  if jsonb_typeof(p_definition -> 'definition_id') is distinct from 'string' then
    raise exception
      'applied-status definition_id must be a JSON string status_effect identity';
  end if;
  v_definition_id := p_definition ->> 'definition_id';
  if not public._rhc_full_id_match(
    v_definition_id, '^status_effect:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status definition_id must be a status_effect:<slug> definition identity';
  end if;

  -- Target: the EV2-08 mutable-actor identity space only.
  if jsonb_typeof(p_definition -> 'target_entity_id') is distinct from 'string' then
    raise exception
      'applied-status target_entity_id must be a JSON string mutable-actor identity';
  end if;
  v_target := p_definition ->> 'target_entity_id';
  if not public._rhc_full_id_match(
    v_target, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status target_entity_id must be a character: or creature: mutable-actor identity';
  end if;

  -- Optional known source identity. Unknown stays Unknown: when absent it is
  -- stored as null, never invented.
  if p_definition ? 'source_entity_id' then
    v_source := p_definition -> 'source_entity_id';
    if jsonb_typeof(v_source) is distinct from 'null' then
      if jsonb_typeof(v_source) is distinct from 'string' then
        raise exception
          'applied-status source_entity_id must be null or a JSON string entity identity';
      end if;
      if not public._rhc_full_id_match(
        (v_source #>> '{}'),
        '^(character|location|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$') then
        raise exception
          'applied-status source_entity_id must be null or a typed <entity_type>:<slug> identity';
      end if;
    end if;
  else
    v_source := 'null'::jsonb;
  end if;

  -- Bounded elapsed thresholds expressed only as relative whole durations.
  v_thresholds := p_definition -> 'thresholds';
  if v_thresholds is null or jsonb_typeof(v_thresholds) is distinct from 'array' then
    raise exception 'applied-status thresholds must be a JSON array';
  end if;
  if jsonb_array_length(v_thresholds) = 0 then
    raise exception
      'applied-status requires at least one elapsed threshold; a non-timed status_effect does not belong in the timed applied-status namespace';
  end if;

  for v_entry in select e from jsonb_array_elements(v_thresholds) e loop
    if jsonb_typeof(v_entry) is distinct from 'object' then
      raise exception 'applied-status threshold must be a JSON object';
    end if;
    if (v_entry - 'threshold_id' - 'amount' - 'unit') <> '{}'::jsonb then
      raise exception
        'applied-status threshold contains fields outside the EV2-13.1 contract (threshold_id, amount, unit)';
    end if;
    if not (v_entry ?& array['threshold_id', 'amount', 'unit']) then
      raise exception
        'applied-status threshold requires threshold_id, amount and unit';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    if not public._rhc_full_id_match(v_tid, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
      raise exception
        'applied-status threshold_id must be a stable non-blank token';
    end if;
    if array_position(v_seen, v_tid) is not null then
      raise exception
        'applied-status thresholds must be unique; duplicate threshold_id % is ambiguous',
        v_tid;
    end if;
    v_seen := array_append(v_seen, v_tid);

    v_amount := v_entry -> 'amount';
    if jsonb_typeof(v_amount) is distinct from 'number' then
      raise exception
        'applied-status threshold amount must be a JSON number of whole units';
    end if;
    if jsonb_typeof(v_entry -> 'unit') is distinct from 'string' then
      raise exception 'applied-status threshold unit must be a JSON string';
    end if;
    v_unit := v_entry ->> 'unit';

    -- EV2-13.420 is the only mechanical-duration arithmetic contract.
    v_minutes := public.mechanical_duration_to_campaign_minutes(
      (v_amount #>> '{}')::numeric, v_unit);

    v_due := p_applied_at::bigint + v_minutes;
    if v_due > v_rt02_max then
      raise exception
        'applied-status threshold % due anchor exceeds the RT02 elapsed_campaign_minutes range (0..%); a threshold the Clock can never reach is refused',
        v_tid, v_rt02_max;
    end if;

    v_out := v_out || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'due_at_elapsed_minutes', v_due::integer
    ));
  end loop;

  -- Deterministic ordering by threshold_id so value equality is stable.
  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_out
    from jsonb_array_elements(v_out) t;

  return jsonb_build_object(
    'definition_id', v_definition_id,
    'target_entity_id', v_target,
    'source_entity_id', v_source,
    'thresholds', v_out
  );
end;
$$;

revoke all on function public._rhc_normalize_applied_status_definition(jsonb, integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Full stored application-record validation + canonicalization (internal).
--    Proves a stored record is exactly the bounded EV2-13.1 shape and is
--    internally coherent: absolute elapsed anchors only, unique thresholds,
--    acknowledgements a subset of declared thresholds stamped at or after the
--    threshold became due, and no world-calendar/date field anywhere.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_applied_status_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_app_id text;
  v_definition_id text;
  v_target text;
  v_source jsonb;
  v_applied integer;
  v_thresholds jsonb;
  v_ack jsonb;
  v_entry jsonb;
  v_tid text;
  v_due integer;
  v_ack_at integer;
  v_ended jsonb;
  v_seen text[] := '{}';
  v_thr jsonb := '[]'::jsonb;
  v_out_ack jsonb := '[]'::jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'applied-status record must be a JSON object';
  end if;
  if (p_record - 'application_version' - 'application_id' - 'definition_id'
        - 'target_entity_id' - 'source_entity_id' - 'applied_at_elapsed_minutes'
        - 'thresholds' - 'acknowledged_thresholds'
        - 'ended_at_elapsed_minutes') <> '{}'::jsonb then
    raise exception
      'applied-status record contains fields outside the EV2-13.1 contract; a world-calendar or invented field is refused rather than canonicalized';
  end if;
  if not (p_record ?& array[
    'application_version', 'application_id', 'definition_id', 'target_entity_id',
    'source_entity_id', 'applied_at_elapsed_minutes', 'thresholds',
    'acknowledged_thresholds', 'ended_at_elapsed_minutes']) then
    raise exception
      'applied-status record is missing a required EV2-13.1 field';
  end if;

  if jsonb_typeof(p_record -> 'application_version') is distinct from 'number'
     or (p_record ->> 'application_version') is distinct from '1' then
    raise exception 'applied-status application_version must be 1';
  end if;

  if jsonb_typeof(p_record -> 'application_id') is distinct from 'string' then
    raise exception 'applied-status application_id must be a JSON string';
  end if;
  v_app_id := p_record ->> 'application_id';
  if not public._rhc_full_id_match(v_app_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
    raise exception
      'applied-status application_id must be a stable non-blank token';
  end if;

  if jsonb_typeof(p_record -> 'definition_id') is distinct from 'string' then
    raise exception 'applied-status definition_id must be a JSON string';
  end if;
  v_definition_id := p_record ->> 'definition_id';
  if not public._rhc_full_id_match(
    v_definition_id, '^status_effect:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status definition_id must be a status_effect:<slug> definition identity';
  end if;

  if jsonb_typeof(p_record -> 'target_entity_id') is distinct from 'string' then
    raise exception 'applied-status target_entity_id must be a JSON string';
  end if;
  v_target := p_record ->> 'target_entity_id';
  if not public._rhc_full_id_match(
    v_target, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status target_entity_id must be a character: or creature: mutable-actor identity';
  end if;

  v_source := p_record -> 'source_entity_id';
  if jsonb_typeof(v_source) is distinct from 'null' then
    if jsonb_typeof(v_source) is distinct from 'string'
       or not public._rhc_full_id_match(
         (v_source #>> '{}'),
         '^(character|location|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$') then
      raise exception
        'applied-status source_entity_id must be null or a typed <entity_type>:<slug> identity';
    end if;
  end if;

  if jsonb_typeof(p_record -> 'applied_at_elapsed_minutes') is distinct from 'number'
     or (p_record ->> 'applied_at_elapsed_minutes') !~ '^[0-9]+$' then
    raise exception
      'applied-status applied_at_elapsed_minutes must be a non-negative whole elapsed minute';
  end if;
  v_applied := (p_record ->> 'applied_at_elapsed_minutes')::integer;

  v_thresholds := p_record -> 'thresholds';
  if v_thresholds is null or jsonb_typeof(v_thresholds) is distinct from 'array'
     or jsonb_array_length(v_thresholds) = 0 then
    raise exception
      'applied-status record requires a non-empty thresholds array';
  end if;
  for v_entry in select e from jsonb_array_elements(v_thresholds) e loop
    if jsonb_typeof(v_entry) is distinct from 'object'
       or (v_entry - 'threshold_id' - 'due_at_elapsed_minutes') <> '{}'::jsonb
       or not (v_entry ?& array['threshold_id', 'due_at_elapsed_minutes']) then
      raise exception
        'applied-status record threshold must be exactly {threshold_id, due_at_elapsed_minutes}';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status record threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    if not public._rhc_full_id_match(v_tid, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
      raise exception
        'applied-status record threshold_id must be a stable non-blank token';
    end if;
    if array_position(v_seen, v_tid) is not null then
      raise exception
        'applied-status record thresholds must be unique; duplicate threshold_id %',
        v_tid;
    end if;
    v_seen := array_append(v_seen, v_tid);
    if jsonb_typeof(v_entry -> 'due_at_elapsed_minutes') is distinct from 'number'
       or (v_entry ->> 'due_at_elapsed_minutes') !~ '^[0-9]+$' then
      raise exception
        'applied-status record threshold due anchor must be a non-negative whole elapsed minute';
    end if;
    v_due := (v_entry ->> 'due_at_elapsed_minutes')::integer;
    if v_due < v_applied then
      raise exception
        'applied-status record threshold due anchor cannot precede the application anchor';
    end if;
    v_thr := v_thr || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'due_at_elapsed_minutes', v_due
    ));
  end loop;

  v_ack := p_record -> 'acknowledged_thresholds';
  if v_ack is null or jsonb_typeof(v_ack) is distinct from 'array' then
    raise exception 'applied-status record acknowledged_thresholds must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(v_ack) e loop
    if jsonb_typeof(v_entry) is distinct from 'object'
       or (v_entry - 'threshold_id' - 'acknowledged_at_elapsed_minutes') <> '{}'::jsonb
       or not (v_entry ?& array['threshold_id', 'acknowledged_at_elapsed_minutes']) then
      raise exception
        'applied-status acknowledgement must be exactly {threshold_id, acknowledged_at_elapsed_minutes}';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status acknowledgement threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    select (t ->> 'due_at_elapsed_minutes')::integer
      into v_due
      from jsonb_array_elements(v_thr) t
     where (t ->> 'threshold_id') = v_tid;
    if v_due is null then
      raise exception
        'applied-status acknowledgement names unknown threshold %', v_tid;
    end if;
    if jsonb_typeof(v_entry -> 'acknowledged_at_elapsed_minutes') is distinct from 'number'
       or (v_entry ->> 'acknowledged_at_elapsed_minutes') !~ '^[0-9]+$' then
      raise exception
        'applied-status acknowledgement anchor must be a non-negative whole elapsed minute';
    end if;
    v_ack_at := (v_entry ->> 'acknowledged_at_elapsed_minutes')::integer;
    if v_ack_at < v_due then
      raise exception
        'applied-status acknowledgement anchor cannot precede its threshold due anchor';
    end if;
    v_out_ack := v_out_ack || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'acknowledged_at_elapsed_minutes', v_ack_at
    ));
  end loop;

  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_out_ack
    from jsonb_array_elements(v_out_ack) t;

  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_thr
    from jsonb_array_elements(v_thr) t;

  v_ended := p_record -> 'ended_at_elapsed_minutes';
  if jsonb_typeof(v_ended) is distinct from 'null' then
    if jsonb_typeof(v_ended) is distinct from 'number'
       or (v_ended #>> '{}') !~ '^[0-9]+$' then
      raise exception
        'applied-status ended_at_elapsed_minutes must be null or a non-negative whole elapsed minute';
    end if;
    if (v_ended #>> '{}')::integer < v_applied then
      raise exception
        'applied-status end anchor cannot precede the application anchor';
    end if;
  end if;

  return jsonb_build_object(
    'application_version', 1,
    'application_id', v_app_id,
    'definition_id', v_definition_id,
    'target_entity_id', v_target,
    'source_entity_id', v_source,
    'applied_at_elapsed_minutes', v_applied,
    'thresholds', v_thr,
    'acknowledged_thresholds', v_out_ack,
    'ended_at_elapsed_minutes', v_ended
  );
end;
$$;

revoke all on function public._rhc_normalize_applied_status_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Whole-collection validation (internal). Proves the complete candidate
--    `applied_statuses` namespace is a JSON array of canonical records with
--    exactly one authoritative record per application identity. A duplicate
--    application identity is an ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_applied_statuses_collection(
  p_collection jsonb
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entry jsonb;
  v_norm jsonb;
  v_app_id text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'applied_statuses namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_applied_status_record(v_entry);
    v_app_id := v_norm ->> 'application_id';
    if array_position(v_seen, v_app_id) is not null then
      raise exception
        'applied_statuses namespace holds duplicate records for application %; exactly one authoritative record per application is required',
        v_app_id;
    end if;
    v_seen := array_append(v_seen, v_app_id);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_applied_statuses_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. Explicit same-save applied-status staging marker (internal). Closure keys
--    on the operation fact, not on final JSON equality: an absolute record can be
--    re-staged to a value that already equals published reality (a replay), and
--    the final value would look unchanged even though a successful staging
--    operation occurred. The save locator records the lock_token that staged an
--    applied status, so the marker can only match the CURRENT save's token and
--    never leaks into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists applied_status_staged_lock_token text;

create or replace function public._rhc_applied_status_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.applied_status_staged_lock_token is not null
            and cr.applied_status_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_applied_status_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.applied_status_staged_lock_token is
  'EV2-13.1 internal operation fact: the lock_token of the save that most recently staged a successful timed applied-status mutation. Matched against the active lock_token so the same-save applied-status/Run-ownership and applied-status/Campaign-Clock exclusions key on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 6. The validated atomic timed applied-status mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_applied_status(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "application_id": "<stable token>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "definition": {
--          "definition_id": "status_effect:<slug>",
--          "target_entity_id": "<character|creature>:<slug>",
--          "source_entity_id": null | "<entity_type>:<slug>",
--          "thresholds": [ { "threshold_id": "...", "amount": <whole number>,
--                             "unit": "second|round|minute|hour|day" } ]
--        },
--        "acknowledge": [ "<threshold_id>", ... ],
--        "end": true | false
--      }
--
--    `application_id` and `controller` are always required. `definition` is
--    required when the application does not yet exist and, when supplied on an
--    existing application, must exactly reproduce the immutable timing
--    definition (a replay). `acknowledge` and `end` are optional and additive.
--
--    Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth for
--        the target mutable actor (malformed/duplicated batch, parked claiming
--        Run and two-Run claim all fail closed rather than falling through to
--        MAINRUN);
--      * a same-save staged `runs` change (Run-ownership handoff) fails closed,
--        and a same-save staged `campaign_clock` change fails closed, because the
--        elapsed/controller truth this save would publish is not the truth the
--        mutation would be proven against;
--      * the application never trusts a caller `applied_at`, acknowledgement
--        anchor, end anchor, world date or absolute threshold position; every
--        anchor is derived from the authoritative published Clock;
--      * the complete existing and resulting `applied_statuses` namespaces are
--        validated before staging, so malformed or duplicate unrelated truth
--        fails closed and is never canonicalized by overwrite;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
--
--    This route does NOT change Run ownership, does not change the Clock, does
--    not mint a status_effect definition, and performs no automatic gameplay
--    consequence when a threshold becomes due.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_applied_status(
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
  v_app_id text;
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_target text;
  v_now integer;
  v_collection jsonb;
  v_new_collection jsonb;
  v_new_record jsonb;
  v_existing jsonb;
  v_matches integer;
  v_definition jsonb;
  v_applied_at integer;
  v_source jsonb;
  v_thresholds jsonb;
  v_ack jsonb;
  v_new_ack jsonb := '[]'::jsonb;
  v_ack_entry jsonb;
  v_ack_id text;
  v_ack_seen text[] := '{}';
  v_requested_ack jsonb;
  v_requested_ack_id text;
  v_thr jsonb;
  v_thr_id text;
  v_due integer;
  v_ended jsonb;
  v_end_requested boolean := false;
  v_has_definition boolean := false;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save controller integrity: applied-status authority is proven against
  -- PUBLISHED Run truth. If this save has already staged a different `runs`
  -- batch, published truth no longer describes the Run ownership this save will
  -- publish. Fail closed; Run-ownership changes and applied-status mutations
  -- belong in separate saves.
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; applied-status controller cannot be proven against published Run truth, so timed applied-status mutation fails closed (change Run ownership and applied status in separate saves)';
  end if;

  -- Same-save elapsed integrity: the elapsed anchors are derived from the
  -- authoritative published Clock. If this save has already staged a different
  -- `campaign_clock`, the elapsed truth this save would publish is not the truth
  -- the mutation would be proven against. Fail closed; Clock advances and
  -- applied-status mutations belong in separate saves.
  if public._rhc_state_key_changed_in_save(
       'campaign_clock', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different campaign_clock; applied-status elapsed anchors cannot be proven against the Clock this save would publish, so timed applied-status mutation fails closed (advance the Clock and mutate applied status in separate saves)';
  end if;

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'applied-status mutation request must be a JSON object';
  end if;
  if not (p_request ?& array['application_id', 'controller']) then
    raise exception
      'applied-status mutation request requires application_id and controller';
  end if;
  if (p_request - 'application_id' - 'controller' - 'definition'
        - 'acknowledge' - 'end') <> '{}'::jsonb then
    raise exception
      'applied-status mutation request contains fields outside the EV2-13.1 contract (application_id, controller, definition, acknowledge, end)';
  end if;

  if jsonb_typeof(p_request -> 'application_id') is distinct from 'string' then
    raise exception 'applied-status application_id must be a JSON string';
  end if;
  v_app_id := p_request ->> 'application_id';
  if not public._rhc_full_id_match(v_app_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
    raise exception
      'applied-status application_id must be a stable non-blank token';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch,
  -- so a null/missing/non-string/unknown kind can never fall through to MAINRUN.
  v_controller := p_request -> 'controller';
  if v_controller is null or jsonb_typeof(v_controller) is distinct from 'object' then
    raise exception 'controller must be a JSON object';
  end if;
  if not (v_controller ? 'kind') then
    raise exception 'controller requires a kind';
  end if;
  if jsonb_typeof(v_controller -> 'kind') is distinct from 'string' then
    raise exception 'controller kind must be a JSON string of mainrun or run';
  end if;
  v_kind := v_controller ->> 'kind';
  if v_kind is null or v_kind not in ('mainrun', 'run') then
    raise exception 'controller kind must be mainrun or run';
  end if;
  if v_kind = 'run' then
    if not (v_controller ? 'run_id')
       or (v_controller - 'kind' - 'run_id') <> '{}'::jsonb then
      raise exception 'run controller requires exactly kind and run_id';
    end if;
    v_run_id := v_controller ->> 'run_id';
    if not public._rhc_full_id_match(v_run_id, '^R[0-9]{2,}$') then
      raise exception 'controller run_id must be R followed by at least two digits';
    end if;
  else
    if (v_controller - 'kind') <> '{}'::jsonb then
      raise exception 'mainrun controller accepts exactly kind';
    end if;
  end if;

  if p_request ? 'definition' then
    v_has_definition := true;
    if jsonb_typeof(p_request -> 'definition') is distinct from 'object' then
      raise exception 'applied-status definition must be a JSON object';
    end if;
  end if;

  if p_request ? 'acknowledge' then
    v_requested_ack := p_request -> 'acknowledge';
    if v_requested_ack is null or jsonb_typeof(v_requested_ack) is distinct from 'array' then
      raise exception 'applied-status acknowledge must be a JSON array of threshold ids';
    end if;
  else
    v_requested_ack := '[]'::jsonb;
  end if;
  if p_request ? 'end' then
    if jsonb_typeof(p_request -> 'end') is distinct from 'boolean' then
      raise exception 'applied-status end must be a JSON boolean';
    end if;
    v_end_requested := (p_request ->> 'end')::boolean;
  end if;

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'applied_statuses';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'applied_statuses';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'applied_statuses namespace is unreadable; mutation fails closed';
  end if;

  -- Validate the EXISTING namespace before anything is staged.
  perform public._rhc_validate_applied_statuses_collection(v_collection);

  select count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'application_id') = v_app_id
    )
    into v_matches
    from jsonb_array_elements(v_collection) e;

  -- Find the existing canonical record (there is at most one, already proven).
  select public._rhc_normalize_applied_status_record(e)
    into v_existing
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'application_id') = v_app_id;

  -- Authoritative elapsed cursor. Missing Clock fails closed.
  v_now := public._rhc_published_clock_elapsed();

  if v_existing is null then
    if not v_has_definition then
      raise exception
        'application % does not exist; a new timed applied-status requires a definition',
        v_app_id;
    end if;
    v_applied_at := v_now;
    v_definition := public._rhc_normalize_applied_status_definition(
      p_request -> 'definition', v_applied_at);
  else
    v_applied_at := (v_existing ->> 'applied_at_elapsed_minutes')::integer;
    if v_has_definition then
      v_definition := public._rhc_normalize_applied_status_definition(
        p_request -> 'definition', v_applied_at);
      if v_definition ->> 'definition_id'
           is distinct from v_existing ->> 'definition_id'
         or v_definition ->> 'target_entity_id'
           is distinct from v_existing ->> 'target_entity_id'
         or (v_definition -> 'source_entity_id')
           is distinct from (v_existing -> 'source_entity_id')
         or (v_definition -> 'thresholds')
           is distinct from (v_existing -> 'thresholds') then
        raise exception
          'applied-status timing definition is immutable after application; changing the definition (reapplication/refresh/replace) is deferred to later status-rules work';
      end if;
    else
      v_definition := jsonb_build_object(
        'definition_id', v_existing -> 'definition_id',
        'target_entity_id', v_existing -> 'target_entity_id',
        'source_entity_id', v_existing -> 'source_entity_id',
        'thresholds', v_existing -> 'thresholds'
      );
    end if;
  end if;

  v_target := v_definition ->> 'target_entity_id';
  v_source := v_definition -> 'source_entity_id';
  v_thresholds := v_definition -> 'thresholds';

  -- Authoritative controller: published Run truth only, via the shared EV2-10
  -- resolver.
  declare
    v_current text;
  begin
    v_current := public._rhc_inventory_controller_for_owner(v_target);
    if v_kind = 'run' then
      if v_current is null then
        raise exception
          'no published Run currently controls %; a Run controller cannot assert timed applied-status authority',
          v_target;
      end if;
      if v_current is distinct from v_run_id then
        raise exception
          'published Run % currently controls %; asserted Run % does not own it, so this applied-status mutation crosses controllers and fails closed',
          v_current, v_target, v_run_id;
      end if;
    else
      if v_current is not null then
        raise exception
          'published Run % currently controls %; MAINRUN may not mutate that actor''s applied status (route the cross-controller handoff through the existing reconciliation boundary)',
          v_current, v_target;
      end if;
    end if;
  end;

  -- Preserve existing acknowledgement anchors (idempotent), then apply the
  -- requested acknowledgements. Anchors are stamped from the authoritative
  -- published elapsed cursor, never from caller input.
  if v_existing is not null then
    for v_ack_entry in
      select a from jsonb_array_elements(v_existing -> 'acknowledged_thresholds') a
    loop
      v_new_ack := v_new_ack || jsonb_build_array(v_ack_entry);
      v_ack_seen := array_append(v_ack_seen, v_ack_entry ->> 'threshold_id');
    end loop;
  end if;

  v_ended := case when v_existing is null then 'null'::jsonb
                  else v_existing -> 'ended_at_elapsed_minutes' end;

  for v_requested_ack_id in
    select (a #>> '{}') from jsonb_array_elements(v_requested_ack) a
  loop
    if not public._rhc_full_id_match(
      v_requested_ack_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
      raise exception
        'applied-status acknowledge names malformed threshold id %',
        v_requested_ack_id;
    end if;

    select (t -> 'threshold_id') into v_thr_id
      from jsonb_array_elements(v_thresholds) t
     where (t ->> 'threshold_id') = v_requested_ack_id;
    if v_thr_id is null then
      raise exception
        'applied-status acknowledge names unknown threshold %',
        v_requested_ack_id;
    end if;

    if array_position(v_ack_seen, v_requested_ack_id) is not null then
      continue;  -- idempotent replay of an already-acknowledged threshold
    end if;

    if jsonb_typeof(v_ended) is distinct from 'null' then
      raise exception
        'application % has ended; a threshold cannot be acknowledged after the application end anchor',
        v_app_id;
    end if;

    select (t ->> 'due_at_elapsed_minutes')::integer into v_due
      from jsonb_array_elements(v_thresholds) t
     where (t ->> 'threshold_id') = v_requested_ack_id;
    if v_due > v_now then
      raise exception
        'threshold % of application % is not yet due at elapsed minute %; due detection and acknowledgement are separate and a future threshold cannot be pre-acknowledged',
        v_requested_ack_id, v_app_id, v_now;
    end if;

    v_new_ack := v_new_ack || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_requested_ack_id,
      'acknowledged_at_elapsed_minutes', v_now
    ));
    v_ack_seen := array_append(v_ack_seen, v_requested_ack_id);
  end loop;

  select coalesce(jsonb_agg(a order by (a ->> 'threshold_id')), '[]'::jsonb)
    into v_new_ack
    from jsonb_array_elements(v_new_ack) a;

  -- End lifecycle: terminal, stamped from the authoritative elapsed cursor.
  if v_end_requested and jsonb_typeof(v_ended) = 'null' then
    v_ended := to_jsonb(v_now);
  end if;

  v_new_record := public._rhc_normalize_applied_status_record(jsonb_build_object(
    'application_version', 1,
    'application_id', v_app_id,
    'definition_id', v_definition ->> 'definition_id',
    'target_entity_id', v_target,
    'source_entity_id', v_source,
    'applied_at_elapsed_minutes', v_applied_at,
    'thresholds', v_thresholds,
    'acknowledged_thresholds', v_new_ack,
    'ended_at_elapsed_minutes', v_ended
  ));

  -- Replace the application's single record, or append it when new.
  select coalesce(jsonb_agg(
    case when jsonb_typeof(e) = 'object' and (e ->> 'application_id') = v_app_id
         then v_new_record else e end
  ), '[]'::jsonb)
  into v_new_collection
  from jsonb_array_elements(v_collection) e;

  if v_matches = 0 then
    v_new_collection := v_new_collection || jsonb_build_array(v_new_record);
  elsif v_matches > 1 then
    raise exception
      'applied_statuses namespace already holds duplicate records for %; failing closed',
      v_app_id;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_applied_statuses_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'applied_statuses', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact: a successful applied-status staging happened in
  -- this save, independent of value equality. This closes every Run-ownership
  -- and Campaign-Clock writing doorway for the rest of the save.
  update public.campaign_runtime
     set applied_status_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'applied_status_mutation_version', 1,
    'application_id', v_app_id,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'application', v_new_record
  );
end;
$$;

revoke all on function public.mutate_applied_status(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_applied_status(text, jsonb) to service_role;

comment on function public.mutate_applied_status(text, jsonb) is
  'EV2-13.1: the only validated atomic timed applied-status mutation route, inside the normal RT01 save lifecycle. Requires application_id and an explicit structurally valid controller assertion, proves the asserted MAINRUN-or-one-RUN controller against authoritative published Run truth for the target character:/creature: actor, derives the application anchor and every acknowledgement/end anchor from the authoritative published Clock elapsed cursor, normalizes relative durations through EV2-13.420 without duplicating time arithmetic, keeps the timing definition immutable, and stages exactly one application record per identity into the engine-owned applied_statuses namespace while recording the staging operation fact that closes Run-ownership and Campaign-Clock writing doorways for the rest of the save. Absolute, replay-safe, all-or-nothing through the existing gateway. Owns no controller authority and no elapsed-time authority.';

-- ---------------------------------------------------------------------------
-- 7. Pure service-only due-threshold read. Derives due-ness from the current
--    published elapsed cursor, so an arbitrarily large forward jump exposes ALL
--    still-unacknowledged crossed thresholds with no per-minute ticking. Reads
--    published state only and mutates nothing.
-- ---------------------------------------------------------------------------
create or replace function public.read_timed_applied_status(
  p_application_id text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_collection jsonb;
  v_record jsonb;
  v_now integer;
  v_applied integer;
  v_ended jsonb;
  v_thr jsonb;
  v_ack_ids text[] := '{}';
  v_entry jsonb;
  v_due jsonb;
  v_ack jsonb := '[]'::jsonb;
  v_due_out jsonb := '[]'::jsonb;
  v_pending_out jsonb := '[]'::jsonb;
  v_t jsonb;
  v_tid text;
  v_due_at integer;
begin
  if not public._rhc_full_id_match(
    p_application_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
    raise exception
      'applied-status read requires a stable non-blank application_id token';
  end if;

  v_now := public._rhc_published_clock_elapsed();

  select csg.value into v_collection
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation
   where csg.key = 'applied_statuses';
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'applied_statuses namespace is unreadable; applied-status read fails closed';
  end if;
  perform public._rhc_validate_applied_statuses_collection(v_collection);

  select public._rhc_normalize_applied_status_record(e)
    into v_record
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'application_id') = p_application_id;

  if v_record is null then
    return jsonb_build_object(
      'read_version', 1,
      'mode', 'timed_applied_status',
      'runtime', public._rhc_dm_runtime_metadata(),
      'application_id', p_application_id,
      'application', null,
      'due_thresholds', '[]'::jsonb,
      'pending_thresholds', '[]'::jsonb
    );
  end if;

  v_applied := (v_record ->> 'applied_at_elapsed_minutes')::integer;
  v_ended := v_record -> 'ended_at_elapsed_minutes';
  v_thr := v_record -> 'thresholds';

  for v_entry in
    select a from jsonb_array_elements(v_record -> 'acknowledged_thresholds') a
  loop
    v_ack_ids := array_append(v_ack_ids, v_entry ->> 'threshold_id');
  end loop;

  for v_t in select t from jsonb_array_elements(v_thr) t loop
    v_tid := v_t ->> 'threshold_id';
    v_due_at := (v_t ->> 'due_at_elapsed_minutes')::integer;
    if array_position(v_ack_ids, v_tid) is not null then
      continue;
    end if;
    if jsonb_typeof(v_ended) is distinct from 'null' then
      continue;
    end if;
    if v_due_at <= v_now then
      v_due_out := v_due_out || jsonb_build_array(jsonb_build_object(
        'threshold_id', v_tid,
        'due_at_elapsed_minutes', v_due_at,
        'overdue_by_elapsed_minutes', v_now - v_due_at
      ));
    else
      v_pending_out := v_pending_out || jsonb_build_array(jsonb_build_object(
        'threshold_id', v_tid,
        'due_at_elapsed_minutes', v_due_at,
        'remaining_elapsed_minutes', v_due_at - v_now
      ));
    end if;
  end loop;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'timed_applied_status',
    'runtime', public._rhc_dm_runtime_metadata(),
    'application_id', p_application_id,
    'application', v_record || jsonb_build_object(
      'age_elapsed_minutes', v_now - v_applied
    ),
    'due_thresholds', v_due_out,
    'pending_thresholds', v_pending_out
  );
end;
$$;

revoke all on function public.read_timed_applied_status(text)
  from public, anon, authenticated;
grant execute on function public.read_timed_applied_status(text) to service_role;

comment on function public.read_timed_applied_status(text) is
  'EV2-13.1: the service-only pure read for one timed applied-status application. Reads only the published applied_statuses namespace and the published Clock elapsed cursor, derives age and every due/pending threshold from elapsed minutes (never from a world date or a per-minute tick), and exposes all still-unacknowledged crossed thresholds after a forward jump. Mutates nothing.';

-- ---------------------------------------------------------------------------
-- 8. Close the generic `applied_statuses` bypass. The namespace is engine-owned:
--    it can never be staged or deleted through the generic routes. This
--    re-declares the HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13 generic routes
--    unchanged except for the added applied_statuses closure and the same-save
--    applied-status/Run-ownership exclusion, preserving every existing
--    dedicated-key closure and the server-owned ordinary-save allowlist exactly.
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
  if p_key = 'inventory' then
    raise exception 'inventory is engine-owned and can only be staged through mutate_owner_inventory';
  end if;
  if p_key = 'item_custody' then
    raise exception 'item_custody is engine-owned and can only be staged through mutate_item_custody or admit_item_identity';
  end if;
  if p_key = 'item_admissions' then
    raise exception 'item_admissions is engine-owned and can only be staged through admit_item_identity';
  end if;
  if p_key = 'entity_state' then
    raise exception 'entity_state is engine-owned and can only be staged through mutate_entity_state';
  end if;
  if p_key = 'applied_statuses' then
    raise exception 'applied_statuses is engine-owned and can only be staged through mutate_applied_status';
  end if;
  if p_key = 'runs'
     and public._rhc_reconciliation_new_in_save(r.staging_generation, r.published_generation) then
    raise exception
      'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; a later generic runs mutation could reintroduce duplicate mutable ownership or erase the reconciled candidate; abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_inventory_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged an inventory mutation; inventory authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_custody_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged an item custody or admission operation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_entity_state_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a mutable entity-state mutation; entity-state authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_applied_status_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  -- HWB-02: server-owned ordinary-save key policy. The allowlist is a constant
  -- of this schema, never caller-supplied. Unknown/undeclared keys fail closed.
  if p_key not in ('daily_recap', 'day_resolution', 'live_status', 'dm_meta',
                   'narrative_hooks', 'runs') then
    raise exception
      'campaign state key % is not allowed for campaign_save; the server-owned allowlist is daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs; unknown or undeclared runtime keys fail closed (HWB-02 save runtime authority)',
      p_key;
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
  if p_key = 'inventory' then
    raise exception 'inventory is engine-owned and cannot be deleted through the generic route';
  end if;
  if p_key = 'item_custody' then
    raise exception 'item_custody is engine-owned and cannot be deleted through the generic route';
  end if;
  if p_key = 'item_admissions' then
    raise exception 'item_admissions is engine-owned and cannot be deleted through the generic route';
  end if;
  if p_key = 'entity_state' then
    raise exception 'entity_state is engine-owned and cannot be deleted through the generic route';
  end if;
  if p_key = 'applied_statuses' then
    raise exception 'applied_statuses is engine-owned and cannot be deleted through the generic route';
  end if;
  if p_key = 'runs'
     and public._rhc_reconciliation_new_in_save(r.staging_generation, r.published_generation) then
    raise exception
      'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; deleting it would erase the reconciled candidate while the consumption ledger claims it was applied; abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_inventory_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged an inventory mutation; inventory authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_custody_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged an item custody or admission operation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_entity_state_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a mutable entity-state mutation; entity-state authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  if p_key = 'runs'
     and public._rhc_applied_status_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one';
  end if;
  -- HWB-02: the same server-owned ordinary-save key policy as staging.
  if p_key not in ('daily_recap', 'day_resolution', 'live_status', 'dm_meta',
                   'narrative_hooks', 'runs') then
    raise exception
      'campaign state key % is not allowed for campaign_save; the server-owned allowlist is daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs; unknown or undeclared runtime keys fail closed (HWB-02 save runtime authority)',
      p_key;
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory, item_custody, item_admissions, entity_state and applied_statuses keys are rejected here and must use their validated routes (applied_statuses via mutate_applied_status). Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation, an item custody/admission operation, a mutable entity-state mutation, or a timed applied-status mutation, the runs key is refused for the rest of the save. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';
comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody/admission/entity-state/applied-status and Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';

-- ---------------------------------------------------------------------------
-- 9. Close the Campaign-Clock-after-applied-status doorway. The generic `runs`
--    closure above stops same-save Run changes once applied status is staged, but
--    RT02's dedicated Clock route writes `campaign_clock` with a direct INSERT and
--    would bypass it. This re-declares the RT02 route unchanged except for the
--    same-save applied-status guard, so a Clock advance cannot share one candidate
--    save with a status mutation in either ordering. The Clock remains the only
--    elapsed-time authority; nothing about Clock validation changes.
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

  -- EV2-13.1 same-save coupling: applied-status anchors were derived from the
  -- published Clock, so advancing the Clock in the same generation would leave
  -- those anchors proven against elapsed truth this save is about to replace.
  if public._rhc_applied_status_staged_in_save() then
    raise exception
      'this save has already staged a timed applied-status mutation; advancing the Campaign Clock in the same save would leave applied-status anchors proven against the wrong elapsed truth, so the Clock write fails closed (advance the Clock and mutate applied status in separate saves)';
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

  if v_bday is not null then
    if v_tday is null then
      raise exception 'campaign_clock day cannot be unset once established';
    end if;
    if v_tday < v_bday then
      raise exception 'campaign_clock day cannot move backwards';
    end if;
  end if;

  if v_tday is not null and v_tday = v_bday and v_bphase <> 'unknown' then
    if v_tphase = 'unknown' then
      raise exception 'campaign_clock phase cannot become unknown on the established day';
    end if;
    if public._rhc_phase_order(v_tphase) < public._rhc_phase_order(v_bphase) then
      raise exception 'campaign_clock phase cannot move backwards within the same day';
    end if;
  end if;

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

comment on function public.stage_campaign_clock(text, jsonb) is
  'RT02/EV2-13.1: the only validated Clock mutation route. Stages an absolute target Clock after shape + monotonic/coherence validation against the authoritative published Clock. Replay-safe by construction. EV2-13.1 adds the same-save guard: once this save has staged a timed applied-status mutation, a Clock advance fails closed so applied-status anchors are never proven against stale elapsed truth.';

-- ---------------------------------------------------------------------------
-- 10. Close the dedicated RT04 reconciliation-after-applied-status doorway. The
--     generic `runs` closure above stops generic same-save Run changes once
--     applied status has been staged, but `reconcile_run_resolution` writes the
--     `runs` batch with a direct INSERT and would bypass it. This re-declares the
--     RT04 route unchanged except for the same-save applied-status guard (on top
--     of the EV2-10 inventory and EV2-11 custody and EV2-13 entity-state guards),
--     so every Run-ownership-writing doorway fails closed in a save that has
--     staged a timed applied-status mutation. RT04 is not redesigned.
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

  if public._rhc_inventory_staged_in_save() then
    raise exception
      'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)';
  end if;

  if public._rhc_custody_staged_in_save() then
    raise exception
      'this save has already staged an item custody mutation; a Run reconciliation would change Run ownership after custody authority was proven, so reconciliation fails closed (change Run ownership and item custody in separate saves)';
  end if;

  if public._rhc_entity_state_staged_in_save() then
    raise exception
      'this save has already staged a mutable entity-state mutation; a Run reconciliation would change Run ownership after entity-state authority was proven, so reconciliation fails closed (change Run ownership and mutable entity state in separate saves)';
  end if;

  -- EV2-13.1 same-save coupling: the same law for a staged timed applied-status
  -- mutation. Applied-status controller authority was proven against the
  -- published Run controller, so a later reconciliation must not change Run
  -- ownership in the same generation.
  if public._rhc_applied_status_staged_in_save() then
    raise exception
      'this save has already staged a timed applied-status mutation; a Run reconciliation would change Run ownership after applied-status controller authority was proven, so reconciliation fails closed (change Run ownership and applied status in separate saves)';
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

  v_read := public.dm_runtime_read_run(v_run_id);
  v_run := v_read -> 'run';
  if v_run is null or jsonb_typeof(v_run) is distinct from 'object' then
    raise exception 'source Run % does not exist in published reality; reconciliation fails closed', v_run_id;
  end if;

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

  for v_t in select * from jsonb_array_elements(v_released) loop
    if not (v_owners ? (v_t #>> '{}')) then
      raise exception 'source Run does not own released mutable entity %; releasing it would be stale authority', v_t #>> '{}';
    end if;
  end loop;

  select coalesce(jsonb_agg(o), '[]'::jsonb)
    into v_new_owners
    from jsonb_array_elements(v_owners) o
   where not (v_released ? (o #>> '{}'));

  v_preserved := '[]'::jsonb;
  for v_c in select * from jsonb_array_elements(v_resolution -> 'proposed_consequences') loop
    v_scope := v_c ->> 'scope';
    v_kind := v_c ->> 'kind';

    if v_scope = 'run_objective' and v_kind = 'objective_result' then
      continue;
    end if;

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

  v_mode := v_run ->> 'execution_mode';
  v_state := v_run ->> 'control_state';
  if jsonb_array_length(v_new_owners) = 0 and v_mode = 'played' then
    v_new_state := 'parked';
  else
    v_new_state := v_state;
  end if;

  v_band := v_resolution ->> 'outcome_band';
  v_summary := 'Resolution ' || v_rid || ' accepted: ' || v_band
    || ' objective result. Scenario objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,scenario_objective}'), ' '), '.')
    || '. Hook objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,hook_objective}'), ' '), '.')
    || '.';

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

  perform public._rhc_validate_candidate_run_ownership(v_new_runs);

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
  'RT04/EV2-10/EV2-11/EV2-13/EV2-13.1: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet, and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. EV2-13.1 adds the same-save guard for a staged timed applied-status mutation on top of the EV2-10 inventory, EV2-11 custody and EV2-13 entity-state guards. All-or-nothing through the existing gateway.';
