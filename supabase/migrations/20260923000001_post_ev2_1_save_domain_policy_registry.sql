-- POST-EV2-1 — Save Gateway basement, Patch 1A: server-owned domain policy registry
-- Rolling High Club validated persistence basement for the ONE Save Gateway.
--
-- This migration is NOT a second save engine, NOT a second publication authority
-- and NOT a domain refactor. It adds exactly ONE server-owned, machine-readable
-- policy registry and routes the generic `stage_campaign_state` /
-- `delete_staged_campaign_state` admission decisions through it, with NO
-- semantic behavior change.
--
-- Architecture sentence:
--   POST-EV2-1 owns the modular INSIDE of the single Save Gateway. RT01
--   begin/publish/abort, generation, lease/lock, mirror and confirmation remain
--   central and unchanged; dedicated semantic routes keep their domain behavior;
--   and the generic route's "generic vs dedicated vs forbidden" admission and
--   the HWB-02 ordinary-save allowlist stop being hard-coded branches in the
--   gateway and become the output of one deterministic server-owned registry.
--
-- WHAT this migration changes (Patch 1A of the frozen POST-EV2-1 decomposition):
--   1. `public._rhc_save_domain_policy(p_key text)` is the single server-owned
--      registry. It classifies a runtime state key as:
--        * `generic`   — admitted by the generic route and on the ordinary-save
--                        allowlist (`daily_recap`, `day_resolution`,
--                        `live_status`, `dm_meta`, `narrative_hooks`, `runs`);
--        * `dedicated` — engine-owned; the generic route must refuse it and the
--                        registry must name every legal writer exhaustively
--                        (an array, never a single misleading route);
--        * `forbidden` — unknown/undeclared; the generic route fails closed.
--      The function consumes ONLY the key. It takes no caller-supplied policy,
--      reads no table and selects no mutable store, so the decision can never
--      become caller-controlled authority. It is internal-only (execute revoked
--      from every role).
--   2. `public.stage_campaign_state(...)` and
--      `public.delete_staged_campaign_state(...)` are re-declared to obtain the
--      admission decision from that registry instead of accumulating hard-coded
--      dedicated-key / allowlist branches. Every existing dedicated-key closure
--      message, the `runs` same-save coupling guards, the engineering_release
--      refusal and the exact server-owned ordinary-save allowlist are preserved
--      byte-for-byte in effect. The `runs` same-save compatibility edges remain
--      inline here; centralizing them is Patch 1B and is deliberately NOT done
--      in this patch.
--
-- Deliberate non-goals (Deferred Ownership — must NOT be absorbed here):
--   * same-save compatibility dispatcher and cross-domain edge centralization
--     -> Patch 1B;
--   * durable ORCHESTRATOR/JOHNNY mutation-domain memory + workflow proof
--     -> Patch 1C;
--   * clean bootstrap/baseline equivalence and any baseline/squash mechanism
--     -> Patch 1D;
--   * dedicated domain semantics/validation (Clock, RT04 reconciliation,
--     Inventory, Custody/Admission, Entity State, Applied Status) remain owned
--     by their existing routes; this migration moves none of that behavior;
--   * no table, no mutable policy store, no new mutation domain, no second
--     publication authority.
--
-- STOP conditions honored: behavior equivalence needs no dedicated-route change;
-- the registry is not caller-writable/caller-selectable; no new table/store is
-- required; no dedicated semantics changed.

-- ---------------------------------------------------------------------------
-- 1. The server-owned domain policy registry.
--    Machine-readable classification of every current runtime state key. The
--    only input is the key itself; the only output is the deterministic policy
--    record. Unknown/undeclared keys resolve to `forbidden` with the exact
--    HWB-02 fail-closed message.
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
  -- The registry body. Each declared key maps to exactly one admission class.
  -- `generic` keys are the HWB-02 ordinary-save allowlist. `dedicated` keys are
  -- engine-owned and may only be written by their named semantic route(s). The
  -- messages are the exact historical fail-closed texts, preserved verbatim so
  -- this patch is behaviorally indistinguishable from the prior hard-coded
  -- branches.
  --
  -- `dedicated_routes` is deliberately an EXHAUSTIVE ARRAY, never a singular
  -- field: a domain may have more than one legal writer (item_custody is
  -- written by both mutate_item_custody and admit_item_identity). A singular
  -- "route" field would falsely imply a complete writer set, so it is not
  -- exposed. Generic and forbidden keys expose an explicit empty array.
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
  'POST-EV2-1 Patch 1A: the single server-owned, machine-readable runtime state key policy registry. Consumes only the key and returns admission (generic | dedicated | forbidden), the exhaustive array `dedicated_routes` of every legal writer for engine-owned keys, and the exact fail-closed messages. `generic` is the HWB-02 ordinary-save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs) and exposes `dedicated_routes=[]`. `dedicated` exposes every legal writer, never a single route that could imply a complete set: campaign_clock=[stage_campaign_clock], run_reconciliations=[reconcile_run_resolution], inventory=[mutate_owner_inventory], item_custody=[mutate_item_custody, admit_item_identity], item_admissions=[admit_item_identity], entity_state=[mutate_entity_state], applied_statuses=[mutate_applied_status]. Unknown/undeclared keys are `forbidden` and expose `dedicated_routes=[]`. No caller-supplied policy, no table, no mutable store: the decision cannot become caller-controlled authority. Internal-only.';

-- ---------------------------------------------------------------------------
-- 2. Generic staging route. Re-declared so dedicated-key admission and the
--    ordinary-save allowlist come from the registry instead of hard-coded
--    branches. The `runs` same-save coupling guards and every other behavior
--    are preserved exactly (Patch 1B owns centralizing the compatibility edges).
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

  -- Same-save coupling guards (Patch 1B centralization deferred). `runs` is a
  -- legal generic key, so it passes the registry; these engine-owned ownership
  -- couplings still apply for the rest of the save.
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

comment on function public.stage_campaign_state(text, text, jsonb) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1/POST-EV2-1-1A: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory, item_custody, item_admissions, entity_state and applied_statuses keys are rejected here and must use their validated routes (applied_statuses via mutate_applied_status). Admission and the server-owned campaign_save allowlist are now decided by the server-owned domain policy registry `_rhc_save_domain_policy`; unknown or undeclared keys fail closed. Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation, an item custody/admission operation, a mutable entity-state mutation, or a timed applied-status mutation, the runs key is refused for the rest of the save.';

-- ---------------------------------------------------------------------------
-- 3. Generic deletion route. Same registry-driven admission; same preserved
--    dedicated closures, same-save `runs` guards and allowlist outcome.
-- ---------------------------------------------------------------------------
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

  -- Same-save coupling guards (Patch 1B centralization deferred).
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

comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1/POST-EV2-1-1A: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody/admission/entity-state/applied-status and Run-ownership mutual exclusion on runs). Admission and the server-owned campaign_save allowlist are decided by the server-owned domain policy registry `_rhc_save_domain_policy`; unknown or undeclared keys fail closed.';
