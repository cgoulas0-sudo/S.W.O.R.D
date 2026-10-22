-- EV2-11 — Unique-item custody for already-declared persistent `item:` identities
-- Rolling High Club validated custody mutation route on the existing RT01 SAVE
-- spine, plus the authoritative `item_custody` runtime namespace.
--
-- This migration is NOT a second save engine, NOT a second inventory system and
-- NOT an item-identity registry. It adds ONE validated, atomic custody mutation
-- route for identities that an authorized source has ALREADY admitted, and it
-- composes with every existing dedicated closure (RT02 `campaign_clock`, RT04
-- `run_reconciliations`, HWB-02 ordinary-save allowlist, EV2-10 `inventory`) and
-- reuses the existing RT01 begin -> validated stage -> publish -> mirror/
-- confirmation law.
--
-- WHAT this migration changes:
--   1. `public.mutate_item_custody(p_lock_token, p_request)` — the ONLY way to
--      stage the engine-owned `item_custody` runtime namespace. It runs INSIDE
--      the normal campaign save lifecycle, proves the caller's asserted
--      controller (MAINRUN or exactly one RUN #) against authoritative PUBLISHED
--      Run truth for EVERY actor whose custody fact is relinquished or newly
--      assigned, validates the absolute owner/holder target, and updates exactly
--      one already-admitted custody record.
--   2. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--      routes reject the `item_custody` key (same closure pattern as
--      `campaign_clock`, `run_reconciliations` and `inventory`), so a
--      caller/model cannot bypass the validated route with a raw generic runtime
--      write. The HWB-02 ordinary-save allowlist is preserved unchanged.
--   3. Run-ownership changes and custody mutations are mutually exclusive within
--      one save. Detection keys on the explicit custody-staging operation fact,
--      not on final value equality, so a re-staged absolute target that already
--      equals published reality (or a mutation later reverted) still closes every
--      Run-writing doorway for the rest of the save: generic `runs` stage/delete
--      and the dedicated RT04 `reconcile_run_resolution` route.
--
-- CUSTODY MODEL (mirrors schemas/item_custody.schema.json):
--   * a custody record is exactly `item_id` + `owner_entity_id` +
--     `holder_entity_id`; there is no stored status field;
--   * `item_id` is always a valid `item:` identity;
--   * owner and holder are independent, required facts, each JSON null or a
--     valid `character:` / `party:` identity (`character:` covers PCs/NPCs/
--     villains; `party:` supports party-owned/party-held custody);
--   * derived labels only: held = holder non-null; owned = owner non-null and
--     holder null; treasure = both null;
--   * a gameplay mutation is an ABSOLUTE target replacement for ONE existing
--     record, atomic across owner and holder, so a gift/trade may change both at
--     once while theft/loan/pickup/drop changes only the fact that changed.
--
-- NON-MINTING LAW:
--   Gameplay mutation updates an already-admitted custody record only. If no
--   current admitted record exists for the requested `item_id`, the route fails
--   closed and stages nothing. Initial admission/seeding of real item identity +
--   first custody is deferred to EV2-12 / a later authorized identity-intake
--   flow. No rarity, magic, price, wording or narrative importance can mint a
--   new `item:` identity.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * the union of every non-null actor across current owner, current holder,
--     new owner and new holder must resolve compatibly under ONE asserted
--     current controller;
--   * under a MAINRUN assertion every involved actor must currently be
--     unclaimed by any published Run; under a RUN # assertion every involved
--     actor must be currently controlled by exactly that RUN #;
--   * a mutation that would cross incompatible MAINRUN/RUN controllers fails
--     closed and must route through the existing handoff/reconciliation boundary;
--   * parked/malformed/duplicated published Run truth fails closed.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10 forward-only install
--    pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'EV2-11 migration refused: resolve the active campaign save before installing the unique-item custody route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Custody actor validation (internal). Owner/holder are each either JSON null
--    (a real absence fact) or a valid `character:` / `party:` identity. A SQL
--    NULL (key absent) is NOT valid here: missing-vs-null must stay unambiguous.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_custody_actor(
  p_value jsonb,
  p_field text
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if jsonb_typeof(p_value) = 'null' then
    return 'null'::jsonb;
  end if;
  if jsonb_typeof(p_value) is distinct from 'string' then
    raise exception
      'item custody % must be JSON null or a character:/party: identity', p_field;
  end if;
  if not public._rhc_full_id_match(
    p_value #>> '{}', '^(character|party):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'item custody % must be JSON null or a valid character:/party: identity', p_field;
  end if;
  return p_value;
end;
$$;

revoke all on function public._rhc_normalize_custody_actor(jsonb, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Custody record validation + canonicalization (internal). Validates the
--    approved EV2-11 record and returns the canonical record. Only `item:`
--    identities are accepted for `item_id`; extra fields and a stored status
--    field are rejected, matching the schema's `additionalProperties: false`.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_item_custody_record(p_record jsonb)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_owner jsonb;
  v_holder jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'item custody record must be a JSON object';
  end if;
  if (p_record - 'item_id' - 'owner_entity_id' - 'holder_entity_id') <> '{}'::jsonb then
    raise exception 'item custody record contains fields outside the EV2-11 contract (item_id, owner_entity_id, holder_entity_id)';
  end if;
  if not (p_record ?& array['item_id', 'owner_entity_id', 'holder_entity_id']) then
    raise exception 'item custody record requires item_id, owner_entity_id and holder_entity_id';
  end if;

  if jsonb_typeof(p_record -> 'item_id') is distinct from 'string'
     or not public._rhc_full_id_match(
       p_record ->> 'item_id', '^item:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'item custody item_id must be a valid item: identity';
  end if;

  v_owner := public._rhc_normalize_custody_actor(
    p_record -> 'owner_entity_id', 'owner_entity_id');
  v_holder := public._rhc_normalize_custody_actor(
    p_record -> 'holder_entity_id', 'holder_entity_id');

  return jsonb_build_object(
    'item_id', p_record -> 'item_id',
    'owner_entity_id', v_owner,
    'holder_entity_id', v_holder
  );
end;
$$;

revoke all on function public._rhc_normalize_item_custody_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Whole-collection validation (internal). The complete candidate
--    `item_custody` namespace is proven before it can be staged: a JSON array of
--    canonical EV2-11 records with exactly one record per `item_id`, every record
--    re-validated. This is the one-authoritative-record-per-item law.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_item_custody_collection(p_collection jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entry jsonb;
  v_norm jsonb;
  v_item text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'item_custody namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_item_custody_record(v_entry);
    v_item := v_norm ->> 'item_id';
    if array_position(v_seen, v_item) is not null then
      raise exception
        'item_custody namespace holds duplicate custody records for %; exactly one authoritative record per item_id is required',
        v_item;
    end if;
    v_seen := array_append(v_seen, v_item);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_item_custody_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Explicit same-save custody-staging marker (internal). Closure must key on
--    the operation fact, not on final JSON equality: an absolute target can be
--    re-staged to a value that already equals published reality (a replay), or
--    mutated away and back, and in both cases the final value would look
--    unchanged even though a successful custody staging operation occurred.
--    The save locator therefore records the lock_token that staged custody. The
--    database mints a fresh lock_token at every BEGIN and clears stale candidate
--    rows, so the marker can only match the CURRENT save's token and never leaks
--    into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists item_custody_staged_lock_token text;

create or replace function public._rhc_custody_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.item_custody_staged_lock_token is not null
            and cr.item_custody_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_custody_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.item_custody_staged_lock_token is
  'EV2-11 internal operation fact: the lock_token of the save that most recently staged a successful item custody mutation. Matched against the active lock_token so the same-save custody/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 4b. Authoritative published Run truth (internal). Validates the complete
--     published `runs` batch and returns it (or '[]' when absent). This is the
--     same strictness the shared EV2-10 controller resolver applies: a
--     non-object entry, an entry without a string run_id, a duplicated
--     authoritative Run identity, an EV2-08-invalid record, or a cross-Run
--     mutable-owner conflict (one actor claimed by more than one Run) fails
--     closed rather than being skipped. Gameplay custody mutation proves this
--     truth for EVERY request, including the no-actor treasure case, so an empty
--     actor set cannot bypass controller/published-Run validation.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_published_runs_truth()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_runs jsonb;
  v_entry jsonb;
begin
  select csg.value into v_runs
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'runs'
   where cr.id = 1;

  if v_runs is null then
    return '[]'::jsonb;
  end if;
  if jsonb_typeof(v_runs) is distinct from 'array' then
    raise exception 'published runs state is unreadable; custody controller cannot be proven';
  end if;

  -- Whole-batch shape/identity proof: a non-object entry, an entry without a
  -- string run_id, or a duplicated authoritative Run identity fails closed
  -- rather than being skipped.
  if exists (
       select 1 from jsonb_array_elements(v_runs) e
        where jsonb_typeof(e) is distinct from 'object'
     ) then
    raise exception 'published runs state contains a non-object entry; custody controller cannot be proven';
  end if;
  if exists (
       select 1 from jsonb_array_elements(v_runs) e
        where jsonb_typeof(e -> 'run_id') is distinct from 'string'
     ) then
    raise exception 'published runs state contains an entry without a string run_id; custody controller cannot be proven';
  end if;
  if exists (
       select 1 from jsonb_array_elements(v_runs) e
        group by e ->> 'run_id' having count(*) > 1
     ) then
    raise exception 'published runs state contains a duplicate authoritative Run identity; custody controller is ambiguous';
  end if;

  for v_entry in select e from jsonb_array_elements(v_runs) e loop
    perform public._rhc_validate_run_record(v_entry);
  end loop;

  -- Existing EV2-08 batch invariant: one mutable actor may be claimed by at most
  -- one authoritative Run. Reuse the RT04 candidate-ownership validator over the
  -- published batch, so two otherwise valid Runs claiming the same mutable owner
  -- fail closed for EVERY custody mutation (including the empty-actor treasure
  -- case) instead of being trusted because no actor was involved. Duplicate
  -- run_id rejection alone is not sufficient.
  perform public._rhc_validate_candidate_run_ownership(v_runs);

  return v_runs;
end;
$$;

revoke all on function public._rhc_published_runs_truth()
  from public, anon, authenticated, service_role;

comment on function public._rhc_published_runs_truth() is
  'EV2-11 internal authoritative published Run truth reader. Returns the complete published runs batch (or [] when absent) after proving every entry is an object with a unique string run_id and a valid EV2-08 record, and after proving the existing EV2-08 cross-Run mutable-owner uniqueness invariant (no mutable actor claimed by more than one Run); malformed, duplicated or ownership-conflicting published Run truth fails closed. Used so gameplay custody mutation proves controller truth even when the custody actor set is empty. Internal-only.';

-- ---------------------------------------------------------------------------
-- 5. The validated atomic unique-item custody mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_item_custody(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "item_id": "<item:slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "owner_entity_id": <null | character:/party: identity>,
--        "holder_entity_id": <null | character:/party: identity>
--      }
--
--    The target is ABSOLUTE, not a delta, so replaying one logical update
--    re-stages the same facts and cannot drift. Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth for
--        every involved actor;
--      * a same-save staged `runs` change (ownership handoff) fails closed,
--        because published Run truth would no longer describe the actors this
--        save would publish -> no former/stale-controller overwrite;
--      * a mutation for an absent/unadmitted `item_id` fails closed and mints
--        nothing; an existing `item_id` counts as admitted ONLY after the
--        current custody record/collection satisfies the EV2-11 contract, so
--        malformed current truth fails closed and is never canonicalized by
--        overwrite;
--      * authoritative published Run truth is proven for every mutation,
--        including the no-actor treasure case, so an empty actor set cannot
--        bypass controller validation; the full published Run batch must also
--        satisfy the existing cross-Run mutable-owner uniqueness invariant, so
--        two distinct valid Runs claiming one actor fail closed;
--      * the complete candidate custody namespace is validated (one record per
--        item_id, every record EV2-11-valid) before anything is staged;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_item_custody(
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
  v_item text;
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_record jsonb;
  v_collection jsonb;
  v_new_collection jsonb;
  v_current_record jsonb;
  v_current_owner text;
  v_current_holder text;
  v_new_owner text;
  v_new_holder text;
  v_matches integer;
  v_actors text[] := '{}';
  v_actor text;
  v_actor_controller text;
  v_runs_truth jsonb;
  v_asserted_run jsonb;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save controller integrity: custody authority is proven against
  -- PUBLISHED Run truth. If this save has already staged a different `runs`
  -- batch, published truth no longer describes the Run ownership this save will
  -- publish, so a former controller could stage a stale custody update. Fail
  -- closed; Run-ownership changes and custody mutations belong in separate
  -- saves. (The staging generation starts as a copy of published reality, so an
  -- untouched runs batch compares equal and does not trip this guard.)
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; item custody controller cannot be proven against published Run truth, so custody mutation fails closed (change Run ownership and item custody in separate saves)';
  end if;

  -- Bounded request contract. owner/holder are REQUIRED keys so a missing field
  -- (SQL NULL) cannot be confused with an explicit JSON null (a real absence).
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'item custody mutation request must be a JSON object';
  end if;
  if not p_request ?& array['item_id', 'controller', 'owner_entity_id', 'holder_entity_id'] then
    raise exception 'item custody mutation request requires item_id, controller, owner_entity_id and holder_entity_id';
  end if;
  if (p_request - 'item_id' - 'controller' - 'owner_entity_id' - 'holder_entity_id') <> '{}'::jsonb then
    raise exception 'item custody mutation request contains fields outside the EV2-11 contract';
  end if;

  -- item_id: gameplay addresses only an already-admitted `item:` identity.
  if jsonb_typeof(p_request -> 'item_id') is distinct from 'string' then
    raise exception 'item custody item_id must be a JSON string item: identity';
  end if;
  v_item := p_request ->> 'item_id';
  if not public._rhc_full_id_match(v_item, '^item:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'item custody item_id must be a valid item: identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch.
  -- `kind: null` (or an array/object) would make `v_kind NOT IN (...)` evaluate
  -- to SQL NULL under three-valued logic, the guard would not fire, and the
  -- later `v_kind = 'run'` test would also be NULL, silently falling through to
  -- the MAINRUN branch. Require an explicit JSON string first so null, missing,
  -- non-string and unknown values all fail closed. (Identical law to EV2-10.)
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

  -- Prove authoritative published Run truth for EVERY custody mutation, even
  -- when the actor set turns out to be empty. The treasure case (owner=null,
  -- holder=null) must not bypass controller validation: a malformed or
  -- duplicated published `runs` batch fails closed here regardless of actors,
  -- and a Run assertion is additionally proven to name an existing,
  -- non-parked authoritative Run below.
  v_runs_truth := public._rhc_published_runs_truth();

  -- Validate + canonicalize the absolute target. Missing-vs-null is already
  -- unambiguous because the keys were required above; an explicit JSON null
  -- stays a valid absent-owner/absent-holder fact.
  v_record := public._rhc_normalize_item_custody_record(
    jsonb_build_object(
      'item_id', v_item,
      'owner_entity_id', p_request -> 'owner_entity_id',
      'holder_entity_id', p_request -> 'holder_entity_id'
    )
  );

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope. The candidate begins as a copy of published
  -- reality via BEGIN, so this only fills the never-yet-created case.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'item_custody';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'item_custody';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'item_custody namespace is unreadable; custody mutation fails closed';
  end if;

  -- Validate the EXISTING custody truth before `item_id` presence can count as
  -- admission proof. A record that is malformed under the EV2-11 contract (or a
  -- collection holding duplicate records) is not an admitted identity: the
  -- mutation fails closed and must not canonicalize malformed truth by
  -- overwriting it. This reuses the same contract validator the staged
  -- candidate is proven against.
  perform public._rhc_validate_item_custody_collection(v_collection);

  -- Gameplay updates an existing admitted record only; it never appends/mints a
  -- new item identity. A duplicate current record is already an ambiguity.
  select count(*) into v_matches
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object' and (e ->> 'item_id') = v_item;
  if v_matches = 0 then
    raise exception
      'no admitted custody record exists for %; gameplay mutation cannot mint or admit a new item identity (initial admission is deferred to EV2-12)',
      v_item;
  end if;
  if v_matches > 1 then
    raise exception
      'item_custody namespace already holds duplicate custody records for %; failing closed',
      v_item;
  end if;

  select e into v_current_record
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object' and (e ->> 'item_id') = v_item
   limit 1;

  v_current_owner := v_current_record ->> 'owner_entity_id';
  v_current_holder := v_current_record ->> 'holder_entity_id';
  v_new_owner := v_record ->> 'owner_entity_id';
  v_new_holder := v_record ->> 'holder_entity_id';

  -- Authority follows the current controllers of the actors whose ownership/
  -- holding facts are being relinquished or newly assigned. Collect every
  -- non-null actor across current and target owner/holder.
  for v_actor in
    select unnest(array[v_current_owner, v_current_holder, v_new_owner, v_new_holder])
  loop
    if v_actor is not null and array_position(v_actors, v_actor) is null then
      v_actors := array_append(v_actors, v_actor);
    end if;
  end loop;

  -- Every involved actor must resolve compatibly under the one asserted current
  -- controller, using the shared EV2-10 published-Run resolver (malformed batch,
  -- parked claiming Run, two-Run claim and duplicated Run identity all fail
  -- closed there rather than falling through to MAINRUN).
  foreach v_actor in array v_actors loop
    v_actor_controller := public._rhc_inventory_controller_for_owner(v_actor);
    if v_kind = 'run' then
      if v_actor_controller is null then
        raise exception
          'no published Run currently controls %; a Run controller cannot assert custody authority',
          v_actor;
      end if;
      if v_actor_controller is distinct from v_run_id then
        raise exception
          'published Run % currently controls %; asserted Run % does not own it, so this custody mutation crosses controllers and fails closed',
          v_actor_controller, v_actor, v_run_id;
      end if;
    else
      if v_actor_controller is not null then
        raise exception
          'published Run % currently controls %; MAINRUN may not mutate that actor''s custody facts (route the cross-controller handoff through the existing reconciliation boundary)',
          v_actor_controller, v_actor;
      end if;
    end if;
  end loop;

  -- No-actor case (treasure: current and target owner/holder are all null). The
  -- per-actor loop above cannot prove anything, so the asserted controller is
  -- proven here against the already-validated published Run truth: a nonexistent
  -- asserted Run, or a parked Run that is not a current controller, fails
  -- closed. (Malformed/duplicated published Run truth already failed in
  -- `_rhc_published_runs_truth`.) A MAINRUN assertion is vacuous-but-valid when
  -- no actor facts are implicated.
  if v_kind = 'run' and coalesce(array_length(v_actors, 1), 0) = 0 then
    select e into v_asserted_run
      from jsonb_array_elements(v_runs_truth) e
     where e ->> 'run_id' = v_run_id
     limit 1;
    if v_asserted_run is null then
      raise exception
        'published Run % does not exist; asserted Run controller cannot be proven for this custody mutation',
        v_run_id;
    end if;
    if (v_asserted_run ->> 'execution_mode') = 'played'
       and (v_asserted_run ->> 'control_state') = 'parked' then
      raise exception
        'published Run % is parked and cannot control custody; custody controller cannot be proven',
        v_run_id;
    end if;
  end if;

  -- Replace the single admitted record with the absolute target.
  select coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'item_id') = v_item
           then v_record else e end
    ), '[]'::jsonb)
    into v_new_collection
    from jsonb_array_elements(v_collection) e;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_item_custody_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'item_custody', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact: a successful custody staging happened in this
  -- save, independent of whether the staged value differs from published
  -- reality. This closes every Run-ownership-writing doorway for the rest of the
  -- save, even for a value-equal replay.
  update public.campaign_runtime
     set item_custody_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'item_custody_mutation_version', 1,
    'item_id', v_item,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'custody', v_record
  );
end;
$$;

revoke all on function public.mutate_item_custody(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_item_custody(text, jsonb) to service_role;

comment on function public.mutate_item_custody(text, jsonb) is
  'EV2-11: the only validated atomic unique-item custody mutation route, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion (controller.kind must be a JSON string exactly mainrun or run; null/missing/non-string/unknown fails closed before any authority branch), proves every non-null actor across current/new owner/holder against authoritative published Run truth (fail-closed on a malformed published runs batch, a parked claiming Run, a duplicated authoritative Run identity, and a same-save staged runs change), validates the absolute owner/holder target (item: item_id, owner/holder each JSON null or character:/party:), updates exactly one already-admitted custody record (never mints a new item: identity), then stages the updated single-record collection into the engine-owned item_custody namespace and records the custody-staging operation fact that closes every Run-ownership-writing doorway for the rest of the save. Absolute target, replay-safe, all-or-nothing through the existing gateway.';

-- ---------------------------------------------------------------------------
-- 6. Close the generic `item_custody` bypass. The custody namespace is
--    engine-owned: it can never be staged or deleted through the generic routes.
--    This re-declares the HWB-02/EV2-10 generic routes unchanged except for the
--    added item_custody closure and the same-save custody/Run-ownership mutual
--    exclusion (once this save has staged a custody mutation, the generic `runs`
--    key is refused too), preserving every existing dedicated-key closure and
--    the server-owned ordinary-save allowlist exactly.
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
    raise exception 'item_custody is engine-owned and can only be staged through mutate_item_custody';
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
      'the runs batch cannot be changed in a save that has already staged an item custody mutation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one';
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
      'the runs batch cannot be changed in a save that has already staged an item custody mutation; custody authority would become stale against the changed Run ownership, so abort this save and start a new one';
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory and item_custody keys are rejected here and must use their validated routes. Once a reconciliation is newly staged in the current save, or once this save has staged an inventory or item custody mutation, the runs key is refused for the rest of the save; historical receipts copied forward from published reality do not trigger the reconciliation closure. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';
comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody and Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';
comment on function public._rhc_normalize_item_custody_record(jsonb) is
  'EV2-11 internal unique-item custody record validation + canonicalization. Enforces exactly item_id + owner_entity_id + holder_entity_id with no stored status field, item_id a valid item: identity, and owner/holder each JSON null or a valid character:/party: identity (missing-vs-null is unambiguous). Internal-only: custody payloads are reachable only through the validated mutate_item_custody route.';
comment on function public._rhc_validate_item_custody_collection(jsonb) is
  'EV2-11 internal whole-collection validation. Proves the complete candidate item_custody namespace is a JSON array of canonical records with exactly one authoritative record per item_id, rejecting duplicate custody records. Internal-only.';
comment on function public._rhc_custody_staged_in_save() is
  'EV2-11 internal same-save custody-staging operation fact. True only when the active save''s lock_token matches the lock_token that most recently staged a successful item custody mutation, so closure keys on the staging operation rather than on final value equality (a value-equal replay still trips it) and never leaks into a later save. Internal-only.';

-- ---------------------------------------------------------------------------
-- 7. Close the dedicated RT04 reconciliation-after-custody doorway. The generic
--    `runs` stage/delete closure above stops generic same-save Run changes once
--    custody has been staged, but `reconcile_run_resolution` writes the `runs`
--    batch with a direct INSERT and would bypass it. This re-declares the RT04
--    route unchanged except for the same-save custody guard (on top of the
--    EV2-10 inventory guard), so every Run-ownership-writing doorway fails
--    closed in a save that has staged a custody mutation. The guard reads the
--    explicit staging operation fact, not final custody value equality. RT04 is
--    not redesigned and no second save engine is added.
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

  -- EV2-10 same-save coupling (round-2/round-3 P1): once this save has staged a
  -- successful inventory mutation, Run ownership must not change in the same
  -- generation. Inventory authority was proven against the published Run
  -- controller, so a later reconciliation could release that owner and publish a
  -- stale inventory update. Every Run-ownership-writing doorway, including this
  -- dedicated RT04 route, fails closed here; change Run ownership and inventory
  -- in separate saves. Detection is the explicit staging operation fact, not
  -- final value equality, so a value-equal replay of the same absolute inventory
  -- target still trips this guard.
  if public._rhc_inventory_staged_in_save() then
    raise exception
      'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)';
  end if;

  -- EV2-11 same-save coupling: the same law for a staged item custody mutation.
  -- Custody authority was proven against the published Run controller, so a
  -- later reconciliation must not change Run ownership in the same generation.
  if public._rhc_custody_staged_in_save() then
    raise exception
      'this save has already staged an item custody mutation; a Run reconciliation would change Run ownership after custody authority was proven, so reconciliation fails closed (change Run ownership and item custody in separate saves)';
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
  'RT04/EV2-10/EV2-11: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet (with their validated summary), and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. EV2-10 adds the same-save guard for a staged inventory mutation; EV2-11 adds the same guard for a staged item custody mutation. All-or-nothing through the existing gateway.';
