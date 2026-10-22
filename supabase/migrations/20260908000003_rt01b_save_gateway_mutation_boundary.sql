-- RT01-B — Save Gateway + Mutation Boundary
-- Rolling High Club guarded PostgreSQL mutation/publication doorway.
--
-- This migration adds ONE legal SQL mutation/publication doorway on top of the
-- RT01-A published-runtime floor:
--
--     BEGIN -> STAGE/DELETE -> ABORT | PUBLISH
--
-- The product law it enforces mechanically:
--   AI/DM intent is not persistence. A raw SQL write is not persistence. A
--   durable mutation is only one that passes this guarded save lifecycle and
--   publishes coherently. The DATABASE, not caller prose or caller-supplied
--   checkpoint identity, owns the critical publication invariant.
--
-- Architecture authority is the proven Mission10 runtime spine
-- (Nollie-gif/Mission10-Simulation-Sequel@f16ee4bad25a1bef4bae691984d98beed5e18809:
--  supabase/migrations/20260811230000_mutation_lifecycle_gate.sql). The reusable
-- LAWS are ported; the Mission10 domain BAGGAGE is deliberately NOT:
--   * no staging-procedure / domain-procedure allowlist (quicksave/hook/clock/...);
--   * no campaign-state key allowlist (live_status/daily_recap/...);
--   * no entity_knowledge staging machinery;
--   * no legacy campaign_state compatibility mirror on publish;
--   * no caller-supplied Git SHA / hash / day accepted as authoritative identity;
--   * no runtime-published mirror confirmation (that is RT01-C).
--
-- RT01-B is SQL-side mutation/publication ONLY. It does not perform, require, or
-- confirm any external Git mirror. It invents no campaign day, story, Hook, Run,
-- knowledge, economy, or Clock fact. SQL remains inert as live RHC authority.

-- ---------------------------------------------------------------------------
-- 1. Lifecycle columns on the singleton runtime locator
-- ---------------------------------------------------------------------------
-- RT01-A reserved the save_in_progress / staging_generation shape and explicitly
-- left the mutation lifecycle to RT01-B. The Save Gateway needs a per-save active
-- context so BEGIN/STAGE/ABORT/PUBLISH can prove they belong to the same save and
-- so a crashed caller's stale lock is recoverable within a bounded window.
--
-- lock_token   : opaque per-save handle. DB-GENERATED at BEGIN (never chosen by
--                the caller) so the active-save identity is owned by the database.
--                It is a matching handle, NOT an authentication secret and NOT a
--                checkpoint identity: table privileges + the DML guard below are
--                the real authorization boundary.
-- save_started_at / lock_expires_at : bounded stale-lock recovery, so a crashed
--                save does not deadlock the singleton forever.
alter table public.campaign_runtime
  add column if not exists lock_token text,
  add column if not exists save_started_at timestamptz,
  add column if not exists lock_expires_at timestamptz;

-- The active-save context is one coherent state, exactly like RT01-A's staging
-- locator: the lock fields are present precisely when a save is in progress. The
-- floor can never represent "save active with no lock" or "lock lingering with no
-- active save".
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'campaign_runtime_lock_coherence_check'
      and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_lock_coherence_check
      check (
        (lock_token is not null) = save_in_progress
        and (save_started_at is not null) = save_in_progress
        and (lock_expires_at is not null) = save_in_progress
      );
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 2. Transaction-local raw-DML guard
-- ---------------------------------------------------------------------------
-- Layer 2 of the mutation boundary (layer 1 is the privilege revocation in
-- section 8). Every runtime-owned table rejects DML unless a trusted gateway
-- function has asserted the transaction-local guard for the current transaction.
-- This stops an ungated owner/superuser/raw write from masquerading as a valid
-- gated mutation. The guard is an ASSERTION set by trusted SECURITY DEFINER
-- execution, not a secret: it cannot be reached without either (a) executing a
-- gateway function or (b) already holding break-glass superuser rights, and the
-- latter is an intentional administrative path, not normal gameplay authority.
create or replace function public._rhc_guard_runtime_owned_dml()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_setting('rhc.gated_write', true) is distinct from 'active' then
    raise exception using
      errcode = '42501',
      message = 'runtime-owned table mutation requires the guarded RHC save gateway';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

revoke all on function public._rhc_guard_runtime_owned_dml()
  from public, anon, authenticated, service_role;

-- TRUNCATE does NOT fire row-level (INSERT/UPDATE/DELETE) triggers, so the guard
-- above cannot see it. A statement-level BEFORE TRUNCATE guard closes that hole:
-- privilege revocation (section 8) already denies service_role TRUNCATE, and this
-- rejects an ungated owner/superuser TRUNCATE that would otherwise erase the
-- runtime locator or every published/historical generation without passing through
-- the gateway. Break-glass administration still works by asserting the same
-- transaction-local guard first, exactly like ungated row DML.
create or replace function public._rhc_guard_runtime_owned_truncate()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_setting('rhc.gated_write', true) is distinct from 'active' then
    raise exception using
      errcode = '42501',
      message = 'runtime-owned table truncation requires the guarded RHC save gateway';
  end if;
  return null;
