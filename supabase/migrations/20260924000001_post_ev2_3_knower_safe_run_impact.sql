-- POST-EV2-3 — Knower-safe Run impact wiring
-- Rolling High Club validated runtime wiring for owner-local knowledge.
--
-- This migration is NOT a second save engine, NOT a second knowledge system and
-- NOT a second Run/controller authority. It adds ONE validated, atomic runtime
-- mutation route for EV2-14 owner-local knowledge on the existing RT01
-- begin -> validated stage -> publish -> mirror/confirmation spine, reuses the
-- shared EV2-10 published-Run controller resolver, and extends POST-EV2-1
-- Patch 1A's domain registry and Patch 1B's same-save compatibility contract by
-- exactly one domain and its audited edges.
--
-- Architecture sentence:
--   POST-EV2-3 does not create a new persistence authority. It creates the
--   dedicated engine-owned `entity_knowledge` runtime mutation surface that is
--   bound to the entity that owns the knowledge (the knower), with controller
--   authority resolved only from authoritative published Run truth, so Run
--   impact can use an existing legal domain owner instead of a new generic
--   impact/lock engine.
--
-- WHAT this migration changes:
--   1. `public.mutate_entity_knowledge(p_lock_token, p_request)` — the ONLY way
--      to stage the engine-owned `entity_knowledge` runtime namespace. It runs
--      INSIDE the normal campaign save lifecycle, proves the caller's asserted
--      controller (MAINRUN or exactly one RUN #) against authoritative PUBLISHED
--      Run truth for the knower entity, validates + canonicalizes one absolute
--      EV2-14 owner-local knowledge record, and stages exactly one authoritative
--      record per knower.
--   2. The engine-owned `entity_knowledge` runtime namespace is a JSON array
--      holding exactly one authoritative EV2-14 record per knower. Knowledge
--      belongs to the knower: it is not stored per Run and is never duplicated
--      per controller. It is not a second knowledge store — it is the runtime
--      representation of the existing `schemas/knowledge.schema.json` contract.
--   3. POST-EV2-1 Patch 1A: `_rhc_save_domain_policy` gains `entity_knowledge`
--      as `dedicated` with the exhaustive writer set
--      `[mutate_entity_knowledge]`; the generic `stage_campaign_state` /
--      `delete_staged_campaign_state` routes therefore fail closed for this key.
--   4. POST-EV2-1 Patch 1B: `_rhc_same_save_compatibility_policy` gains the
--      `mutate_entity_knowledge` operation (blocked by a same-save `runs`
--      change) and a new `entity_knowledge` edge on `stage_runs` / `delete_runs`
--      / `reconcile_runs` (Run ownership / reconciliation fails closed once a
--      knowledge mutation has been staged in the save). The compatibility
--      decision function gains the `knowledge_staged_in_save` detector. The
--      existing doorways already delegate to the shared contract, so no other
--      route body changes.
--
-- KNOWLEDGE MODEL (mirrors `schemas/knowledge.schema.json`, EV2-14 exactly):
--   * a record is `entity_id` + `status` + (`entries` only when known);
--   * `entity_id` is the knower — a `character:` / `location:` / `faction:` /
--     `party:` / `creature:` / `item:` stable identity;
--   * `status` is `known` / `unknown` / `not_applicable`; a `known` record
--     requires a non-empty `entries` array and an `unknown` / `not_applicable`
--     record forbids `entries`;
--   * every entry declares `topic` + `epistemic_status`
--     (`confirmed | belief | suspicion`) and exactly one content mode:
--       - a reusable fact reference: `fact_id` (non-blank string), which
--         structurally forbids `value` and `visibility` because reader exposure
--         is inherited from the referenced fact at read time and is never copied
--         into the knower record;
--       - or a concise local assertion: `value` (plain scalar string/number/
--         boolean) + `visibility` (`meta | non_meta`), because the assertion
--         itself is the underlying information;
--     optional `note` / `source` are non-blank knower-local annotations;
--   * duplicate exact entries and duplicate topics within one record fail
--     closed (a repeated topic is a contradiction, not two independent facts);
--   * one authoritative record per knower; duplicate records for one entity are
--     an ambiguity and fail closed.
--   EV2-14 semantics are consumed, not redesigned. No per-entry knowledge
--   identity, propagation, secret machinery or second truth system is modelled.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * the asserted controller is the ONLY current controller of the target
--     knower, and it must match authoritative PUBLISHED Run truth;
--   * under a MAINRUN assertion the knower must currently be unclaimed by any
--     published Run; under a RUN # assertion the knower must currently be
--     controlled by exactly that RUN #;
--   * a parked played Run that still claims the knower, two Runs claiming one
--     knower, a malformed or duplicated published Run batch, and a duplicated
--     authoritative Run identity all fail closed rather than falling through to
--     MAINRUN;
--   * there is no stored controller authority: a former/stale controller write
--     fails closed because published Run truth no longer grants it authority;
--   * non-mutable knowers (location/faction/party/item) can never be claimed by
--     a published Run, so MAINRUN is their controller and a Run assertion for
--     them fails closed.
--
-- SAME-SAVE COMPATIBILITY (through the existing Patch 1B contract):
--   * knowledge mutation fails closed when this save has already staged a
--     different `runs` batch, because controller authority is proven against
--     PUBLISHED Run truth and a same-save ownership handoff would make it stale;
--   * once this save has staged a knowledge mutation every Run-ownership-writing
--     doorway is refused (generic `runs` stage/delete and the dedicated RT04
--     `reconcile_run_resolution`), so a former/stale controller can never
--     publish knowledge through a same-save ownership handoff.
--   Closure keys on the explicit knowledge-staging operation fact, not on final
--   value equality, and the marker is bound to the save's own database-minted
--   lock token so it never leaks into a later save.
--
-- HANDOFF LAW:
--   Knowledge is attached to the knower, not to the Run. Changing Run ownership
--   (RUN -> MAINRUN, MAINRUN -> RUN or RUN A -> RUN B) changes only the
--   controller; the entity's knowledge record remains attached to the same
--   entity and is never copied to any other entity or party member.

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
      'POST-EV2-3 migration refused: resolve the active campaign save before installing the owner-local knowledge route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Bounded EV2-14 knowledge entry validation + canonicalization (internal).
--    Exactly one content mode: a fact reference (`fact_id`, which forbids
--    `value` and `visibility`) or a local assertion (`value` + `visibility`).
--    `topic` and `epistemic_status` are always required; optional `note` /
--    `source` must be non-blank when present.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_knowledge_entry(
  p_entry jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_es text;
  v_value jsonb;
  v_vis text;
  v_out jsonb;
begin
  if p_entry is null or jsonb_typeof(p_entry) is distinct from 'object' then
    raise exception 'knowledge entry must be a JSON object';
  end if;
  if (p_entry - 'topic' - 'epistemic_status' - 'fact_id' - 'value'
        - 'visibility' - 'note' - 'source') <> '{}'::jsonb then
    raise exception
      'knowledge entry contains fields outside the EV2-14 contract (topic, epistemic_status, fact_id, value, visibility, note, source)';
  end if;
  if not (p_entry ?& array['topic', 'epistemic_status']) then
    raise exception 'knowledge entry requires topic and epistemic_status';
  end if;
  if jsonb_typeof(p_entry -> 'topic') is distinct from 'string'
     or (p_entry ->> 'topic') !~ '\S' then
    raise exception 'knowledge entry topic must be a non-blank JSON string';
  end if;
  if jsonb_typeof(p_entry -> 'epistemic_status') is distinct from 'string' then
    raise exception
      'knowledge entry epistemic_status must be a JSON string of confirmed, belief or suspicion';
  end if;
  v_es := p_entry ->> 'epistemic_status';
  if v_es not in ('confirmed', 'belief', 'suspicion') then
    raise exception
      'knowledge entry epistemic_status must be confirmed, belief or suspicion';
  end if;
  if p_entry ? 'note'
     and (jsonb_typeof(p_entry -> 'note') is distinct from 'string'
          or (p_entry ->> 'note') !~ '\S') then
    raise exception 'knowledge entry note must be a non-blank JSON string';
  end if;
  if p_entry ? 'source'
     and (jsonb_typeof(p_entry -> 'source') is distinct from 'string'
          or (p_entry ->> 'source') !~ '\S') then
    raise exception 'knowledge entry source must be a non-blank JSON string';
  end if;

  if p_entry ? 'fact_id' then
    -- Reusable fact reference: reader exposure is inherited from the referenced
    -- fact at read time, so a copied `visibility` is structurally forbidden and
    -- a `value` would be a second, competing content mode.
    if jsonb_typeof(p_entry -> 'fact_id') is distinct from 'string'
       or (p_entry ->> 'fact_id') !~ '\S' then
      raise exception 'knowledge entry fact_id must be a non-blank JSON string';
    end if;
    if p_entry ? 'value' then
      raise exception
        'a fact-reference knowledge entry must not carry a value';
    end if;
    if p_entry ? 'visibility' then
      raise exception
        'a fact-reference knowledge entry must not carry a visibility; reader exposure is inherited from the referenced fact';
    end if;
    v_out := jsonb_build_object(
      'topic', p_entry -> 'topic',
      'epistemic_status', p_entry -> 'epistemic_status',
      'fact_id', p_entry -> 'fact_id'
    );
  else
    -- Concise local assertion: the assertion itself is the underlying
    -- information, so its own visibility is required.
    if not (p_entry ? 'value') then
      raise exception 'a local-assertion knowledge entry requires a value';
    end if;
    v_value := p_entry -> 'value';
    if jsonb_typeof(v_value) not in ('string', 'number', 'boolean') then
      raise exception
        'knowledge entry value must be a plain scalar (string, number or boolean)';
    end if;
    if not (p_entry ? 'visibility') then
      raise exception 'a local-assertion knowledge entry requires a visibility';
    end if;
    if jsonb_typeof(p_entry -> 'visibility') is distinct from 'string' then
      raise exception
        'knowledge entry visibility must be a JSON string of meta or non_meta';
    end if;
    v_vis := p_entry ->> 'visibility';
    if v_vis not in ('meta', 'non_meta') then
      raise exception 'knowledge entry visibility must be meta or non_meta';
    end if;
    v_out := jsonb_build_object(
      'topic', p_entry -> 'topic',
      'epistemic_status', p_entry -> 'epistemic_status',
      'value', v_value,
      'visibility', v_vis
    );
  end if;

  if p_entry ? 'note' then
    v_out := v_out || jsonb_build_object('note', p_entry -> 'note');
  end if;
  if p_entry ? 'source' then
    v_out := v_out || jsonb_build_object('source', p_entry -> 'source');
  end if;
  return v_out;
end;
$$;

revoke all on function public._rhc_normalize_knowledge_entry(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Bounded EV2-14 knowledge body validation + canonicalization (internal).
--    The body is the record minus `entity_id`: `status` plus `entries` only when
--    known. Unknown stays Unknown: no entry is invented and belief/suspicion is
--    never promoted. Duplicate exact entries and duplicate topics within one
--    record fail closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_knowledge_body(
  p_body jsonb
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
  v_norm jsonb;
  v_topic text;
  v_topics text[] := '{}';
  v_out jsonb;
  v_count integer;
  v_distinct integer;
begin
  if p_body is null or jsonb_typeof(p_body) is distinct from 'object' then
    raise exception 'knowledge record must be a JSON object';
  end if;
  if (p_body - 'status' - 'entries') <> '{}'::jsonb then
    raise exception
      'knowledge record contains fields outside the EV2-14 contract (entity_id, status, entries)';
  end if;
  if not (p_body ? 'status') then
    raise exception 'knowledge record requires a status';
  end if;
  if jsonb_typeof(p_body -> 'status') is distinct from 'string' then
    raise exception
      'knowledge record status must be a JSON string of known, unknown or not_applicable';
  end if;
  v_status := p_body ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception
      'knowledge record status must be known, unknown or not_applicable';
  end if;

  if v_status = 'known' then
    if not (p_body ? 'entries') then
      raise exception 'a known knowledge record requires an entries array';
    end if;
    v_entries := p_body -> 'entries';
    if jsonb_typeof(v_entries) is distinct from 'array' then
      raise exception 'known knowledge record entries must be a JSON array';
    end if;
    if jsonb_array_length(v_entries) = 0 then
      raise exception 'a known knowledge record requires at least one entry';
    end if;

    -- Exact whole-entry duplicates (the schema's uniqueItems) fail closed.
    select count(*), count(distinct e)
      into v_count, v_distinct
      from jsonb_array_elements(v_entries) e;
    if v_distinct < v_count then
      raise exception
        'knowledge record entries must be unique; a duplicate entry is a double-count';
    end if;

    v_out := '[]'::jsonb;
    for v_entry in select e from jsonb_array_elements(v_entries) e loop
      v_norm := public._rhc_normalize_knowledge_entry(v_entry);
      v_topic := v_norm ->> 'topic';
      -- A repeated topic is a contradiction (the same knower cannot hold two
      -- independent statements under one routing label), not two facts.
      if array_position(v_topics, v_topic) is not null then
        raise exception
          'knowledge record entries must not repeat a topic; duplicate topic % is ambiguous',
          v_topic;
      end if;
      v_topics := array_append(v_topics, v_topic);
      v_out := v_out || jsonb_build_array(v_norm);
    end loop;

    return jsonb_build_object('status', v_status, 'entries', v_out);
  end if;

  -- unknown / not_applicable: entries are forbidden, not merely empty.
  if p_body ? 'entries' then
    raise exception
      'an unknown or not_applicable knowledge record must not carry entries';
  end if;
  return jsonb_build_object('status', v_status);
end;
$$;

revoke all on function public._rhc_normalize_knowledge_body(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Full EV2-14 knowledge record validation + canonicalization (internal).
--    Binds the knower identity (the full EV2-14 identity space) to the bounded
--    body. A missing/blank/out-of-space `entity_id` fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_knowledge_record(
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
    raise exception 'knowledge record must be a JSON object';
  end if;
  if not (p_record ? 'entity_id') then
    raise exception 'knowledge record requires entity_id';
  end if;
  if jsonb_typeof(p_record -> 'entity_id') is distinct from 'string' then
    raise exception 'knowledge record entity_id must be a JSON string identity';
  end if;
  v_entity := p_record ->> 'entity_id';
  if not public._rhc_full_id_match(
    v_entity,
    '^(character|location|faction|party|creature|item):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'knowledge record entity_id must be a character:, location:, faction:, party:, creature: or item: identity';
  end if;

  v_body := public._rhc_normalize_knowledge_body(p_record - 'entity_id');
  return jsonb_build_object('entity_id', v_entity) || v_body;
end;
$$;

revoke all on function public._rhc_normalize_knowledge_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Whole-collection validation (internal). The complete candidate
--    `entity_knowledge` namespace is proven before it can be staged: a JSON
--    array of canonical records with exactly one authoritative record per
--    knower. A duplicate record for one knower is an ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_knowledge_collection(
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
    raise exception 'entity_knowledge namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_knowledge_record(v_entry);
    v_entity := v_norm ->> 'entity_id';
    if array_position(v_seen, v_entity) is not null then
      raise exception
        'entity_knowledge namespace holds duplicate records for %; exactly one authoritative knowledge record per knower is required',
        v_entity;
    end if;
    v_seen := array_append(v_seen, v_entity);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_knowledge_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. Explicit same-save knowledge-staging marker (internal). Closure must key
--    on the operation fact, not on final JSON equality: an absolute target can
--    be re-staged to a value that already equals published reality (a replay),
--    or mutated away and back, and in both cases the final value would look
--    unchanged even though a successful staging operation occurred. The save
--    locator therefore records the lock_token that staged knowledge. The
--    database mints a fresh lock_token at every BEGIN and clears stale candidate
--    rows, so the marker can only match the CURRENT save's token and never leaks
--    into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists entity_knowledge_staged_lock_token text;

create or replace function public._rhc_entity_knowledge_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.entity_knowledge_staged_lock_token is not null
            and cr.entity_knowledge_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_entity_knowledge_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.entity_knowledge_staged_lock_token is
  'POST-EV2-3 internal operation fact: the lock_token of the save that most recently staged a successful owner-local knowledge mutation. Matched against the active lock_token so the same-save knowledge/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 6. The validated atomic owner-local knowledge mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_entity_knowledge(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "entity_id": "<character|location|faction|party|creature|item>:<slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "knowledge": { "status": "known" | "unknown" | "not_applicable",
--                       "entries": [ ... ] }
--      }
--
--    `entity_id`, `controller` and `knowledge` are required. `entity_id` plus
--    `knowledge` form the absolute EV2-14 record. The target is ABSOLUTE, not a
--    delta, so replaying one logical update is idempotent and cannot drift.
--    Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth for
--        the target knower (malformed/duplicated batch, parked claiming Run and
--        two-Run claim all fail closed rather than falling through to MAINRUN);
--      * a same-save staged `runs` change (ownership handoff) fails closed,
--        because published Run truth would no longer describe the controller
--        this save would publish -> no former/stale-controller overwrite;
--      * the complete existing candidate `entity_knowledge` namespace is
--        validated (one record per knower, every record EV2-14-valid) before
--        anything is staged, so malformed or duplicate unrelated truth fails
--        closed and is never canonicalized;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
--
--    This route does NOT change Run ownership, does not create a second
--    controller/ownership ledger or knowledge store, and never propagates
--    knowledge to any other entity.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_entity_knowledge(
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

  -- Same-save compatibility (POST-EV2-1 Patch 1B, extended by POST-EV2-3):
  -- knowledge authority is proven against PUBLISHED Run truth. If this save has
  -- already staged a different `runs` batch, published truth no longer describes
  -- the Run ownership this save will publish, so a former controller could stage
  -- a stale knowledge update. Fail closed; Run-ownership changes and knowledge
  -- mutations belong in separate saves.
  perform public._rhc_require_same_save_compatibility(
    'mutate_entity_knowledge', r.staging_generation, r.published_generation);

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'knowledge mutation request must be a JSON object';
  end if;
  if not p_request ?& array['entity_id', 'controller', 'knowledge'] then
    raise exception
      'knowledge mutation request requires entity_id, controller and knowledge';
  end if;
  if (p_request - 'entity_id' - 'controller' - 'knowledge') <> '{}'::jsonb then
    raise exception
      'knowledge mutation request contains fields outside the EV2-14 runtime contract';
  end if;

  -- entity_id: the knower. It is never inferred from prose.
  if jsonb_typeof(p_request -> 'entity_id') is distinct from 'string' then
    raise exception
      'knowledge mutation entity_id must be a JSON string identity';
  end if;
  v_entity := p_request ->> 'entity_id';
  if not public._rhc_full_id_match(
    v_entity,
    '^(character|location|faction|party|creature|item):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'knowledge mutation entity_id must be a character:, location:, faction:, party:, creature: or item: identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch.
  -- `kind: null` (or an array/object) would make `v_kind NOT IN (...)` evaluate
  -- to SQL NULL under three-valued logic, the guard would not fire, and the
  -- later `v_kind = 'run'` test would also be NULL, silently falling through to
  -- the MAINRUN branch. Require an explicit JSON string first so null, missing,
  -- non-string and unknown values all fail closed. (Identical law to EV2-10/11/13.)
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
        'no published Run currently controls %; a Run controller cannot assert owner-local knowledge authority',
        v_entity;
    end if;
    if v_current is distinct from v_run_id then
      raise exception
        'published Run % currently controls %; asserted Run % does not own it, so this knowledge mutation crosses controllers and fails closed',
        v_current, v_entity, v_run_id;
    end if;
  else
    if v_current is not null then
      raise exception
        'published Run % currently controls %; MAINRUN may not mutate that entity''s knowledge (route the cross-controller handoff through the existing reconciliation boundary)',
        v_current, v_entity;
    end if;
  end if;

  -- Validate + canonicalize the absolute bounded knowledge target.
  if not (p_request ? 'knowledge') then
    raise exception 'knowledge mutation requires a knowledge object';
  end if;
  v_body := public._rhc_normalize_knowledge_body(p_request -> 'knowledge');
  v_record := jsonb_build_object('entity_id', v_entity) || v_body;

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope. The candidate begins as a copy of published
  -- reality via BEGIN, so this only fills the never-yet-created case.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'entity_knowledge';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'entity_knowledge';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'entity_knowledge namespace is unreadable; mutation fails closed';
  end if;

  -- Validate the EXISTING namespace before anything is staged. Malformed or
  -- duplicate unrelated truth fails closed and is never canonicalized by
  -- overwrite.
  perform public._rhc_validate_knowledge_collection(v_collection);

  -- Replace the knower's single record, or append it when the knower is new.
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
      'entity_knowledge namespace already holds duplicate records for %; failing closed',
      v_entity;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_knowledge_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'entity_knowledge', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact: a successful knowledge staging happened in this
  -- save, independent of whether the staged value differs from published
  -- reality. This closes every Run-ownership-writing doorway for the rest of the
  -- save, even for a value-equal replay.
  update public.campaign_runtime
     set entity_knowledge_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'knowledge_mutation_version', 1,
    'entity_id', v_entity,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'knowledge', v_record
  );
end;
$$;

revoke all on function public.mutate_entity_knowledge(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_entity_knowledge(text, jsonb) to service_role;

comment on function public.mutate_entity_knowledge(text, jsonb) is
  'POST-EV2-3: the only validated atomic owner-local knowledge mutation route, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion (controller.kind must be a JSON string exactly mainrun or run; null/missing/non-string/unknown fails closed before any authority branch), proves the asserted MAINRUN-or-one-RUN controller against authoritative published Run truth for the target knower (fail-closed on a malformed published runs batch, a parked claiming Run, a duplicated authoritative Run identity, and a same-save staged runs change), validates + canonicalizes one absolute EV2-14 knowledge record (status known/unknown/not_applicable; entries only when known; each entry exactly one content mode with a plain-scalar local assertion or a fact reference that forbids a copied visibility; duplicate topics/entries fail closed), then stages the knower''s single record into the engine-owned entity_knowledge namespace and records the knowledge-staging operation fact that closes every Run-ownership-writing doorway for the rest of the save. Absolute target, replay-safe, all-or-nothing through the existing gateway. Owns no controller authority of its own: published Run truth is the only controller source, no Run ownership is changed here, and knowledge is never propagated to any other entity.';

-- ---------------------------------------------------------------------------
-- 7. POST-EV2-1 Patch 1A: extend the server-owned domain policy registry with
--    the new dedicated `entity_knowledge` domain. Every existing branch and
--    exact fail-closed message is preserved verbatim; only the new domain is
--    added. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--    routes consult this registry, so they fail closed for `entity_knowledge`
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
  'POST-EV2-1 Patch 1A (extended by POST-EV2-3): the single server-owned, machine-readable runtime state key policy registry. Consumes only the key and returns admission (generic | dedicated | forbidden), the exhaustive array `dedicated_routes` of every legal writer for engine-owned keys, and the exact fail-closed messages. `generic` is the HWB-02 ordinary-save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs) and exposes `dedicated_routes=[]`. `dedicated` exposes every legal writer, never a single route that could imply a complete set: campaign_clock=[stage_campaign_clock], run_reconciliations=[reconcile_run_resolution], inventory=[mutate_owner_inventory], item_custody=[mutate_item_custody, admit_item_identity], item_admissions=[admit_item_identity], entity_state=[mutate_entity_state], applied_statuses=[mutate_applied_status], entity_knowledge=[mutate_entity_knowledge]. Unknown/undeclared keys are `forbidden` and expose `dedicated_routes=[]`. No caller-supplied policy, no table, no mutable store: the decision cannot become caller-controlled authority. Internal-only.';

-- ---------------------------------------------------------------------------
-- 8. POST-EV2-1 Patch 1B: extend the same-save compatibility policy with the
--    new `entity_knowledge` edges. The `mutate_entity_knowledge` operation is
--    blocked by a same-save `runs` change; the Run-ownership-writing operations
--    (`stage_runs`, `delete_runs`, `reconcile_runs`) gain a trailing
--    `entity_knowledge` edge. Every existing edge and exact message is preserved
--    verbatim.
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
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'this save has already staged an owner-local knowledge mutation; a Run reconciliation would change Run ownership after knowledge controller authority was proven, so reconciliation fails closed (change Run ownership and knowledge in separate saves)')
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
  'POST-EV2-1 Patch 1B (extended by POST-EV2-3): the single server-owned, machine-readable same-save compatibility policy. For each legal mutation operation it declares, in deterministic order, every audited cross-domain incompatibility as {blocked_by, detector, error}, where `error` is the exact fail-closed message that operation must raise. POST-EV2-3 adds the `mutate_entity_knowledge` operation (blocked by a same-save runs change) and a trailing `entity_knowledge` edge on stage_runs/delete_runs/reconcile_runs. Consumes only the operation name; reads no table and selects no mutable store, so the policy can never be caller-supplied or caller-controlled. Unknown operations report known=false. Internal-only.';

-- ---------------------------------------------------------------------------
-- 9. POST-EV2-1 Patch 1B: extend the compatibility decision with the
--    `knowledge_staged_in_save` detector. Every existing detector and the
--    fail-closed unknown-detector behavior are preserved.
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
  'POST-EV2-1 Patch 1B (extended by POST-EV2-3): the server-owned same-save compatibility decision. Evaluates the declared policy for one operation against the active save''s staging/published generations and returns {operation, domain, known, compatible, blocked_by, error}. It answers only whether already-legal operations may coexist in this save; it never judges a mutation''s own semantic validity. Unknown operations/detectors fail closed. Internal-only; no caller-supplied policy.';

comment on function public._rhc_normalize_knowledge_entry(jsonb) is
  'POST-EV2-3 internal EV2-14 knowledge-entry validation + canonicalization. Requires topic + epistemic_status (confirmed/belief/suspicion) and exactly one content mode: a non-blank fact_id (which structurally forbids value and visibility, because reader exposure is inherited from the referenced fact) or a plain-scalar value + meta/non_meta visibility local assertion. Optional note/source must be non-blank. Internal-only.';
comment on function public._rhc_normalize_knowledge_body(jsonb) is
  'POST-EV2-3 internal EV2-14 knowledge-body validation + canonicalization. Accepts exactly status (known/unknown/not_applicable) and, only when known, a non-empty entries array whose entries are each EV2-14-valid, unique, and do not repeat a topic; unknown/not_applicable forbid entries. Unknown stays Unknown; belief/suspicion is never promoted to world truth. Internal-only.';
comment on function public._rhc_normalize_knowledge_record(jsonb) is
  'POST-EV2-3 internal full EV2-14 knowledge-record validation + canonicalization. Binds a knower identity in the full EV2-14 identity space (character/location/faction/party/creature/item) to a canonical knowledge body; extra fields and identities outside that space fail closed. Internal-only: knowledge payloads are reachable only through the validated mutate_entity_knowledge route.';
comment on function public._rhc_validate_knowledge_collection(jsonb) is
  'POST-EV2-3 internal whole-collection validation. Proves the complete candidate entity_knowledge namespace is a JSON array of canonical EV2-14 records with exactly one authoritative record per knower, rejecting duplicate records. Internal-only.';
comment on function public._rhc_entity_knowledge_staged_in_save() is
  'POST-EV2-3 internal same-save knowledge-staging operation fact. True only when the active save''s lock_token matches the lock_token that most recently staged a successful owner-local knowledge mutation, so closure keys on the staging operation rather than on final value equality (a value-equal replay still trips it) and never leaks into a later save. Internal-only.';