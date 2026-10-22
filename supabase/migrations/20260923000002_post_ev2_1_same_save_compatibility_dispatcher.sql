-- POST-EV2-1 — Save Gateway basement, Patch 1B: same-save compatibility dispatcher
-- Rolling High Club validated persistence basement for the ONE Save Gateway.
--
-- This migration is NOT a second save engine, NOT a second publication authority
-- and NOT a domain refactor. It adds ONE server-owned, machine-readable same-save
-- compatibility contract and routes every already-existing cross-domain
-- exclusion through it, with NO semantic behavior change.
--
-- Architecture sentence:
--   POST-EV2-1 owns the modular INSIDE of the single Save Gateway. RT01
--   begin/publish/abort, generation, lease/lock, mirror and confirmation remain
--   central and unchanged; dedicated semantic routes keep their domain behavior;
--   Patch 1A's domain admission registry remains intact and is not duplicated;
--   and the "may these already-legal operations coexist in this active save?"
--   decision stops being a hand-coded cross-domain branch in each doorway and
--   becomes the output of one deterministic server-owned compatibility contract.
--
-- WHAT this migration changes (Patch 1B of the frozen POST-EV2-1 decomposition):
--   1. `public._rhc_same_save_compatibility_policy(p_operation text)` is the ONE
--      machine-readable declaration of every audited cross-domain
--      incompatibility: for each legal mutation operation, the ordered blocking
--      facts and the exact fail-closed message. It consumes only the operation
--      name, reads no table and selects no mutable store.
--   2. `public._rhc_same_save_compatibility(p_operation, staging, published)`
--      evaluates that policy against the active save and returns a
--      machine-readable decision. Unknown operations/detectors fail closed.
--   3. `public._rhc_require_same_save_compatibility(...)` is the thin internal
--      enforcement helper every doorway calls; it raises the exact message.
--   4. Every existing doorway that carried an inline same-save cross-domain
--      guard is re-declared to delegate ONLY that compatibility decision to the
--      contract: generic `stage_campaign_state` / `delete_staged_campaign_state`
--      (`runs`), the dedicated RT04 `reconcile_run_resolution`, the EV2-10
--      `mutate_owner_inventory`, EV2-11 `mutate_item_custody`, EV2-12.1
--      `admit_item_identity`, EV2-13 `mutate_entity_state`, EV2-13.1
--      `mutate_applied_status` and RT02 `stage_campaign_clock`. Every other
--      byte of every function body, every existing dedicated-key closure, the
--      HWB-02 ordinary-save allowlist and every semantic validation are
--      preserved exactly. The two generic doorways derive their admission from
--      Patch 1A's registry, so they are re-declared only when that registry is
--      present; in the forward chain it always is.
--
-- The audited compatibility edges owned by this Mission (all centralized here):
--   * runs <-> run_reconciliations;
--   * runs <-> inventory;
--   * runs <-> item_custody / item admission custody effects;
--   * runs <-> entity_state;
--   * runs <-> applied_statuses;
--   * campaign_clock <-> applied_statuses.
--
-- Deliberate non-goals (Deferred Ownership — must NOT be absorbed here):
--   * durable ORCHESTRATOR/JOHNNY mutation-domain memory + workflow proof
--     -> Patch 1C;
--   * clean bootstrap/baseline equivalence and any baseline/squash mechanism
--     -> Patch 1D;
--   * dedicated domain semantics/validation (Clock, RT04 reconciliation,
--     Inventory, Custody/Admission, Entity State, Applied Status) remain owned
--     by their existing routes; this migration moves none of that behavior;
--   * no new mutation domain, no new compatibility edge, no new table, no
--     mutable policy store, no second publication authority.
--
-- STOP conditions honored: no audited edge needed a semantic change; no new
-- table/mutable policy authority was required; no previously unknown edge was
-- discovered; no path outside the Surface Budget was touched; no caller-supplied
-- authority was introduced; Patch 1A's registry is untouched.