end;
$$;

revoke all on function public._rhc_guard_runtime_owned_truncate()
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Internal active-save assertion (not a public API)
-- ---------------------------------------------------------------------------
-- Serializes on the singleton, row-locks the locator, verifies the caller's save
-- is the active one, and only then asserts the DML guard for this transaction.
-- Internal helper: revoked from every non-owner role so it can never be called as
-- a public bypass to flip the guard around the gateway.
create or replace function public._rhc_require_active_save(
  p_lock_token text
)
returns public.campaign_runtime
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
begin
  -- Transaction-level serialization: only one save lifecycle mutates at a time.
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if not r.save_in_progress or r.lock_token is distinct from p_lock_token then
    raise exception 'campaign save lock mismatch';
  end if;
  if r.staging_generation is null then
    raise exception 'active campaign save is missing its staging generation';
  end if;
  -- Stale-context fail-closed (WIN 5 / invariants F & C): an active save whose
  -- lease has elapsed must NOT be able to stage/delete/abort/publish, even before
  -- another caller's BEGIN performs recovery. Compare against wall-clock time via
  -- clock_timestamp(), which advances during the transaction; now()/
  -- transaction_timestamp() is frozen at transaction start and would let a
  -- long-lived or abandoned caller keep asserting a lease that has really expired.
  -- Candidate cleanup/recovery stays in BEGIN; this assertion only fails closed and
  -- never silently auto-recovers a stale save.
  if r.lock_expires_at is null or r.lock_expires_at <= clock_timestamp() then
    raise exception 'campaign save lock expired';
  end if;

  -- Transaction-local guard assertion established by trusted gateway execution.
  perform set_config('rhc.gated_write', 'active', true);
  return r;
end;
$$;

