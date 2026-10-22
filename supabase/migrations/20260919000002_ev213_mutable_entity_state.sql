-- EV2-13 — Save-Gateway-integrated mutable entity state
-- Rolling High Club validated mutation route for bounded entity-owned mutable
-- state, on the existing RT01 SAVE / publish / mirror / confirm spine.
--
-- This migration is NOT a second save engine, NOT a second controller/ownership
-- ledger and NOT a new persistence/mirror path. It adds ONE validated, atomic
-- route for the bounded current state of a mutable entity, reuses the existing
-- RT01 begin -> validated stage -> publish -> mirror/confirmation law, reuses the
-- shared EV2-10 published-Run controller resolver, and composes with every
-- existing dedicated closure (RT02 `campaign_clock`, RT04 `run_reconciliations`,
-- HWB-02 ordinary-save allowlist, EV2-10 `inventory`, EV2-11 `item_custody`,
-- EV2-12.1 `item_admissions`).
--
-- Architecture sentence:
--   EV2-13 does not create a new save system. It creates the bounded durable
--   entity-state mutation surface on top of the existing RT01 SAVE / publish /
--   mirror / confirm spine, with controller authority resolved only from
--   authoritative published Run truth.
--
-- WHAT this migration changes:
--   1. `public.mutate_entity_state(p_lock_token, p_request)` — the ONLY way to
--      stage the engine-owned `entity_state` runtime namespace. It runs INSIDE
--      the normal campaign save lifecycle, proves the caller's asserted
--      controller (MAINRUN or exactly one RUN #) against authoritative PUBLISHED
--      Run truth for the target mutable entity, validates the absolute bounded
--      entity-state target, and stages exactly one current-state record per
--      mutable entity.
--   2. The engine-owned `entity_state` runtime namespace is a JSON array holding
--      exactly one authoritative record per mutable entity (`character:` /
--      `creature:`). It is the durable current-state surface for a mutable
--      entity, not a history/event subsystem and not a second ownership ledger.
--   3. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--      routes reject the `entity_state` key (the same dedicated-key closure
--      pattern as `campaign_clock`, `run_reconciliations`, `inventory`,
--      `item_custody` and `item_admissions`), so a caller/model cannot bypass the
--      validated route with a raw generic runtime write. The HWB-02 ordinary-save
--      allowlist is preserved unchanged.
--   4. Run-ownership changes and mutable entity-state mutations are mutually
--      exclusive within one save. Detection keys on the explicit entity-state
--      staging operation fact, not on final value equality, so a re-staged
--      absolute target that already equals published reality (a replay) or a
--      mutation later reverted still closes every Run-writing doorway for the
--      rest of the save: generic `runs` stage/delete and the dedicated RT04
--      `reconcile_run_resolution` route.
--
-- ENTITY-STATE MODEL (mirrors schemas/state.schema.json, mutable actors only):
--   * a record is exactly `entity_id` + `status` + (entries only when known);
--   * `entity_id` is a `character:` / `creature:` mutable-actor identity — the
--     same identity space EV2-08 `mutable_owner_entity_ids` uses;
--   * `status` is `known` / `unknown` / `not_applicable`;
--   * when `known`, `entries` is a required, non-empty array of
--     `{ attribute, status, value }` where each entry's own `status` is
--     independently `known` / `unknown` / `not_applicable` and `value` is a plain
--     scalar (string/number/boolean) present only when that entry is `known`;
--   * when `unknown` / `not_applicable`, `entries` must be absent; a present
--     `entries` (even empty) or a stored status field is rejected rather than
--     canonicalized;
--   * entries are unique under JSON value equality, so a numerically equal
--     duplicate (`value: 1` and `value: 1.0`) cannot be stored twice.
--   The state box deliberately does not model HP, resources, conditions,
--   relationships or applied status instances; time-dependent applied status
--   instances and timing/threshold processing are EV2-13.1's later concern.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * the asserted controller is the ONLY current controller of the target
--     mutable entity, and it must match authoritative PUBLISHED Run truth;
--   * under a MAINRUN assertion the entity must currently be unclaimed by any
--     published Run; under a RUN # assertion the entity must currently be
--     controlled by exactly that RUN #;
--   * a parked played Run that still claims the entity fails closed (it is not a
--     current controller, and its stale claim means MAINRUN is not provably the
--     controller either); two Runs claiming one entity fail closed; a malformed
--     or duplicated published Run batch fails closed;
--   * there is no stored controller authority: the former controller is
--     historical/reference-only, and a former/stale controller write fails
--     closed because published Run truth no longer grants it authority.
--
-- REPLAY / CRASH LAW:
--   The target is ABSOLUTE, so replaying one logical update is idempotent. A
--   crash/abort before publication leaves no durable entity state; retry
--   converges on exactly one record. A retry after publication replaces the same
--   entity's single record, never creating a second authoritative copy.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1
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
      'EV2-13 migration refused: resolve the active campaign save before installing the mutable entity-state route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Bounded entity-state body validation + canonicalization (internal). The
--    body is the EV2-03/state.schema.json box minus `entity_id`: `status`
--    plus `entries` only when known. Unknown stays Unknown: no entry is invented,
--    and a value is never synthesized.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_entity_state_body(
  p_state jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_entries jsonb;
  v_entry jsonb;
  v_norm_entry jsonb;
  v_estatus text;
  v_value jsonb;
  v_out jsonb;
  v_count integer;
  v_distinct integer;
begin
  if p_state is null or jsonb_typeof(p_state) is distinct from 'object' then
    raise exception 'entity state must be a JSON object';
  end if;
  if (p_state - 'status' - 'entries') <> '{}'::jsonb then
    raise exception
      'entity state contains fields outside the EV2-13 contract (status, entries)';
  end if;
  if not (p_state ? 'status') then
    raise exception 'entity state requires a status';
  end if;
  if jsonb_typeof(p_state -> 'status') is distinct from 'string' then
    raise exception
      'entity state status must be a JSON string of known, unknown or not_applicable';
  end if;
  v_status := p_state ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception
      'entity state status must be known, unknown or not_applicable';
  end if;

  if v_status = 'known' then
    if not (p_state ? 'entries') then
      raise exception 'known entity state requires an entries array';
    end if;
    v_entries := p_state -> 'entries';
    if jsonb_typeof(v_entries) is distinct from 'array' then
      raise exception 'known entity state entries must be a JSON array';
    end if;
    if jsonb_array_length(v_entries) = 0 then
      raise exception 'known entity state requires at least one entry';
    end if;

    -- JSON value equality (not text serialization), so a numerically equal
    -- duplicate such as value 1 and 1.0 is the same entry, not two facts.
    select count(*), count(distinct e)
      into v_count, v_distinct
      from jsonb_array_elements(v_entries) e;
    if v_distinct < v_count then
      raise exception
        'entity state entries must be unique; a duplicate attribute entry is a double-count, not two independent facts';
    end if;

    v_out := '[]'::jsonb;
    for v_entry in select e from jsonb_array_elements(v_entries) e loop
      if jsonb_typeof(v_entry) is distinct from 'object' then
        raise exception 'entity state entry must be a JSON object';
      end if;
      if (v_entry - 'attribute' - 'status' - 'value') <> '{}'::jsonb then
        raise exception
          'entity state entry contains fields outside the EV2-13 contract (attribute, status, value)';
      end if;
      if not (v_entry ?& array['attribute', 'status']) then
        raise exception 'entity state entry requires attribute and status';
      end if;
      if jsonb_typeof(v_entry -> 'attribute') is distinct from 'string'
         or (v_entry ->> 'attribute') !~ '\S' then
        raise exception
          'entity state entry attribute must be a non-blank JSON string';
      end if;
      if jsonb_typeof(v_entry -> 'status') is distinct from 'string' then
        raise exception
          'entity state entry status must be a JSON string of known, unknown or not_applicable';
      end if;
      v_estatus := v_entry ->> 'status';
      if v_estatus not in ('known', 'unknown', 'not_applicable') then
        raise exception
          'entity state entry status must be known, unknown or not_applicable';
      end if;

      if v_estatus = 'known' then
        if not (v_entry ? 'value') then
          raise exception 'known entity state entry requires a value';
        end if;
        v_value := v_entry -> 'value';
        if jsonb_typeof(v_value) not in ('string', 'number', 'boolean') then
          raise exception
            'known entity state entry value must be a plain scalar (string, number or boolean)';
        end if;
        v_norm_entry := jsonb_build_object(
          'attribute', v_entry -> 'attribute',
          'status', v_entry -> 'status',
          'value', v_value
        );
      else
        if v_entry ? 'value' then
          raise exception
            'an unknown or not_applicable entity state entry must not carry a value';
        end if;
        v_norm_entry := jsonb_build_object(
          'attribute', v_entry -> 'attribute',
          'status', v_entry -> 'status'
        );
      end if;
      v_out := v_out || jsonb_build_array(v_norm_entry);
    end loop;

    return jsonb_build_object('status', v_status, 'entries', v_out);
  end if;

  -- unknown / not_applicable: entries are forbidden, not merely empty.
  if p_state ? 'entries' then
    raise exception
      'an unknown or not_applicable entity state must not carry entries';
  end if;
  return jsonb_build_object('status', v_status);
end;
$$;

revoke all on function public._rhc_normalize_entity_state_body(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Full entity-state record validation + canonicalization (internal). Binds
--    the mutable-entity identity to the bounded body. Only `character:` /
--    `creature:` identities are accepted, matching the EV2-08 mutable-owner
--    space; a missing `entity_id` or an identity outside that space fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_entity_state_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entity text;
  v_body jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'entity state record must be a JSON object';
  end if;
  if not (p_record ? 'entity_id') then
    raise exception 'entity state record requires entity_id';
  end if;
  if jsonb_typeof(p_record -> 'entity_id') is distinct from 'string' then
    raise exception
      'entity state entity_id must be a JSON string mutable-entity identity';
  end if;
  v_entity := p_record ->> 'entity_id';
  if not public._rhc_full_id_match(
    v_entity, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'entity state entity_id must be a character: or creature: mutable-entity identity';
  end if;

  v_body := public._rhc_normalize_entity_state_body(p_record - 'entity_id');
  return jsonb_build_object('entity_id', v_entity) || v_body;
end;
$$;

revoke all on function public._rhc_normalize_entity_state_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Whole-collection validation (internal). The complete candidate
--    `entity_state` namespace is proven before it can be staged: a JSON array of
--    canonical records with exactly one authoritative record per mutable entity.
--    A duplicate record for one entity is an ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_entity_state_collection(
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
  v_entity text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'entity_state namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_entity_state_record(v_entry);
    v_entity := v_norm ->> 'entity_id';
    if array_position(v_seen, v_entity) is not null then
      raise exception
        'entity_state namespace holds duplicate records for %; exactly one authoritative record per mutable entity is required',
        v_entity;
    end if;
    v_seen := array_append(v_seen, v_entity);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_entity_state_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Explicit same-save entity-state staging marker (internal). Closure must key
--    on the operation fact, not on final JSON equality: an absolute target can
--    be re-staged to a value that already equals published reality (a replay),
--    or mutated away and back, and in both cases the final value would look
--    unchanged even though a successful staging operation occurred. The save
--    locator therefore records the lock_token that staged entity state. The
--    database mints a fresh lock_token at every BEGIN and clears stale candidate
--    rows, so the marker can only match the CURRENT save's token and never leaks
--    into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists entity_state_staged_lock_token text;

create or replace function public._rhc_entity_state_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.entity_state_staged_lock_token is not null
            and cr.entity_state_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_entity_state_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.entity_state_staged_lock_token is
  'EV2-13 internal operation fact: the lock_token of the save that most recently staged a successful mutable entity-state mutation. Matched against the active lock_token so the same-save entity-state/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 5. The validated atomic mutable entity-state mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_entity_state(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "entity_id": "<character|creature>:<slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "state": {
--          "status": "known" | "unknown" | "not_applicable",
--          "entries": [ { "attribute": "...", "status": "...", "value": ... } ]
--        }
--      }
--
--    `entity_id`, `controller` and `state` are required. The target is ABSOLUTE,
--    not a delta, so replaying one logical update is idempotent and cannot drift.
--    Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth for
--        the target mutable entity (malformed/duplicated batch, parked claiming
--        Run and two-Run claim all fail closed rather than falling through to
--        MAINRUN);
--      * a same-save staged `runs` change (ownership handoff) fails closed,
--        because published Run truth would no longer describe the controller
--        this save would publish -> no former/stale-controller overwrite;
--      * the complete existing candidate `entity_state` namespace is validated
--        (one record per mutable entity, every record EV2-13-valid) before
--        anything is staged, so malformed or duplicate unrelated truth fails
--        closed and is never canonicalized;
--      * the complete resulting namespace is validated before staging;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
--
--    This route does NOT change Run ownership, does not create a second
--    controller/ownership ledger, and does not model HP/resources/conditions or
--    time-dependent applied status instances.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_entity_state(
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
  v_entity text;
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_body jsonb;
  v_record jsonb;
  v_collection jsonb;
  v_new_collection jsonb;
  v_matches integer;
  v_current text;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save controller integrity: entity-state authority is proven against
  -- PUBLISHED Run truth. If this save has already staged a different `runs`
  -- batch, published truth no longer describes the Run ownership this save will
  -- publish, so a former controller could stage a stale entity-state update.
  -- Fail closed; Run-ownership changes and mutable entity-state mutations belong
  -- in separate saves. (The staging generation starts as a copy of published
  -- reality, so an untouched runs batch compares equal and does not trip this
  -- guard.)
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; entity-state controller cannot be proven against published Run truth, so mutable entity-state mutation fails closed (change Run ownership and mutable entity state in separate saves)';
  end if;

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'entity-state mutation request must be a JSON object';
  end if;
  if not p_request ?& array['entity_id', 'controller', 'state'] then
    raise exception
      'entity-state mutation request requires entity_id, controller and state';
  end if;
  if (p_request - 'entity_id' - 'controller' - 'state') <> '{}'::jsonb then
    raise exception
      'entity-state mutation request contains fields outside the EV2-13 contract';
  end if;

  -- entity_id: a mutable actor identity. It is never inferred from prose.
  if jsonb_typeof(p_request -> 'entity_id') is distinct from 'string' then
    raise exception
      'entity-state mutation entity_id must be a JSON string mutable-entity identity';
  end if;
  v_entity := p_request ->> 'entity_id';
  if not public._rhc_full_id_match(
    v_entity, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'entity-state mutation entity_id must be a character: or creature: identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch.
  -- `kind: null` (or an array/object) would make `v_kind NOT IN (...)` evaluate
  -- to SQL NULL under three-valued logic, the guard would not fire, and the
  -- later `v_kind = 'run'` test would also be NULL, silently falling through to
  -- the MAINRUN branch. Require an explicit JSON string first so null, missing,
  -- non-string and unknown values all fail closed. (Identical law to EV2-10/11.)
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

  -- Authoritative controller: published Run truth only, via the shared EV2-10
  -- resolver (a malformed published batch, a parked claiming Run, a two-Run
  -- claim and a duplicated authoritative Run identity all fail closed there
  -- rather than falling through to MAINRUN).
  v_current := public._rhc_inventory_controller_for_owner(v_entity);
  if v_kind = 'run' then
    if v_current is null then
      raise exception
        'no published Run currently controls %; a Run controller cannot assert mutable entity-state authority',
        v_entity;
    end if;
    if v_current is distinct from v_run_id then
      raise exception
        'published Run % currently controls %; asserted Run % does not own it, so this mutable entity-state mutation crosses controllers and fails closed',
        v_current, v_entity, v_run_id;
    end if;
  else
    if v_current is not null then
      raise exception
        'published Run % currently controls %; MAINRUN may not mutate that entity''s state (route the cross-controller handoff through the existing reconciliation boundary)',
        v_current, v_entity;
    end if;
  end if;

  -- Validate + canonicalize the absolute bounded state target.
  if not (p_request ? 'state') then
    raise exception 'entity-state mutation requires a state object';
  end if;
  v_body := public._rhc_normalize_entity_state_body(p_request -> 'state');
  v_record := jsonb_build_object('entity_id', v_entity) || v_body;

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope. The candidate begins as a copy of published
  -- reality via BEGIN, so this only fills the never-yet-created case.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'entity_state';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'entity_state';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'entity_state namespace is unreadable; mutation fails closed';
  end if;

  -- Validate the EXISTING namespace before anything is staged. Malformed or
  -- duplicate unrelated truth fails closed and is never canonicalized by
  -- overwrite.
  perform public._rhc_validate_entity_state_collection(v_collection);

  -- Replace the entity's single record, or append it when the entity is new.
  select
    coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'entity_id') = v_entity
           then v_record else e end
    ), '[]'::jsonb),
    count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'entity_id') = v_entity
    )
    into v_new_collection, v_matches
    from jsonb_array_elements(v_collection) e;

  if v_matches = 0 then
    v_new_collection := v_new_collection || jsonb_build_array(v_record);
  elsif v_matches > 1 then
    raise exception
      'entity_state namespace already holds duplicate records for %; failing closed',
      v_entity;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_entity_state_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'entity_state', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact: a successful entity-state staging happened in
  -- this save, independent of whether the staged value differs from published
  -- reality. This closes every Run-ownership-writing doorway for the rest of the
  -- save, even for a value-equal replay.
  update public.campaign_runtime
     set entity_state_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'entity_state_mutation_version', 1,
    'entity_id', v_entity,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'state', v_record
  );