-- ---------------------------------------------------------------------------
-- 1. The machine-readable same-save compatibility policy (internal). This is
--    the ONE server-owned declaration of every audited cross-domain
--    incompatibility: for each legal mutation operation it names, in a fixed
--    deterministic order, the domain fact that blocks it and the exact
--    fail-closed message that operation must raise. It consumes ONLY the
--    operation name, reads no table and selects no mutable store, so the policy
--    can never become caller-supplied or caller-controlled. Internal-only.
--
--    Operation -> blocking facts (order preserved from the pre-Patch-1B inline
--    guards, so the first matching blocker and its exact message are unchanged):
--      stage_runs          : run_reconciliations, inventory, item_custody,
--                            entity_state, applied_statuses
--      delete_runs         : run_reconciliations, inventory, item_custody,
--                            entity_state, applied_statuses
--      reconcile_runs      : inventory, item_custody, entity_state,
--                            applied_statuses
--      mutate_inventory    : runs (changed in this save)
--      mutate_item_custody : runs (changed in this save)
--      admit_item_identity : runs (changed in this save)
--      mutate_entity_state : runs (changed in this save)
--      mutate_applied_status : runs (changed in this save), campaign_clock
--                            (changed in this save)
--      stage_campaign_clock  : applied_statuses
--
--    `detector` is an internal enum evaluated by the compatibility decision
--    function; it is never caller input.
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
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'this save has already staged a timed applied-status mutation; a Run reconciliation would change Run ownership after applied-status controller authority was proven, so reconciliation fails closed (change Run ownership and applied status in separate saves)')
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
  'POST-EV2-1 Patch 1B: the single server-owned, machine-readable same-save compatibility policy. For each legal mutation operation it declares, in deterministic order, every audited cross-domain incompatibility as {blocked_by, detector, error}, where `error` is the exact fail-closed message that operation must raise. Consumes only the operation name; reads no table and selects no mutable store, so the policy can never be caller-supplied or caller-controlled. Unknown operations report known=false. Internal-only.';

-- ---------------------------------------------------------------------------
-- 2. The compatibility decision (internal). Evaluates the declared policy
--    against the active save's staging/published generations and returns a
--    machine-readable decision. It answers ONLY "may these already-legal
--    operations coexist in this active save?"; it never answers whether the
--    mutation is itself semantically valid. Unknown operations and unknown
--    detectors fail closed rather than silently permitting a mutation.
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
  'POST-EV2-1 Patch 1B: the server-owned same-save compatibility decision. Evaluates the declared policy for one operation against the active save''s staging/published generations and returns {operation, domain, known, compatible, blocked_by, error}. It answers only whether already-legal operations may coexist in this save; it never judges a mutation''s own semantic validity. Unknown operations/detectors fail closed. Internal-only; no caller-supplied policy.';

-- ---------------------------------------------------------------------------
-- 3. The enforcement helper (internal). Every affected doorway delegates its
--    same-save compatibility decision to this one call and raises the exact
--    fail-closed message the contract returns. The doorway supplies only its
--    own hard-coded operation name; it never supplies, overrides, disables or
--    reinterprets a rule.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_require_same_save_compatibility(
  p_operation text,
  p_staging_generation bigint,
  p_published_generation bigint
)
returns void
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_decision jsonb;
begin
  v_decision := public._rhc_same_save_compatibility(
    p_operation, p_staging_generation, p_published_generation);
  if not (v_decision ->> 'compatible')::boolean then
    raise exception '%', v_decision ->> 'error';
  end if;
end;
$$;

revoke all on function public._rhc_require_same_save_compatibility(text, bigint, bigint)
  from public, anon, authenticated, service_role;

comment on function public._rhc_require_same_save_compatibility(text, bigint, bigint) is
  'POST-EV2-1 Patch 1B: the internal enforcement helper every affected doorway calls. Delegates to `_rhc_same_save_compatibility` and raises the exact fail-closed message when the requested operation is incompatible with a fact or change already staged in this active save. Internal-only.';


