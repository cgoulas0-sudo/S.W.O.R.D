-- POST-EV2-4A — Temporal / timespace travel continuity
-- Rolling High Club validated runtime placement of a play lane in world-calendar
-- and timespace coordinates, on the ONE Save Gateway spine.
--
-- This migration is NOT a world calendar, NOT an alternate-reality system, NOT a
-- second elapsed-time authority and NOT a second Run/controller authority. It
-- adds ONE validated, atomic runtime mutation route for lane-scoped
-- temporal/timespace placement on the existing RT01 begin -> validated stage ->
-- publish -> mirror/confirmation spine, and extends POST-EV2-1 Patch 1A's domain
-- registry and Patch 1B's same-save compatibility contract by exactly one
-- domain and its audited edges.
--
-- Architecture sentence:
--   POST-EV2-4A does not create a new persistence authority. It creates ONE
--   engine-owned `temporal_positions` runtime mutation surface that records the
--   current world-calendar/timespace placement of a play lane (CAMPAIGN MAINRUN
--   or one valid published RUN #) inside the single canonical campaign reality,
--   so a portal / planar / magical / DM-authored jump can move a lane backward or
--   forward in world chronology without being confused with Campaign Day
--   identity, RT02 experienced elapsed time, EV2-13 mutable state, EV2-13.1
--   status ageing or EV2-14 knowledge.
--
-- WHAT this migration changes:
--   1. `public.mutate_temporal_position(p_lock_token, p_request)` — the ONLY way
--      to stage the engine-owned `temporal_positions` runtime namespace. It runs
--      INSIDE the normal campaign save lifecycle, resolves the target play lane
--      from the caller's controller assertion, proves a RUN-scoped lane against
--      authoritative PUBLISHED Run truth, validates + canonicalizes one absolute
--      temporal/timespace position (or one supported deterministic relative
--      whole-year displacement from the current position), and stages exactly one
--      authoritative record per play lane.
--   2. The engine-owned `temporal_positions` runtime namespace is a JSON array
--      holding exactly one record per play lane (`mainrun` or `run:<R##>`). It is
--      NOT a second chronology engine and NOT a per-era copy of entity state: it
--      stores only the lane's current placement truth.
--   3. POST-EV2-1 Patch 1A: `_rhc_save_domain_policy` gains `temporal_positions`
--      as `dedicated` with the exhaustive writer set `[mutate_temporal_position]`;
--      the generic `stage_campaign_state` / `delete_staged_campaign_state` routes
--      therefore fail closed for this key.
--   4. POST-EV2-1 Patch 1B: `_rhc_same_save_compatibility_policy` gains the
--      `mutate_temporal_position` operation (blocked by a same-save `runs`
--      change) and a trailing `temporal_positions` edge on `stage_runs` /
--      `delete_runs` / `reconcile_runs`. The compatibility decision function
--      gains the `temporal_position_staged_in_save` detector. The existing
--      doorways already delegate to the shared contract, so no other route body
--      changes.
--
-- TIME MODEL (the declared layering is preserved exactly):
--   * Campaign Day ID is archive/gameplay sequence identity, not chronology.
--   * RT02 `campaign_clock.elapsed_campaign_minutes` is monotonic experienced
--     duration and is never a world-calendar date or a minute-of-day clock.
--   * EV2-13.420 owns deterministic mechanical-duration arithmetic only.
--   * EV2-13.1 ages live timed statuses only from RT02 elapsed time.
--   * `temporal_positions` owns only the current lane placement in
--     world-calendar/timespace coordinates. It never mutates Campaign Day, RT02
--     elapsed minutes, Long Rest counters, entity state, applied statuses or
--     knowledge.
--   * A backward or forward world-calendar jump is NOT elapsed-time mutation:
--     RT02 never moves backward and a future jump does not mean travelers
--     personally experienced the intervening years.
--
-- POSITION MODEL:
--   * A record is `lane` + `chronology` + `timespace`.
--   * `lane` is `mainrun` or `run:<R##>`.
--   * `chronology` is a bounded object carrying any subset of the integer
--     components `year` (signed), `month`, `day`, `hour`, `minute` (non-negative).
--     A missing component is truthful Unknown; the engine never invents finer
--     precision. An empty `chronology` is a wholly Unknown local chronology.
--     No calendar-specific range or month-length rule is enforced (Harptos /
--     Dalereckoning calendar arithmetic is deliberately deferred); only integral
--     shape is validated.
--   * `timespace` is `{"status":"unknown"}` or
--     `{"status":"known","ref":"<lower-slug>"}` — a known/Unknown plane or
--     timespace reference.
--   * There is no engine default position: absence of a lane record is truthful
--     Unknown, never an invented default date.
--
-- RELATIVE DISPLACEMENT:
--   * The only supported relative arithmetic is a signed whole-YEAR displacement
--     (`relative_year_displacement`) applied to a lane whose current year is
--     known. Already-known finer components (month/day/hour/minute) and the
--     current timespace are preserved deterministically.
--   * A relative displacement from an Unknown current year fails closed rather
--     than inventing a destination. Day/month/calendar offsets are not part of
--     the contract and fail closed.
--
-- LANE AUTHORITY:
--   * MAINRUN is always a valid lane and needs no Run proof; it is also
--     independent of the Campaign Clock and of a same-save `runs` change.
--   * A RUN-scoped lane is valid only when the exact Run identity is present in
--     authoritative PUBLISHED Run truth and is not a parked played Run; a
--     missing/malformed/duplicate/non-authoritative published Run batch fails
--     closed via the shared reader.
--   * `dm_meta.run_claims` is coordination metadata only and never grants
--     temporal placement authority.
--
-- SAME-SAVE COMPATIBILITY (through the existing Patch 1B contract):
--   * a RUN-scoped temporal mutation fails closed when this save has already
--     staged a different `runs` batch, because RUN identity/control truth is
--     proven against PUBLISHED Run state;
--   * once this save has staged a RUN-scoped temporal position every
--     Run-ownership-writing doorway is refused (generic `runs` stage/delete and
--     the dedicated RT04 `reconcile_run_resolution`), so stale RUN lane authority
--     can never be published through a same-save ownership handoff;
--   * a MAINRUN temporal mutation is deliberately not blocked by, and does not
--     block, a same-save `runs` change or Campaign Clock change: MAINRUN lane
--     placement does not rest on published Run truth and is not elapsed time.
--   Closure keys on the explicit RUN-scoped temporal-staging operation fact, not
--   on final value equality, and the marker is bound to the save's own
--   database-minted lock token so it never leaks into a later save.
--
-- DEFERRED OWNERSHIP (must NOT be absorbed here):
--   * POST-EV2-4B owns alternate reality / alternate-history identity.
--   * Harptos/Dalereckoning representation, the exact RHC timeline anchor and
--     non-trivial month/day calendar adapters belong to a later consumer-driven
--     gate; POST-EV2-4A stores only the caller's own chronology truth.
--   * ERA-appropriate selective context/RAG hydration, automatic knowledge gain/
--     loss, paradox resolution, prepared-content rewriting by era, NPC
--     scheduling/autosave, general spatial/location movement and ageing/
--     rejuvenation effects are all out of scope.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/
--    EV2-13.1/POST-EV2-1/POST-EV2-3 forward-only install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'POST-EV2-4A migration refused: resolve the active campaign save before installing the temporal/timespace position route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Bounded world-calendar chronology validation + canonicalization (internal).
--    `chronology` carries any subset of the integer components year, month, day,
--    hour, minute. A missing component is truthful Unknown. The engine validates
--    integral shape only; NO calendar-specific range/month-length rule is
--    invented (Harptos/Dalereckoning arithmetic is deferred).
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_temporal_chronology(
  p_chronology jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_key text;
  v_text text;
  v_out jsonb := '{}'::jsonb;
begin
  if p_chronology is null or jsonb_typeof(p_chronology) is distinct from 'object' then
    raise exception 'temporal chronology must be a JSON object';
  end if;
  if (p_chronology - 'year' - 'month' - 'day' - 'hour' - 'minute') <> '{}'::jsonb then
    raise exception
      'temporal chronology contains fields outside the POST-EV2-4A contract (year, month, day, hour, minute)';
  end if;

  foreach v_key in array array['year', 'month', 'day', 'hour', 'minute'] loop
    if p_chronology ? v_key then
      if jsonb_typeof(p_chronology -> v_key) is distinct from 'number' then
        raise exception 'temporal chronology % must be a JSON integer', v_key;
      end if;
      v_text := p_chronology ->> v_key;
      if v_key = 'year' then
        -- Year is signed so backwards placement (for example year -400) is real.
        if v_text !~ '^-?[0-9]+$' then
          raise exception 'temporal chronology year must be a signed integer';
        end if;
      else
        if v_text !~ '^[0-9]+$' then
          raise exception 'temporal chronology % must be a non-negative integer', v_key;
        end if;
      end if;
      v_out := v_out || jsonb_build_object(v_key, v_text::bigint);
    end if;
  end loop;
  return v_out;
end;
$$;

revoke all on function public._rhc_normalize_temporal_chronology(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Bounded timespace/plane reference validation + canonicalization (internal).
--    Unknown stays Unknown and never carries a ref; a known reference is a
--    non-blank lower-slug identity. No setting-specific plane catalog is encoded.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_temporal_timespace(
  p_timespace jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_ref text;
begin
  if p_timespace is null or jsonb_typeof(p_timespace) is distinct from 'object' then
    raise exception 'temporal timespace must be a JSON object';
  end if;
  if (p_timespace - 'status' - 'ref') <> '{}'::jsonb then
    raise exception
      'temporal timespace contains fields outside the POST-EV2-4A contract (status, ref)';
  end if;
  if not (p_timespace ? 'status') then
    raise exception 'temporal timespace requires a status';
  end if;
  if jsonb_typeof(p_timespace -> 'status') is distinct from 'string' then
    raise exception 'temporal timespace status must be a JSON string of known or unknown';
  end if;
  v_status := p_timespace ->> 'status';
  if v_status not in ('known', 'unknown') then
    raise exception 'temporal timespace status must be known or unknown';
  end if;

  if v_status = 'unknown' then
    if p_timespace ? 'ref' then
      raise exception 'an unknown temporal timespace must not carry a ref';
    end if;
    return jsonb_build_object('status', 'unknown');
  end if;

  if not (p_timespace ? 'ref') then
    raise exception 'a known temporal timespace requires a ref';
  end if;
  if jsonb_typeof(p_timespace -> 'ref') is distinct from 'string'
     or not public._rhc_full_id_match(
              p_timespace ->> 'ref', '^[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'temporal timespace ref must be a non-blank lower-slug identity';
  end if;
  v_ref := p_timespace ->> 'ref';
  return jsonb_build_object('status', 'known', 'ref', v_ref);
end;
$$;

revoke all on function public._rhc_normalize_temporal_timespace(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Full temporal-position record validation + canonicalization (internal).
--    Binds a play-lane identity to a canonical chronology + timespace placement.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_temporal_position_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_lane text;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'temporal position record must be a JSON object';
  end if;
  if (p_record - 'lane' - 'chronology' - 'timespace') <> '{}'::jsonb then
    raise exception
      'temporal position record contains fields outside the POST-EV2-4A contract (lane, chronology, timespace)';
  end if;
  if not (p_record ?& array['lane', 'chronology', 'timespace']) then
    raise exception 'temporal position record requires lane, chronology and timespace';
  end if;
  if jsonb_typeof(p_record -> 'lane') is distinct from 'string' then
    raise exception 'temporal position lane must be a JSON string identity';
  end if;
  v_lane := p_record ->> 'lane';
  if not public._rhc_full_id_match(v_lane, '^mainrun$|^run:R[0-9]{2,}$') then
    raise exception
      'temporal position lane must be mainrun or run:<R##>';
  end if;

  return jsonb_build_object(
    'lane', v_lane,
    'chronology', public._rhc_normalize_temporal_chronology(p_record -> 'chronology'),
    'timespace', public._rhc_normalize_temporal_timespace(p_record -> 'timespace')
  );
end;
$$;

revoke all on function public._rhc_normalize_temporal_position_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Whole-collection validation (internal). The complete candidate
--    `temporal_positions` namespace is proven before it can be staged: a JSON
--    array of canonical records with exactly one authoritative record per play
--    lane. A duplicate lane record is an ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_temporal_positions_collection(
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
  v_lane text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'temporal_positions namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_temporal_position_record(v_entry);
    v_lane := v_norm ->> 'lane';
    if array_position(v_seen, v_lane) is not null then
      raise exception
        'temporal_positions namespace holds duplicate records for lane %; exactly one authoritative position per play lane is required',
        v_lane;
    end if;
    v_seen := array_append(v_seen, v_lane);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_temporal_positions_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. Explicit same-save RUN-scoped temporal-staging marker (internal). Closure
--    must key on the operation fact, not on final JSON equality. The marker is
--    recorded ONLY for a RUN-scoped placement: a MAINRUN placement does not rest
--    on published Run truth and must not block a same-save `runs` change. The
--    database mints a fresh lock_token at every BEGIN and clears stale candidate
--    rows, so the marker can only match the CURRENT save's token and never leaks
--    into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists temporal_position_staged_lock_token text;

create or replace function public._rhc_temporal_position_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.temporal_position_staged_lock_token is not null
            and cr.temporal_position_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_temporal_position_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.temporal_position_staged_lock_token is
  'POST-EV2-4A internal operation fact: the lock_token of the save that most recently staged a successful RUN-scoped temporal/timespace position mutation. Matched against the active lock_token so the same-save RUN-lane-temporal/Run-ownership exclusion keys on the staging operation, not on final value equality. Never set by a MAINRUN placement and never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 6. The validated atomic lane-scoped temporal/timespace mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_temporal_position(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Absolute request shape:
--      {
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "target": {
--          "chronology": { "year": ..., "month": ..., ... },
--          "timespace": { "status": "unknown" }
--                      | { "status": "known", "ref": "<lower-slug>" }
--        }
--      }
--
--    Relative request shape:
--      {
--        "controller": { ... },
--        "relative_year_displacement": <signed whole-year integer>,
--        "relative_from": {
--          "chronology": { ... },
--          "timespace": { ... }
--        },
--        "timespace": { ... }   -- optional target override
--      }
--
--    `controller` and exactly one of `target` / `relative_year_displacement` are
--    required. Absolute targets are replay-safe by construction. A relative
--    request MUST pin the exact source position in `relative_from`; the engine
--    derives one stable absolute target from that source, treats current==target
--    as an idempotent replay (including after uncertain publication), and fails
--    closed when current matches neither source nor target. Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * a RUN-scoped lane must be a valid non-parked identity in authoritative
--        PUBLISHED Run truth, and a same-save staged `runs` change fails closed;
--      * a relative displacement requires a sufficiently-known current lane
--        position (a known year) and fails closed otherwise; unsupported
--        day/month arithmetic fails closed;
--      * the complete candidate `temporal_positions` namespace is validated (one
--        record per lane, every record EV2-4A-valid) before anything is staged;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
--
--    This route does NOT change Campaign Day, RT02 elapsed time, Long Rest
--    counters, entity state, applied statuses, knowledge or Run ownership, and
--    never mints an alternate reality.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_temporal_position(
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
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_lane text;
  v_run_lane boolean := false;
  v_has_target boolean;
  v_has_relative boolean;
  v_target jsonb;
  v_chronology jsonb;
  v_timespace jsonb;
  v_timespace_override jsonb;
  v_displacement bigint;
  v_runs jsonb;
  v_entry jsonb;
  v_found integer := 0;
  v_collection jsonb;
  v_current jsonb;
  v_relative_from jsonb;
  v_source_record jsonb;
  v_new_collection jsonb;
  v_record jsonb;
  v_matches integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'temporal position mutation request must be a JSON object';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch.
  -- Require an explicit JSON string first so null, missing, non-string and
  -- unknown values all fail closed rather than falling through to MAINRUN.
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
    v_lane := 'run:' || v_run_id;
    v_run_lane := true;
  else
    if (v_controller - 'kind') <> '{}'::jsonb then
      raise exception 'mainrun controller accepts exactly kind';
    end if;
    v_lane := 'mainrun';
    v_run_lane := false;
  end if;

  -- RUN-scoped lane authority: proven against authoritative PUBLISHED Run truth.
  -- A missing/malformed/duplicate/non-authoritative batch fails closed inside the
  -- shared reader; a parked played Run is not an active lane.
  if v_run_lane then
    -- Same-save compatibility (POST-EV2-1 Patch 1B, extended by POST-EV2-4A):
    -- RUN lane authority is proven against PUBLISHED Run truth. If this save has
    -- already staged a different `runs` batch, published truth no longer
    -- describes the Run ownership this save will publish, so a former controller
    -- could stage a stale RUN-scoped placement. Fail closed; Run-ownership
    -- changes and RUN-scoped placement belong in separate saves.
    perform public._rhc_require_same_save_compatibility(
      'mutate_temporal_position', r.staging_generation, r.published_generation);

    v_runs := public._rhc_published_runs_truth();
    for v_entry in select e from jsonb_array_elements(v_runs) e loop
      if (v_entry ->> 'run_id') = v_run_id then
        v_found := v_found + 1;
        if (v_entry ->> 'execution_mode') = 'played'
           and (v_entry ->> 'control_state') = 'parked' then
          raise exception
            'published Run % is parked and is not an active temporal lane; RUN-scoped temporal placement fails closed',
            v_run_id;
        end if;
      end if;
    end loop;
    if v_found = 0 then
      raise exception
        'no published Run % exists; a RUN-scoped temporal position requires an authoritative published lane',
        v_run_id;
    end if;
  end if;

  -- Load the existing candidate namespace once: this save's staged value, else
  -- published reality, else the truthful empty envelope. Validate it before
  -- anything is staged so malformed or duplicate unrelated truth fails closed
  -- and is never canonicalized by overwrite.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'temporal_positions';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'temporal_positions';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'temporal_positions namespace is unreadable; mutation fails closed';
  end if;
  perform public._rhc_validate_temporal_positions_collection(v_collection);

  v_has_target := p_request ? 'target';
  v_has_relative := p_request ? 'relative_year_displacement';
  if v_has_target and v_has_relative then
    raise exception
      'temporal position mutation accepts either target or relative_year_displacement, not both';
  end if;
  if not v_has_target and not v_has_relative then
    raise exception
      'temporal position mutation requires target or relative_year_displacement';
  end if;

  if v_has_target then
    if (p_request - 'controller' - 'target') <> '{}'::jsonb then
      raise exception
        'temporal position mutation request contains fields outside the POST-EV2-4A runtime contract';
    end if;
    v_target := p_request -> 'target';
    if v_target is null or jsonb_typeof(v_target) is distinct from 'object' then
      raise exception 'temporal position target must be a JSON object';
    end if;
    if (v_target - 'chronology' - 'timespace') <> '{}'::jsonb then
      raise exception
        'temporal position target contains fields outside the POST-EV2-4A contract (chronology, timespace)';
    end if;
    if not (v_target ?& array['chronology', 'timespace']) then
      raise exception 'temporal position target requires chronology and timespace';
    end if;
    v_chronology := public._rhc_normalize_temporal_chronology(v_target -> 'chronology');
    v_timespace := public._rhc_normalize_temporal_timespace(v_target -> 'timespace');
    v_record := jsonb_build_object(
      'lane', v_lane,
      'chronology', v_chronology,
      'timespace', v_timespace
    );
  else
    -- Supported deterministic relative displacement: whole years only. The
    -- request pins the exact source position in relative_from so the derived
    -- absolute target is stable across same-save retries and uncertain
    -- publication retries. We NEVER add the displacement to "whatever is
    -- current now" on each invocation.
    if (p_request - 'controller' - 'relative_year_displacement' - 'relative_from' - 'timespace')
       <> '{}'::jsonb then
      raise exception
        'relative temporal position request contains fields outside the POST-EV2-4A contract (controller, relative_year_displacement, relative_from, timespace)';
    end if;
    if jsonb_typeof(p_request -> 'relative_year_displacement') is distinct from 'number'
       or (p_request ->> 'relative_year_displacement') !~ '^-?[0-9]+$' then
      raise exception
        'relative_year_displacement must be a signed whole-year integer';
    end if;
    v_displacement := (p_request ->> 'relative_year_displacement')::bigint;

    if not (p_request ? 'relative_from')
       or jsonb_typeof(p_request -> 'relative_from') is distinct from 'object' then
      raise exception
        'relative temporal position request requires relative_from as an exact source position object';
    end if;
    v_relative_from := p_request -> 'relative_from';
    if (v_relative_from - 'chronology' - 'timespace') <> '{}'::jsonb
       or not (v_relative_from ?& array['chronology', 'timespace']) then
      raise exception
        'relative_from requires exactly chronology and timespace';
    end if;

    v_chronology :=
      public._rhc_normalize_temporal_chronology(v_relative_from -> 'chronology');
    v_timespace :=
      public._rhc_normalize_temporal_timespace(v_relative_from -> 'timespace');
    v_source_record := jsonb_build_object(
      'lane', v_lane,
      'chronology', v_chronology,
      'timespace', v_timespace
    );

    if not (v_chronology ? 'year') then
      raise exception
        'relative_from for lane % has an Unknown world-calendar year; a relative year displacement fails closed rather than inventing a destination',
        v_lane;
    end if;

    if p_request ? 'timespace' then
      v_timespace_override :=
        public._rhc_normalize_temporal_timespace(p_request -> 'timespace');
    end if;

    -- Derive the target ONLY from the pinned source, never from the latest
    -- staged/published position. This turns the relative command into a stable
    -- absolute target before comparing it with current state.
    v_chronology := v_chronology
      || jsonb_build_object(
           'year',
           (v_chronology ->> 'year')::bigint + v_displacement);
    v_chronology := public._rhc_normalize_temporal_chronology(v_chronology);
    if p_request ? 'timespace' then
      v_timespace := v_timespace_override;
    else
      v_timespace :=
        public._rhc_normalize_temporal_timespace(v_source_record -> 'timespace');
    end if;
    v_record := jsonb_build_object(
      'lane', v_lane,
      'chronology', v_chronology,
      'timespace', v_timespace
    );

    select e into v_current
      from jsonb_array_elements(v_collection) e
     where jsonb_typeof(e) = 'object' and (e ->> 'lane') = v_lane;
    if v_current is null then
      raise exception
        'no current temporal position exists for lane %; relative displacement requires a sufficiently-known current position',
        v_lane;
    end if;

    -- First application requires current==source. A retry after the first call
    -- (same save) or after uncertain publication is current==target and is a
    -- no-drift idempotent replay. Anything else is stale/ambiguous and fails
    -- closed instead of applying the delta again.
    if v_current <> v_source_record and v_current <> v_record then
      raise exception
        'relative_from does not match the current temporal position for lane % and the current position is not the already-derived target; request is stale or ambiguous',
        v_lane;
    end if;
  end if;

  -- Replace the lane's single record, or append it when the lane is new.
  select
    coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'lane') = v_lane
           then v_record else e end
    ), '[]'::jsonb),
    count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'lane') = v_lane
    )
    into v_new_collection, v_matches
    from jsonb_array_elements(v_collection) e;

  if v_matches = 0 then
    v_new_collection := v_new_collection || jsonb_build_array(v_record);
  elsif v_matches > 1 then
    raise exception
      'temporal_positions namespace already holds duplicate records for lane %; failing closed',
      v_lane;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_temporal_positions_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'temporal_positions', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact ONLY for a RUN-scoped placement: a MAINRUN
  -- placement does not rest on published Run truth and must not block a
  -- same-save `runs` change. This closes every Run-ownership-writing doorway for
  -- the rest of the save, even for a value-equal replay.
  if v_run_lane then
    update public.campaign_runtime
       set temporal_position_staged_lock_token = r.lock_token
     where id = 1;
  end if;

  return jsonb_build_object(
    'temporal_position_mutation_version', 1,
    'lane', v_lane,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'temporal_position', v_record
  );
end;
$$;

revoke all on function public.mutate_temporal_position(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_temporal_position(text, jsonb) to service_role;

comment on function public.mutate_temporal_position(text, jsonb) is
  'POST-EV2-4A: the only validated atomic lane-scoped temporal/timespace placement route, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion (controller.kind must be a JSON string exactly mainrun or run; null/missing/non-string/unknown fails closed before any authority branch), proves a RUN-scoped lane against authoritative published Run truth (fail-closed on a malformed/duplicated published runs batch, a parked played Run, and a same-save staged runs change), and stages exactly one absolute world-calendar/timespace placement per play lane into the engine-owned temporal_positions namespace. Supports an absolute target or a supported deterministic relative whole-year displacement whose request pins the exact source position in relative_from; the route derives one stable absolute target, treats current==target as an idempotent retry (including after uncertain publication), and fails closed when current matches neither source nor target. Finer known components and timespace are preserved; an Unknown source year or unsupported day/month arithmetic fails closed. It records the RUN-scoped temporal-staging operation fact that closes every Run-ownership-writing doorway for the rest of the save. Never mutates Campaign Day, RT02 elapsed time, Long Rest counters, entity state, applied statuses, knowledge or Run ownership, and never mints an alternate reality. Absolute target, replay-safe, all-or-nothing through the existing gateway.';

-- ---------------------------------------------------------------------------
-- 7. POST-EV2-1 Patch 1A: extend the server-owned domain policy registry with
--    the new dedicated `temporal_positions` domain. Every existing branch and
--    exact fail-closed message is preserved verbatim; only the new domain is
--    added. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--    routes consult this registry, so they fail closed for `temporal_positions`
--    with no further change.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_save_domain_policy(
  p_key text
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  v_admission text;
  v_routes jsonb;
  v_stage_error text;
  v_delete_error text;
begin
  v_routes := '[]'::jsonb;
  case p_key
    when 'daily_recap' then
      v_admission := 'generic';
    when 'day_resolution' then
      v_admission := 'generic';
    when 'live_status' then
      v_admission := 'generic';
    when 'dm_meta' then
      v_admission := 'generic';
    when 'narrative_hooks' then
      v_admission := 'generic';
    when 'runs' then
      v_admission := 'generic';
    when 'campaign_clock' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('stage_campaign_clock');
      v_stage_error := 'campaign_clock must be staged through stage_campaign_clock';
      v_delete_error := 'campaign_clock is engine-owned and cannot be deleted';
    when 'run_reconciliations' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('reconcile_run_resolution');
      v_stage_error := 'run_reconciliations is engine-owned and can only be staged through reconcile_run_resolution';
      v_delete_error := 'run_reconciliations is engine-owned and cannot be deleted';
    when 'inventory' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_owner_inventory');
      v_stage_error := 'inventory is engine-owned and can only be staged through mutate_owner_inventory';
      v_delete_error := 'inventory is engine-owned and cannot be deleted through the generic route';
    when 'item_custody' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_item_custody', 'admit_item_identity');
      v_stage_error := 'item_custody is engine-owned and can only be staged through mutate_item_custody or admit_item_identity';
      v_delete_error := 'item_custody is engine-owned and cannot be deleted through the generic route';
    when 'item_admissions' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('admit_item_identity');
      v_stage_error := 'item_admissions is engine-owned and can only be staged through admit_item_identity';
      v_delete_error := 'item_admissions is engine-owned and cannot be deleted through the generic route';
    when 'entity_state' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_entity_state');
      v_stage_error := 'entity_state is engine-owned and can only be staged through mutate_entity_state';
      v_delete_error := 'entity_state is engine-owned and cannot be deleted through the generic route';
    when 'applied_statuses' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_applied_status');
      v_stage_error := 'applied_statuses is engine-owned and can only be staged through mutate_applied_status';
      v_delete_error := 'applied_statuses is engine-owned and cannot be deleted through the generic route';
    when 'entity_knowledge' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_entity_knowledge');
      v_stage_error := 'entity_knowledge is engine-owned and can only be staged through mutate_entity_knowledge';
      v_delete_error := 'entity_knowledge is engine-owned and cannot be deleted through the generic route';
    when 'temporal_positions' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_temporal_position');
      v_stage_error := 'temporal_positions is engine-owned and can only be staged through mutate_temporal_position';
      v_delete_error := 'temporal_positions is engine-owned and cannot be deleted through the generic route';
    else
      v_admission := 'forbidden';
      v_stage_error := format(
        'campaign state key %s is not allowed for campaign_save; the server-owned allowlist is daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs; unknown or undeclared runtime keys fail closed (HWB-02 save runtime authority)',
        p_key);
      v_delete_error := v_stage_error;
  end case;

  return jsonb_build_object(
    'key', p_key,
    'admission', v_admission,
    'dedicated_routes', v_routes,
    'stage_error', v_stage_error,
    'delete_error', v_delete_error
  );
end;
$$;

revoke all on function public._rhc_save_domain_policy(text)
  from public, anon, authenticated, service_role;

comment on function public._rhc_save_domain_policy(text) is
  'POST-EV2-1 Patch 1A (extended by POST-EV2-3 and POST-EV2-4A): the single server-owned, machine-readable runtime state key policy registry. Consumes only the key and returns admission (generic | dedicated | forbidden), the exhaustive array `dedicated_routes` of every legal writer for engine-owned keys, and the exact fail-closed messages. `generic` is the HWB-02 ordinary-save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs) and exposes `dedicated_routes=[]`. `dedicated` exposes every legal writer, never a single route that could imply a complete set: campaign_clock=[stage_campaign_clock], run_reconciliations=[reconcile_run_resolution], inventory=[mutate_owner_inventory], item_custody=[mutate_item_custody, admit_item_identity], item_admissions=[admit_item_identity], entity_state=[mutate_entity_state], applied_statuses=[mutate_applied_status], entity_knowledge=[mutate_entity_knowledge], temporal_positions=[mutate_temporal_position]. Unknown/undeclared keys are `forbidden` and expose `dedicated_routes=[]`. No caller-supplied policy, no table, no mutable store: the decision cannot become caller-controlled authority. Internal-only.';

-- ---------------------------------------------------------------------------
-- 8. POST-EV2-1 Patch 1B: extend the same-save compatibility policy with the
--    new `temporal_positions` edges. The `mutate_temporal_position` operation is
--    blocked by a same-save `runs` change; the Run-ownership-writing operations
--    (`stage_runs`, `delete_runs`, `reconcile_runs`) gain a trailing
--    `temporal_positions` edge. Every existing edge and exact message is
--    preserved verbatim.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_same_save_compatibility_policy(
  p_operation text
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_domain text;
  v_edges jsonb := '[]'::jsonb;
begin
  case p_operation
    when 'stage_runs' then
      v_domain := 'runs';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'run_reconciliations',
          'detector', 'reconciliation_new_in_save',
          'error', 'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; a later generic runs mutation could reintroduce duplicate mutable ownership or erase the reconciled candidate; abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'inventory',
          'detector', 'inventory_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an inventory mutation; inventory authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'item_custody',
          'detector', 'custody_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an item custody or admission operation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_state',
          'detector', 'entity_state_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a mutable entity-state mutation; entity-state authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'applied_statuses',
          'detector', 'applied_status_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a RUN-scoped temporal/timespace placement; RUN lane authority would become stale against the changed Run ownership, so abort this save and start a new one')
      );
    when 'delete_runs' then
      v_domain := 'runs';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'run_reconciliations',
          'detector', 'reconciliation_new_in_save',
          'error', 'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; deleting it would erase the reconciled candidate while the consumption ledger claims it was applied; abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'inventory',
          'detector', 'inventory_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an inventory mutation; inventory authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'item_custody',
          'detector', 'custody_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an item custody or admission operation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_state',
          'detector', 'entity_state_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a mutable entity-state mutation; entity-state authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'applied_statuses',
          'detector', 'applied_status_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a RUN-scoped temporal/timespace placement; RUN lane authority would become stale against the changed Run ownership, so abort this save and start a new one')
      );
    when 'reconcile_runs' then
      v_domain := 'runs';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'inventory',
          'detector', 'inventory_staged_in_save',
          'error', 'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'item_custody',
          'detector', 'custody_staged_in_save',
          'error', 'this save has already staged an item custody mutation; a Run reconciliation would change Run ownership after custody authority was proven, so reconciliation fails closed (change Run ownership and item custody in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'entity_state',
          'detector', 'entity_state_staged_in_save',
          'error', 'this save has already staged a mutable entity-state mutation; a Run reconciliation would change Run ownership after entity-state authority was proven, so reconciliation fails closed (change Run ownership and mutable entity state in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'applied_statuses',
          'detector', 'applied_status_staged_in_save',
          'error', 'this save has already staged a timed applied-status mutation; a Run reconciliation would change Run ownership after applied-status controller authority was proven, so reconciliation fails closed (change Run ownership and applied status in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'this save has already staged an owner-local knowledge mutation; a Run reconciliation would change Run ownership after knowledge controller authority was proven, so reconciliation fails closed (change Run ownership and knowledge in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'this save has already staged a RUN-scoped temporal/timespace placement; a Run reconciliation would change Run ownership after RUN lane authority was proven, so reconciliation fails closed (change Run ownership and temporal placement in separate saves)')
      );
    when 'mutate_inventory' then
      v_domain := 'inventory';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; inventory controller cannot be proven against published Run truth, so inventory mutation fails closed (change Run ownership and inventory in separate saves)')
      );
    when 'mutate_item_custody' then
      v_domain := 'item_custody';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; item custody controller cannot be proven against published Run truth, so custody mutation fails closed (change Run ownership and item custody in separate saves)')
      );
    when 'admit_item_identity' then
      v_domain := 'item_admissions';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; admission controller cannot be proven against published Run truth, so item identity admission fails closed (change Run ownership and admit items in separate saves)')
      );
    when 'mutate_entity_state' then
      v_domain := 'entity_state';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; entity-state controller cannot be proven against published Run truth, so mutable entity-state mutation fails closed (change Run ownership and mutable entity state in separate saves)')
      );
    when 'mutate_applied_status' then
      v_domain := 'applied_statuses';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; applied-status controller cannot be proven against published Run truth, so timed applied-status mutation fails closed (change Run ownership and applied status in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'campaign_clock',
          'detector', 'campaign_clock_changed_in_save',
          'error', 'this save has staged a different campaign_clock; applied-status elapsed anchors cannot be proven against the Clock this save would publish, so timed applied-status mutation fails closed (advance the Clock and mutate applied status in separate saves)')
      );
    when 'mutate_entity_knowledge' then
      v_domain := 'entity_knowledge';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; knowledge controller cannot be proven against published Run truth, so owner-local knowledge mutation fails closed (change Run ownership and knowledge in separate saves)')
      );
    when 'mutate_temporal_position' then
      v_domain := 'temporal_positions';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; RUN lane authority cannot be proven against published Run truth, so RUN-scoped temporal placement fails closed (change Run ownership and RUN-scoped temporal placement in separate saves)')
      );
    when 'stage_campaign_clock' then
      v_domain := 'campaign_clock';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'applied_statuses',
          'detector', 'applied_status_staged_in_save',
          'error', 'this save has already staged a timed applied-status mutation; advancing the Campaign Clock in the same save would leave applied-status anchors proven against the wrong elapsed truth, so the Clock write fails closed (advance the Clock and mutate applied status in separate saves)')
      );
    else
      return jsonb_build_object(
        'operation', p_operation,
        'domain', null,
        'known', false,
        'edges', '[]'::jsonb
      );
  end case;

  return jsonb_build_object(
    'operation', p_operation,
    'domain', v_domain,
    'known', true,
    'edges', v_edges
  );