end;
$$;

revoke all on function public.mutate_entity_state(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_entity_state(text, jsonb) to service_role;

comment on function public.mutate_entity_state(text, jsonb) is
  'EV2-13: the only validated atomic mutable entity-state mutation route, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion (controller.kind must be a JSON string exactly mainrun or run; null/missing/non-string/unknown fails closed before any authority branch), proves the asserted MAINRUN-or-one-RUN controller against authoritative published Run truth for the target character:/creature: mutable entity (fail-closed on a malformed published runs batch, a parked claiming Run, a duplicated authoritative Run identity, and a same-save staged runs change), validates + canonicalizes the absolute bounded state target (status known/unknown/not_applicable; entries only when known, each plain-scalar-valued and unique), then stages the entity''s single current-state record into the engine-owned entity_state namespace and records the entity-state-staging operation fact that closes every Run-ownership-writing doorway for the rest of the save. Absolute target, replay-safe, all-or-nothing through the existing gateway. Owns no controller authority of its own: published Run truth is the only controller source, and no Run ownership is changed here.';

-- ---------------------------------------------------------------------------
-- 6. Close the generic `entity_state` bypass. The entity-state namespace is
--    engine-owned: it can never be staged or deleted through the generic routes.
--    This re-declares the HWB-02/EV2-10/EV2-11/EV2-12.1 generic routes unchanged
--    except for the added entity_state closure and the same-save entity-state/
--    Run-ownership mutual exclusion (once this save has staged a mutable
--    entity-state mutation, the generic `runs` key is refused too), preserving
--    every existing dedicated-key closure and the server-owned ordinary-save
--    allowlist exactly.
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory, item_custody, item_admissions and entity_state keys are rejected here and must use their validated routes (entity_state via mutate_entity_state). Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation, an item custody/admission operation, or a mutable entity-state mutation, the runs key is refused for the rest of the save; historical receipts copied forward from published reality do not trigger the reconciliation closure. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';
comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody/admission/entity-state and Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';
comment on function public._rhc_normalize_entity_state_body(jsonb) is
  'EV2-13 internal bounded entity-state body validation + canonicalization. Accepts exactly status (known/unknown/not_applicable) and, only when known, a non-empty unique entries array of {attribute, status, value} where each entry value is a plain scalar present only when that entry is known; unknown/not_applicable forbid entries. Unknown stays Unknown; no fact is invented. Internal-only.';
comment on function public._rhc_normalize_entity_state_record(jsonb) is
  'EV2-13 internal full entity-state record validation + canonicalization. Binds a character:/creature: mutable-entity identity to a canonical bounded state body; extra fields and identities outside the mutable-actor space fail closed. Internal-only: state payloads are reachable only through the validated mutate_entity_state route.';
comment on function public._rhc_validate_entity_state_collection(jsonb) is
  'EV2-13 internal whole-collection validation. Proves the complete candidate entity_state namespace is a JSON array of canonical records with exactly one authoritative record per character:/creature: mutable entity, rejecting duplicate records. Internal-only.';
comment on function public._rhc_entity_state_staged_in_save() is
  'EV2-13 internal same-save entity-state-staging operation fact. True only when the active save''s lock_token matches the lock_token that most recently staged a successful mutable entity-state mutation, so closure keys on the staging operation rather than on final value equality (a value-equal replay still trips it) and never leaks into a later save. Internal-only.';

-- ---------------------------------------------------------------------------
-- 7. Close the dedicated RT04 reconciliation-after-entity-state doorway. The
--    generic `runs` stage/delete closure above stops generic same-save Run
--    changes once entity state has been staged, but `reconcile_run_resolution`
--    writes the `runs` batch with a direct INSERT and would bypass it. This
--    re-declares the RT04 route unchanged except for the same-save entity-state
--    guard (on top of the EV2-10 inventory and EV2-11 custody guards), so every
--    Run-ownership-writing doorway fails closed in a save that has staged a
--    mutable entity-state mutation. The guard reads the explicit staging
--    operation fact, not final entity-state value equality. RT04 is not
--    redesigned and no second save engine is added.
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

  -- EV2-10 same-save coupling: once this save has staged a successful inventory
  -- mutation, Run ownership must not change in the same generation. Every
  -- Run-ownership-writing doorway, including this dedicated RT04 route, fails
  -- closed here; change Run ownership and inventory in separate saves.
  if public._rhc_inventory_staged_in_save() then
    raise exception
      'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)';
  end if;

  -- EV2-11 same-save coupling: the same law for a staged item custody mutation.
  if public._rhc_custody_staged_in_save() then
    raise exception
      'this save has already staged an item custody mutation; a Run reconciliation would change Run ownership after custody authority was proven, so reconciliation fails closed (change Run ownership and item custody in separate saves)';
  end if;

  -- EV2-13 same-save coupling: the same law for a staged mutable entity-state
  -- mutation. Entity-state authority was proven against the published Run
  -- controller, so a later reconciliation must not change Run ownership in the
  -- same generation.
  if public._rhc_entity_state_staged_in_save() then
    raise exception
      'this save has already staged a mutable entity-state mutation; a Run reconciliation would change Run ownership after entity-state authority was proven, so reconciliation fails closed (change Run ownership and mutable entity state in separate saves)';
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
  -- resolution_id is fresh. Only markers this save added on top of the published
  -- ledger count as same-save history.
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
  -- truth is never consulted.
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

  -- Released owners must currently be owned by the Run.
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

  -- Continuation vs collapse.
  v_mode := v_run ->> 'execution_mode';
  v_state := v_run ->> 'control_state';
  if jsonb_array_length(v_new_owners) = 0 and v_mode = 'played' then
    v_new_state := 'parked';
  else
    v_new_state := v_state;
  end if;

  -- Deterministic objective-result translation into the EV2-08 outcome summary.
  v_band := v_resolution ->> 'outcome_band';
  v_summary := 'Resolution ' || v_rid || ' accepted: ' || v_band
    || ' objective result. Scenario objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,scenario_objective}'), ' '), '.')
    || '. Hook objective: '
    || rtrim(rtrim((v_resolution #>> '{objective_context,hook_objective}'), ' '), '.')
    || '.';

  -- Build the updated runs batch.
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

  -- Candidate Run ownership law, proven before anything is staged.
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

  -- Consumption ledger + bounded run update are staged together, atomically.
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
  'RT04/EV2-10/EV2-11/EV2-13: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet (with their validated summary), and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. EV2-10 adds the same-save guard for a staged inventory mutation; EV2-11 adds the same guard for a staged item custody mutation; EV2-13 adds the same guard for a staged mutable entity-state mutation. All-or-nothing through the existing gateway.';
