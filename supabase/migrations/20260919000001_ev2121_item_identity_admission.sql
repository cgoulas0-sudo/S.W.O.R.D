-- EV2-12.1 — Generalized persistent item identity admission
-- Rolling High Club reusable, deterministic, explicitly authorized admission
-- action for persistent unique `item:` identities, on the existing RT01 SAVE /
-- publish / mirror / confirm spine.
--
-- This migration creates NO new save engine, NO parallel persistence/mirror path,
-- and NO automatic identity inference. It generalizes the proven EV2-12 one-off
-- Vampire canary into ONE reusable semantic action, plus a bounded durable
-- admission/provenance receipt namespace.
--
-- Architecture sentence:
--   EV2-12.1 does not create a new save system. It creates a new authorized
--   semantic admission action on top of the existing RT01 SAVE / publish /
--   mirror / confirm spine.
--
-- WHAT this migration changes:
--   1. `public.admit_item_identity(p_lock_token, p_request)` — the ONE reusable,
--      explicitly authorized admission action for an already-approved concrete
--      persistent unique item instance. It runs INSIDE the normal campaign save
--      lifecycle (`begin_campaign_save` -> admit -> `publish_campaign_save` ->
--      existing mirror/confirmation handshake), validates the declared request
--      and bounded provenance facts, proves duplicate/conflict/replay conditions
--      against published + candidate truth, proves the complete cross-collection
--      invariant that every `item_admissions` receipt has exactly one matching
--      `item_custody` record for the same `item_id` (receipt-without-custody
--      fails closed; the forward-only pre-EV2-12.1 legacy asymmetry where
--      `item:vampire` has custody without a receipt stays allowed), stages the
--      item's single `item_custody` record (with optional established initial
--      custody) and its single bounded `item_admissions` receipt, and never
--      invents owner, holder, day, RUN reference or any other unestablished fact.
--   2. The bounded engine-owned `item_admissions` runtime namespace holds exactly
--      one admission/provenance receipt per admitted `item:` identity. It is a
--      bounded receipt, not a history/event subsystem.
--   3. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--      routes reject the `item_admissions` key (the same dedicated-key closure
--      pattern as `campaign_clock`, `run_reconciliations`, `inventory` and
--      `item_custody`), so a caller/model cannot bypass the validated action with
--      a raw generic runtime write. The HWB-02 ordinary-save allowlist is
--      preserved unchanged.
--
-- SEPARATION OF CONCEPTS (preserved, not collapsed):
--   * definition  != instance != custody != provenance;
--   * a reusable static definition may correspond to zero, one or many
--     persistent instances;
--   * the persistent instance identity is the stable `item:` ID, never a display
--     name, type, rarity or narrative importance;
--   * identity admission is not ordinary inventory mutation, not gameplay
--     custody transfer, not equipment/attunement, and not character admission.
--
-- EXPLICIT AUTHORIZATION:
--   Admission authority is explicit in this semantic action and its declared
--   request. Mere ability to call the generic SAVE/stage/delete routes is NOT
--   mint authority: those routes cannot write `item_custody` or
--   `item_admissions` at all.
--
-- REPLAY / CRASH LAW:
--   A crash before publication leaves no durable admission; the next save can
--   admit the same declared instance exactly once. A retry after publication
--   fails closed on the already-admitted identity. Either way the outcome is
--   deterministic and can never mint a second persistent identity or receipt for
--   the same declared instance.
--
-- NON-MINTING LAW (EV2-11) IS UNCHANGED:
--   `public.mutate_item_custody(...)` remains non-minting: gameplay updates an
--   already-admitted custody record only and can never append/mint a new `item:`
--   identity. EV2-12.1 does not widen gameplay authority; it only provides the
--   explicit authorized admission action.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11 forward-only
--    install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'EV2-12.1 migration refused: resolve the active campaign save before installing the generalized item identity admission action';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Bounded admission provenance validation + canonicalization (internal).
--    Provenance is a bounded receipt fact: source/event when established, an
--    optional campaign day, and nothing else. Unknown stays Unknown: missing or
--    explicit JSON null is preserved as null and is never synthesized. Every
--    value is either JSON null or a structurally valid established fact.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_item_admission_provenance(
  p_provenance jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_source text;
  v_event text;
  v_day jsonb;
  v_out jsonb := '{}'::jsonb;
begin
  if p_provenance is null or jsonb_typeof(p_provenance) is distinct from 'object' then
    raise exception 'item admission provenance must be a JSON object';
  end if;
  if (p_provenance - 'source' - 'event' - 'campaign_day') <> '{}'::jsonb then
    raise exception
      'item admission provenance contains fields outside the EV2-12.1 contract (source, event, campaign_day)';
  end if;

  -- source: non-blank string or JSON null; never fabricated.
  if (p_provenance ? 'source')
     and jsonb_typeof(p_provenance -> 'source') is distinct from 'null' then
    if jsonb_typeof(p_provenance -> 'source') is distinct from 'string' then
      raise exception 'item admission provenance source must be a non-blank JSON string or null';
    end if;
    v_source := p_provenance ->> 'source';
    if v_source !~ '\S' then
      raise exception 'item admission provenance source must be a non-blank JSON string or null';
    end if;
    v_out := v_out || jsonb_build_object('source', v_source);
  else
    v_out := v_out || jsonb_build_object('source', null);
  end if;

  -- event: non-blank string or JSON null; never fabricated.
  if (p_provenance ? 'event')
     and jsonb_typeof(p_provenance -> 'event') is distinct from 'null' then
    if jsonb_typeof(p_provenance -> 'event') is distinct from 'string' then
      raise exception 'item admission provenance event must be a non-blank JSON string or null';
    end if;
    v_event := p_provenance ->> 'event';
    if v_event !~ '\S' then
      raise exception 'item admission provenance event must be a non-blank JSON string or null';
    end if;
    v_out := v_out || jsonb_build_object('event', v_event);
  else
    v_out := v_out || jsonb_build_object('event', null);
  end if;

  -- campaign_day: optional non-negative integer or JSON null. It is a declared
  -- historical context fact only; it is never cross-derived from the Clock and
  -- never synthesized.
  if (p_provenance ? 'campaign_day')
     and jsonb_typeof(p_provenance -> 'campaign_day') is distinct from 'null' then
    if jsonb_typeof(p_provenance -> 'campaign_day') is distinct from 'number'
       or (p_provenance ->> 'campaign_day')::numeric < 0
       or (p_provenance ->> 'campaign_day')::numeric
          is distinct from trunc((p_provenance ->> 'campaign_day')::numeric) then
      raise exception 'item admission provenance campaign_day must be a non-negative integer or null';
    end if;
    v_day := p_provenance -> 'campaign_day';
    v_out := v_out || jsonb_build_object('campaign_day', v_day);
  else
    v_out := v_out || jsonb_build_object('campaign_day', null);
  end if;

  return v_out;
end;
$$;

revoke all on function public._rhc_normalize_item_admission_provenance(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Bounded admission receipt validation + canonicalization (internal). The
--    receipt is the durable record that one concrete persistent item instance
--    was explicitly declared and successfully admitted through the authorized
--    action. It carries only established facts: the stable instance identity,
--    the asserted controller context, the bounded provenance, the
--    database-owned generation it was admitted into, and the receipt version.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_item_admission_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_provenance jsonb;
  v_generation jsonb;
  v_version jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'item admission receipt must be a JSON object';
  end if;
  if (p_record - 'item_id' - 'controller' - 'provenance'
        - 'admitted_generation' - 'admission_version') <> '{}'::jsonb then
    raise exception
      'item admission receipt contains fields outside the EV2-12.1 contract (item_id, controller, provenance, admitted_generation, admission_version)';
  end if;
  if not (p_record ?& array['item_id', 'controller', 'provenance',
                            'admitted_generation', 'admission_version']) then
    raise exception
      'item admission receipt requires item_id, controller, provenance, admitted_generation and admission_version';
  end if;

  if jsonb_typeof(p_record -> 'item_id') is distinct from 'string'
     or not public._rhc_full_id_match(
       p_record ->> 'item_id', '^item:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'item admission receipt item_id must be a valid item: identity';
  end if;

  -- Controller context is a bounded mainrun-or-one-RUN assertion, exactly the
  -- shape the custody authority model consumes.
  v_controller := p_record -> 'controller';
  if v_controller is null or jsonb_typeof(v_controller) is distinct from 'object' then
    raise exception 'item admission receipt controller must be a JSON object';
  end if;
  if not (v_controller ? 'kind')
     or jsonb_typeof(v_controller -> 'kind') is distinct from 'string' then
    raise exception 'item admission receipt controller kind must be a JSON string of mainrun or run';
  end if;
  v_kind := v_controller ->> 'kind';
  if v_kind is null or v_kind not in ('mainrun', 'run') then
    raise exception 'item admission receipt controller kind must be mainrun or run';
  end if;
  if v_kind = 'run' then
    if not (v_controller ? 'run_id')
       or (v_controller - 'kind' - 'run_id') <> '{}'::jsonb then
      raise exception 'item admission receipt run controller requires exactly kind and run_id';
    end if;
    v_run_id := v_controller ->> 'run_id';
    if not public._rhc_full_id_match(v_run_id, '^R[0-9]{2,}$') then
      raise exception 'item admission receipt controller run_id must be R followed by at least two digits';
    end if;
  else
    if (v_controller - 'kind') <> '{}'::jsonb then
      raise exception 'item admission receipt mainrun controller accepts exactly kind';
    end if;
  end if;

  v_provenance := public._rhc_normalize_item_admission_provenance(p_record -> 'provenance');

  v_generation := p_record -> 'admitted_generation';
  if jsonb_typeof(v_generation) is distinct from 'number'
     or (v_generation #>> '{}')::numeric < 1
     or (v_generation #>> '{}')::numeric
        is distinct from trunc((v_generation #>> '{}')::numeric) then
    raise exception 'item admission receipt admitted_generation must be a positive integer generation';
  end if;

  v_version := p_record -> 'admission_version';
  if jsonb_typeof(v_version) is distinct from 'number'
     or (v_version #>> '{}')::numeric is distinct from 1 then
    raise exception 'item admission receipt admission_version must be 1';
  end if;

  return jsonb_build_object(
    'item_id', p_record -> 'item_id',
    'controller', v_controller,
    'provenance', v_provenance,
    'admitted_generation', v_generation,
    'admission_version', v_version
  );
end;
$$;

revoke all on function public._rhc_normalize_item_admission_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Whole-collection validation (internal). The complete candidate
--    `item_admissions` namespace must be a JSON array of canonical receipts with
--    exactly one authoritative receipt per `item_id`; a duplicate receipt is an
--    ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_item_admissions_collection(
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
  v_item text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'item_admissions namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_item_admission_record(v_entry);
    v_item := v_norm ->> 'item_id';
    if array_position(v_seen, v_item) is not null then
      raise exception
        'item_admissions namespace holds duplicate admission receipts for %; exactly one authoritative receipt per item_id is required',
        v_item;
    end if;
    v_seen := array_append(v_seen, v_item);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_item_admissions_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3b. Cross-collection receipt-to-custody integrity (internal). Validating
--     `item_custody` and `item_admissions` independently is NOT sufficient: a
--     structurally valid orphan receipt for one item can survive while the
--     action stages a different item, which would republish admission truth that
--     could never have been atomically created with custody.
--
--     The invariant is one-directional: EVERY admission receipt must have
--     EXACTLY ONE matching custody record for the same `item_id`. An
--     admission receipt without custody is always invalid and fails closed. The
--     reverse asymmetry is the intentional forward-only legacy exception: the
--     pre-EV2-12.1 `item:vampire` admission has custody without a receipt, and
--     any custody record may legitimately predate admission receipts, so
--     custody-without-receipt is allowed and is never treated as an orphan.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_item_admission_custody_linkage(
  p_custody jsonb,
  p_admissions jsonb
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_receipt jsonb;
  v_item text;
  v_matches bigint;
begin
  if p_custody is null or jsonb_typeof(p_custody) is distinct from 'array' then
    raise exception 'item_custody namespace must be a JSON array';
  end if;
  if p_admissions is null or jsonb_typeof(p_admissions) is distinct from 'array' then
    raise exception 'item_admissions namespace must be a JSON array';
  end if;

  for v_receipt in select e from jsonb_array_elements(p_admissions) e loop
    if jsonb_typeof(v_receipt) is distinct from 'object' then
      raise exception 'item admission receipt must be a JSON object';
    end if;
    v_item := v_receipt ->> 'item_id';
    select count(*) into v_matches
      from jsonb_array_elements(p_custody) c
     where jsonb_typeof(c) = 'object'
       and (c ->> 'item_id') = v_item;
    if v_matches = 0 then
      raise exception
        'item admission receipt for % has no matching item_custody record; every admission receipt requires exactly one custody record for the same item_id, so receipt-without-custody fails closed (only the forward-only pre-EV2-12.1 custody-without-receipt legacy asymmetry is allowed)',
        coalesce(v_item, '<malformed>');
    end if;
    if v_matches > 1 then
      raise exception
        'item admission receipt for % has multiple matching item_custody records; exactly one custody record per admitted item_id is required',
        v_item;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_item_admission_custody_linkage(jsonb, jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. The reusable, explicitly authorized item identity admission action.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> admit_item_identity(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "item_id": "<item:slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "provenance": {
--          "source": <null | non-blank string>,
--          "event":  <null | non-blank string>,
--          "campaign_day": <null | non-negative integer>
--        },
--        "owner_entity_id":  <optional, null | character:/party: identity>,
--        "holder_entity_id": <optional, null | character:/party: identity>
--      }
--
--    `item_id` + `controller` + `provenance` are required. Initial custody is
--    OPTIONAL: an omitted or explicit-null owner/holder establishes no custody
--    fact (both stay Unknown) and is never invented.
--
--    Fail-closed guarantees:
--      * admission only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller is proven against authoritative PUBLISHED Run
--        truth for every non-null initial-custody actor, and a Run assertion is
--        proven for the empty-actor treasure case too, exactly like EV2-11;
--      * a same-save staged `runs` change fails closed, because published Run
--        truth would no longer describe the actors this save would publish;
--      * the complete existing candidate `item_custody` and `item_admissions`
--        collections are validated before anything is staged, so malformed or
--        duplicate unrelated truth fails closed and is never canonicalized;
--      * the complete existing AND resulting cross-collection invariant is
--        proven before staging: every `item_admissions` receipt must have
--        exactly one matching `item_custody` record for the same `item_id`, so
--        a structurally valid orphan receipt can never survive an append (the
--        forward-only pre-EV2-12.1 custody-without-receipt legacy asymmetry
--        stays allowed);
--      * an `item_id` already present in either collection (published or
--        candidate) fails closed, so duplicate/conflicting/replayed admission
--        cannot mint a second identity or receipt;
--      * the complete resulting collections are validated before staging;
--      * both the custody record and the receipt are staged in the same
--        candidate generation, so a successful runtime admission and its durable
--        receipt cannot split-brain;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted admission all-or-nothing.
--
--    This action does NOT silently equip/attune, transfer custody, mutate
--    ordinary inventory quantity, create relationships, admit characters/NPCs,
--    or redesign taxonomy. It creates identity + first custody + bounded receipt
--    only, all on the existing RT01 spine.
-- ---------------------------------------------------------------------------
create or replace function public.admit_item_identity(
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
  v_owner jsonb;
  v_holder jsonb;
  v_provenance jsonb;
  v_custody_record jsonb;
  v_receipt jsonb;
  v_custody jsonb;
  v_admissions jsonb;
  v_new_custody jsonb;
  v_new_admissions jsonb;
  v_actor text;
  v_actor_controller text;
  v_actors text[] := '{}';
  v_runs_truth jsonb;
  v_asserted_run jsonb;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save controller integrity: admission authority for initial custody is
  -- proven against PUBLISHED Run truth. If this save has already staged a
  -- different `runs` batch, published truth no longer describes the ownership
  -- this save will publish, so admission fails closed. (The staging generation
  -- starts as a copy of published reality, so an untouched runs batch compares
  -- equal and does not trip this guard.)
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; admission controller cannot be proven against published Run truth, so item identity admission fails closed (change Run ownership and admit items in separate saves)';
  end if;

  -- Bounded request contract. `item_id`, `controller` and `provenance` are
  -- required; initial custody is optional and is never invented.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'item identity admission request must be a JSON object';
  end if;
  if not p_request ?& array['item_id', 'controller', 'provenance'] then
    raise exception
      'item identity admission request requires item_id, controller and provenance';
  end if;
  if (p_request - 'item_id' - 'controller' - 'provenance'
        - 'owner_entity_id' - 'holder_entity_id') <> '{}'::jsonb then
    raise exception
      'item identity admission request contains fields outside the EV2-12.1 contract';
  end if;

  -- item_id: the explicit stable persistent instance identity. It is never
  -- inferred from name/type/rarity/presence.
  if jsonb_typeof(p_request -> 'item_id') is distinct from 'string' then
    raise exception 'item identity admission item_id must be a JSON string item: identity';
  end if;
  v_item := p_request ->> 'item_id';
  if not public._rhc_full_id_match(v_item, '^item:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'item identity admission item_id must be a valid item: identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch, so
  -- a null/missing/non-string/unknown kind can never fall through to MAINRUN.
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

  -- Prove authoritative published Run truth for EVERY admission, even when the
  -- initial-custody actor set is empty. A malformed or duplicated published
  -- `runs` batch fails closed here regardless of actors, and a Run assertion is
  -- additionally proven below.
  v_runs_truth := public._rhc_published_runs_truth();

  -- Optional initial custody, validated and canonicalized. Missing and explicit
  -- JSON null both mean "not established" and stay Unknown.
  v_owner := public._rhc_normalize_custody_actor(
    coalesce(p_request -> 'owner_entity_id', 'null'::jsonb), 'owner_entity_id');
  v_holder := public._rhc_normalize_custody_actor(
    coalesce(p_request -> 'holder_entity_id', 'null'::jsonb), 'holder_entity_id');

  -- Bounded provenance receipt facts, validated and canonicalized.
  v_provenance := public._rhc_normalize_item_admission_provenance(p_request -> 'provenance');

  -- The admitted item's single custody record. Identity + custody stay separate
  -- concepts; this only materializes the first custody record for the identity.
  v_custody_record := public._rhc_normalize_item_custody_record(
    jsonb_build_object(
      'item_id', v_item,
      'owner_entity_id', v_owner,
      'holder_entity_id', v_holder
    )
  );

  -- Candidate custody namespace: this save's staged value, else published
  -- reality, else the truthful empty envelope.
  select csg.value into v_custody
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'item_custody';
  if v_custody is null then
    select csg.value into v_custody
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'item_custody';
  end if;
  if v_custody is null then
    v_custody := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_custody) is distinct from 'array' then
    raise exception 'item_custody namespace is unreadable; item identity admission fails closed';
  end if;

  -- Candidate admission-receipt namespace, same resolution.
  select csg.value into v_admissions
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'item_admissions';
  if v_admissions is null then
    select csg.value into v_admissions
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'item_admissions';
  end if;
  if v_admissions is null then
    v_admissions := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_admissions) is distinct from 'array' then
    raise exception 'item_admissions namespace is unreadable; item identity admission fails closed';
  end if;

  -- Validate the COMPLETE existing custody truth and admission receipts before
  -- `item_id` presence can mean anything. Malformed or duplicate unrelated truth
  -- fails closed and is never canonicalized by append.
  perform public._rhc_validate_item_custody_collection(v_custody);
  perform public._rhc_validate_item_admissions_collection(v_admissions);

  -- Duplicate/conflict/replay: a persistent item identity is admitted once. If
  -- the identity already has a custody record OR an admission receipt in
  -- published or candidate truth, admission fails closed and mints nothing.
  if exists (
    select 1
      from jsonb_array_elements(v_custody) e
     where jsonb_typeof(e) = 'object'
       and (e ->> 'item_id') = v_item
  ) then
    raise exception
      'item % already has an admitted custody record; a persistent item identity is admitted once',
      v_item;
  end if;
  if exists (
    select 1
      from jsonb_array_elements(v_admissions) e
     where jsonb_typeof(e) = 'object'
       and (e ->> 'item_id') = v_item
  ) then
    raise exception
      'item % already has an admission receipt; replay would mint a duplicate admission',
      v_item;
  end if;

  -- Cross-collection integrity: the complete existing candidate truth must
  -- already satisfy the EV2-12.1 linkage law before this admission stages
  -- anything. Validating the two collections independently is not enough: a
  -- structurally valid orphan receipt for an unrelated item would otherwise
  -- survive this append and be republished forever with custody it never had.
  -- The forward-only legacy exception is preserved: custody-without-receipt
  -- (e.g. pre-EV2-12.1 `item:vampire`) is allowed and is never an orphan.
  perform public._rhc_validate_item_admission_custody_linkage(v_custody, v_admissions);

  -- Authority follows the current controllers of the actors whose initial
  -- ownership/holding facts are newly assigned. Collect every non-null actor.
  for v_actor in
    select unnest(array[v_owner #>> '{}', v_holder #>> '{}'])
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
          'no published Run currently controls %; a Run controller cannot assert initial-custody authority',
          v_actor;
      end if;
      if v_actor_controller is distinct from v_run_id then
        raise exception
          'published Run % currently controls %; asserted Run % does not own it, so this admission crosses controllers and fails closed',
          v_actor_controller, v_actor, v_run_id;
      end if;
    else
      if v_actor_controller is not null then
        raise exception
          'published Run % currently controls %; MAINRUN may not establish that actor''s initial custody facts (route the cross-controller handoff through the existing reconciliation boundary)',
          v_actor_controller, v_actor;
      end if;
    end if;
  end loop;

  -- No-actor case (no initial custody established). The per-actor loop cannot
  -- prove anything, so a Run assertion is proven here against the already-
  -- validated published Run truth: a nonexistent asserted Run, or a parked Run
  -- that is not a current controller, fails closed. A MAINRUN assertion is
  -- vacuous-but-valid when no actor facts are implicated.
  if v_kind = 'run' and coalesce(array_length(v_actors, 1), 0) = 0 then
    select e into v_asserted_run
      from jsonb_array_elements(v_runs_truth) e
     where e ->> 'run_id' = v_run_id
     limit 1;
    if v_asserted_run is null then
      raise exception
        'published Run % does not exist; asserted Run controller cannot be proven for this admission',
        v_run_id;
    end if;
    if (v_asserted_run ->> 'execution_mode') = 'played'
       and (v_asserted_run ->> 'control_state') = 'parked' then
      raise exception
        'published Run % is parked and cannot control admission; admission controller cannot be proven',
        v_run_id;
    end if;
  end if;

  -- Bounded durable receipt: only successful admissions produce one, and it
  -- records the database-owned generation this admission publishes into.
  v_receipt := public._rhc_normalize_item_admission_record(
    jsonb_build_object(
      'item_id', v_item,
      'controller', v_controller,
      'provenance', v_provenance,
      'admitted_generation', to_jsonb(r.staging_generation),
      'admission_version', 1
    )
  );

  -- Build the complete resulting collections and prove them before staging.
  v_new_custody := v_custody || jsonb_build_array(v_custody_record);
  perform public._rhc_validate_item_custody_collection(v_new_custody);

  v_new_admissions := v_admissions || jsonb_build_array(v_receipt);
  perform public._rhc_validate_item_admissions_collection(v_new_admissions);

  -- Prove the complete resulting cross-collection invariant before staging, so
  -- a candidate can never publish a receipt without exactly one matching
  -- custody record for the same item_id.
  perform public._rhc_validate_item_admission_custody_linkage(v_new_custody, v_new_admissions);

  -- Stage both the identity's custody record and its receipt into the same
  -- candidate generation. They publish together or not at all.
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'item_custody', v_new_custody, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'item_admissions', v_new_admissions, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Admission creates a custody record, so it is a custody-staging operation:
  -- record the operation fact that closes every Run-ownership-writing doorway
  -- for the rest of the save (same-save authority protection as EV2-11).
  update public.campaign_runtime
     set item_custody_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'item_identity_admission_version', 1,
    'item_id', v_item,
    'controller', v_controller,
    'provenance', v_provenance,
    'admitted_generation', r.staging_generation,
    'runtime', public._rhc_dm_runtime_metadata(),
    'custody', v_custody_record,
    'admission', v_receipt
  );
end;
$$;

revoke all on function public.admit_item_identity(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.admit_item_identity(text, jsonb) to service_role;

comment on function public.admit_item_identity(text, jsonb) is
  'EV2-12.1: the ONE reusable, explicitly authorized admission action for an already-approved concrete persistent unique item instance, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion and a bounded provenance object (source/event when established, optional campaign day; Unknown stays Unknown), accepts optional established initial owner/holder (never invented), proves every initial-custody actor against authoritative published Run truth plus the empty-actor Run case, validates the complete existing candidate item_custody and item_admissions collections, enforces the complete existing and resulting cross-collection invariant that every admission receipt has exactly one matching custody record for the same item_id (receipt-without-custody fails closed; the forward-only pre-EV2-12.1 item:vampire custody-without-receipt legacy asymmetry stays allowed), fails closed on any duplicate/conflicting/replayed item identity, validates the complete resulting collections, then stages the identity''s single custody record and single bounded admission receipt into the same candidate generation and records the custody-staging operation fact. It creates no second save engine, no new mirror path, no automatic identity inference, and does not equip, attune, transfer, mutate ordinary inventory, create relationships, or admit characters.';

-- ---------------------------------------------------------------------------
-- 5. Close the generic `item_admissions` bypass. The admission-receipt
--    namespace is engine-owned: it can never be staged or deleted through the
--    generic routes. This re-declares the HWB-02/EV2-10/EV2-11 generic routes
--    unchanged except for the added `item_admissions` closure, preserving every
--    existing dedicated-key closure, the same-save custody/Run-ownership mutual
--    exclusion, and the server-owned ordinary-save allowlist exactly.
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory, item_custody and item_admissions keys are rejected here and must use their validated routes (item_custody via mutate_item_custody or admit_item_identity; item_admissions via admit_item_identity). Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation or an item custody/admission operation, the runs key is refused for the rest of the save; historical receipts copied forward from published reality do not trigger the reconciliation closure. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';
comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody/admission and Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';
comment on function public._rhc_normalize_item_admission_provenance(jsonb) is
  'EV2-12.1 internal bounded admission provenance validation + canonicalization. Accepts exactly source, event and campaign_day; source/event are each JSON null or a non-blank string, campaign_day is JSON null or a non-negative integer; Unknown stays Unknown and is never synthesized. Internal-only.';
comment on function public._rhc_normalize_item_admission_record(jsonb) is
  'EV2-12.1 internal bounded admission receipt validation + canonicalization. Enforces exactly item_id + controller + provenance + admitted_generation + admission_version, a valid item: identity, a bounded mainrun-or-one-RUN controller, canonical bounded provenance, a positive integer database generation and version 1. Internal-only: receipts are reachable only through the validated admit_item_identity action.';
comment on function public._rhc_validate_item_admissions_collection(jsonb) is
  'EV2-12.1 internal whole-collection validation. Proves the complete candidate item_admissions namespace is a JSON array of canonical receipts with exactly one authoritative receipt per item_id, rejecting duplicate receipts. Internal-only.';
comment on function public._rhc_validate_item_admission_custody_linkage(jsonb, jsonb) is
  'EV2-12.1 internal cross-collection integrity validation. Proves every item_admissions receipt has exactly one matching item_custody record for the same item_id; a receipt without custody fails closed, and multiple matches fail closed. The reverse asymmetry is intentionally allowed: the forward-only pre-EV2-12.1 item:vampire admission and any custody record may predate admission receipts, so custody-without-receipt is never treated as an orphan. Internal-only.';