revoke all on function public._rhc_require_active_save(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. BEGIN — derive the candidate from authoritative current state
-- ---------------------------------------------------------------------------
-- The database (not the caller) owns generation identity and the active-save
-- handle:
--   * next generation is ALWAYS locked_published_generation + 1;
--   * the lock_token is generated here, never accepted from the caller.
-- The current published snapshot is copied forward into the candidate generation
-- so staging edits mutate only the candidate, never published history in place.
-- A crashed prior save whose lock has expired is recovered WITHOUT burning an
-- extra generation: the candidate is always published + 1, and stale candidate
-- residue at that generation is cleared before re-staging.
create or replace function public.begin_campaign_save(
  p_ttl_minutes integer default 30
)
returns table (
  published_generation bigint,
  staging_generation bigint,
  lock_token text,
  lock_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_next bigint;
  v_ttl integer;
  v_token text;
  -- One coherent wall-clock instant for this BEGIN's lease lifecycle. clock_timestamp()
  -- (not the transaction-start-frozen now()) so both the expiry decision below and the
  -- new lease derived further down speak the same real-time semantics as the stale
  -- rejection in _rhc_require_active_save; capturing it once avoids racey lease math.
  -- It is captured AFTER lock acquisition (see below), never in this declare block,
  -- so lock-wait time cannot make it stale.
  v_now timestamptz;
begin
  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  -- Start the lease clock ONLY after the authoritative locks are held. If this BEGIN
  -- blocked waiting on pg_advisory_xact_lock or the FOR UPDATE row lock, a timestamp
  -- captured before the wait would be stale: an already-expired prior save could read
  -- as still active, or a fresh lease could be born partially/fully expired by the
  -- time the lock is acquired. Capturing here binds the expiry decision and the new
  -- lease to real post-lock wall time.
  v_now := clock_timestamp();

  -- A healthy (non-expired) active save blocks a second BEGIN; a second save can
  -- never create a parallel valid candidate generation while one is live. An
  -- expired lease is treated as abandoned and is recovered below.
  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  -- Clear any stale candidate residue from an abandoned prior save so recovery
  -- does not expose stale rows and does not consume another generation.
  delete from public.campaign_state_generations where generation = v_next;

  -- Candidate snapshot: copy the currently published generation forward. Edits
  -- during this save target only v_next; published/historical rows are untouched.
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  select v_next, csg.key, csg.value, now(), now()
  from public.campaign_state_generations csg
  where csg.generation = r.published_generation;

  update public.campaign_runtime
     set save_in_progress = true,
         staging_generation = v_next,
         lock_token = v_token,
         save_started_at = v_now,
         lock_expires_at = v_now + make_interval(mins => v_ttl)
   where id = 1;

  return query
  select cr.published_generation,
         cr.staging_generation,
         cr.lock_token,
         cr.lock_expires_at
    from public.campaign_runtime cr
   where cr.id = 1;
end;
$$;

revoke all on function public.begin_campaign_save(integer)
  from public, anon, authenticated;
grant execute on function public.begin_campaign_save(integer) to service_role;

-- ---------------------------------------------------------------------------
-- 5. STAGE / DELETE — guarded candidate mutation
-- ---------------------------------------------------------------------------
-- Candidate state may be mutated ONLY at the active staging generation, and only
-- through the matching active-save context. The store is generic (generation,
-- key) runtime state: RT01-B enforces NO domain key allowlist and claims NO
-- semantic scope validation that RHC consumers have not built yet.
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
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
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
  if p_key is null or btrim(p_key) = '' then
    raise exception 'campaign state key is required';
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

-- ---------------------------------------------------------------------------
-- 6. ABORT — restore a clean candidate boundary
-- ---------------------------------------------------------------------------
-- Removes the unpublished candidate generation and clears the active-save
-- metadata. The published pointer and published values are never touched, so the
-- prior published world remains authoritative.
create or replace function public.abort_campaign_save(
  p_lock_token text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
begin
  r := public._rhc_require_active_save(p_lock_token);

  delete from public.campaign_state_generations
   where generation = r.staging_generation;

  update public.campaign_runtime
     set save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null
   where id = 1;
end;
$$;

revoke all on function public.abort_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.abort_campaign_save(text) to service_role;

-- ---------------------------------------------------------------------------
-- 7. PUBLISH — advance the published pointer exactly once, atomically
-- ---------------------------------------------------------------------------
-- Inside the one authoritative locked transaction: re-verify the active save,
-- assert the candidate is EXACTLY published_generation + 1, advance the pointer,
-- and clear the active-save metadata together. A second publish with the old
-- lock context finds no active save and fails, so it cannot advance again.
--
-- Checkpoint identity is DATABASE-OWNED (PR #24 lesson). PUBLISH accepts NO
-- caller-supplied Git SHA, hash, generation, day, or save label:
--   * the generation is derived and re-validated here, never chosen by the caller;
--   * published_git_ref is set to NULL because this gate establishes NO external
--     Git proof. Retaining the prior generation's SHA would falsely claim the new
--     generation is pinned to it; fabricating one from caller input is the exact
--     PR #24 failure. RT01-C owns the real external mirror + read-back;
--   * published_day is preserved unchanged. RT01-B neither requires nor infers a
--     campaign day; Clock/day truth is RT02.
create or replace function public.publish_campaign_save(
  p_lock_token text
)
returns public.campaign_runtime
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  out_row public.campaign_runtime%rowtype;
begin
  r := public._rhc_require_active_save(p_lock_token);

  -- Structural precondition: the candidate is exactly the next generation. This
  -- is the exactly-one-generation invariant, re-checked against the locked row
  -- inside the publishing transaction rather than trusted from any earlier read.
  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;

  update public.campaign_runtime
     set published_generation = r.staging_generation,
         -- external Git proof is NOT established by RT01-B; do not retain or
         -- fabricate a SHA for the freshly published generation.
         published_git_ref = null,
         -- published_day intentionally preserved (Unknown-safe; RT02 owns day).
         save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null,
         updated_at = now()
   where id = 1
   returning * into out_row;

  return out_row;
end;
$$;

revoke all on function public.publish_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.publish_campaign_save(text) to service_role;

-- ---------------------------------------------------------------------------
-- 8. Mechanical direct-DML prohibition (privilege layer + guard triggers)
-- ---------------------------------------------------------------------------
-- Layer 1: no normal role holds direct data-modifying privileges on runtime-owned
-- tables. service_role keeps SELECT only and must route every mutation through the
-- gateway functions above.
revoke insert, update, delete, truncate on table public.campaign_runtime
  from public, anon, authenticated, service_role;
revoke insert, update, delete, truncate on table public.campaign_state_generations
  from public, anon, authenticated, service_role;
grant select on table public.campaign_runtime to service_role;
grant select on table public.campaign_state_generations to service_role;

-- Layer 2: the guard trigger rejects any ungated DML (including an owner/superuser
-- raw write) that did not pass through a gateway function this transaction.
drop trigger if exists campaign_runtime_mutation_gate on public.campaign_runtime;
create trigger campaign_runtime_mutation_gate
before insert or update or delete on public.campaign_runtime
for each row execute function public._rhc_guard_runtime_owned_dml();

drop trigger if exists campaign_state_generations_mutation_gate on public.campaign_state_generations;
create trigger campaign_state_generations_mutation_gate
before insert or update or delete on public.campaign_state_generations
for each row execute function public._rhc_guard_runtime_owned_dml();

-- Statement-level TRUNCATE guard: row-level triggers never fire for TRUNCATE, so an
-- ungated owner/superuser TRUNCATE would otherwise bypass the mutation boundary
-- entirely. These reject it unless the transaction-local guard is asserted.
drop trigger if exists campaign_runtime_truncate_gate on public.campaign_runtime;
create trigger campaign_runtime_truncate_gate
before truncate on public.campaign_runtime
for each statement execute function public._rhc_guard_runtime_owned_truncate();

drop trigger if exists campaign_state_generations_truncate_gate on public.campaign_state_generations;
create trigger campaign_state_generations_truncate_gate
before truncate on public.campaign_state_generations
for each statement execute function public._rhc_guard_runtime_owned_truncate();