end;
$$;

revoke all on function public._rhc_same_save_compatibility_policy(text)
  from public, anon, authenticated, service_role;

comment on function public._rhc_same_save_compatibility_policy(text) is
  'POST-EV2-1 Patch 1B (extended by POST-EV2-3 and POST-EV2-4A): the single server-owned, machine-readable same-save compatibility policy. For each legal mutation operation it declares, in deterministic order, every audited cross-domain incompatibility as {blocked_by, detector, error}, where `error` is the exact fail-closed message that operation must raise. POST-EV2-4A adds the `mutate_temporal_position` operation (blocked by a same-save runs change) and a trailing `temporal_positions` edge on stage_runs/delete_runs/reconcile_runs. Consumes only the operation name; reads no table and selects no mutable store, so the policy can never be caller-supplied or caller-controlled. Unknown operations report known=false. Internal-only.';

-- ---------------------------------------------------------------------------
-- 9. POST-EV2-1 Patch 1B: extend the compatibility decision with the
--    `temporal_position_staged_in_save` detector. Every existing detector and
--    the fail-closed unknown-detector behavior are preserved.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_same_save_compatibility(
  p_operation text,
  p_staging_generation bigint,
  p_published_generation bigint
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_policy jsonb;
  v_edge jsonb;
  v_detector text;
  v_blocked boolean;
begin
  v_policy := public._rhc_same_save_compatibility_policy(p_operation);
  if not (v_policy ->> 'known')::boolean then
    return jsonb_build_object(
      'operation', p_operation,
      'domain', null,
      'known', false,
      'compatible', false,
      'blocked_by', 'unknown_operation',
      'error', format('unknown same-save compatibility operation %s; failing closed', p_operation)
    );
  end if;

  for v_edge in select e from jsonb_array_elements(v_policy -> 'edges') e loop
    v_detector := v_edge ->> 'detector';
    v_blocked := case v_detector
      when 'reconciliation_new_in_save' then
        public._rhc_reconciliation_new_in_save(p_staging_generation, p_published_generation)
      when 'inventory_staged_in_save' then
        public._rhc_inventory_staged_in_save()
      when 'custody_staged_in_save' then
        public._rhc_custody_staged_in_save()
      when 'entity_state_staged_in_save' then
        public._rhc_entity_state_staged_in_save()
      when 'applied_status_staged_in_save' then
        public._rhc_applied_status_staged_in_save()
      when 'knowledge_staged_in_save' then
        public._rhc_entity_knowledge_staged_in_save()
      when 'temporal_position_staged_in_save' then
        public._rhc_temporal_position_staged_in_save()
      when 'runs_changed_in_save' then
        public._rhc_state_key_changed_in_save('runs', p_staging_generation, p_published_generation)
      when 'campaign_clock_changed_in_save' then
        public._rhc_state_key_changed_in_save('campaign_clock', p_staging_generation, p_published_generation)
      else
        null
    end;

    if v_blocked is null then
      raise exception 'unknown same-save compatibility detector %; failing closed', v_detector;
    end if;

    if v_blocked then
      return jsonb_build_object(
        'operation', p_operation,
        'domain', v_policy ->> 'domain',
        'known', true,
        'compatible', false,
        'blocked_by', v_edge ->> 'blocked_by',
        'error', v_edge ->> 'error'
      );
    end if;
  end loop;

  return jsonb_build_object(
    'operation', p_operation,
    'domain', v_policy ->> 'domain',
    'known', true,
    'compatible', true,
    'blocked_by', null,
    'error', null
  );
end;
$$;

revoke all on function public._rhc_same_save_compatibility(text, bigint, bigint)
  from public, anon, authenticated, service_role;

comment on function public._rhc_same_save_compatibility(text, bigint, bigint) is
  'POST-EV2-1 Patch 1B (extended by POST-EV2-3 and POST-EV2-4A): the server-owned same-save compatibility decision. Evaluates the declared policy for one operation against the active save''s staging/published generations and returns {operation, domain, known, compatible, blocked_by, error}. It answers only whether already-legal operations may coexist in this save; it never judges a mutation''s own semantic validity. Unknown operations/detectors fail closed. Internal-only; no caller-supplied policy.';

comment on function public._rhc_normalize_temporal_chronology(jsonb) is
  'POST-EV2-4A internal world-calendar chronology validation + canonicalization. Accepts any subset of the integer components year (signed) and month/day/hour/minute (non-negative); a missing component stays truthful Unknown and no finer precision is invented. No calendar-specific range/month-length rule is enforced (Harptos/Dalereckoning arithmetic is deferred). Internal-only.';
comment on function public._rhc_normalize_temporal_timespace(jsonb) is
  'POST-EV2-4A internal timespace/plane reference validation + canonicalization. Accepts exactly status (known/unknown) and, only when known, a non-blank lower-slug ref; unknown forbids ref. No setting-specific plane catalog is encoded. Internal-only.';
comment on function public._rhc_normalize_temporal_position_record(jsonb) is
  'POST-EV2-4A internal full temporal-position record validation + canonicalization. Binds a play-lane identity (mainrun or run:<R##>) to a canonical chronology + timespace placement; extra fields and lanes outside that space fail closed. Internal-only: positions are reachable only through the validated mutate_temporal_position route.';
comment on function public._rhc_validate_temporal_positions_collection(jsonb) is
  'POST-EV2-4A internal whole-collection validation. Proves the complete candidate temporal_positions namespace is a JSON array of canonical records with exactly one authoritative position per play lane, rejecting duplicate lane records. Internal-only.';
comment on function public._rhc_temporal_position_staged_in_save() is
  'POST-EV2-4A internal same-save RUN-scoped temporal-staging operation fact. True only when the active save''s lock_token matches the lock_token that most recently staged a successful RUN-scoped temporal/timespace placement, so closure keys on the staging operation rather than on final value equality (a value-equal replay still trips it) and never leaks into a later save. A MAINRUN placement never sets it. Internal-only.';