-- ---------------------------------------------------------------------------
-- 4. Re-declared dedicated doorways. Each carried an inline same-save
--    cross-domain guard; each now delegates ONLY that decision to the shared
--    contract. All other behavior is byte-for-byte identical to the prior
--    definition.
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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the cross-domain exclusion decision. A Run reconciliation
  -- writes Run ownership, so the contract fails it closed when a domain whose
  -- authority was proven against published Run truth has already staged here.
  perform public._rhc_require_same_save_compatibility(
    'reconcile_runs', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the applied-status exclusion decision. Advancing the Clock in
  -- a save that already staged a timed applied-status mutation would leave those
  -- anchors proven against the wrong elapsed truth, so the Clock write fails
  -- closed.
  perform public._rhc_require_same_save_compatibility(
    'stage_campaign_clock', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns both exclusion decisions for this route. Applied-status
  -- authority is proven against published Run truth, and its elapsed anchors
  -- against the published Clock, so a same-save staged runs or campaign_clock
  -- change fails this mutation closed.
  perform public._rhc_require_same_save_compatibility(
    'mutate_applied_status', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the Run-ownership exclusion decision. Inventory authority is
  -- proven against published Run truth, so a same-save staged runs change fails
  -- this mutation closed.
  perform public._rhc_require_same_save_compatibility(
    'mutate_inventory', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the Run-ownership exclusion decision. Custody authority is
  -- proven against published Run truth, so a same-save staged runs change fails
  -- this mutation closed.
  perform public._rhc_require_same_save_compatibility(
    'mutate_item_custody', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the Run-ownership exclusion decision. Admission authority for
  -- initial custody is proven against published Run truth, so a same-save staged
  -- runs change fails this action closed.
  perform public._rhc_require_same_save_compatibility(
    'admit_item_identity', r.staging_generation, r.published_generation);

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

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the Run-ownership exclusion decision. Entity-state authority
  -- is proven against published Run truth, so a same-save staged runs change
  -- fails this mutation closed.
  perform public._rhc_require_same_save_compatibility(
    'mutate_entity_state', r.staging_generation, r.published_generation);

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

-- ---------------------------------------------------------------------------
-- 5. Re-declared generic doorways. The generic `runs` compatibility
--    delegation layers on top of Patch 1A's domain admission registry, so
--    these two doorways are re-declared only when that registry is present:
--    against a chain that predates Patch 1A they correctly retain their prior
--    inline form, and Patch 1B never silently drops or duplicates Patch 1A's
--    admission decision. In the forward chain the registry is always present,
--    so the generic routes always delegate to the shared contract.
-- ---------------------------------------------------------------------------
do $dispatch$
begin
  if to_regprocedure('public._rhc_save_domain_policy(text)') is null then
    return;
  end if;
  execute $stage_ddl$
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
  v_policy jsonb;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
  end if;

  -- POST-EV2-1 Patch 1A: generic-vs-dedicated admission and the ordinary-save
  -- allowlist are the single server-owned registry's decision, not gateway
  -- hard-coded branches. Dedicated keys name their route; unknown keys fail closed.
  v_policy := public._rhc_save_domain_policy(p_key);
  if v_policy ->> 'admission' is distinct from 'generic' then
    raise exception '%', v_policy ->> 'stage_error';
  end if;

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the cross-domain exclusion decision. `runs` is a legal generic
  -- key, so it passes the registry; the contract fails the mutation closed if an
  -- incompatible domain fact or change already exists in this save.
  if p_key = 'runs' then
    perform public._rhc_require_same_save_compatibility(
      'stage_runs', r.staging_generation, r.published_generation);
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
$stage_ddl$;
  execute $delete_ddl$
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
  v_policy jsonb;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
  end if;

  -- POST-EV2-1 Patch 1A: the same server-owned registry decision as staging.
  v_policy := public._rhc_save_domain_policy(p_key);
  if v_policy ->> 'admission' is distinct from 'generic' then
    raise exception '%', v_policy ->> 'delete_error';
  end if;

  -- Same-save compatibility (Patch 1B): the shared server-owned compatibility
  -- contract owns the cross-domain exclusion decision. `runs` is a legal generic
  -- key, so it passes the registry; the contract fails the deletion closed if an
  -- incompatible domain fact or change already exists in this save.
  if p_key = 'runs' then
    perform public._rhc_require_same_save_compatibility(
      'delete_runs', r.staging_generation, r.published_generation);
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
$delete_ddl$;
end;
$dispatch$;

