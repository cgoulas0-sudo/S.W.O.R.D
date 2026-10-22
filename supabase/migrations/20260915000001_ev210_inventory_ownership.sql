-- EV2-10 — Owner-local inventory ownership + party stash + owned assets
-- Rolling High Club validated inventory mutation route on the existing RT01 SAVE
-- spine, plus the EV2-10 evolution of the EV2-03 inventory box.
--
-- This migration is NOT a second save engine and NOT an inventory subsystem
-- beside the box. It adds ONE validated, owner-local inventory mutation route
-- that composes with every existing dedicated closure (RT02 `campaign_clock`,
-- RT04 `run_reconciliations`, HWB-02 ordinary-save allowlist) and reuses the
-- existing RT01 begin -> validated stage -> publish -> mirror/confirmation law.
--
-- WHAT this migration changes:
--   1. `public.mutate_owner_inventory(p_lock_token, p_request)` — the ONLY way
--      to stage the engine-owned `inventory` runtime namespace. It runs INSIDE
--      the normal campaign save lifecycle, proves the caller's asserted
--      controller (MAINRUN or exactly one RUN #) against authoritative PUBLISHED
--      Run truth, validates + canonicalizes the owner-local inventory record,
--      and stages the updated owner record on the RT01 spine.
--   2. The generic `stage_campaign_state` / `delete_staged_campaign_state`
--      routes reject the `inventory` key (same closure pattern as
--      `campaign_clock` and `run_reconciliations`), so a caller/model cannot
--      bypass the validated route with a raw generic runtime write. The HWB-02
--      ordinary-save allowlist is preserved unchanged.
--   3. Run-ownership changes and inventory mutations are mutually exclusive
--      within one save. Detection keys on the explicit inventory-staging
--      operation fact, not on final inventory value equality, so a re-staged
--      absolute target that already equals published reality (or a mutation that
--      is later reverted) still closes every Run-writing doorway for the rest of
--      the save: generic `runs` stage/delete and the dedicated RT04
--      `reconcile_run_resolution` route.
--
-- STORAGE ENVELOPE (not semantic ownership):
--   The engine-owned runtime key `inventory` holds a JSON array of EV2-10
--   inventory records, each exactly one owner entity (`entity_id`) with its own
--   `status`, ordinary `entries` and `currency`. The collection key is a storage
--   envelope only: `entity_id`/owner locality remains the semantic owner. There
--   is exactly one record per owner, never one per Run, so inventory is not
--   duplicated per Run indefinitely. Character inventory and Party stash are the
--   same record shape with different owners.
--
-- ENTRY / CURRENCY LAW (mirrors schemas/inventory.schema.json):
--   * an ordinary entry is exactly `name` + `description` + `quantity`;
--   * `name`/`description` are non-blank; `quantity` follows the schema's
--     Draft 2020-12 integer semantics (a mathematically integral number >= 1,
--     so `1` and `1.0` agree) and non-integral values fail;
--   * zero quantity means absence/removal and is never persisted as an entry;
--   * `currency` is structurally separate and accepts exactly cp/sp/ep/gp/pp,
--     each a non-negative integral number (the same integer semantics); zero
--     balances are coherent; omitting `currency` is coherent but an explicit
--     JSON null fails closed;
--   * ordinary entries are unique under JSON numeric equality (schema
--     `uniqueItems`), so `quantity` 1 and 1.0 are the same entry;
--   * no category/taxonomy field and no persistent `item:` identity is created
--     or required. Owned assets (mounts/carts/ships/...) are ordinary entries.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth; invents nothing):
--   * if an authoritative PUBLISHED Run currently claims the owner in its
--     `mutable_owner_entity_ids`, only that RUN # may author the owner's
--     inventory mutation;
--   * if no authoritative published Run currently claims the owner, MAINRUN is
--     the current gameplay controller for inventory mutation;
--   * historical participation, a parked/past Run, or caller self-assertion
--     never grants mutation authority; two Runs claiming one owner fails closed.
--
-- EV2-11 remains the sole current owner for individually tracked unique-item
-- identity/custody. This migration never mints `item:` identity and never infers
-- custody from rarity, magic, price or narrative importance.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02 forward-only install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'EV2-10 migration refused: resolve the active campaign save before installing the inventory ownership route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Owner-local inventory record validation + canonicalization (internal).
--    Validates the approved EV2-10 payload and returns the canonical record with
--    the owner bound into `entity_id`. The route never accepts a caller-supplied
--    entity_id inside the record, so owner locality cannot be contradicted.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_inventory_record(
  p_owner text,
  p_inventory jsonb
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
  v_currency jsonb;
  v_entry jsonb;
  v_name text;
  v_description text;
  v_out_entries jsonb;
  v_canonical jsonb;
  v_seen_entries jsonb := '[]'::jsonb;
  v_out_currency jsonb;
  v_denom text;
  v_denoms text[] := array['cp', 'sp', 'ep', 'gp', 'pp'];
  v_out jsonb;
begin
  if p_inventory is null or jsonb_typeof(p_inventory) is distinct from 'object' then
    raise exception 'inventory must be a JSON object';
  end if;
  if (p_inventory - 'status' - 'entries' - 'currency') <> '{}'::jsonb then
    raise exception 'inventory contains fields outside the EV2-10 contract (status, entries, currency)';
  end if;

  v_status := p_inventory ->> 'status';
  if v_status is null or v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception 'inventory status must be known, unknown or not_applicable';
  end if;

  if v_status = 'known' then
    if not (p_inventory ? 'entries') then
      raise exception 'known inventory requires entries (use [] for a known-empty inventory)';
    end if;
    v_entries := p_inventory -> 'entries';
    if jsonb_typeof(v_entries) is distinct from 'array' then
      raise exception 'inventory entries must be a JSON array';
    end if;

    v_out_entries := '[]'::jsonb;
    for v_entry in select e from jsonb_array_elements(v_entries) e loop
      if jsonb_typeof(v_entry) is distinct from 'object' then
        raise exception 'inventory entry must be a JSON object';
      end if;
      if (v_entry - 'name' - 'description' - 'quantity') <> '{}'::jsonb then
        raise exception 'inventory entry contains fields outside the EV2-10 contract (name, description, quantity)';
      end if;

      v_name := v_entry ->> 'name';
      if jsonb_typeof(v_entry -> 'name') is distinct from 'string' then
        raise exception 'inventory entry name must be a JSON string';
      end if;
      if v_name !~ '\S' then
        raise exception 'inventory entry name must be a non-blank string';
      end if;
      v_description := v_entry ->> 'description';
      if jsonb_typeof(v_entry -> 'description') is distinct from 'string' then
        raise exception 'inventory entry description must be a JSON string';
      end if;
      if v_description !~ '\S' then
        raise exception 'inventory entry description must be a non-blank string';
      end if;

      -- Quantity is explicit and follows the owning JSON schema's integer
      -- semantics (Draft 2020-12 `type: integer` accepts any mathematically
      -- integral number, so `1` and `1.0` are the same quantity). Zero (absence),
      -- negative, non-integral, quoted, boolean, array, object and missing
      -- quantities all fail closed here.
      if jsonb_typeof(v_entry -> 'quantity') is distinct from 'number'
         or (v_entry ->> 'quantity')::numeric < 1
         or (v_entry ->> 'quantity')::numeric
            is distinct from trunc((v_entry ->> 'quantity')::numeric) then
        raise exception 'inventory entry quantity must be an explicit integer >= 1';
      end if;

      v_canonical := jsonb_build_object(
        'name', v_name,
        'description', v_description,
        'quantity', v_entry -> 'quantity'
      );

      -- Mirror the schema's `uniqueItems`: two ordinary entries that are equal
      -- as `{ name, description, quantity }` are a double-count, not two facts.
      -- Comparison is canonical JSONB equality, matching Draft 2020-12 item
      -- equality, so numerically equal quantities spellings (`1` vs `1.0`) are
      -- the same entry rather than two independent ones.
      if v_seen_entries @> jsonb_build_array(v_canonical) then
        raise exception 'inventory entries must be unique; duplicate ordinary entry % is rejected (uniqueItems)', v_name;
      end if;
      v_seen_entries := v_seen_entries || jsonb_build_array(v_canonical);

      v_out_entries := v_out_entries || v_canonical;
    end loop;

    v_currency := p_inventory -> 'currency';
    if v_currency is null then
      -- Omitted currency is coherent: the schema does not require the property.
      v_out_currency := null;
    elsif jsonb_typeof(v_currency) = 'null' then
      -- An explicit JSON null is NOT the same as an omitted property: when
      -- present, the schema requires `currency` to be an object, so fail closed
      -- rather than silently dropping the caller's explicit null.
      raise exception 'inventory currency must be a JSON object; explicit null is not an omitted currency';
    else
      if jsonb_typeof(v_currency) is distinct from 'object' then
        raise exception 'inventory currency must be a JSON object';
      end if;
      if exists (
        select 1 from jsonb_object_keys(v_currency) k where k <> all(v_denoms)
      ) then
        raise exception 'inventory currency accepts exactly the D&D denominations cp, sp, ep, gp, pp';
      end if;
      v_out_currency := '{}'::jsonb;
      foreach v_denom in array v_denoms loop
        if v_currency ? v_denom then
          -- Same integer semantics as the owning schema: a non-negative
          -- mathematically integral number, so `0` and `0.0` agree while
          -- negative/non-integral/quoted balances fail closed.
          if jsonb_typeof(v_currency -> v_denom) is distinct from 'number'
             or (v_currency ->> v_denom)::numeric < 0
             or (v_currency ->> v_denom)::numeric
                is distinct from trunc((v_currency ->> v_denom)::numeric) then
            raise exception 'inventory currency % must be a non-negative integer', v_denom;
          end if;
          v_out_currency := v_out_currency
            || jsonb_build_object(v_denom, v_currency -> v_denom);
        end if;
      end loop;
    end if;

    v_out := jsonb_build_object('entity_id', p_owner, 'status', v_status, 'entries', v_out_entries);
    if v_out_currency is not null then
      v_out := v_out || jsonb_build_object('currency', v_out_currency);
    end if;
  else
    if (p_inventory ? 'entries') or (p_inventory ? 'currency') then
      raise exception 'inventory entries and currency are forbidden unless status is known';
    end if;
    v_out := jsonb_build_object('entity_id', p_owner, 'status', v_status);
  end if;

  return v_out;
end;
$$;

revoke all on function public._rhc_normalize_inventory_record(text, jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Whole-collection validation (internal). The complete candidate `inventory`
--    namespace is proven before it can be staged: a JSON array of canonical
--    EV2-10 records with unique owner identities, every record re-validated.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_inventory_collection(p_inventory jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entry jsonb;
  v_owner text;
  v_seen text[] := '{}';
begin
  if p_inventory is null or jsonb_typeof(p_inventory) is distinct from 'array' then
    raise exception 'inventory namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_inventory) e loop
    if jsonb_typeof(v_entry) is distinct from 'object' then
      raise exception 'inventory namespace entries must be JSON objects';
    end if;
    v_owner := v_entry ->> 'entity_id';
    if not public._rhc_full_id_match(
      v_owner,
      '^(character|location|faction|party|creature|item):[a-z0-9]+(-[a-z0-9]+)*$') then
      raise exception 'inventory namespace record has an invalid owner entity_id';
    end if;
    if array_position(v_seen, v_owner) is not null then
      raise exception 'inventory namespace holds duplicate records for owner %; failing closed', v_owner;
    end if;
    v_seen := array_append(v_seen, v_owner);
    perform public._rhc_normalize_inventory_record(v_owner, v_entry - 'entity_id');
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_inventory_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2b. Same-save `runs` change detector (internal). A save's staging generation
--     starts as a byte copy of published reality, so a key this save never
--     touched is identical in both generations. A staged `runs` value that
--     differs from published means this save is changing Run ownership before it
--     publishes — used so an inventory mutation cannot be proven against a
--     controller that same save is about to replace (or be bypassed by a new
--     controller), because inventory authority is proven against PUBLISHED Run
--     truth. SQL NULL and a JSON-null value are distinct here, which is correct:
--     a value this save never created is not the same as one it did. Inventory
--     staging itself is NOT detected here (see 2c): a re-staged absolute target
--     can legitimately equal published reality.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_state_key_changed_in_save(
  p_key text,
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
begin
  select csg.value into v_stg
    from public.campaign_state_generations csg
   where csg.generation = p_staging_generation
     and csg.key = p_key;
  select csg.value into v_pub
    from public.campaign_state_generations csg
   where csg.generation = p_published_generation
     and csg.key = p_key;
  return v_stg is distinct from v_pub;
end;
$$;

revoke all on function public._rhc_state_key_changed_in_save(text, bigint, bigint)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2c. Explicit same-save inventory-staging marker (internal). Closure must key
--     on the operation fact, not on final JSON equality: an absolute target can
--     be re-staged to a value that already equals published reality (a replay),
--     or mutated away and back, and in both cases the final value would look
--     unchanged even though a successful inventory staging operation occurred.
--     The save locator therefore records the lock_token that staged inventory.
--     The database mints a fresh lock_token at every BEGIN and clears stale
--     candidate rows, so the marker can only match the CURRENT save's token and
--     can never be inherited by a later save merely by copying published state.
--     Internal-only: readable solely through the guarded routes.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists inventory_staged_lock_token text;

create or replace function public._rhc_inventory_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.inventory_staged_lock_token is not null
            and cr.inventory_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_inventory_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.inventory_staged_lock_token is
  'EV2-10 internal operation fact: the lock_token of the save that most recently staged a successful inventory mutation. Matched against the active lock_token so the same-save inventory/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 3. Current controller lookup (internal). Reads ONLY the authoritative
--    PUBLISHED `runs` batch: the run_id currently claiming the owner's mutable
--    ownership, or NULL when no published Run claims it (MAINRUN). Duplicate
--    claims for one owner fail closed. Historical participation, a parked or
--    past Run's continued existence, and caller prose are never authority.
--    A malformed published batch (non-object entry, non-string run_id, or an
--    EV2-08-invalid record) fails closed rather than being skipped, so a
--    possible claim can never silently fall through to MAINRUN. A parked Run
--    that still claims the owner fails closed too: it is not a current
--    controller, and its claim means MAINRUN is not provably the controller.
--    A duplicated authoritative Run identity fails closed as well: if two valid
--    published records share one `run_id`, Run authority is ambiguous even when
--    only one of them lists the requested owner, so no controller is granted
--    (the canonical RT03 reader refuses a duplicated identity for the same
--    reason).
-- ---------------------------------------------------------------------------
create or replace function public._rhc_inventory_controller_for_owner(p_owner text)
returns text
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_runs jsonb;
  v_entry jsonb;
  v_owners jsonb;
  v_id text;
  v_seen_ids text[] := '{}';
  v_claim text := null;
  v_found integer := 0;
begin
  select csg.value into v_runs
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'runs'
   where cr.id = 1;

  if v_runs is null then
    return null;
  end if;
  if jsonb_typeof(v_runs) is distinct from 'array' then
    raise exception 'published runs state is unreadable; inventory controller cannot be proven';
  end if;

  for v_entry in select e from jsonb_array_elements(v_runs) e loop
    -- The published `runs` batch is authoritative Run truth. A malformed entry
    -- must never be silently skipped: if it might carry a mutable-ownership claim,
    -- skipping the possible claim could return NULL and unsafely authorize
    -- MAINRUN. Reject the unreadable batch instead of guessing.
    if jsonb_typeof(v_entry) is distinct from 'object' then
      raise exception 'published runs state contains a non-object entry; inventory controller cannot be proven';
    end if;
    if jsonb_typeof(v_entry -> 'run_id') is distinct from 'string' then
      raise exception 'published runs state contains an entry without a string run_id; inventory controller cannot be proven';
    end if;
    v_id := v_entry ->> 'run_id';

    -- Duplicate authoritative identity (round-3 P1): if two valid records share
    -- one run_id, the batch cannot be trusted to name one controller, even when
    -- only one of the duplicates lists this owner. Fail closed before granting
    -- any authority, exactly like the canonical RT03 read refuses a duplicated
    -- identity. Without this, a duplicated record that lists the owner alongside
    -- a duplicate that does not could still resolve to a single claim.
    if array_position(v_seen_ids, v_id) is not null then
      raise exception
        'published runs state contains duplicate authoritative Run identity %; inventory controller is ambiguous',
        v_id;
    end if;
    v_seen_ids := array_append(v_seen_ids, v_id);

    -- Every entry must itself be a valid EV2-08 Run record, so execution_mode and
    -- control_state can be trusted when deciding inventory authority.
    perform public._rhc_validate_run_record(v_entry);

    v_owners := v_entry -> 'mutable_owner_entity_ids';
    if jsonb_typeof(v_owners) is distinct from 'array' then
      raise exception
        'published Run % has an unreadable mutable_owner_entity_ids; inventory controller cannot be proven',
        v_entry ->> 'run_id';
    end if;

    if v_owners ? p_owner then
      v_found := v_found + 1;
      if v_found > 1 then
        raise exception
          'mutable entity % is claimed by more than one published Run; inventory controller is ambiguous',
          p_owner;
      end if;
      -- A parked played Run is not a current gameplay controller. It must not be
      -- granted authority, and the mere existence of its claim means MAINRUN is
      -- not provably the controller either, so the proof fails closed instead of
      -- falling through to MAINRUN.
      if (v_entry ->> 'execution_mode') = 'played'
         and (v_entry ->> 'control_state') = 'parked' then
        raise exception
          'published Run % is parked and cannot control inventory for %; inventory controller cannot be proven',
          v_entry ->> 'run_id', p_owner;
      end if;
      v_claim := v_entry ->> 'run_id';
    end if;
  end loop;

  return v_claim;
end;
$$;

revoke all on function public._rhc_inventory_controller_for_owner(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. The validated owner-local inventory mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_owner_inventory(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "owner_entity_id": "<character|party>:<slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "inventory": { "status": ..., "entries": [...], "currency": {...} }
--      }
--
--    The target is ABSOLUTE, not a delta, so replaying one logical update
--    re-stages the same record and cannot drift. Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth;
--      * a same-save staged `runs` change (ownership handoff) fails closed,
--        because published Run truth would no longer describe the controller
--        this save would publish -> no former/stale-controller overwrite;
--      * the complete candidate inventory namespace is validated (unique owners,
--        every record EV2-10-valid) before anything is staged;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_owner_inventory(
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
  v_owner text;
  v_controller jsonb;
  v_kind text;
  v_run_id text;
  v_current text;
  v_record jsonb;
  v_inventory jsonb;
  v_new_inventory jsonb;
  v_matches integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save controller integrity: inventory authority is proven against
  -- PUBLISHED Run truth. If this save has already staged a different `runs`
  -- batch, published truth no longer describes the Run ownership this save will
  -- publish, so a former controller could stage a stale inventory update. Fail
  -- closed; Run-ownership changes and inventory mutations belong in separate
  -- saves. (The staging generation starts as a copy of published reality, so an
  -- untouched runs batch compares equal and does not trip this guard.)
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; inventory controller cannot be proven against published Run truth, so inventory mutation fails closed (change Run ownership and inventory in separate saves)';
  end if;

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'inventory mutation request must be a JSON object';
  end if;
  if not p_request ?& array['owner_entity_id', 'controller', 'inventory'] then
    raise exception 'inventory mutation request requires owner_entity_id, controller and inventory';
  end if;
  if (p_request - 'owner_entity_id' - 'controller' - 'inventory') <> '{}'::jsonb then
    raise exception 'inventory mutation request contains fields outside the EV2-10 contract';
  end if;

  -- Owner locality: EV2-10 mutation is for a Character inventory or a Party
  -- stash. The record's own entity_id is never caller-supplied; it is bound here.
  v_owner := p_request ->> 'owner_entity_id';
  if not public._rhc_full_id_match(v_owner, '^(character|party):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'owner_entity_id must be a character: or party: identity';
  end if;

  v_controller := p_request -> 'controller';
  if v_controller is null or jsonb_typeof(v_controller) is distinct from 'object' then
    raise exception 'controller must be a JSON object';
  end if;
  if not (v_controller ? 'kind') then
    raise exception 'controller requires a kind';
  end if;
  -- Controller-kind type/enum validation happens BEFORE any authority branch.
  -- `kind: null` (or an array/object) would make `v_kind NOT IN (...)` evaluate
  -- to SQL NULL under three-valued logic, the guard would not fire, and the
  -- later `v_kind = 'run'` test would also be NULL, silently falling through to
  -- the MAINRUN branch. Require an explicit JSON string first so null, missing,
  -- non-string and unknown values all fail closed.
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

  -- Authoritative controller: published Run truth only.
  v_current := public._rhc_inventory_controller_for_owner(v_owner);
  if v_kind = 'run' then
    if v_current is null then
      raise exception
        'no published Run currently controls %; a Run controller cannot assert inventory authority',
        v_owner;
    end if;
    if v_current is distinct from v_run_id then
      raise exception
        'published Run % currently controls %; asserted Run % does not own it and fails closed',
        v_current, v_owner, v_run_id;
    end if;
  else
    if v_current is not null then
      raise exception
        'published Run % currently controls %; MAINRUN may not mutate an owner under a Run controller',
        v_current, v_owner;
    end if;
  end if;

  -- Validate + canonicalize the owner-local record.
  v_record := public._rhc_normalize_inventory_record(v_owner, p_request -> 'inventory');

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope. The candidate begins as a copy of published
  -- reality via BEGIN, so this only fills the never-yet-created case.
  select csg.value into v_inventory
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'inventory';
  if v_inventory is null then
    select csg.value into v_inventory
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'inventory';
  end if;
  if v_inventory is null then
    v_inventory := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_inventory) is distinct from 'array' then
    raise exception 'inventory namespace is unreadable; mutation fails closed';
  end if;

  -- Replace the owner's record, or append it when the owner is new.
  select
    coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'entity_id') = v_owner
           then v_record else e end
    ), '[]'::jsonb),
    count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'entity_id') = v_owner
    )
    into v_new_inventory, v_matches
    from jsonb_array_elements(v_inventory) e;

  if v_matches = 0 then
    v_new_inventory := v_new_inventory || jsonb_build_array(v_record);
  elsif v_matches > 1 then
    raise exception 'inventory namespace already holds duplicate records for %; failing closed', v_owner;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_inventory_collection(v_new_inventory);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'inventory', v_new_inventory, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact (round-3 P1): a successful inventory staging
  -- happened in this save, independent of whether the staged value differs from
  -- published reality. This is what makes every Run-ownership-writing doorway
  -- fail closed for the rest of the save, even for a value-equal replay.
  update public.campaign_runtime
     set inventory_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'inventory_mutation_version', 1,
    'owner_entity_id', v_owner,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'inventory', v_record
  );
