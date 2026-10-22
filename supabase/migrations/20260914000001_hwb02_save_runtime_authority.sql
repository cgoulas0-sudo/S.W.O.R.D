-- HWB-02 — SAVE Runtime Authority
-- Rolling High Club forward-only hardening of the ordinary campaign-save key
-- admission boundary on top of the existing RT01-B Save Gateway / RT02 / RT03 /
-- RT04 spine. This migration is NOT a second save engine: it adds one
-- server-owned ordinary-save key policy to the generic staging routes and
-- composes with every existing dedicated closure.
--
-- The failure class it closes:
--   RT01-B intentionally shipped generic `stage_campaign_state` /
--   `delete_staged_campaign_state` with NO domain key allowlist. RT02/RT04 later
--   closed individual engine-owned keys (`campaign_clock`, `run_reconciliations`)
--   and added the same-save `runs` closure, but an ordinary `campaign_save` could
--   still name any new/undeclared key. That means caller/model prose, not the
--   database, decided which runtime keys existed — the exact hole HWB-02 exists
--   to close. Prose must not be the authority boundary.
--
-- The server-owned policy for ordinary `campaign_save` is a constant of this
-- schema (never caller-supplied, never widened by a caller/model):
--   daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs
-- Unknown/undeclared keys fail closed. Stage and delete enforce the same policy.
--
-- Composition (unchanged, re-declared because create-or-replace replaces the
-- whole function body):
--   * `staging_save_kind = 'engineering_release'` still forbids campaign state
--     mutation entirely (RT01-D).
--   * `campaign_clock` is still rejected here: dedicated validated route only
--     (RT02 `stage_campaign_clock`).
--   * `run_reconciliations` is still rejected here: dedicated reconciliation
--     route only (RT04 `reconcile_run_resolution`).
--   * `runs` is still refused for the rest of a save once a reconciliation is
--     newly staged in it (RT04 same-save candidate protection).
--   * Publication, generation identity, mirror token, `runtime-published`
--     read-back and verifier confirmation are NOT touched (RT01-B/C/D).
--   * Direct-DML privileges and guard triggers are NOT touched (RT01-B §8).
--
-- Dedicated routes compose without change: `stage_campaign_clock` and
-- `reconcile_run_resolution` write their engine-owned keys with direct INSERTs
-- inside the guarded gateway, not through the generic routes.
--
-- Installation is forward-only, following the RT02/RT04 pattern: never rewrite an
-- applied migration. The install check takes the same authoritative
-- `pg_advisory_xact_lock('rhc_campaign_save')` and row lock that
-- `begin_campaign_save` takes BEFORE testing `save_in_progress`, so a concurrent
-- BEGIN can neither race the check nor start staging under the pre-HWB-02 generic
-- function definitions. An active save is refused.
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'HWB-02 migration refused: resolve the active campaign save before installing the campaign_save runtime key policy';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Generic staging: compose existing closures + the HWB-02 ordinary-save key
--    policy.
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

-- ---------------------------------------------------------------------------
-- 2. Generic deletion: compose existing closures + the same HWB-02 ordinary-save
--    key policy. Stage/delete symmetry is mechanical, not prose.
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
  'RT01-B/RT02/RT04/HWB-02: generic runtime-state staging. Engine-owned campaign_clock and run_reconciliations keys are rejected here and must use their validated routes. Once a reconciliation is newly staged in the current save (absent from the published reconciliation ledger), the runs key is refused for the rest of the save so the validated candidate Run ownership cannot be contradicted before publication; historical receipts copied forward from published reality do not trigger the closure. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';

comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02: generic runtime-state deletion with the same dedicated-key closures and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';