end;
$$;

revoke all on function public.mutate_owner_inventory(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_owner_inventory(text, jsonb) to service_role;

comment on function public.mutate_owner_inventory(text, jsonb) is
  'EV2-10: the only validated owner-local inventory mutation route, inside the normal RT01 save lifecycle. Requires an explicit structurally valid controller assertion (controller.kind must be a JSON string exactly mainrun or run; null/missing/non-string/unknown fails closed before any authority branch with no MAINRUN fallthrough), proves the asserted MAINRUN-or-one-RUN controller against authoritative published Run truth (fail-closed on a malformed published runs batch, a parked claiming Run, a duplicated authoritative Run identity, and a same-save staged runs change), validates + canonicalizes the EV2-10 owner-local inventory record (ordinary unique name/description/quantity entries plus structural cp/sp/ep/gp/pp currency, both with the owning schema''s integer semantics), then stages the updated single-owner record into the engine-owned inventory namespace and records the inventory-staging operation fact that closes every Run-ownership-writing doorway for the rest of the save. Absolute target, replay-safe, all-or-nothing through the existing gateway. Never mints unique-item identity.';

-- ---------------------------------------------------------------------------
-- 5. Close the generic `inventory` bypass. The inventory namespace is
--    engine-owned: it can never be staged or deleted through the generic routes.
--    This re-declares the HWB-02 generic routes unchanged except for the added
--    inventory closure and the same-save inventory/Run-ownership mutual
--    exclusion (once this save has staged an inventory mutation, the generic
--    `runs` key is refused too), preserving every existing dedicated-key closure
--    and the server-owned ordinary-save allowlist exactly.
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations and inventory keys are rejected here and must use their validated routes. Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation, the runs key is refused for the rest of the save; historical receipts copied forward from published reality do not trigger the reconciliation closure. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';

comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';

comment on function public._rhc_normalize_inventory_record(text, jsonb) is
  'EV2-10 internal owner-local inventory record validation + canonicalization. Enforces non-blank JSON-string name/description, explicit integer quantity >= 1 with the owning schema''s Draft 2020-12 integer semantics (so 1 and 1.0 agree, non-integral values fail), unique ordinary entries under JSON numeric equality (schema uniqueItems, so {quantity:1} and {quantity:1.0} are the same entry), and an omitted currency stays coherent while an explicit JSON null currency fails closed. Internal-only: inventory payloads are reachable only through the validated mutate_owner_inventory route.';
comment on function public._rhc_inventory_controller_for_owner(text) is
  'EV2-10 internal current-controller lookup. Reads only authoritative published Run truth; returns the single claiming run_id or NULL when no published Run claims the owner. A malformed published runs batch, a parked claiming Run, or a duplicated authoritative Run identity fails closed rather than falling through to MAINRUN. Internal-only.';
comment on function public._rhc_state_key_changed_in_save(text, bigint, bigint) is
  'EV2-10 internal same-save `runs` change detector. A save begins as a copy of published reality, so a differing staged `runs` value means this save is changing Run ownership. Used so inventory authority cannot be proven against a controller this save is replacing. Inventory staging uses the explicit operation marker instead. Internal-only.';
comment on function public._rhc_inventory_staged_in_save() is
  'EV2-10 internal same-save inventory-staging operation fact. True only when the active save''s lock_token matches the lock_token that most recently staged a successful inventory mutation, so closure keys on the staging operation rather than on final value equality (a value-equal replay still trips it) and never leaks into a later save. Internal-only.';


-- ---------------------------------------------------------------------------
-- 6. Close the dedicated RT04 reconciliation-after-inventory doorway.
--    The generic `runs` stage/delete closure above stops generic same-save Run
--    changes once inventory has been staged, but `reconcile_run_resolution`
--    writes the `runs` batch with a direct INSERT and would bypass it. This
--    re-declares the RT04 route unchanged except for the same-save inventory
--    guard, so every Run-ownership-writing doorway fails closed in a save that
--    has staged an inventory mutation. The guard reads the explicit staging
--    operation fact (2c), not final inventory value equality. RT04 is not
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

  -- EV2-10 same-save coupling (round-2/round-3 P1): once this save has staged a
  -- successful inventory mutation, Run ownership must not change in the same
  -- generation. Inventory authority was proven against the published Run
  -- controller, so a later reconciliation could release that owner and publish a
  -- stale inventory update. Every Run-ownership-writing doorway, including this
  -- dedicated RT04 route, fails closed here; change Run ownership and inventory
  -- in separate saves. Detection is the explicit staging operation fact (2c),
  -- not final value equality, so a value-equal replay of the same absolute
  -- inventory target still trips this guard.
  if public._rhc_inventory_staged_in_save() then
    raise exception
      'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)';
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
  'RT04/EV2-10: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet (with their validated summary), and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. EV2-10 adds the same-save guard: once this save has staged an inventory mutation, reconciliation fails closed because it would change Run ownership after inventory authority was proven against the published controller. All-or-nothing through the existing gateway.';
