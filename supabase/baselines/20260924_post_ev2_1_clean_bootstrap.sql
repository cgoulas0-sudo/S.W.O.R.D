-- POST-EV2-1 Patch 1D — clean bootstrap baseline
-- Rolling High Club runtime, clean-environment bootstrap only.
--
-- PINNED FRONTIER:
--   repository: Nollie-gif/Rolling-High-Club
--   base/main cut point: d3292fd53cbb162a9e13c9e6148f88cfc474fa75
--   final historical migration:
--     20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql
--   migration count: 18
--
-- CONTRACT:
--   * This file is NOT a migration and MUST NOT be placed under supabase/migrations/.
--   * It is valid only for a fresh/empty environment that already has the
--     Supabase baseline roles anon/authenticated/service_role.
--   * Existing databases continue to upgrade through the preserved historical
--     migration chain. Never apply this file on top of an existing RHC runtime.
--   * The body below is a deterministic flattened replay of the exact 18-file
--     historical chain at the pinned cut point. Patch 1D tests prove this file
--     remains source-identical to that chain and behaviorally equivalent on
--     PostgreSQL 15 and 17.
--   * It contains no production campaign data and preserves Unknown-safe
--     bootstrap state.
--
-- WHY THIS SHAPE:
--   Patch 1D deliberately does not attempt a semantic SQL rewrite or pg_dump
--   canonicalization. The safest first clean baseline is a single pinned
--   clean-install artifact assembled verbatim from already-reviewed migrations.
--   Historical migration files remain the upgrade/audit authority.

-- ============================================================================
-- SOURCE MIGRATION: 20260908000001_rt01a_published_runtime_floor.sql
-- ============================================================================

-- RT01-A — PostgreSQL Published Runtime Floor (structural only)
-- Rolling High Club runtime/publication foundation.
--
-- This migration establishes the INERT PostgreSQL/Supabase published-runtime
-- structural floor. It defines shape only. It does NOT build the Save Gateway,
-- the mutation/publication procedures, the runtime-published Git handshake, the
-- DM read facade, engineering_release, or any downstream consumer mechanic.
-- Those belong to RT01-B / RT01-C / RT01-D and later gates.
--
-- Merging this alone does not switch RHC live runtime authority to SQL and does
-- not change campaign, canon, or gameplay behavior.
--
-- Adapted from the proven Mission10 runtime spine
-- (Nollie-gif/Mission10-Simulation-Sequel@f16ee4bad25a1bef4bae691984d98beed5e18809):
--   * campaign_runtime singleton publication locator / head;
--   * generation-versioned state store;
--   * a published-only, security_invoker read projection.
-- Mission10-specific baggage is deliberately NOT ported: no legacy
-- `campaign_state` compatibility mirror, no entity_registry / entity_knowledge
-- domain machinery, no begin/stage/publish/abort Save Gateway functions, no
-- dm_runtime_lookup facade.

-- ---------------------------------------------------------------------------
-- 1. Publication locator / head (singleton)
-- ---------------------------------------------------------------------------
-- A single row (id = 1) names the current published generation, the exact full
-- Git SHA that generation is pinned to (when one exists), and the minimum
-- structural staging separation later gates require to advance the pointer.
create table if not exists public.campaign_runtime (
  id smallint primary key default 1 check (id = 1),

  -- Current published generation pointer. Bootstraps at 0 (empty world).
  published_generation bigint not null default 0
    check (published_generation >= 0),

  -- Exact full Git commit SHA pinned to the published checkpoint.
  -- NULL is a valid Unknown bootstrap value: no checkpoint pinned yet.
  -- When present it must be an exact 40-character lowercase hex commit SHA,
  -- never a mutable branch name or an abbreviated revision.
  published_git_ref text
    check (published_git_ref is null or published_git_ref ~ '^[0-9a-f]{40}$'),

  -- Published in-world day, when established. NULL means Unknown; RT01-A never
  -- invents a current campaign day.
  published_day integer
    check (published_day is null or published_day >= 0),

  -- Minimum structural staging separation. RT01-B (Save Gateway) owns the
  -- mutation lifecycle that sets/clears these; RT01-A only reserves the shape.
  save_in_progress boolean not null default false,
  staging_generation bigint,

  -- Structural bookkeeping (row provenance), not campaign time.
  bootstrapped_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- A staging generation, when present, must advance strictly beyond the
  -- published generation so publication can move the pointer forward without
  -- rewriting historical generations in place.
  constraint campaign_runtime_staging_ahead_check
    check (staging_generation is null or staging_generation > published_generation),

  -- The staging locator is one coherent state, not two independent flags.
  -- RT01-B will own the lifecycle transitions, but RT01-A guarantees the floor
  -- can never represent "save active with no staging generation" or "staging
  -- generation present while no save is active". This is structural only: no
  -- gateway behavior is introduced here.
  constraint campaign_runtime_staging_coherence_check
    check (save_in_progress = (staging_generation is not null))
);

comment on table public.campaign_runtime is
  'RT01-A: singleton published-runtime locator/head. Row id=1 only. Structural floor; mutation lifecycle is RT01-B.';

alter table public.campaign_runtime enable row level security;

revoke all on table public.campaign_runtime from public, anon, authenticated;
grant select on table public.campaign_runtime to service_role;

-- ---------------------------------------------------------------------------
-- 2. Generation-keyed runtime state store
-- ---------------------------------------------------------------------------
-- Runtime state is keyed by (generation, key). Because each generation's rows
-- are stored independently, publication can advance the current pointer without
-- rewriting or destroying prior generations.
create table if not exists public.campaign_state_generations (
  generation bigint not null,
  key text not null,
  value jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (generation, key)
);

comment on table public.campaign_state_generations is
  'RT01-A: generation-scoped runtime state store. Keyed by (generation, key) so publication advances a pointer, never rewrites history in place.';

alter table public.campaign_state_generations enable row level security;

revoke all on table public.campaign_state_generations from public, anon, authenticated;
-- RT01-A withholds every raw data-modifying grant (insert/update/delete) on
-- generation-owned runtime state, matching campaign_runtime's read-only floor.
-- A direct write path here would let published state change without advancing
-- the publication locator or refreshing checkpoint provenance. The guarded
-- mutation/publication path is RT01-B's Save Gateway, not RT01-A's to expose.
grant select on table public.campaign_state_generations to service_role;

-- ---------------------------------------------------------------------------
-- 3. Published-only read projection
-- ---------------------------------------------------------------------------
-- The published read surface exposes ONLY rows belonging to the generation the
-- locator currently points at. Staged rows (which live at a higher generation)
-- cannot leak through this projection. security_invoker keeps the caller's own
-- privileges/RLS in force rather than the view owner's — this is the minimum
-- projection RT01-A needs to prove published/staged isolation, not the RT01-D
-- DM read facade.
create or replace view public.campaign_state_runtime
with (security_invoker = true)
as
select
  csg.generation as runtime_generation,
  cr.published_git_ref,
  cr.published_day,
  csg.key,
  csg.value,
  csg.created_at,
  csg.updated_at
from public.campaign_state_generations csg
join public.campaign_runtime cr
  on cr.id = 1
 and csg.generation = cr.published_generation;

comment on view public.campaign_state_runtime is
  'RT01-A: published-only projection of campaign_state_generations at campaign_runtime.published_generation. Staged/future-generation rows never appear here.';

revoke all on table public.campaign_state_runtime from public, anon, authenticated;
grant select on table public.campaign_state_runtime to service_role;

-- ============================================================================
-- SOURCE MIGRATION: 20260908000002_rt01a_bootstrap_unknown_runtime.sql
-- ============================================================================

-- RT01-A — Unknown-safe runtime bootstrap
-- Rolling High Club published-runtime floor initialization.
--
-- Establishes the singleton runtime locator in its smallest structurally valid
-- Unknown state. It invents NO campaign facts:
--   * generation 0 (empty world);
--   * NO pinned Git SHA (published_git_ref left NULL);
--   * NO current day (published_day left NULL);
--   * NO staging in progress;
--   * NO seeded campaign/runtime state rows.
--
-- This bootstrap hardcodes no generated commit SHA, so it is reusable and
-- idempotent. It is intentionally separate from the schema migration so that
-- structure and initialization stay distinct (a proven Mission10 law), and so
-- environment-specific pinning is never baked into reusable schema.
--
-- Re-running is harmless: an already-initialized locator is left untouched.

insert into public.campaign_runtime (id, published_generation, published_git_ref, published_day, save_in_progress, staging_generation)
values (1, 0, null, null, false, null)
on conflict (id) do nothing;

-- ============================================================================
-- SOURCE MIGRATION: 20260908000003_rt01b_save_gateway_mutation_boundary.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260908000004_rt01c_runtime_published_git_handshake.sql
-- ============================================================================

-- RT01-C — runtime-published Git handshake
-- SQL publication and external Git recovery proof are two stages of one save.

alter table public.campaign_runtime
  add column if not exists runtime_mirror_token uuid,
  add column if not exists runtime_published_confirmed boolean not null default false,
  add column if not exists runtime_published_confirmed_at timestamptz,
  add column if not exists last_confirmed_generation bigint,
  add column if not exists last_confirmed_git_ref text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'campaign_runtime_mirror_confirmation_coherence_check'
      and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_mirror_confirmation_coherence_check
      check (
        runtime_mirror_token is null
        or (
          (runtime_published_confirmed
           and published_git_ref is not null
           and runtime_published_confirmed_at is not null)
          or
          (not runtime_published_confirmed
           and published_git_ref is null
           and runtime_published_confirmed_at is null)
        )
      );
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'campaign_runtime_last_confirmed_pair_check'
      and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_last_confirmed_pair_check
      check (
        (last_confirmed_generation is null) = (last_confirmed_git_ref is null)
        and (last_confirmed_generation is null or last_confirmed_generation >= 0)
        and (last_confirmed_generation is null or last_confirmed_generation <= published_generation)
        and (last_confirmed_git_ref is null or last_confirmed_git_ref ~ '^[0-9a-f]{40}$')
        and (
          not runtime_published_confirmed
          or (
            last_confirmed_generation = published_generation
            and last_confirmed_git_ref = published_git_ref
          )
        )
      );
  end if;
end;
$$;

-- Dedicated verifier authority. PostgreSQL 16+ represents role membership with
-- independent ADMIN, INHERIT and SET options. A non-superuser CREATEROLE
-- executor receives creator-side ADMIN automatically, so retain that narrow
-- administrative relationship and add only the non-inherited SET path used by
-- the external mirror worker. Every unrelated or incoming membership still
-- fails closed before verifier object grants are applied.
do $$
declare
  v_oid oid;
  v_executor_oid oid;
  v_executor_super boolean;
  v_invalid_membership boolean;
  v_has_admin boolean;
  v_can_set boolean;
  v_role record;
begin
  select oid, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
         rolreplication, rolbypassrls
    into v_role
    from pg_roles
   where rolname = 'rhc_mirror_verifier';

  if not found then
    create role rhc_mirror_verifier
      nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  else
    if v_role.rolcanlogin
       or v_role.rolsuper
       or v_role.rolcreatedb
       or v_role.rolcreaterole
       or v_role.rolreplication
       or v_role.rolbypassrls then
      raise exception
        'RT01-C migration refused: pre-existing rhc_mirror_verifier has unsafe role attributes';
    end if;
  end if;

  select oid into v_oid from pg_roles where rolname = 'rhc_mirror_verifier';
  select oid, rolsuper into v_executor_oid, v_executor_super
    from pg_roles
   where rolname = current_user;

  if current_setting('server_version_num')::integer >= 160000
     and not v_executor_super then
    execute $membership_check$
      select exists (
        select 1
          from pg_auth_members
         where (roleid = $1 and member <> $2)
            or member = $1
            or (roleid = $1 and inherit_option)
            or (roleid = $1 and not admin_option and not set_option)
      )
    $membership_check$
      into v_invalid_membership
      using v_oid, v_executor_oid;

    execute $admin_check$
      select exists (
        select 1
          from pg_auth_members
         where roleid = $1
           and member = $2
           and admin_option
      )
    $admin_check$
      into v_has_admin
      using v_oid, v_executor_oid;

    if v_invalid_membership or not v_has_admin then
      raise exception
        'RT01-C migration refused: rhc_mirror_verifier has unsafe role membership';
    end if;

    select pg_has_role(v_executor_oid, v_oid, 'SET') into v_can_set;
    if not v_can_set then
      execute format(
        'grant rhc_mirror_verifier to %I with inherit false, set true',
        current_user
      );
    end if;

    select pg_has_role(v_executor_oid, v_oid, 'SET') into v_can_set;
    if not v_can_set then
      raise exception
        'RT01-C migration refused: executor cannot SET ROLE rhc_mirror_verifier';
    end if;
  else
    if exists (
      select 1
        from pg_auth_members
       where roleid = v_oid
          or member = v_oid
    ) then
      raise exception
        'RT01-C migration refused: rhc_mirror_verifier has unsafe role membership';
    end if;
  end if;
end;
$$;
grant usage on schema public to rhc_mirror_verifier;

-- Fail closed at the RT01-B -> RT01-C upgrade boundary if an already-issued
-- RT01-B save token could still publish N+1 over a generation N we are about to
-- mark mirror-pending.
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  select * into r from public.campaign_runtime where id = 1;
  if found
     and r.published_generation > 0
     and r.save_in_progress
     and r.runtime_mirror_token is null then
    raise exception
      'RT01-C migration refused: an active RT01-B save (staging generation %) is open over already-published generation %; resolve it (publish or abort under RT01-B) before enabling the runtime-published mirror contract',
      r.staging_generation, r.published_generation;
  end if;
end;
$$;

select set_config('rhc.gated_write', 'active', true);
update public.campaign_runtime
   set runtime_mirror_token = gen_random_uuid(),
       published_git_ref = null,
       runtime_published_confirmed = false,
       runtime_published_confirmed_at = null
 where id = 1
   and published_generation > 0
   and runtime_mirror_token is null;

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
  v_now timestamptz;
begin
  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  v_now := clock_timestamp();

  if r.published_generation > 0 then
    if r.runtime_mirror_token is null then
      raise exception 'published generation % predates the RT01-C mirror contract; repair its mirror before a new save',
        r.published_generation;
    end if;
    if not r.runtime_published_confirmed then
      raise exception 'published generation % has a pending runtime-published mirror; repair it before a new save',
        r.published_generation;
    end if;
  end if;

  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  delete from public.campaign_state_generations where generation = v_next;

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
  v_mirror_token uuid;
begin
  r := public._rhc_require_active_save(p_lock_token);

  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;

  v_mirror_token := gen_random_uuid();

  update public.campaign_runtime
     set published_generation = r.staging_generation,
         published_git_ref = null,
         runtime_mirror_token = v_mirror_token,
         runtime_published_confirmed = false,
         runtime_published_confirmed_at = null,
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

create or replace function public.get_pending_runtime_mirror()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_state jsonb;
begin
  select * into r from public.campaign_runtime where id = 1;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or r.runtime_published_confirmed then
    raise exception 'no runtime-published mirror is pending';
  end if;

  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  return jsonb_build_object(
    'schema_version', 1,
    'generation', r.published_generation,
    'published_day', r.published_day,
    'mirror_token', r.runtime_mirror_token::text,
    'last_confirmed_git_ref', r.last_confirmed_git_ref,
    'state', v_state
  );
end;
$$;

revoke all on function public.get_pending_runtime_mirror()
  from public, anon, authenticated;
grant execute on function public.get_pending_runtime_mirror()
  to service_role, rhc_mirror_verifier;

create or replace function public.confirm_runtime_published_mirror(
  p_generation bigint,
  p_mirror_token uuid,
  p_git_ref text
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
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if p_git_ref is null or p_git_ref !~ '^[0-9a-f]{40}$' then
    raise exception 'runtime-published Git ref must be an exact full commit SHA';
  end if;
  if r.published_generation is distinct from p_generation then
    raise exception 'runtime-published generation mismatch';
  end if;
  if r.runtime_mirror_token is null or r.runtime_mirror_token is distinct from p_mirror_token then
    raise exception 'runtime-published mirror token mismatch';
  end if;
  if r.save_in_progress then
    raise exception 'cannot confirm runtime-published while a save is active';
  end if;

  if r.runtime_published_confirmed then
    if r.published_git_ref is distinct from p_git_ref then
      raise exception 'runtime-published mirror already confirmed at a different Git ref';
    end if;
    return r;
  end if;

  perform set_config('rhc.gated_write', 'active', true);
  update public.campaign_runtime
     set published_git_ref = p_git_ref,
         runtime_published_confirmed = true,
         runtime_published_confirmed_at = clock_timestamp(),
         last_confirmed_generation = r.published_generation,
         last_confirmed_git_ref = p_git_ref,
         updated_at = now()
   where id = 1
   returning * into out_row;

  return out_row;
end;
$$;

revoke all on function public.confirm_runtime_published_mirror(bigint, uuid, text)
  from public, anon, authenticated, service_role, rhc_mirror_verifier;
-- Intentionally no verifier EXECUTE grant yet. Migration 000005 adds the durable
-- bootstrap-base column, republishes confirmation with the required base-binding
-- precondition, and only then enables verifier execution.

comment on column public.campaign_runtime.runtime_mirror_token is
  'Database-owned token minted with SQL publication and embedded in the external Git recovery artifact; not a secret.';
comment on column public.campaign_runtime.runtime_published_confirmed is
  'True only after the external runtime-published Git artifact has been independently created and exact-SHA read back for this published generation/token.';
comment on column public.campaign_runtime.last_confirmed_git_ref is
  'Last healthy confirmed runtime-published Git recovery anchor; remains available while a newer SQL generation is mirror-pending.';
comment on function public.get_pending_runtime_mirror() is
  'Read-only exact SQL-published candidate used by the external runtime-published mirror worker.';
comment on function public.confirm_runtime_published_mirror(bigint, uuid, text) is
  'Verifier confirmation is defined here but remains non-executable by rhc_mirror_verifier until migration 000005 installs the bootstrap-base precondition.';

-- ============================================================================
-- SOURCE MIGRATION: 20260908000005_rt01c_bind_runtime_mirror_base.sql
-- ============================================================================

-- RT01-C — durable bootstrap base anchor for the runtime-published Git mirror

alter table public.campaign_runtime
  add column if not exists runtime_mirror_base_git_ref text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'campaign_runtime_mirror_base_ref_shape_check'
      and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_mirror_base_ref_shape_check
      check (
        runtime_mirror_base_git_ref is null
        or runtime_mirror_base_git_ref ~ '^[0-9a-f]{40}$'
      );
  end if;
end;
$$;

create or replace function public.bind_runtime_mirror_base(
  p_generation bigint,
  p_mirror_token uuid,
  p_base_git_ref text
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
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if p_base_git_ref is null or p_base_git_ref !~ '^[0-9a-f]{40}$' then
    raise exception 'runtime-published base ref must be an exact full commit SHA';
  end if;
  if r.published_generation is distinct from p_generation then
    raise exception 'runtime-published generation mismatch';
  end if;
  if r.runtime_mirror_token is null or r.runtime_mirror_token is distinct from p_mirror_token then
    raise exception 'runtime-published mirror token mismatch';
  end if;
  if r.save_in_progress then
    raise exception 'cannot bind runtime-published base while a save is active';
  end if;
  if r.runtime_published_confirmed then
    raise exception 'runtime-published mirror already confirmed; base anchor is fixed';
  end if;
  if r.last_confirmed_generation is not null then
    raise exception 'runtime-published base binding only applies to the bootstrap generation';
  end if;

  if r.runtime_mirror_base_git_ref is not null then
    if r.runtime_mirror_base_git_ref is distinct from p_base_git_ref then
      raise exception 'runtime-published base already bound to a different anchor';
    end if;
    return r;
  end if;

  perform set_config('rhc.gated_write', 'active', true);
  update public.campaign_runtime
     set runtime_mirror_base_git_ref = p_base_git_ref,
         updated_at = now()
   where id = 1
   returning * into out_row;

  return out_row;
end;
$$;

revoke all on function public.bind_runtime_mirror_base(bigint, uuid, text)
  from public, anon, authenticated, service_role;
grant execute on function public.bind_runtime_mirror_base(bigint, uuid, text)
  to rhc_mirror_verifier;

-- New SQL publications clear the bootstrap-only base anchor. Later generations
-- anchor on last_confirmed_git_ref instead.
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
  v_mirror_token uuid;
begin
  r := public._rhc_require_active_save(p_lock_token);

  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;

  v_mirror_token := gen_random_uuid();

  update public.campaign_runtime
     set published_generation = r.staging_generation,
         published_git_ref = null,
         runtime_mirror_token = v_mirror_token,
         runtime_mirror_base_git_ref = null,
         runtime_published_confirmed = false,
         runtime_published_confirmed_at = null,
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

create or replace function public.get_pending_runtime_mirror()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_state jsonb;
begin
  select * into r from public.campaign_runtime where id = 1;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or r.runtime_published_confirmed then
    raise exception 'no runtime-published mirror is pending';
  end if;

  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  return jsonb_build_object(
    'schema_version', 1,
    'generation', r.published_generation,
    'published_day', r.published_day,
    'mirror_token', r.runtime_mirror_token::text,
    'last_confirmed_git_ref', r.last_confirmed_git_ref,
    'mirror_base_git_ref', r.runtime_mirror_base_git_ref,
    'state', v_state
  );
end;
$$;

revoke all on function public.get_pending_runtime_mirror()
  from public, anon, authenticated;
grant execute on function public.get_pending_runtime_mirror()
  to service_role, rhc_mirror_verifier;

-- Confirmation is republished after the base column exists. Bootstrap confirmation
-- is impossible until the exact selected main base has been durably bound.
create or replace function public.confirm_runtime_published_mirror(
  p_generation bigint,
  p_mirror_token uuid,
  p_git_ref text
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
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if p_git_ref is null or p_git_ref !~ '^[0-9a-f]{40}$' then
    raise exception 'runtime-published Git ref must be an exact full commit SHA';
  end if;
  if r.published_generation is distinct from p_generation then
    raise exception 'runtime-published generation mismatch';
  end if;
  if r.runtime_mirror_token is null or r.runtime_mirror_token is distinct from p_mirror_token then
    raise exception 'runtime-published mirror token mismatch';
  end if;
  if r.save_in_progress then
    raise exception 'cannot confirm runtime-published while a save is active';
  end if;
  if r.last_confirmed_generation is null
     and r.runtime_mirror_base_git_ref is null then
    raise exception 'bootstrap runtime-published confirmation requires a bound base Git ref';
  end if;

  if r.runtime_published_confirmed then
    if r.published_git_ref is distinct from p_git_ref then
      raise exception 'runtime-published mirror already confirmed at a different Git ref';
    end if;
    return r;
  end if;

  perform set_config('rhc.gated_write', 'active', true);
  update public.campaign_runtime
     set published_git_ref = p_git_ref,
         runtime_published_confirmed = true,
         runtime_published_confirmed_at = clock_timestamp(),
         last_confirmed_generation = r.published_generation,
         last_confirmed_git_ref = p_git_ref,
         updated_at = now()
   where id = 1
   returning * into out_row;

  return out_row;
end;
$$;

revoke all on function public.confirm_runtime_published_mirror(bigint, uuid, text)
  from public, anon, authenticated, service_role;
grant execute on function public.confirm_runtime_published_mirror(bigint, uuid, text)
  to rhc_mirror_verifier;

comment on column public.campaign_runtime.runtime_mirror_base_git_ref is
  'Durably bound exact origin/main SHA selected for the bootstrap runtime-published mirror; verifier-bound before first publication proof and reused verbatim by every retry. Null for post-bootstrap generations, which anchor on last_confirmed_git_ref.';
comment on function public.bind_runtime_mirror_base(bigint, uuid, text) is
  'Verifier-only durable binding of the bootstrap base anchor to the current generation/token. Idempotent for the same anchor; fails closed on a different anchor, a non-bootstrap generation, or an already-confirmed mirror.';
comment on function public.confirm_runtime_published_mirror(bigint, uuid, text) is
  'Verifier-only final handshake. Bootstrap confirmation additionally requires a durably bound exact base Git ref before the external publication SHA can become authoritative.';

-- ============================================================================
-- SOURCE MIGRATION: 20260908000006_rt01d_dm_read_engineering_release.sql
-- ============================================================================

-- RT01-D -- published DM read facade + guarded engineering release
--
-- This migration finishes the inert RT01 published-runtime foundation. It does
-- not activate SQL as the live RHC authority and it does not populate campaign
-- state. Reads remain published-generation-only; engineering releases clone the
-- current world without changing campaign state or day.

-- A pre-D save has no operation marker. Refuse the upgrade rather than guessing
-- whether an in-flight candidate is an ordinary save or an engineering release.
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT01-D migration refused: resolve the active campaign save before installing engineering-release lifecycle metadata';
  end if;
end;
$$;

alter table public.campaign_runtime
  add column if not exists staging_save_kind text,
  add column if not exists staging_engineering_git_ref text,
  add column if not exists staging_base_published_day integer,
  add column if not exists published_engineering_git_ref text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_staging_save_kind_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_staging_save_kind_check
      check (staging_save_kind is null or staging_save_kind in ('campaign_save', 'engineering_release'));
  end if;

  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_engineering_ref_shape_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_engineering_ref_shape_check
      check (
        (staging_engineering_git_ref is null or staging_engineering_git_ref ~ '^[0-9a-f]{40}$')
        and (published_engineering_git_ref is null or published_engineering_git_ref ~ '^[0-9a-f]{40}$')
      );
  end if;

  if not exists (
    select 1 from pg_constraint
     where conname = 'campaign_runtime_staging_kind_coherence_check'
       and conrelid = 'public.campaign_runtime'::regclass
  ) then
    alter table public.campaign_runtime
      add constraint campaign_runtime_staging_kind_coherence_check
      check (
        save_in_progress = (staging_save_kind is not null)
        and (
          (staging_save_kind = 'engineering_release' and staging_engineering_git_ref is not null)
          or
          (staging_save_kind is distinct from 'engineering_release' and staging_engineering_git_ref is null)
        )
      );
  end if;
end;
$$;

-- Ordinary saves retain the RT01-C contract and one-parent mirror shape. The
-- operation marker only lets shared stage/publish functions distinguish them
-- from engineering releases.
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
  v_now timestamptz;
begin
  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  v_now := clock_timestamp();

  if r.published_generation > 0 then
    if r.runtime_mirror_token is null then
      raise exception 'published generation % predates the RT01-C mirror contract; repair its mirror before a new save',
        r.published_generation;
    end if;
    if not r.runtime_published_confirmed then
      raise exception 'published generation % has a pending runtime-published mirror; repair it before a new save',
        r.published_generation;
    end if;
  end if;

  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;
  if r.save_in_progress and r.staging_save_kind = 'engineering_release' then
    raise exception 'expired engineering release must be resumed with the same engineering target';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  delete from public.campaign_state_generations where generation = v_next;
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  select v_next, csg.key, csg.value, now(), now()
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  update public.campaign_runtime
     set save_in_progress = true,
         staging_generation = v_next,
         lock_token = v_token,
         save_started_at = v_now,
         lock_expires_at = v_now + make_interval(mins => v_ttl),
         staging_save_kind = 'campaign_save',
         staging_engineering_git_ref = null,
         staging_base_published_day = null
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

-- Bind the exact approved-main target when the release begins. PostgreSQL owns
-- retry stability; the external worker separately proves reachability from the
-- fetched origin/main and validates the bounded engineering path set.
create or replace function public.begin_engineering_release(
  p_engineering_git_ref text,
  p_ttl_minutes integer default 30
)
returns table (
  published_generation bigint,
  published_git_ref text,
  published_day integer,
  staging_generation bigint,
  lock_token text,
  engineering_git_ref text,
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
  v_now timestamptz;
begin
  if p_engineering_git_ref is null or p_engineering_git_ref !~ '^[0-9a-f]{40}$' then
    raise exception 'engineering release target must be an exact full commit SHA';
  end if;

  perform set_config('rhc.gated_write', 'active', true);
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;

  v_now := clock_timestamp();
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or not r.runtime_published_confirmed
     or r.published_git_ref is null
     or r.last_confirmed_generation is distinct from r.published_generation
     or r.last_confirmed_git_ref is distinct from r.published_git_ref then
    raise exception 'engineering release requires a fully confirmed current published checkpoint';
  end if;

  if r.save_in_progress
     and r.lock_expires_at is not null
     and r.lock_expires_at > v_now then
    raise exception 'campaign save already in progress';
  end if;
  if r.save_in_progress and (
    r.staging_save_kind is distinct from 'engineering_release'
    or r.staging_engineering_git_ref is distinct from p_engineering_git_ref
  ) then
    raise exception 'engineering release retry must preserve the bound engineering target';
  end if;

  v_next := r.published_generation + 1;
  v_ttl := greatest(1, least(coalesce(p_ttl_minutes, 30), 120));
  v_token := gen_random_uuid()::text;

  delete from public.campaign_state_generations where generation = v_next;
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  select v_next, csg.key, csg.value, now(), now()
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  update public.campaign_runtime
     set save_in_progress = true,
         staging_generation = v_next,
         lock_token = v_token,
         save_started_at = v_now,
         lock_expires_at = v_now + make_interval(mins => v_ttl),
         staging_save_kind = 'engineering_release',
         staging_engineering_git_ref = p_engineering_git_ref,
         staging_base_published_day = r.published_day
   where id = 1;

  return query
  select cr.published_generation,
         cr.published_git_ref,
         cr.published_day,
         cr.staging_generation,
         cr.lock_token,
         cr.staging_engineering_git_ref,
         cr.lock_expires_at
    from public.campaign_runtime cr
   where cr.id = 1;
end;
$$;

revoke all on function public.begin_engineering_release(text, integer)
  from public, anon, authenticated;
grant execute on function public.begin_engineering_release(text, integer) to service_role;

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
         lock_expires_at = null,
         staging_save_kind = null,
         staging_engineering_git_ref = null,
         staging_base_published_day = null
   where id = 1;
end;
$$;

revoke all on function public.abort_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.abort_campaign_save(text) to service_role;

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
  v_mirror_token uuid;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;
  if r.staging_save_kind not in ('campaign_save', 'engineering_release') then
    raise exception 'active campaign save is missing a valid save kind';
  end if;

  if r.staging_save_kind = 'engineering_release' then
    if r.staging_engineering_git_ref is null then
      raise exception 'engineering release is missing its bound engineering target';
    end if;
    if r.published_day is distinct from r.staging_base_published_day then
      raise exception 'engineering_release may not change published day';
    end if;
    if exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
      ) missing_from_candidate
    ) or exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
      ) added_to_candidate
    ) then
      raise exception 'engineering_release may not change campaign state';
    end if;
  end if;

  v_mirror_token := gen_random_uuid();
  update public.campaign_runtime
     set published_generation = r.staging_generation,
         published_git_ref = null,
         runtime_mirror_token = v_mirror_token,
         runtime_mirror_base_git_ref = null,
         runtime_published_confirmed = false,
         runtime_published_confirmed_at = null,
         published_engineering_git_ref = r.staging_engineering_git_ref,
         save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null,
         staging_save_kind = null,
         staging_engineering_git_ref = null,
         staging_base_published_day = null,
         updated_at = now()
   where id = 1
   returning * into out_row;
  return out_row;
end;
$$;

revoke all on function public.publish_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.publish_campaign_save(text) to service_role;

create or replace function public.get_pending_runtime_mirror()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  r public.campaign_runtime%rowtype;
  v_state jsonb;
begin
  select * into r from public.campaign_runtime where id = 1;
  if not found then
    raise exception 'campaign_runtime singleton is not initialized';
  end if;
  if r.published_generation < 1
     or r.runtime_mirror_token is null
     or r.runtime_published_confirmed then
    raise exception 'no runtime-published mirror is pending';
  end if;

  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
   where csg.generation = r.published_generation;

  return jsonb_build_object(
    'schema_version', 1,
    'generation', r.published_generation,
    'published_day', r.published_day,
    'mirror_token', r.runtime_mirror_token::text,
    'last_confirmed_git_ref', r.last_confirmed_git_ref,
    'mirror_base_git_ref', r.runtime_mirror_base_git_ref,
    'engineering_git_ref', r.published_engineering_git_ref,
    'state', v_state
  );
end;
$$;

revoke all on function public.get_pending_runtime_mirror()
  from public, anon, authenticated;
grant execute on function public.get_pending_runtime_mirror()
  to service_role, rhc_mirror_verifier;

-- One coherent metadata block is used by context and targeted reads. A pending
-- SQL generation is current even though git_ref is null; the previous confirmed
-- ref is explicitly labelled current/stale rather than aliased to that generation.
create or replace function public._rhc_dm_runtime_metadata()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'generation', cr.published_generation,
    'git_ref', cr.published_git_ref,
    'day', cr.published_day,
    'mirror_confirmed', cr.runtime_published_confirmed,
    'mirror_confirmed_at', cr.runtime_published_confirmed_at,
    'last_confirmed_generation', cr.last_confirmed_generation,
    'last_confirmed_git_ref', cr.last_confirmed_git_ref,
    'fallback_freshness', case
      when cr.last_confirmed_git_ref is null then 'unavailable'
      when cr.runtime_published_confirmed
       and cr.last_confirmed_generation = cr.published_generation then 'current'
      else 'stale'
    end
  )
  from public.campaign_runtime cr
  where cr.id = 1
$$;

revoke all on function public._rhc_dm_runtime_metadata()
  from public, anon, authenticated, service_role;

-- Compact known index entries without expanding description/body/secret fields.
create or replace function public._rhc_compact_dm_index_array(
  p_items jsonb,
  p_limit integer
)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select coalesce(jsonb_agg(q.compact order by q.ordinality), '[]'::jsonb)
  from (
    select e.ordinality,
           jsonb_strip_nulls(jsonb_build_object(
             'id', e.item -> 'id',
             'title', e.item -> 'title',
             'label', e.item -> 'label',
             'summary', e.item -> 'summary',
             'status', e.item -> 'status',
             'visibility', e.item -> 'visibility',
             'priority', e.item -> 'priority',
             'influence', e.item -> 'influence',
             'current_day_update', e.item -> 'current_day_update',
             'source', e.item -> 'source'
           )) as compact
      from jsonb_array_elements(
        case when jsonb_typeof(p_items) = 'array' then p_items else '[]'::jsonb end
      ) with ordinality as e(item, ordinality)
     where jsonb_typeof(e.item) = 'object'
     order by e.ordinality
     limit greatest(0, least(coalesce(p_limit, 0), 100))
  ) q
$$;

revoke all on function public._rhc_compact_dm_index_array(jsonb, integer)
  from public, anon, authenticated, service_role;

create or replace function public.dm_quick_context()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_state jsonb;
  v_daily jsonb;
  v_live jsonb;
  v_day jsonb;
  v_meta jsonb;
  v_hooks jsonb;
  v_next_scene jsonb;
begin
  select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb)
    into v_state
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation;

  v_daily := coalesce(v_state -> 'daily_recap', '{}'::jsonb);
  v_live := coalesce(v_state -> 'live_status', '{}'::jsonb);
  v_day := coalesce(v_state -> 'day_resolution', '{}'::jsonb);
  v_meta := coalesce(v_state -> 'dm_meta', '{}'::jsonb);
  v_hooks := coalesce(v_state -> 'narrative_hooks', '{}'::jsonb);
  v_next_scene := case
    when jsonb_typeof(v_daily #> '{current_summary,next_scene_handoff}') = 'array'
      then jsonb_path_query_array(v_daily #> '{current_summary,next_scene_handoff}', '$[0 to 19]')
    else '[]'::jsonb
  end;

  return jsonb_build_object(
    'context_version', 1,
    'runtime', public._rhc_dm_runtime_metadata(),
    'scene', jsonb_build_object(
      'status', coalesce(v_daily -> 'status', '"unknown"'::jsonb),
      'next_scene_handoff', v_next_scene,
      'hooks', jsonb_build_object(
        'day_status', coalesce(v_hooks -> 'day_status', '"unknown"'::jsonb),
        'active', public._rhc_compact_dm_index_array(v_hooks -> 'active_hooks', 20),
        'dormant', public._rhc_compact_dm_index_array(v_hooks -> 'dormant_hooks', 20),
        'closed_today', public._rhc_compact_dm_index_array(v_hooks -> 'closed_hooks_today', 20)
      )
    ),
    'world', jsonb_build_object(
      'status', coalesce(v_live -> 'status', '"unknown"'::jsonb),
      'current_day', v_live -> 'current_day',
      'party_state', coalesce(v_live -> 'party_state', '{}'::jsonb),
      'campaign_resources', coalesce(v_live -> 'campaign_resources', '{}'::jsonb),
      'organizations', coalesce(v_live -> 'organizations', '{}'::jsonb),
      'assets', coalesce(v_live -> 'assets', '{}'::jsonb),
      'persistent_effects', case
        when jsonb_typeof(v_live -> 'persistent_effects') = 'array'
          then jsonb_path_query_array(v_live -> 'persistent_effects', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'financial_obligations', coalesce(v_live -> 'financial_obligations', '{}'::jsonb)
    ),
    'today', jsonb_build_object(
      'status', coalesce(v_day -> 'status', '"unknown"'::jsonb),
      'current_day', v_day -> 'current_day',
      'rng_rolls', case
        when jsonb_typeof(v_day -> 'rng_rolls') = 'array'
          then jsonb_path_query_array(v_day -> 'rng_rolls', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'mechanical_resolutions', case
        when jsonb_typeof(v_day -> 'mechanical_resolutions') = 'array'
          then jsonb_path_query_array(v_day -> 'mechanical_resolutions', '$[0 to 49]')
        else '[]'::jsonb
      end,
      'persistent_effects_applied', case
        when jsonb_typeof(v_day -> 'persistent_effects_applied') = 'array'
          then jsonb_path_query_array(v_day -> 'persistent_effects_applied', '$[0 to 49]')
        else '[]'::jsonb
      end
    ),
    'dm_index', jsonb_build_object(
      'status', coalesce(v_meta -> 'status', '"unknown"'::jsonb),
      'committed_hidden_truths', public._rhc_compact_dm_index_array(v_meta -> 'committed_hidden_truths', 50),
      'durable_dm_plans', public._rhc_compact_dm_index_array(v_meta -> 'durable_dm_plans', 50),
      'ghost_seeds', public._rhc_compact_dm_index_array(v_meta -> 'ghost_seeds', 50),
      'unresolved_reveal_conditions', public._rhc_compact_dm_index_array(v_meta -> 'unresolved_reveal_conditions', 50)
    )
  );
end;
$$;

create or replace function public.dm_runtime_lookup(
  p_query text,
  p_limit integer default 20
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_query text;
  v_limit integer;
  v_results jsonb;
begin
  v_query := btrim(coalesce(p_query, ''));
  if v_query = '' then
    raise exception 'runtime lookup query is required';
  end if;
  if char_length(v_query) > 200 then
    raise exception 'runtime lookup query exceeds 200 characters';
  end if;
  v_limit := greatest(1, least(coalesce(p_limit, 20), 100));

  select coalesce(jsonb_agg(q.result order by q.score desc, q.key), '[]'::jsonb)
    into v_results
    from (
      select csg.key,
             case
               when lower(csg.key) = lower(v_query) then 100
               when lower(csg.key) like lower(v_query) || '%' then 80
               when position(lower(v_query) in lower(csg.key)) > 0 then 60
               else 20
             end as score,
             jsonb_build_object(
               'key', csg.key,
               'value', csg.value
             ) as result
        from public.campaign_state_generations csg
        join public.campaign_runtime cr
          on cr.id = 1
         and csg.generation = cr.published_generation
       where position(lower(v_query) in lower(csg.key || ' ' || csg.value::text)) > 0
       order by score desc, csg.key
       limit v_limit
    ) q;
  return v_results;
end;
$$;

create or replace function public.dm_runtime_read(
  p_query text default null,
  p_limit integer default 20
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_context jsonb;
begin
  if p_query is null or btrim(p_query) = '' then
    v_context := public.dm_quick_context();
    return jsonb_build_object(
      'read_version', 1,
      'mode', 'context',
      'runtime', v_context -> 'runtime',
      'context', v_context - 'runtime'
    );
  end if;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'lookup',
    'runtime', public._rhc_dm_runtime_metadata(),
    'query', btrim(p_query),
    'results', public.dm_runtime_lookup(p_query, p_limit)
  );
end;
$$;

revoke all on function public.dm_quick_context()
  from public, anon, authenticated;
revoke all on function public.dm_runtime_lookup(text, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.dm_runtime_read(text, integer)
  from public, anon, authenticated;
grant execute on function public.dm_quick_context() to service_role;
grant execute on function public.dm_runtime_read(text, integer) to service_role;

-- RT01-A/B allowed service tooling to inspect the raw generation store before a
-- consumer facade existed. RT01-D makes that facade the service read boundary,
-- so staging/future generations must no longer be directly readable.
revoke select on table public.campaign_state_generations from service_role;

comment on column public.campaign_runtime.published_engineering_git_ref is
  'Exact approved origin/main commit bound to the current engineering_release generation; null for ordinary campaign saves.';
comment on function public.begin_engineering_release(text, integer) is
  'Begins a state/day-preserving engineering release from a fully confirmed runtime checkpoint and durably binds one exact target SHA.';
comment on function public.dm_runtime_read(text, integer) is
  'Unified service-only published-runtime facade: compact context for a blank query, bounded targeted lookup otherwise, with coherent checkpoint/fallback metadata in both modes.';

-- ============================================================================
-- SOURCE MIGRATION: 20260911000001_rt02_campaign_clock.sql
-- ============================================================================

-- RT02 — Campaign Clock Foundation
-- Rolling High Club deterministic in-world time authority on the RT01 spine.
--
-- This migration adds the FIRST validated Clock mutation route without creating
-- any parallel persistence path. The Clock is one engine-owned runtime state
-- record keyed as `campaign_clock` inside the existing generation store, mutated
-- ONLY through this route and published through the existing guarded Save Gateway.
--
-- Clock record shape (schema_version 1):
--   {
--     "schema_version": 1,
--     "day": null | <non-negative integer>,
--     "phase": "unknown" | "dawn" | "morning" | "midday" | "afternoon"
--            | "evening" | "night" | "late_night",
--     "elapsed_campaign_minutes": <non-negative integer>,
--     "long_rests_completed": <non-negative integer>
--   }
--
-- Two time representations deliberately coexist without inferring each other:
--   * presentation day/phase (broad, may be partially unknown);
--   * monotonic `elapsed_campaign_minutes` (engine cursor from the RT02 epoch).
--
-- WHAT this migration changes:
--   1. `public.stage_campaign_clock(...)` — the ONLY validated Clock mutation
--      route. It validates Clock shape and monotonic/coherence invariants against
--      the authoritative published Clock, then stages the candidate value.
--   2. `public.stage_campaign_state(...)` / `delete_staged_campaign_state(...)`
--      now REJECT the `campaign_clock` key, closing the generic bypass.
--   3. `public.publish_campaign_save(...)` now DERIVES `published_day` from the
--      candidate Clock day so the locator never becomes a second day authority.
--
-- No new table, no new Git mirror, no scheduler/autosave, no campaign facts.
-- Unknown remains valid truth: an absent Clock or a null day is never coerced.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight.
--    A pre-RT02 active save's candidate generation may already contain a
--    `campaign_clock` staged through the (pre-RT02) generic staging route. The
--    RT02 publisher only derives `day` and would let that invalid candidate
--    publish. Mirroring RT01-C/D, refuse rather than guess.
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT02 migration refused: resolve the active campaign save before installing the Campaign Clock mutation route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Broad-phase ordering (internal). `unknown` has no order and is never used
--    as an ordering input because regression checks only compare known phases.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_phase_order(p_phase text)
returns integer
language sql
immutable
set search_path = ''
as $$
  select case p_phase
    when 'dawn' then 0
    when 'morning' then 1
    when 'midday' then 2
    when 'afternoon' then 3
    when 'evening' then 4
    when 'night' then 5
    when 'late_night' then 6
    else null
  end
$$;

revoke all on function public._rhc_phase_order(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Clock shape validation + canonical normalization (internal).
--    Returns the canonical Clock object or raises on any invalid field.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_campaign_clock(p_clock jsonb)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_day integer;
  v_phase text;
  v_elapsed integer;
  v_rests integer;
begin
  if p_clock is null or jsonb_typeof(p_clock) <> 'object' then
    raise exception 'campaign_clock must be a JSON object';
  end if;
  if (p_clock ->> 'schema_version') is distinct from '1' then
    raise exception 'campaign_clock schema_version must be 1';
  end if;

  -- day: null (Unknown) or a non-negative integer. Never coerced to 0/1.
  if jsonb_typeof(p_clock -> 'day') = 'null' then
    v_day := null;
  elsif jsonb_typeof(p_clock -> 'day') = 'number'
        and (p_clock ->> 'day') ~ '^[0-9]+$' then
    v_day := (p_clock ->> 'day')::integer;
  else
    raise exception 'campaign_clock day must be null or a non-negative integer';
  end if;

  -- phase: exactly one enumerated broad phase.
  v_phase := p_clock ->> 'phase';
  if v_phase is null then
    raise exception 'campaign_clock phase is required';
  end if;
  if v_phase not in (
    'unknown','dawn','morning','midday','afternoon','evening','night','late_night'
  ) then
    raise exception 'campaign_clock phase must be an enumerated broad phase';
  end if;

  -- elapsed_campaign_minutes: non-negative integer engine cursor.
  if jsonb_typeof(p_clock -> 'elapsed_campaign_minutes') = 'number'
     and (p_clock ->> 'elapsed_campaign_minutes') ~ '^[0-9]+$' then
    v_elapsed := (p_clock ->> 'elapsed_campaign_minutes')::integer;
  else
    raise exception 'campaign_clock elapsed_campaign_minutes must be a non-negative integer';
  end if;

  -- long_rests_completed: non-negative integer engine counter.
  if jsonb_typeof(p_clock -> 'long_rests_completed') = 'number'
     and (p_clock ->> 'long_rests_completed') ~ '^[0-9]+$' then
    v_rests := (p_clock ->> 'long_rests_completed')::integer;
  else
    raise exception 'campaign_clock long_rests_completed must be a non-negative integer';
  end if;

  return jsonb_build_object(
    'schema_version', 1,
    'day', v_day,
    'phase', v_phase,
    'elapsed_campaign_minutes', v_elapsed,
    'long_rests_completed', v_rests
  );
end;
$$;

revoke all on function public._rhc_normalize_campaign_clock(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Validated Clock mutation route (the ONLY way to stage `campaign_clock`).
--
--    The caller supplies the complete TARGET Clock state. The target is
--    absolute, not a delta, so replaying one logical update re-stages the same
--    value and cannot double-advance the monotonic cursors. The transition is
--    validated against the authoritative PUBLISHED Clock (not the candidate),
--    so a partial in-save edit can never relax a published invariant.
-- ---------------------------------------------------------------------------
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

  -- Established day never decreases and never erases to Unknown.
  if v_bday is not null then
    if v_tday is null then
      raise exception 'campaign_clock day cannot be unset once established';
    end if;
    if v_tday < v_bday then
      raise exception 'campaign_clock day cannot move backwards';
    end if;
  end if;

  -- A known same-day phase never moves to an earlier known phase and never
  -- erases to Unknown. A later day may begin at any valid phase.
  if v_tday is not null and v_tday = v_bday and v_bphase <> 'unknown' then
    if v_tphase = 'unknown' then
      raise exception 'campaign_clock phase cannot become unknown on the established day';
    end if;
    if public._rhc_phase_order(v_tphase) < public._rhc_phase_order(v_bphase) then
      raise exception 'campaign_clock phase cannot move backwards within the same day';
    end if;
  end if;

  -- Monotonic engine cursors never decrease.
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

-- ---------------------------------------------------------------------------
-- 4. Close the generic `campaign_clock` bypass. The generic stage/delete must
--    never accept an engine-owned Clock record, malformed or otherwise.
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
-- 5. Publication coherence. `published_day` is DERIVED from the candidate Clock
--    day so the locator can never become an independent second day authority.
--    An absent Clock or a null day keeps `published_day` null (Unknown).
-- ---------------------------------------------------------------------------
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
  v_mirror_token uuid;
  v_published_day integer;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_generation is distinct from r.published_generation + 1 then
    raise exception 'staging generation % is not the next generation after published %',
      r.staging_generation, r.published_generation;
  end if;
  if r.staging_save_kind not in ('campaign_save', 'engineering_release') then
    raise exception 'active campaign save is missing a valid save kind';
  end if;

  -- Derive the published day locator from the candidate Clock day. Because every
  -- Clock value is validated at stage time and copy-forwarded by BEGIN, a Clock
  -- present here is well-formed; the regex guard is defense-in-depth only.
  select case
           when jsonb_typeof(csg.value -> 'day') = 'number'
            and (csg.value ->> 'day') ~ '^[0-9]+$'
           then (csg.value ->> 'day')::integer
           else null
         end
    into v_published_day
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'campaign_clock';

  if r.staging_save_kind = 'engineering_release' then
    if r.staging_engineering_git_ref is null then
      raise exception 'engineering release is missing its bound engineering target';
    end if;
    if r.published_day is distinct from r.staging_base_published_day then
      raise exception 'engineering_release may not change published day';
    end if;
    if v_published_day is distinct from r.published_day then
      raise exception 'engineering_release may not change the campaign clock day';
    end if;
    if exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
      ) missing_from_candidate
    ) or exists (
      select 1 from (
        (select key, value from public.campaign_state_generations where generation = r.staging_generation)
        except
        (select key, value from public.campaign_state_generations where generation = r.published_generation)
      ) added_to_candidate
    ) then
      raise exception 'engineering_release may not change campaign state';
    end if;
  end if;

  v_mirror_token := gen_random_uuid();
  update public.campaign_runtime
     set published_generation = r.staging_generation,
         published_git_ref = null,
         runtime_mirror_token = v_mirror_token,
         runtime_mirror_base_git_ref = null,
         runtime_published_confirmed = false,
         runtime_published_confirmed_at = null,
         published_engineering_git_ref = r.staging_engineering_git_ref,
         published_day = v_published_day,
         save_in_progress = false,
         staging_generation = null,
         lock_token = null,
         save_started_at = null,
         lock_expires_at = null,
         staging_save_kind = null,
         staging_engineering_git_ref = null,
         staging_base_published_day = null,
         updated_at = now()
   where id = 1
   returning * into out_row;
  return out_row;
end;
$$;

revoke all on function public.publish_campaign_save(text)
  from public, anon, authenticated;
grant execute on function public.publish_campaign_save(text) to service_role;

comment on function public.stage_campaign_clock(text, jsonb) is
  'RT02: the only validated Clock mutation route. Stages an absolute target Clock after shape + monotonic/coherence validation against the authoritative published Clock. Replay-safe by construction.';
comment on function public.stage_campaign_state(text, text, jsonb) is
  'RT01-B/RT02: generic runtime-state staging. The engine-owned campaign_clock key is rejected here and must use stage_campaign_clock.';

-- ============================================================================
-- SOURCE MIGRATION: 20260911000002_rt03_canonical_run_runtime_read.sql
-- ============================================================================

-- RT03 — Canonical Run Runtime Read (09B-ID canary)
-- Rolling High Club read-only Run resolution on the RT01 published-runtime spine.
--
-- WHAT this migration changes:
--   1. `public.dm_runtime_read_run(<run_id>)` — the supported service-facing
--      canonical Run read. One exact EV2-08-valid Run from the current
--      published generation, returned inside the same RT01-D runtime
--      metadata envelope used by every other supported read.
--   2. Internal-only EV2-08 Run shape/coherence validation helpers beneath it.
--
-- Run namespace rule (deterministic, system-owned):
--   The ONLY system-owned Run records in a published generation are the JSON
--   object entries of the published state key `runs`, whose value must be a
--   JSON array. Identity matching is exact: an entry is a candidate for
--   `<run_id>` only when it is an object whose string `run_id` field equals
--   `<run_id>` exactly. Any other runtime JSON that merely contains a
--   run_id-looking value is discovery noise, never Run authority.
--
-- Resolution rules (all fail closed):
--   * malformed `run_id` (not `R` + >= 2 digits, absolute end) -> refuse;
--   * a published `runs` value that is not a JSON array -> refuse;
--   * more than one candidate claiming one identity -> refuse (no first-match);
--   * a matching candidate that violates EV2-08 (including a played Run whose
--     control_state is absent or invalid) -> refuse;
--   * a matching candidate whose mutable owners are also claimed by another
--     published Run entry -> refuse (EV2-08 Run-batch unique mutable ownership);
--   * exactly zero candidates -> truthful absence: `run: null` with coherent
--     runtime metadata. No default Run is ever fabricated.
--
-- RT03 is read-only: it stages nothing, mutates nothing, seeds nothing, owns
-- no Clock arithmetic, performs no Git/repository resolution, and returns
-- minimum trusted Run context (the record itself, never a hydrated graph).
-- EV2-08 remains the Run contract; EV2-09A proposals remain non-canonical.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT01-D/RT02 forward-only installation pattern.
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT03 migration refused: resolve the active campaign save before installing the canonical Run read';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Absolute-end identity matching (internal). PostgreSQL `$` also matches
--    before a trailing newline; the EV2-08 patterns reject any trailing
--    character (`(?![\s\S])`), so the newline case is cancelled explicitly.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_full_id_match(
  p_value text,
  p_pattern text
)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select p_value is not null
     and p_value ~ p_pattern
     and p_value !~ E'\n$'
$$;

revoke all on function public._rhc_full_id_match(text, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. String identity-array validation (internal). Mirrors the EV2-08 schema:
--    JSON array, unique items, every item a string inside the given identity
--    pattern, with an optional minimum length.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_require_string_id_array(
  p_arr jsonb,
  p_label text,
  p_pattern text,
  p_min_items integer
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_count integer;
  v_distinct integer;
  v_item jsonb;
begin
  if p_arr is null or jsonb_typeof(p_arr) is distinct from 'array' then
    raise exception 'Run % must be a JSON array', p_label;
  end if;
  v_count := jsonb_array_length(p_arr);
  if v_count < greatest(0, coalesce(p_min_items, 0)) then
    raise exception 'Run % requires at least % item(s)', p_label, p_min_items;
  end if;
  select count(*), count(distinct item)
    into v_count, v_distinct
    from jsonb_array_elements(p_arr) item;
  if v_distinct < v_count then
    raise exception 'Run % must not contain duplicate entries', p_label;
  end if;
  for v_item in select * from jsonb_array_elements(p_arr) loop
    if not public._rhc_full_id_match(v_item #>> '{}', p_pattern) then
      raise exception 'Run % contains an entry outside its EV2-08 identity pattern', p_label;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_require_string_id_array(jsonb, text, text, integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. EV2-08 Run record validation (internal). Shape, identity patterns,
--    execution/control coherence and record-internal ownership semantics only.
--    Cross-domain resolution (Scenario/Encounter existence, anchor Git
--    reachability) stays owned by the repository EV2-08 validator; the runtime
--    read never fetches Git or repository files.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_run_record(p_run jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_mode text;
  v_state text;
  v_anchor jsonb;
begin
  if p_run is null or jsonb_typeof(p_run) is distinct from 'object' then
    raise exception 'Run must be a JSON object';
  end if;

  if not p_run ?& array[
    'run_id', 'execution_mode', 'control_state', 'scenario_id',
    'occurred_encounter_ids', 'participant_entity_ids',
    'mutable_owner_entity_ids', 'location_ids', 'campaign_anchor'
  ] then
    raise exception 'Run is missing a required EV2-08 field';
  end if;

  if (
    p_run - 'run_id' - 'execution_mode' - 'control_state' - 'scenario_id'
        - 'occurred_encounter_ids' - 'party_id' - 'participant_entity_ids'
        - 'mutable_owner_entity_ids' - 'location_ids' - 'campaign_anchor'
        - 'outcome_summary'
  ) <> '{}'::jsonb then
    raise exception 'Run contains fields outside the EV2-08 contract';
  end if;

  if not public._rhc_full_id_match(p_run ->> 'run_id', '^R[0-9]{2,}$') then
    raise exception 'Run run_id must be R followed by at least two digits';
  end if;

  v_mode := p_run ->> 'execution_mode';
  if v_mode is null or v_mode not in ('played', 'off_screen') then
    raise exception 'Run execution_mode must be played or off_screen';
  end if;

  v_state := p_run ->> 'control_state';
  -- Null-safe on purpose: `v_state not in (...)` silently evaluates to SQL
  -- NULL for a JSON-null control state, which would let an invalid played
  -- Run slip through as trusted context.
  if v_mode = 'played'
     and (v_state is null or v_state not in ('active', 'parked')) then
    raise exception 'played Run control_state must be active or parked';
  end if;
  if v_mode = 'off_screen' and v_state is distinct from 'not_applicable' then
    raise exception 'off_screen Run control_state must be not_applicable';
  end if;

  if not public._rhc_full_id_match(p_run ->> 'scenario_id', '^S[0-9]{2,}$') then
    raise exception 'Run scenario_id must be S followed by at least two digits';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'occurred_encounter_ids', 'occurred_encounter_ids', '^E[0-9]{2,}$', 0);

  if p_run ? 'party_id'
     and not public._rhc_full_id_match(
       p_run ->> 'party_id', '^party:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'Run party_id must be party: followed by a slug';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'participant_entity_ids', 'participant_entity_ids',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$', 1);

  perform public._rhc_require_string_id_array(
    p_run -> 'mutable_owner_entity_ids', 'mutable_owner_entity_ids',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$', 0);

  if not ((p_run -> 'mutable_owner_entity_ids')
            <@ (p_run -> 'participant_entity_ids')) then
    raise exception 'Run mutable owner must also appear in participant_entity_ids';
  end if;

  perform public._rhc_require_string_id_array(
    p_run -> 'location_ids', 'location_ids',
    '^location:[a-z0-9]+(-[a-z0-9]+)*$', 0);

  v_anchor := p_run -> 'campaign_anchor';
  if v_anchor is null or jsonb_typeof(v_anchor) is distinct from 'object' then
    raise exception 'Run campaign_anchor must be a JSON object';
  end if;
  if not v_anchor ?& array['base_commit', 'campaign_time'] then
    raise exception 'Run campaign_anchor requires base_commit and campaign_time';
  end if;
  if (v_anchor - 'base_commit' - 'campaign_time') <> '{}'::jsonb then
    raise exception 'Run campaign_anchor contains fields outside the EV2-08 contract';
  end if;
  if not public._rhc_full_id_match(v_anchor ->> 'base_commit', '^[0-9a-f]{40}$') then
    raise exception 'Run campaign_anchor.base_commit must be an exact 40-character lowercase hex commit';
  end if;
  if jsonb_typeof(v_anchor -> 'campaign_time') is distinct from 'string'
     or (v_anchor ->> 'campaign_time') !~ '\S' then
    raise exception 'Run campaign_anchor.campaign_time must be a non-blank label';
  end if;

  if p_run ? 'outcome_summary'
     and (jsonb_typeof(p_run -> 'outcome_summary') is distinct from 'string'
          or (p_run ->> 'outcome_summary') !~ '\S') then
    raise exception 'Run outcome_summary must be a non-blank string';
  end if;

  return true;
end;
$$;

revoke all on function public._rhc_validate_run_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Supported service-facing canonical Run read. Published-generation-only,
--    metadata-bearing, exact identity, fail-closed. Returns truthful absence
--    as `run: null` without fabricating a default Run.
-- ---------------------------------------------------------------------------
create or replace function public.dm_runtime_read_run(p_run_id text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_id text;
  v_runs jsonb;
  v_matches jsonb;
  v_count integer;
  v_run jsonb;
  v_owners jsonb;
  v_other jsonb;
  v_other_owners jsonb;
  v_conflict text;
begin
  v_id := coalesce(p_run_id, '');
  if not public._rhc_full_id_match(v_id, '^R[0-9]{2,}$') then
    raise exception 'run_id must be R followed by at least two digits';
  end if;

  select csg.value into v_runs
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'runs'
   where cr.id = 1;

  if found and v_runs is not null then
    if jsonb_typeof(v_runs) is distinct from 'array' then
      raise exception 'published runs state is unreadable; refusing to treat it as Run authority';
    end if;

    select coalesce(jsonb_agg(item), '[]'::jsonb), count(*)
      into v_matches, v_count
      from jsonb_array_elements(v_runs) item
     where jsonb_typeof(item) = 'object'
       and item ->> 'run_id' = v_id;

    if v_count > 1 then
      raise exception 'duplicate authoritative Run claims for %; failing closed', v_id;
    end if;
    if v_count = 1 then
      v_run := v_matches -> 0;
      perform public._rhc_validate_run_record(v_run);

      -- EV2-08 Run-batch law: across the published Run batch an actor may
      -- appear in at most one `mutable_owner_entity_ids` list. The requested
      -- Run is trusted only when no other published Run entry claims one of
      -- its mutable owners. A zero-claim Run cannot conflict, so the
      -- namespace is only read for the uniqueness proof when the requested
      -- Run claims owners; an unreadable owner list where overlap is still
      -- possible fails closed.
      v_owners := v_run -> 'mutable_owner_entity_ids';
      if jsonb_array_length(v_owners) > 0 then
        -- Only entries claiming a string Run identity participate in the
        -- uniqueness proof; namespace noise without one cannot hold a
        -- controller token (same rule as identity matching).
        for v_other in
          select item
            from jsonb_array_elements(v_runs) item
           where jsonb_typeof(item) = 'object'
             and jsonb_typeof(item -> 'run_id') = 'string'
             and (item ->> 'run_id') is distinct from v_id
        loop
          v_other_owners := v_other -> 'mutable_owner_entity_ids';
          if v_other_owners is null
             or jsonb_typeof(v_other_owners) is distinct from 'array' then
            raise exception
              'published Run % has an unreadable mutable_owner_entity_ids list; mutable-owner uniqueness cannot be proven',
              v_other ->> 'run_id';
          end if;
          select oo #>> '{}'
            into v_conflict
            from jsonb_array_elements(v_other_owners) oo
           where v_owners ? (oo #>> '{}')
           limit 1;
          if found then
            raise exception
              'mutable owner % is claimed by both % and %; EV2-08 allows at most one mutable-owner claim per actor across the published Run batch',
              v_conflict, v_id, v_other ->> 'run_id';
          end if;
        end loop;
      end if;
    end if;
  end if;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'run',
    'run_id', v_id,
    'runtime', public._rhc_dm_runtime_metadata(),
    'run', v_run
  );
end;
$$;

revoke all on function public.dm_runtime_read_run(text)
  from public, anon, authenticated;
grant execute on function public.dm_runtime_read_run(text) to service_role;

comment on function public.dm_runtime_read_run(text) is
  'RT03: supported service-facing canonical Run read. Resolves one exact EV2-08-valid Run from the current published generation inside the RT01-D runtime metadata envelope. Truthful absence returns run: null; malformed identity, unreadable namespace, duplicate claims, an EV2-08-invalid match (including a played Run with an absent or invalid control state) or a cross-Run mutable-owner conflict fail closed.';
comment on function public._rhc_validate_run_record(jsonb) is
  'RT03 internal EV2-08 Run shape/coherence validation. Internal-only: not executable by service consumers, so Run data is reachable only through the metadata-bearing supported read.';

-- ============================================================================
-- SOURCE MIGRATION: 20260912000001_rt04_safe_run_reconciliation.sql
-- ============================================================================

-- RT04 — Safe Run Reconciliation
-- Rolling High Club legality + translation layer in front of the existing RT01
-- Save Gateway / publication spine. RT04 is NOT a second save engine.
--
-- WHAT this migration changes:
--   1. `public.reconcile_run_resolution(p_lock_token, p_request)` — the ONLY
--      validated Run-reconciliation staging route. It runs INSIDE the normal
--      campaign save lifecycle (`begin_campaign_save` -> reconcile -> publish),
--      proves the source Run is still the current legal controller, translates
--      the accepted EV2-09A resolution into the bounded mutations the current
--      repository truth can express, and records a replay-proof consumption
--      marker. It never creates an alternate `reconcile_publish`, an independent
--      generation counter, a second database truth, a separate mirror path or a
--      parallel save lifecycle.
--   2. An engine-owned `run_reconciliations` consumption ledger inside the
--      existing generation store. It is staged only by this route; the generic
--      `stage_campaign_state` / `delete_staged_campaign_state` routes reject the
--      key (the same closure RT02 applies to `campaign_clock`) so the
--      idempotency proof cannot be bypassed or erased.
--
-- SOURCE TRUTH (never caller self-certified):
--   The source Run is resolved ONLY through the RT03 authoritative published
--   read `public.dm_runtime_read_run(...)`. Caller-supplied Run-shaped payload
--   is not source truth. The published `runs` batch decides whether the Run
--   still exists and what it currently owns. A resolution proposal identifies a
--   Run but never certifies it.
--
-- BOUNDED TRANSLATION (no whole-world replacement, no JSON Patch language):
--   Under current repository truth the only legal durable mutation surfaces for
--   an accepted reconciliation are the source Run's own EV2-08 record (its
--   `outcome_summary`, and its mutable ownership / control state for the
--   continuation-vs-collapse law) plus the consumption ledger. Accepted
--   consequences that target domains with no legal durable mutation surface yet
--   (entity state, inventory/custody, Hook mutation, location world changes,
--   knowledge, ...) are PRESERVED in the durable ledger and REPORTED with the
--   exact missing downstream owner (including their validated human-readable
--   `summary`, so the meaning of a consumed resolution is never lost). They are
--   never silently dropped and RT04 never invents those subsystems.
--
-- ONE RECONCILIATION PER SOURCE RUN PER SAVE (self-contradiction guard):
--   Within one active campaign save, one source `run_id` may be reconciled at
--   most once. A second distinct resolution for the same Run is refused even
--   though its `resolution_id` is fresh: it would reconstruct the source Run
--   from the PUBLISHED record instead of the already-staged reconciliation
--   result and could resurrect ownership the first reconciliation just
--   released. This is one backend save context contradicting its own staged
--   mutation — not a second player save; QuickSave remains a frozen-frame
--   operation and no concurrency machinery exists here. Chaining from the
--   published result of a PRIOR save remains legal (new save, new candidate).
--
-- CANDIDATE RUN OWNERSHIP LAW (validated before anything is staged):
--   The complete candidate `runs` batch this route is about to preserve or
--   publish is validated as a whole: no mutable entity may be claimed by more
--   than one Run in the candidate state, and a pre-staged sibling Run may not
--   claim an entity the source Run still owns in published reality (a staged
-- claim is never honored as an ownership transfer — `released_mutable_owners`
--   is subtractive-only). Contradictory candidates fail closed before any
--   write. Once a reconciliation is NEWLY staged in a save, the candidate
--   `runs` batch is engine-owned for the rest of that save: the generic staging
--   and deletion routes refuse the `runs` key so a later same-save mutation
--   cannot reintroduce overlap or erase the reconciled candidate before
--   publication. Historical receipts copied forward from published reality do
--   not trigger the closure — the guard detects only markers this save added
--   on top of the published ledger.
--
-- CONTINUATION VS COLLAPSE (Run is not auto-terminated by synchronization):
--   If the accepted reconciliation releases mutable owners and the Run still has
--   owners, the Run continues as their current continuation lane (control state
--   unchanged). If the Run ends with zero mutable owners, its mutable authority
--   is removed and a played Run collapses to `parked` (historical participation
--   is preserved; stale write authority is not). Off-screen Runs keep
--   `not_applicable` control state and simply lose released owners.
--
-- RT04 is not the future Hard Write Boundary patch: generic staging of the
-- `runs` batch remains the pre-existing RT01-B behavior. This route guarantees
-- that the *reconciliation* path itself fails closed and uses the gateway.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03 forward-only installation pattern.
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
      from public.campaign_runtime
     where id = 1
       and save_in_progress
  ) then
    raise exception
      'RT04 migration refused: resolve the active campaign save before installing the Run reconciliation route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Outcome band classification (internal). Mirrors the EV2-09A approved
--    resolution mechanic exactly.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_band_for_roll(p_roll integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_roll = 1 then 'critical_trigger'
    when p_roll between 2 and 5 then 'bad'
    when p_roll between 6 and 10 then 'below_average'
    when p_roll between 11 and 16 then 'normal'
    when p_roll between 17 and 19 then 'above_average'
    when p_roll = 20 then 'exceptional'
    else null
  end
$$;

revoke all on function public._rhc_band_for_roll(integer)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_band_for_severity(p_roll integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_roll between 1 and 2 then 'minor'
    when p_roll between 3 and 4 then 'moderate'
    when p_roll = 5 then 'serious'
    when p_roll = 6 then 'catastrophic'
    else null
  end
$$;

revoke all on function public._rhc_band_for_severity(integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Generic string-identity array validation (internal). JSON array, unique
--    items, every item a string inside the given identity pattern.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_require_entity_id_array(
  p_arr jsonb,
  p_label text,
  p_pattern text
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_count integer;
  v_distinct integer;
  v_item jsonb;
begin
  if p_arr is null or jsonb_typeof(p_arr) is distinct from 'array' then
    raise exception '% must be a JSON array', p_label;
  end if;
  select count(*), count(distinct item)
    into v_count, v_distinct
    from jsonb_array_elements(p_arr) item;
  if v_distinct < v_count then
    raise exception '% must not contain duplicate entries', p_label;
  end if;
  for v_item in select * from jsonb_array_elements(p_arr) loop
    if not public._rhc_full_id_match(v_item #>> '{}', p_pattern) then
      raise exception '% contains an entry outside its EV2-09A identity pattern', p_label;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_require_entity_id_array(jsonb, text, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Released mutable-owner validation (internal). Optional; when present it
--    must be a JSON array of unique character/creature identities.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_released_owners(p_arr jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_arr is null or jsonb_typeof(p_arr) = 'null' then
    return true;
  end if;
  perform public._rhc_require_entity_id_array(
    p_arr, 'released_mutable_owners',
    '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$');
  return true;
end;
$$;

revoke all on function public._rhc_validate_released_owners(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. EV2-09A proposal contract validation (internal, SQL-level). Shape, exact
--    identity patterns, exact band/severity classification, bounded consequence
--    vocabulary and references. Cross-domain Scenario/Hook content resolution
--    (git-anchored) remains owned by the repository EV2-09A validator; this
--    helper enforces the full EV2-09A *schema/mechanics* contract so a malformed
--    or self-inconsistent proposal can never reach the save boundary.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_resolution_proposal(p_proposal jsonb)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_required text[] := array[
    'resolution_id', 'run_id', 'scenario_id', 'primary_hook_id',
    'campaign_anchor', 'objective_context', 'primary_roll',
    'outcome_band', 'proposed_consequences'
  ];
  v_anchor jsonb;
  v_obj_ctx jsonb;
  v_roll integer;
  v_band text;
  v_sev_roll integer;
  v_sev_band text;
  v_consequences jsonb;
  v_c jsonb;
  v_cid text;
  v_scope text;
  v_kind text;
  v_seen text[] := '{}';
begin
  if p_proposal is null or jsonb_typeof(p_proposal) is distinct from 'object' then
    raise exception 'resolution must be a JSON object';
  end if;
  if not p_proposal ?& v_required then
    raise exception 'resolution is missing a required EV2-09A field';
  end if;
  if (
    p_proposal - 'resolution_id' - 'run_id' - 'scenario_id' - 'primary_hook_id'
        - 'campaign_anchor' - 'objective_context' - 'primary_roll'
        - 'outcome_band' - 'severity_roll' - 'severity_band'
        - 'proposed_consequences'
  ) <> '{}'::jsonb then
    raise exception 'resolution contains fields outside the EV2-09A contract';
  end if;

  if not public._rhc_full_id_match(p_proposal ->> 'resolution_id', '^RP[0-9]{2,}$') then
    raise exception 'resolution_id must be RP followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'run_id', '^R[0-9]{2,}$') then
    raise exception 'resolution run_id must be R followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'scenario_id', '^S[0-9]{2,}$') then
    raise exception 'resolution scenario_id must be S followed by at least two digits';
  end if;
  if not public._rhc_full_id_match(p_proposal ->> 'primary_hook_id', '^H[0-9]{2,}$') then
    raise exception 'resolution primary_hook_id must be H followed by at least two digits';
  end if;

  v_anchor := p_proposal -> 'campaign_anchor';
  if v_anchor is null or jsonb_typeof(v_anchor) is distinct from 'object' then
    raise exception 'resolution campaign_anchor must be a JSON object';
  end if;
  if not v_anchor ?& array['base_commit', 'campaign_time'] then
    raise exception 'resolution campaign_anchor requires base_commit and campaign_time';
  end if;
  if (v_anchor - 'base_commit' - 'campaign_time') <> '{}'::jsonb then
    raise exception 'resolution campaign_anchor contains fields outside the EV2-09A contract';
  end if;
  if not public._rhc_full_id_match(v_anchor ->> 'base_commit', '^[0-9a-f]{40}$') then
    raise exception 'resolution campaign_anchor.base_commit must be an exact 40-character lowercase hex commit';
  end if;
  if jsonb_typeof(v_anchor -> 'campaign_time') is distinct from 'string'
     or (v_anchor ->> 'campaign_time') !~ '\S' then
    raise exception 'resolution campaign_anchor.campaign_time must be a non-blank label';
  end if;

  v_obj_ctx := p_proposal -> 'objective_context';
  if v_obj_ctx is null or jsonb_typeof(v_obj_ctx) is distinct from 'object' then
    raise exception 'resolution objective_context must be a JSON object';
  end if;
  if not v_obj_ctx ?& array['scenario_objective', 'hook_objective'] then
    raise exception 'resolution objective_context requires scenario_objective and hook_objective';
  end if;
  if (v_obj_ctx - 'scenario_objective' - 'hook_objective') <> '{}'::jsonb then
    raise exception 'resolution objective_context contains fields outside the EV2-09A contract';
  end if;
  if jsonb_typeof(v_obj_ctx -> 'scenario_objective') is distinct from 'string'
     or (v_obj_ctx ->> 'scenario_objective') !~ '\S' then
    raise exception 'resolution objective_context.scenario_objective must be a non-blank string';
  end if;
  if jsonb_typeof(v_obj_ctx -> 'hook_objective') is distinct from 'string'
     or (v_obj_ctx ->> 'hook_objective') !~ '\S' then
    raise exception 'resolution objective_context.hook_objective must be a non-blank string';
  end if;

  if jsonb_typeof(p_proposal -> 'primary_roll') is distinct from 'number'
     or (p_proposal ->> 'primary_roll') !~ '^[0-9]+$'
     or (p_proposal ->> 'primary_roll')::integer not between 1 and 20 then
    raise exception 'resolution primary_roll must be an integer between 1 and 20';
  end if;
  v_roll := (p_proposal ->> 'primary_roll')::integer;
  v_band := public._rhc_band_for_roll(v_roll);
  if (p_proposal ->> 'outcome_band') is distinct from v_band then
    raise exception 'resolution outcome_band must be % for primary_roll %', v_band, v_roll;
  end if;

  if v_roll = 1 then
    if jsonb_typeof(p_proposal -> 'severity_roll') is distinct from 'number'
       or (p_proposal ->> 'severity_roll') !~ '^[0-9]+$'
       or (p_proposal ->> 'severity_roll')::integer not between 1 and 6 then
      raise exception 'primary_roll 1 requires severity_roll between 1 and 6';
    end if;
    v_sev_roll := (p_proposal ->> 'severity_roll')::integer;
    v_sev_band := public._rhc_band_for_severity(v_sev_roll);
    if (p_proposal ->> 'severity_band') is distinct from v_sev_band then
      raise exception 'resolution severity_band must be % for severity_roll %', v_sev_band, v_sev_roll;
    end if;
  else
    if p_proposal ? 'severity_roll' or p_proposal ? 'severity_band' then
      raise exception 'severity is forbidden when primary_roll is not 1';
    end if;
  end if;

  v_consequences := p_proposal -> 'proposed_consequences';
  if jsonb_typeof(v_consequences) is distinct from 'array'
     or jsonb_array_length(v_consequences) < 1 then
    raise exception 'resolution proposed_consequences must be a non-empty array';
  end if;

  for v_c in select * from jsonb_array_elements(v_consequences) loop
    if jsonb_typeof(v_c) is distinct from 'object' then
      raise exception 'proposed consequence must be a JSON object';
    end if;
    if not v_c ?& array['consequence_id', 'scope', 'kind', 'summary', 'related_entity_ids', 'location_ids'] then
      raise exception 'proposed consequence is missing a required EV2-09A field';
    end if;
    if (v_c - 'consequence_id' - 'scope' - 'kind' - 'summary' - 'related_entity_ids' - 'location_ids') <> '{}'::jsonb then
      raise exception 'proposed consequence contains fields outside the EV2-09A contract';
    end if;

    v_cid := v_c ->> 'consequence_id';
    if not public._rhc_full_id_match(v_cid, '^PC[0-9]{2,}$') then
      raise exception 'consequence_id must be PC followed by at least two digits';
    end if;
    if array_position(v_seen, v_cid) is not null then
      raise exception 'duplicate consequence_id % within resolution', v_cid;
    end if;
    v_seen := array_append(v_seen, v_cid);

    v_scope := v_c ->> 'scope';
    if v_scope not in ('run_objective', 'participant', 'location', 'related_entity') then
      raise exception 'consequence scope must be run_objective, participant, location or related_entity';
    end if;
    v_kind := v_c ->> 'kind';
    if v_kind not in (
      'objective_result', 'gain', 'loss', 'injury', 'capture', 'discovery', 'setback', 'world_change'
    ) then
      raise exception 'consequence kind is outside the EV2-09A vocabulary';
    end if;

    if jsonb_typeof(v_c -> 'summary') is distinct from 'string'
       or (v_c ->> 'summary') !~ '\S' then
      raise exception 'consequence summary must be a non-blank string';
    end if;

    perform public._rhc_require_entity_id_array(
      v_c -> 'related_entity_ids', 'related_entity_ids',
      '^(character|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$');
    perform public._rhc_require_entity_id_array(
      v_c -> 'location_ids', 'location_ids',
      '^location:[a-z0-9]+(-[a-z0-9]+)*$');

    if v_scope = 'participant' and jsonb_array_length(v_c -> 'related_entity_ids') < 1 then
      raise exception 'participant-scoped consequence requires at least one related entity';
    end if;
    if v_scope = 'location' and jsonb_array_length(v_c -> 'location_ids') < 1 then
      raise exception 'location-scoped consequence requires at least one location';
    end if;
    if v_scope = 'related_entity' and jsonb_array_length(v_c -> 'related_entity_ids') < 1 then
      raise exception 'related_entity-scoped consequence requires at least one related entity';
    end if;
  end loop;

  return true;
end;
$$;

revoke all on function public._rhc_validate_resolution_proposal(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4b. Candidate Run ownership validation (internal, RT04). Proves the complete
--     candidate `runs` batch is globally exclusive before it may be preserved
--     or published: no mutable entity may be claimed by more than one Run in
--     the candidate state. Only JSON object entries carrying a string `run_id`
--     participate as Run records (same participation rule as the RT03
--     identity read); an owner list that exists but is unreadable fails closed
--     rather than silently skipping a possible overlap.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_candidate_run_ownership(
  p_runs jsonb
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_entry jsonb;
  v_owners jsonb;
  v_owner text;
  v_seen jsonb := '{}'::jsonb;
begin
  if p_runs is null or jsonb_typeof(p_runs) is distinct from 'array' then
    raise exception 'candidate runs batch must be a JSON array';
  end if;
  for v_entry in select * from jsonb_array_elements(p_runs) loop
    continue when jsonb_typeof(v_entry) is distinct from 'object'
       or jsonb_typeof(v_entry -> 'run_id') is distinct from 'string';

    v_owners := v_entry -> 'mutable_owner_entity_ids';
    continue when v_owners is null or jsonb_typeof(v_owners) = 'null';
    if jsonb_typeof(v_owners) is distinct from 'array' then
      raise exception
        'candidate Run % has an unreadable mutable_owner_entity_ids; candidate ownership cannot be proven exclusive',
        v_entry ->> 'run_id';
    end if;

    for v_owner in select o #>> '{}' from jsonb_array_elements(v_owners) o loop
      if v_seen ? v_owner then
        raise exception
          'candidate Run ownership is contradictory: mutable entity % is claimed by more than one Run (% and %); reconciliation fails closed before publication',
          v_owner, v_seen ->> v_owner, v_entry ->> 'run_id';
      end if;
      v_seen := jsonb_set(v_seen, array[v_owner], to_jsonb(v_entry ->> 'run_id'));
    end loop;
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_candidate_run_ownership(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4c. Current-save reconciliation detector (internal, RT04). A save's staging
--     generation starts as a copy of published reality, so a historical
--     `run_reconciliations` receipt can legitimately be present in staged state
--     before this save has reconciled anything. The generic-`runs` closure must
--     therefore not key on the ledger's mere existence: it fires only when this
--     save carries at least one reconciliation marker that is ABSENT from the
--     published ledger, i.e. newly staged during the current active save. An
--     unreadable ledger fails closed. If there is no published reconciliation
--     ledger at all, any staged marker is by definition new in this save.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_reconciliation_new_in_save(
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
  v_key text;
  v_marker jsonb;
begin
  select value into v_stg
    from public.campaign_state_generations
   where generation = p_staging_generation
     and key = 'run_reconciliations';
  if v_stg is null then
    return false;
  end if;
  if jsonb_typeof(v_stg) is distinct from 'object' then
    raise exception 'staged run_reconciliations ledger is unreadable; runs mutation cannot be proven safe';
  end if;
  if p_published_generation is null then
    return true;
  end if;
  select value into v_pub
    from public.campaign_state_generations
   where generation = p_published_generation
     and key = 'run_reconciliations';
  if v_pub is null then
    return true;
  end if;
  if jsonb_typeof(v_pub) is distinct from 'object' then
    raise exception 'published run_reconciliations ledger is unreadable; runs mutation cannot be proven safe';
  end if;
  for v_key, v_marker in select key, value from jsonb_each(v_stg) loop
    if not (v_pub ? v_key) then
      return true;
    end if;
  end loop;
  return false;
end;
$$;

revoke all on function public._rhc_reconciliation_new_in_save(bigint, bigint)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. The validated Run-reconciliation staging route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> reconcile_run_resolution(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape (EV2-09A proposal is NOT modified; this is an RT04 wrapper):
--      {
--        "resolution": { <full EV2-09A proposal object> },
--        "released_mutable_owners": [ "<character|creature>:<slug>", ... ]  // optional
--      }
--
--    Fail-closed guarantees:
--      * reconciliation only runs inside an active campaign save (not an
--        engineering release) -> gateway bypass is impossible;
--      * the source Run is resolved through the RT03 published read only;
--      * a proposal that is malformed, lineage-incoherent, or already consumed
--        is refused before any write;
--      * a consequence targeting a mutable entity the Run no longer controls is
--        stale authority and fails closed;
--      * released owners must currently be owned by the Run;
--      * one source run_id may be reconciled at most once per active save: a
--        second distinct resolution for the same Run is refused so the save can
--        never contradict its own earlier staged reconciliation;
--      * the complete candidate Run ownership state is validated before any
--        staging: no mutable entity claimed by two Runs, and no pre-staged
--        sibling claim converted into an ownership transfer;
--      * after a reconciliation is newly staged in this save, the generic
--        routes refuse further
--        same-save `runs` staging/deletion so the validated candidate cannot be
--        contradicted again before publish;
--      * zero partial writes: all validation happens before any staging, and
--        the caller's single transaction plus the existing gateway laws make the
--        accepted reconciliation all-or-nothing.
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
  'RT04: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet (with their validated summary), and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. All-or-nothing through the existing gateway.';

-- ---------------------------------------------------------------------------
-- 6. Close the generic `run_reconciliations` bypass. The consumption ledger is
--    engine-owned reconciliation proof: it can never be staged or deleted
--    through the generic routes, otherwise replay could be forged or erased.
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
  if p_key = 'runs'
     and public._rhc_reconciliation_new_in_save(r.staging_generation, r.published_generation) then
    raise exception
      'the runs batch is engine-owned for the rest of this save once a reconciliation has been staged; deleting it would erase the reconciled candidate while the consumption ledger claims it was applied; abort this save and start a new one';
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
  'RT01-B/RT02/RT04: generic runtime-state staging. Engine-owned campaign_clock and run_reconciliations keys are rejected here and must use their validated routes. Once a reconciliation is newly staged in the current save (absent from the published reconciliation ledger), the runs key is refused for the rest of the save so the validated candidate Run ownership cannot be contradicted before publication; historical receipts copied forward from published reality do not trigger the closure.';

-- ============================================================================
-- SOURCE MIGRATION: 20260914000001_hwb02_save_runtime_authority.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260915000001_ev210_inventory_ownership.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260917000001_ev211_item_custody.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260919000001_ev2121_item_identity_admission.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260919000002_ev213_mutable_entity_state.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260920000001_ev213420_temporal_core.sql
-- ============================================================================

-- EV2-13.420 — Temporal Core Foundation
-- Rolling High Club deterministic mechanical-time contract on the existing
-- RT01/RT02 spine.
--
-- This migration adds the smallest pure mechanical-duration contract that
-- EV2-13.1 can safely consume. It creates NO table, runtime key, save route,
-- mirror path, scheduler, controller ledger, status-instance record or second
-- elapsed-time authority. Every function here is deterministic/pure and mutates
-- nothing.
--
-- ARCHITECTURE (the bounded contract):
--   * Mechanical time != world calendar. This is elapsed duration only; Harptos /
--     Dalereckoning / archive chronology / temporal jumps are deferred.
--   * Round != turn. A round represents about six seconds and CONTAINS the
--     participants' turns. A turn is not an additive elapsed-duration unit.
--   * Canonical engine arithmetic: one round maps to six elapsed seconds.
--   * Duration vocabulary is bounded to second, round, minute, hour, day.
--   * One canonical conversion primitive plus one narrow RT02 whole-minute
--     bridge; no ladder of per-pair helpers.
--   * No silent precision loss: a conversion that is not an exact whole number of
--     the target unit fails closed rather than truncating/rounding/inventing
--     hidden precision.
--   * No 32-bit overflow scar: arithmetic is wide enough (numeric intermediate,
--     bigint result) that representable valid conversions do not fail merely
--     because an int4 multiplication overflows; genuinely out-of-range results
--     fail cleanly instead of wrapping.
--   * RT02 remains the only persisted elapsed-time authority. This migration
--     never touches `campaign_clock`, `elapsed_campaign_minutes`,
--     `stage_campaign_clock` or `publish_campaign_save`, and introduces no
--     sub-minute remainder ledger.
--
-- WHAT this migration adds:
--   1. `public._rhc_mechanical_unit_seconds(text)` — internal bounded unit
--      vocabulary. `turn` is rejected explicitly, unknown units fail closed.
--   2. `public.convert_mechanical_duration(numeric, text, text)` — the canonical
--      exact duration-conversion primitive. Validates a whole, non-negative
--      amount, converts second/round/minute/hour/day exactly, and fails closed on
--      any non-whole result or out-of-range magnitude.
--   3. `public.mechanical_duration_to_campaign_minutes(numeric, text)` — the
--      narrow RT02 bridge. It yields a whole number of campaign minutes or fails
--      closed (for example one round is six seconds and cannot become a whole
--      campaign minute). It persists nothing; RT02's `stage_campaign_clock(...)`
--      absolute-target law remains the only way campaign minutes advance.
--
-- These functions are executable by `service_role` only and mutate no state.

-- ---------------------------------------------------------------------------
-- 0. Bound the elapsed-duration unit vocabulary (internal). All arithmetic in
--    this Mission is expressed from this single seconds table, so second/round/
--    minute/hour/day are the only legal units and every other token fails closed.
--    `turn` gets an explicit message because mistaking a turn for an additive
--    six-second duration is the exact regression scar this Mission exists to
--    prevent.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_mechanical_unit_seconds(p_unit text)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_unit is null then
    raise exception 'mechanical duration unit is required';
  end if;
  if p_unit = 'second' then
    return 1;
  elsif p_unit = 'round' then
    -- Official combat semantics: a round represents about six seconds and
    -- contains the participants' turns. This is an engine conversion convention,
    -- not a claim that each participant's turn adds another six seconds.
    return 6;
  elsif p_unit = 'minute' then
    return 60;
  elsif p_unit = 'hour' then
    return 3600;
  elsif p_unit = 'day' then
    return 86400;
  elsif p_unit = 'turn' then
    raise exception
      'turn is not an elapsed-duration unit; a turn occurs inside a roughly six-second round and is never an additive duration unit';
  else
    raise exception
      'unknown mechanical duration unit %; the elapsed-duration vocabulary is second, round, minute, hour, day',
      p_unit;
  end if;
end;
$$;

revoke all on function public._rhc_mechanical_unit_seconds(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 1. Canonical exact duration-conversion primitive.
--
--    `p_amount` is a whole, non-negative number of `p_from_unit`; the result is
--    the exact whole number of `p_to_unit`. Because every unit is defined from a
--    single seconds table, there is exactly one correct answer per pair and no
--    per-pair ladder to drift. A result that is not a whole number of the target
--    unit fails closed rather than silently truncating or rounding.
--
--    Arithmetic is done in infinite-precision `numeric`, so neither a wide
--    seconds intermediate nor a wide but valid same-unit value fails merely
--    because it exceeds bigint. Only the FINAL requested result is range-checked:
--    it must fit in a bigint or the call fails cleanly. Intermediate magnitude is
--    never itself an output-range failure (for example bigint-max days -> days
--    stays representable even though its seconds intermediate is far larger).
-- ---------------------------------------------------------------------------
create or replace function public.convert_mechanical_duration(
  p_amount numeric,
  p_from_unit text,
  p_to_unit text
)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_from_seconds bigint;
  v_to_seconds bigint;
  v_total_seconds numeric;
  v_result numeric;
  v_bigint_max constant numeric := 9223372036854775807;
begin
  if p_amount is null then
    raise exception 'mechanical duration amount is required';
  end if;
  -- Untrusted caller input: reject non-integral and negative magnitudes instead
  -- of coercing them into a valid-looking time.
  if p_amount <> trunc(p_amount) then
    raise exception
      'mechanical duration amount must be a whole number of units, got %',
      p_amount;
  end if;
  if p_amount < 0 then
    raise exception
      'mechanical duration amount must be non-negative, got %',
      p_amount;
  end if;

  v_from_seconds := public._rhc_mechanical_unit_seconds(p_from_unit);
  v_to_seconds := public._rhc_mechanical_unit_seconds(p_to_unit);

  v_total_seconds := p_amount * v_from_seconds;

  if mod(v_total_seconds, v_to_seconds) <> 0 then
    raise exception
      'mechanical duration % % is not an exact whole number of %; refusing silent truncation',
      p_amount, p_from_unit, p_to_unit;
  end if;

  v_result := v_total_seconds / v_to_seconds;
  if v_result > v_bigint_max then
    raise exception
      'mechanical duration % % is out of representable range when expressed in %',
      p_amount, p_from_unit, p_to_unit;
  end if;

  return v_result::bigint;
end;
$$;

revoke all on function public.convert_mechanical_duration(numeric, text, text)
  from public, anon, authenticated;
grant execute on function public.convert_mechanical_duration(numeric, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- 2. Narrow RT02 whole-minute bridge.
--
--    This is the only bridge from a mechanical duration into RT02's elapsed-time
--    world. It succeeds only when the duration is an exact whole number of
--    campaign minutes; a sub-minute result (for example one round = six seconds)
--    fails closed. It persists nothing and invents no sub-minute remainder: a
--    consumer that needs an exact expiry boundary must express it as its own
--    turn-boundary rule, not as hidden Campaign Clock precision.
--
--    It is additionally bounded to the ACTUAL storage range of RT02
--    `elapsed_campaign_minutes`, which RT02 normalizes to a PostgreSQL `integer`
--    (int4). A whole-minute value RT02 cannot persist (above 2147483647) fails
--    closed here rather than being handed back as an unusable result.
-- ---------------------------------------------------------------------------
create or replace function public.mechanical_duration_to_campaign_minutes(
  p_amount numeric,
  p_unit text
)
returns bigint
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_minutes bigint;
  v_rt02_minutes_max constant bigint := 2147483647;
begin
  v_minutes := public.convert_mechanical_duration(p_amount, p_unit, 'minute');
  if v_minutes > v_rt02_minutes_max then
    raise exception
      'mechanical duration % % maps to % campaign minutes, above the RT02 elapsed_campaign_minutes range (0..%); a duration RT02 cannot persist fails closed',
      p_amount, p_unit, v_minutes, v_rt02_minutes_max;
  end if;
  return v_minutes;
end;
$$;

revoke all on function public.mechanical_duration_to_campaign_minutes(numeric, text)
  from public, anon, authenticated;
grant execute on function public.mechanical_duration_to_campaign_minutes(numeric, text)
  to service_role;

comment on function public._rhc_mechanical_unit_seconds(text) is
  'EV2-13.420 internal bounded elapsed-duration unit vocabulary expressed from one seconds table: second=1, round=6, minute=60, hour=3600, day=86400. `turn` is explicitly refused as an additive duration unit and unknown units fail closed. Internal-only.';
comment on function public.convert_mechanical_duration(numeric, text, text) is
  'EV2-13.420 canonical deterministic mechanical-duration conversion. Converts an exact whole non-negative amount among second, round, minute, hour and day using infinite-precision numeric arithmetic, failing closed on non-integral/negative input, on any non-whole result, and only when the FINAL requested result is out of bigint range. A wide seconds intermediate or wide valid same-unit value is never rejected merely for exceeding bigint. Pure: mutates nothing and owns no persistence.';
comment on function public.mechanical_duration_to_campaign_minutes(numeric, text) is
  'EV2-13.420 narrow RT02 bridge. Returns the exact whole number of campaign minutes for a mechanical duration or fails closed; a sub-minute result such as one round (six seconds) never truncates or invents hidden Campaign Clock precision. Bounded to the actual RT02 elapsed_campaign_minutes PostgreSQL integer range (0..2147483647): a whole-minute value RT02 cannot persist fails closed. Pure: persists nothing, leaving stage_campaign_clock as the only way elapsed_campaign_minutes advances.';

-- ============================================================================
-- SOURCE MIGRATION: 20260920000002_ev2131_timed_status_continuity.sql
-- ============================================================================

-- EV2-13.1 — Timed Applied Status Continuity
-- Rolling High Club validated runtime model for one live time-dependent
-- `status_effect` application on a mutable target, on the existing RT01 SAVE /
-- publish / mirror / confirm spine.
--
-- This migration is NOT a second save engine, NOT a second controller/ownership
-- ledger and NOT a new persistence/mirror path. It creates ONE engine-owned
-- runtime namespace `applied_statuses`, ONE validated mutation route, ONE pure
-- due-threshold read and the smallest same-save exclusions required to keep the
-- controller/elapsed-anchor semantics unambiguous.
--
-- Architecture sentence:
--   EV2-13.1 owns the live timed application instance — identity, elapsed-time
--   anchors, due-threshold derivation/acknowledgement and controller-safe
--   mutation — while RT02's monotonic `elapsed_campaign_minutes` remains the only
--   persisted elapsed-time authority and EV2-13.420 remains the only
--   mechanical-duration arithmetic contract.
--
-- Core invariance (the reason the whole Mission exists):
--   World-calendar position may later move backward or forward. Experienced
--   elapsed campaign time never moves backward. Timed status ageing follows
--   experienced elapsed time only.
--
-- WHAT this migration changes:
--   1. The engine-owned `applied_statuses` runtime namespace is a JSON array
--      holding exactly one application record per stable application identity.
--      A record references a `status_effect:` DEFINITION identity (EV2-04.1),
--      never mints or mutates it; it is bound to one mutable target actor
--      (`character:` / `creature:`), an optional known source identity, an
--      engine-derived application anchor from authoritative PUBLISHED RT02
--      `elapsed_campaign_minutes`, bounded absolute elapsed-time threshold
--      anchors in whole campaign minutes, explicit acknowledgement state and an
--      explicit end anchor. It stores elapsed anchors only — never world dates.
--   2. `public.mutate_applied_status(p_lock_token, p_request)` is the ONLY way to
--      stage `applied_statuses`. It runs INSIDE the normal campaign save
--      lifecycle, proves the caller's asserted controller (MAINRUN or exactly one
--      RUN #) against authoritative PUBLISHED Run truth for the target mutable
--      actor, derives every timing anchor from the authoritative published Clock,
--      normalizes relative human-facing durations through EV2-13.420, and stages
--      exactly one application record per identity.
--   3. `public.read_timed_applied_status(p_application_id)` is the service-only
--      pure read that deterministically exposes every still-unacknowledged
--      threshold whose absolute due anchor is now <= current elapsed time. A
--      forward elapsed-time jump needs no per-minute ticking: due-ness is derived
--      from the current elapsed cursor, never from an incremental loop.
--   4. The generic `stage_campaign_state` / `delete_staged_campaign_state` routes
--      reject the `applied_statuses` key (the same dedicated-key closure pattern
--      as `campaign_clock`, `run_reconciliations`, `inventory`, `item_custody`,
--      `item_admissions` and `entity_state`), so a caller/model cannot bypass the
--      validated route with a raw generic runtime write. The HWB-02 ordinary-save
--      allowlist is preserved unchanged. Legacy `live_status` stays generic
--      ordinary-save state and is never applied-status authority.
--   5. Status mutation and Run-ownership mutation are mutually exclusive within
--      one save, and status mutation and Campaign Clock mutation are mutually
--      exclusive within one save, in BOTH orderings. Closure keys on the explicit
--      applied-status staging operation fact, not on final value equality, and
--      the marker is bound to the save's own database-minted lock token so it
--      never leaks into a later save.
--
-- TIMING MODEL:
--   * The application anchor (`applied_at_elapsed_minutes`) is the authoritative
--     published `elapsed_campaign_minutes` at the first accepted mutation — never
--     caller-supplied.
--   * A threshold is described by a relative whole-duration (`threshold_id`,
--     `amount`, `unit`). Its absolute due anchor is the application anchor plus
--     the exact whole-minute result of EV2-13.420's
--     `mechanical_duration_to_campaign_minutes`. No duplicate time arithmetic is
--     introduced; a sub-minute duration such as one round fails closed.
--   * A threshold becomes due purely because `due_at <= current elapsed`. There is
--     no per-minute scheduler/ticker.
--   * Acknowledgement and end anchors are stamped from the current authoritative
--     published elapsed cursor, never from caller input. Acknowledging a due
--     threshold is terminal for that threshold (idempotent on replay) and leaves
--     later thresholds discoverable; it performs NO automatic gameplay
--     consequence.
--   * The whole timing definition (definition identity, target, source, threshold
--     due anchors) is immutable after creation. Re-sending it is an idempotent
--     replay; changing it fails closed, because reapplication/refresh/stacking
--     policy is explicitly deferred to later status-rules work.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * One application record is global to the target in the single campaign
--     reality. It is never copied into MAINRUN and RUN-local versions.
--   * Only the target's current authoritative controller — resolved from
--     PUBLISHED Run truth — may mutate/acknowledge/end the application. A
--     former/stale controller write fails closed because published Run truth no
--     longer grants it authority. There is no stored controller field.
--
-- DEFERRED (not built here): world-calendar / Harptos / Dalereckoning
-- representation or mutation, world-date jumps, turn/initiative-boundary
-- scheduler semantics (`turn` is never an additive duration), stacking /
-- refresh / replace / ignore policy, concentration, D&D condition automation,
-- saving throws, damage/resources, automatic gameplay consequences, alternate
-- realities / save slots, sub-minute persisted remainder and any generic
-- scheduler/autosave. `live_status` is not repurposed.

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
      'EV2-13.1 migration refused: resolve the active campaign save before installing the timed applied-status route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Authoritative elapsed cursor (internal). Reads the published campaign
--    Clock's monotonic `elapsed_campaign_minutes`. Missing/Unknown Clock truth
--    FAILS CLOSED rather than defaulting to elapsed 0: status ageing must never
--    invent timeline position from an absent Clock.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_published_clock_elapsed()
returns integer
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_clock jsonb;
  v_elapsed integer;
begin
  select csg.value into v_clock
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation
   where csg.key = 'campaign_clock';
  if v_clock is null or jsonb_typeof(v_clock) is distinct from 'object' then
    raise exception
      'published campaign_clock is unavailable; timed applied-status elapsed anchoring cannot be derived and never defaults to zero';
  end if;
  if jsonb_typeof(v_clock -> 'elapsed_campaign_minutes') is distinct from 'number'
     or (v_clock ->> 'elapsed_campaign_minutes') !~ '^[0-9]+$' then
    raise exception
      'published campaign_clock elapsed_campaign_minutes is unreadable; timed applied-status timing fails closed';
  end if;
  v_elapsed := (v_clock ->> 'elapsed_campaign_minutes')::integer;
  return v_elapsed;
end;
$$;

revoke all on function public._rhc_published_clock_elapsed()
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Canonical timing definition normalization (internal). Accepts the bounded
--    relative-duration definition and the (engine-derived) application anchor,
--    and returns the canonical definition with absolute whole-minute due
--    anchors. Human-facing durations are normalized through EV2-13.420; no
--    duplicate time arithmetic is introduced. A sub-minute or malformed
--    duration, a forged threshold id, or an anchor beyond the RT02 integer range
--    fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_applied_status_definition(
  p_definition jsonb,
  p_applied_at integer
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_definition_id text;
  v_target text;
  v_source jsonb;
  v_thresholds jsonb;
  v_entry jsonb;
  v_out jsonb := '[]'::jsonb;
  v_tid text;
  v_amount jsonb;
  v_unit text;
  v_minutes bigint;
  v_due bigint;
  v_seen text[] := '{}';
  v_rt02_max constant bigint := 2147483647;
begin
  if p_definition is null or jsonb_typeof(p_definition) is distinct from 'object' then
    raise exception 'applied-status definition must be a JSON object';
  end if;
  if (p_definition - 'definition_id' - 'target_entity_id' - 'source_entity_id'
        - 'thresholds') <> '{}'::jsonb then
    raise exception
      'applied-status definition contains fields outside the EV2-13.1 contract (definition_id, target_entity_id, source_entity_id, thresholds)';
  end if;
  if not (p_definition ?& array['definition_id', 'target_entity_id', 'thresholds']) then
    raise exception
      'applied-status definition requires definition_id, target_entity_id and thresholds';
  end if;

  -- Definition identity: a reference to an EV2-04.1 persistent status_effect.
  -- The runtime references definitions; it never mints or mutates their identity.
  if jsonb_typeof(p_definition -> 'definition_id') is distinct from 'string' then
    raise exception
      'applied-status definition_id must be a JSON string status_effect identity';
  end if;
  v_definition_id := p_definition ->> 'definition_id';
  if not public._rhc_full_id_match(
    v_definition_id, '^status_effect:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status definition_id must be a status_effect:<slug> definition identity';
  end if;

  -- Target: the EV2-08 mutable-actor identity space only.
  if jsonb_typeof(p_definition -> 'target_entity_id') is distinct from 'string' then
    raise exception
      'applied-status target_entity_id must be a JSON string mutable-actor identity';
  end if;
  v_target := p_definition ->> 'target_entity_id';
  if not public._rhc_full_id_match(
    v_target, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status target_entity_id must be a character: or creature: mutable-actor identity';
  end if;

  -- Optional known source identity. Unknown stays Unknown: when absent it is
  -- stored as null, never invented.
  if p_definition ? 'source_entity_id' then
    v_source := p_definition -> 'source_entity_id';
    if jsonb_typeof(v_source) is distinct from 'null' then
      if jsonb_typeof(v_source) is distinct from 'string' then
        raise exception
          'applied-status source_entity_id must be null or a JSON string entity identity';
      end if;
      if not public._rhc_full_id_match(
        (v_source #>> '{}'),
        '^(character|location|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$') then
        raise exception
          'applied-status source_entity_id must be null or a typed <entity_type>:<slug> identity';
      end if;
    end if;
  else
    v_source := 'null'::jsonb;
  end if;

  -- Bounded elapsed thresholds expressed only as relative whole durations.
  v_thresholds := p_definition -> 'thresholds';
  if v_thresholds is null or jsonb_typeof(v_thresholds) is distinct from 'array' then
    raise exception 'applied-status thresholds must be a JSON array';
  end if;
  if jsonb_array_length(v_thresholds) = 0 then
    raise exception
      'applied-status requires at least one elapsed threshold; a non-timed status_effect does not belong in the timed applied-status namespace';
  end if;

  for v_entry in select e from jsonb_array_elements(v_thresholds) e loop
    if jsonb_typeof(v_entry) is distinct from 'object' then
      raise exception 'applied-status threshold must be a JSON object';
    end if;
    if (v_entry - 'threshold_id' - 'amount' - 'unit') <> '{}'::jsonb then
      raise exception
        'applied-status threshold contains fields outside the EV2-13.1 contract (threshold_id, amount, unit)';
    end if;
    if not (v_entry ?& array['threshold_id', 'amount', 'unit']) then
      raise exception
        'applied-status threshold requires threshold_id, amount and unit';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    if not public._rhc_full_id_match(v_tid, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
      raise exception
        'applied-status threshold_id must be a stable non-blank token';
    end if;
    if array_position(v_seen, v_tid) is not null then
      raise exception
        'applied-status thresholds must be unique; duplicate threshold_id % is ambiguous',
        v_tid;
    end if;
    v_seen := array_append(v_seen, v_tid);

    v_amount := v_entry -> 'amount';
    if jsonb_typeof(v_amount) is distinct from 'number' then
      raise exception
        'applied-status threshold amount must be a JSON number of whole units';
    end if;
    if jsonb_typeof(v_entry -> 'unit') is distinct from 'string' then
      raise exception 'applied-status threshold unit must be a JSON string';
    end if;
    v_unit := v_entry ->> 'unit';

    -- EV2-13.420 is the only mechanical-duration arithmetic contract.
    v_minutes := public.mechanical_duration_to_campaign_minutes(
      (v_amount #>> '{}')::numeric, v_unit);

    v_due := p_applied_at::bigint + v_minutes;
    if v_due > v_rt02_max then
      raise exception
        'applied-status threshold % due anchor exceeds the RT02 elapsed_campaign_minutes range (0..%); a threshold the Clock can never reach is refused',
        v_tid, v_rt02_max;
    end if;

    v_out := v_out || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'due_at_elapsed_minutes', v_due::integer
    ));
  end loop;

  -- Deterministic ordering by threshold_id so value equality is stable.
  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_out
    from jsonb_array_elements(v_out) t;

  return jsonb_build_object(
    'definition_id', v_definition_id,
    'target_entity_id', v_target,
    'source_entity_id', v_source,
    'thresholds', v_out
  );
end;
$$;

revoke all on function public._rhc_normalize_applied_status_definition(jsonb, integer)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Full stored application-record validation + canonicalization (internal).
--    Proves a stored record is exactly the bounded EV2-13.1 shape and is
--    internally coherent: absolute elapsed anchors only, unique thresholds,
--    acknowledgements a subset of declared thresholds stamped at or after the
--    threshold became due, and no world-calendar/date field anywhere.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_applied_status_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_app_id text;
  v_definition_id text;
  v_target text;
  v_source jsonb;
  v_applied integer;
  v_thresholds jsonb;
  v_ack jsonb;
  v_entry jsonb;
  v_tid text;
  v_due integer;
  v_ack_at integer;
  v_ended jsonb;
  v_seen text[] := '{}';
  v_thr jsonb := '[]'::jsonb;
  v_out_ack jsonb := '[]'::jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'applied-status record must be a JSON object';
  end if;
  if (p_record - 'application_version' - 'application_id' - 'definition_id'
        - 'target_entity_id' - 'source_entity_id' - 'applied_at_elapsed_minutes'
        - 'thresholds' - 'acknowledged_thresholds'
        - 'ended_at_elapsed_minutes') <> '{}'::jsonb then
    raise exception
      'applied-status record contains fields outside the EV2-13.1 contract; a world-calendar or invented field is refused rather than canonicalized';
  end if;
  if not (p_record ?& array[
    'application_version', 'application_id', 'definition_id', 'target_entity_id',
    'source_entity_id', 'applied_at_elapsed_minutes', 'thresholds',
    'acknowledged_thresholds', 'ended_at_elapsed_minutes']) then
    raise exception
      'applied-status record is missing a required EV2-13.1 field';
  end if;

  if jsonb_typeof(p_record -> 'application_version') is distinct from 'number'
     or (p_record ->> 'application_version') is distinct from '1' then
    raise exception 'applied-status application_version must be 1';
  end if;

  if jsonb_typeof(p_record -> 'application_id') is distinct from 'string' then
    raise exception 'applied-status application_id must be a JSON string';
  end if;
  v_app_id := p_record ->> 'application_id';
  if not public._rhc_full_id_match(v_app_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
    raise exception
      'applied-status application_id must be a stable non-blank token';
  end if;

  if jsonb_typeof(p_record -> 'definition_id') is distinct from 'string' then
    raise exception 'applied-status definition_id must be a JSON string';
  end if;
  v_definition_id := p_record ->> 'definition_id';
  if not public._rhc_full_id_match(
    v_definition_id, '^status_effect:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status definition_id must be a status_effect:<slug> definition identity';
  end if;

  if jsonb_typeof(p_record -> 'target_entity_id') is distinct from 'string' then
    raise exception 'applied-status target_entity_id must be a JSON string';
  end if;
  v_target := p_record ->> 'target_entity_id';
  if not public._rhc_full_id_match(
    v_target, '^(character|creature):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'applied-status target_entity_id must be a character: or creature: mutable-actor identity';
  end if;

  v_source := p_record -> 'source_entity_id';
  if jsonb_typeof(v_source) is distinct from 'null' then
    if jsonb_typeof(v_source) is distinct from 'string'
       or not public._rhc_full_id_match(
         (v_source #>> '{}'),
         '^(character|location|faction|party|creature|item|ability|status_effect):[a-z0-9]+(-[a-z0-9]+)*$') then
      raise exception
        'applied-status source_entity_id must be null or a typed <entity_type>:<slug> identity';
    end if;
  end if;

  if jsonb_typeof(p_record -> 'applied_at_elapsed_minutes') is distinct from 'number'
     or (p_record ->> 'applied_at_elapsed_minutes') !~ '^[0-9]+$' then
    raise exception
      'applied-status applied_at_elapsed_minutes must be a non-negative whole elapsed minute';
  end if;
  v_applied := (p_record ->> 'applied_at_elapsed_minutes')::integer;

  v_thresholds := p_record -> 'thresholds';
  if v_thresholds is null or jsonb_typeof(v_thresholds) is distinct from 'array'
     or jsonb_array_length(v_thresholds) = 0 then
    raise exception
      'applied-status record requires a non-empty thresholds array';
  end if;
  for v_entry in select e from jsonb_array_elements(v_thresholds) e loop
    if jsonb_typeof(v_entry) is distinct from 'object'
       or (v_entry - 'threshold_id' - 'due_at_elapsed_minutes') <> '{}'::jsonb
       or not (v_entry ?& array['threshold_id', 'due_at_elapsed_minutes']) then
      raise exception
        'applied-status record threshold must be exactly {threshold_id, due_at_elapsed_minutes}';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status record threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    if not public._rhc_full_id_match(v_tid, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
      raise exception
        'applied-status record threshold_id must be a stable non-blank token';
    end if;
    if array_position(v_seen, v_tid) is not null then
      raise exception
        'applied-status record thresholds must be unique; duplicate threshold_id %',
        v_tid;
    end if;
    v_seen := array_append(v_seen, v_tid);
    if jsonb_typeof(v_entry -> 'due_at_elapsed_minutes') is distinct from 'number'
       or (v_entry ->> 'due_at_elapsed_minutes') !~ '^[0-9]+$' then
      raise exception
        'applied-status record threshold due anchor must be a non-negative whole elapsed minute';
    end if;
    v_due := (v_entry ->> 'due_at_elapsed_minutes')::integer;
    if v_due < v_applied then
      raise exception
        'applied-status record threshold due anchor cannot precede the application anchor';
    end if;
    v_thr := v_thr || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'due_at_elapsed_minutes', v_due
    ));
  end loop;

  v_ack := p_record -> 'acknowledged_thresholds';
  if v_ack is null or jsonb_typeof(v_ack) is distinct from 'array' then
    raise exception 'applied-status record acknowledged_thresholds must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(v_ack) e loop
    if jsonb_typeof(v_entry) is distinct from 'object'
       or (v_entry - 'threshold_id' - 'acknowledged_at_elapsed_minutes') <> '{}'::jsonb
       or not (v_entry ?& array['threshold_id', 'acknowledged_at_elapsed_minutes']) then
      raise exception
        'applied-status acknowledgement must be exactly {threshold_id, acknowledged_at_elapsed_minutes}';
    end if;
    if jsonb_typeof(v_entry -> 'threshold_id') is distinct from 'string' then
      raise exception 'applied-status acknowledgement threshold_id must be a JSON string';
    end if;
    v_tid := v_entry ->> 'threshold_id';
    select (t ->> 'due_at_elapsed_minutes')::integer
      into v_due
      from jsonb_array_elements(v_thr) t
     where (t ->> 'threshold_id') = v_tid;
    if v_due is null then
      raise exception
        'applied-status acknowledgement names unknown threshold %', v_tid;
    end if;
    if jsonb_typeof(v_entry -> 'acknowledged_at_elapsed_minutes') is distinct from 'number'
       or (v_entry ->> 'acknowledged_at_elapsed_minutes') !~ '^[0-9]+$' then
      raise exception
        'applied-status acknowledgement anchor must be a non-negative whole elapsed minute';
    end if;
    v_ack_at := (v_entry ->> 'acknowledged_at_elapsed_minutes')::integer;
    if v_ack_at < v_due then
      raise exception
        'applied-status acknowledgement anchor cannot precede its threshold due anchor';
    end if;
    v_out_ack := v_out_ack || jsonb_build_array(jsonb_build_object(
      'threshold_id', v_tid,
      'acknowledged_at_elapsed_minutes', v_ack_at
    ));
  end loop;

  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_out_ack
    from jsonb_array_elements(v_out_ack) t;

  select coalesce(jsonb_agg(t order by (t ->> 'threshold_id')), '[]'::jsonb)
    into v_thr
    from jsonb_array_elements(v_thr) t;

  v_ended := p_record -> 'ended_at_elapsed_minutes';
  if jsonb_typeof(v_ended) is distinct from 'null' then
    if jsonb_typeof(v_ended) is distinct from 'number'
       or (v_ended #>> '{}') !~ '^[0-9]+$' then
      raise exception
        'applied-status ended_at_elapsed_minutes must be null or a non-negative whole elapsed minute';
    end if;
    if (v_ended #>> '{}')::integer < v_applied then
      raise exception
        'applied-status end anchor cannot precede the application anchor';
    end if;
  end if;

  return jsonb_build_object(
    'application_version', 1,
    'application_id', v_app_id,
    'definition_id', v_definition_id,
    'target_entity_id', v_target,
    'source_entity_id', v_source,
    'applied_at_elapsed_minutes', v_applied,
    'thresholds', v_thr,
    'acknowledged_thresholds', v_out_ack,
    'ended_at_elapsed_minutes', v_ended
  );
end;
$$;

revoke all on function public._rhc_normalize_applied_status_record(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Whole-collection validation (internal). Proves the complete candidate
--    `applied_statuses` namespace is a JSON array of canonical records with
--    exactly one authoritative record per application identity. A duplicate
--    application identity is an ambiguity and fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_validate_applied_statuses_collection(
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
  v_app_id text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'applied_statuses namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_applied_status_record(v_entry);
    v_app_id := v_norm ->> 'application_id';
    if array_position(v_seen, v_app_id) is not null then
      raise exception
        'applied_statuses namespace holds duplicate records for application %; exactly one authoritative record per application is required',
        v_app_id;
    end if;
    v_seen := array_append(v_seen, v_app_id);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_applied_statuses_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. Explicit same-save applied-status staging marker (internal). Closure keys
--    on the operation fact, not on final JSON equality: an absolute record can be
--    re-staged to a value that already equals published reality (a replay), and
--    the final value would look unchanged even though a successful staging
--    operation occurred. The save locator records the lock_token that staged an
--    applied status, so the marker can only match the CURRENT save's token and
--    never leaks into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists applied_status_staged_lock_token text;

create or replace function public._rhc_applied_status_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.applied_status_staged_lock_token is not null
            and cr.applied_status_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_applied_status_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.applied_status_staged_lock_token is
  'EV2-13.1 internal operation fact: the lock_token of the save that most recently staged a successful timed applied-status mutation. Matched against the active lock_token so the same-save applied-status/Run-ownership and applied-status/Campaign-Clock exclusions key on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 6. The validated atomic timed applied-status mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_applied_status(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "application_id": "<stable token>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "definition": {
--          "definition_id": "status_effect:<slug>",
--          "target_entity_id": "<character|creature>:<slug>",
--          "source_entity_id": null | "<entity_type>:<slug>",
--          "thresholds": [ { "threshold_id": "...", "amount": <whole number>,
--                             "unit": "second|round|minute|hour|day" } ]
--        },
--        "acknowledge": [ "<threshold_id>", ... ],
--        "end": true | false
--      }
--
--    `application_id` and `controller` are always required. `definition` is
--    required when the application does not yet exist and, when supplied on an
--    existing application, must exactly reproduce the immutable timing
--    definition (a replay). `acknowledge` and `end` are optional and additive.
--
--    Fail-closed guarantees:
--      * mutation only runs inside an active campaign save (not engineering
--        release) -> gateway bypass is impossible;
--      * the asserted controller must match authoritative PUBLISHED Run truth for
--        the target mutable actor (malformed/duplicated batch, parked claiming
--        Run and two-Run claim all fail closed rather than falling through to
--        MAINRUN);
--      * a same-save staged `runs` change (Run-ownership handoff) fails closed,
--        and a same-save staged `campaign_clock` change fails closed, because the
--        elapsed/controller truth this save would publish is not the truth the
--        mutation would be proven against;
--      * the application never trusts a caller `applied_at`, acknowledgement
--        anchor, end anchor, world date or absolute threshold position; every
--        anchor is derived from the authoritative published Clock;
--      * the complete existing and resulting `applied_statuses` namespaces are
--        validated before staging, so malformed or duplicate unrelated truth
--        fails closed and is never canonicalized by overwrite;
--      * zero partial writes: all validation happens before staging, and the
--        caller's single transaction plus the existing gateway laws make the
--        accepted mutation all-or-nothing.
--
--    This route does NOT change Run ownership, does not change the Clock, does
--    not mint a status_effect definition, and performs no automatic gameplay
--    consequence when a threshold becomes due.
-- ---------------------------------------------------------------------------
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

  -- Same-save controller integrity: applied-status authority is proven against
  -- PUBLISHED Run truth. If this save has already staged a different `runs`
  -- batch, published truth no longer describes the Run ownership this save will
  -- publish. Fail closed; Run-ownership changes and applied-status mutations
  -- belong in separate saves.
  if public._rhc_state_key_changed_in_save(
       'runs', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different runs batch; applied-status controller cannot be proven against published Run truth, so timed applied-status mutation fails closed (change Run ownership and applied status in separate saves)';
  end if;

  -- Same-save elapsed integrity: the elapsed anchors are derived from the
  -- authoritative published Clock. If this save has already staged a different
  -- `campaign_clock`, the elapsed truth this save would publish is not the truth
  -- the mutation would be proven against. Fail closed; Clock advances and
  -- applied-status mutations belong in separate saves.
  if public._rhc_state_key_changed_in_save(
       'campaign_clock', r.staging_generation, r.published_generation) then
    raise exception
      'this save has staged a different campaign_clock; applied-status elapsed anchors cannot be proven against the Clock this save would publish, so timed applied-status mutation fails closed (advance the Clock and mutate applied status in separate saves)';
  end if;

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

comment on function public.mutate_applied_status(text, jsonb) is
  'EV2-13.1: the only validated atomic timed applied-status mutation route, inside the normal RT01 save lifecycle. Requires application_id and an explicit structurally valid controller assertion, proves the asserted MAINRUN-or-one-RUN controller against authoritative published Run truth for the target character:/creature: actor, derives the application anchor and every acknowledgement/end anchor from the authoritative published Clock elapsed cursor, normalizes relative durations through EV2-13.420 without duplicating time arithmetic, keeps the timing definition immutable, and stages exactly one application record per identity into the engine-owned applied_statuses namespace while recording the staging operation fact that closes Run-ownership and Campaign-Clock writing doorways for the rest of the save. Absolute, replay-safe, all-or-nothing through the existing gateway. Owns no controller authority and no elapsed-time authority.';

-- ---------------------------------------------------------------------------
-- 7. Pure service-only due-threshold read. Derives due-ness from the current
--    published elapsed cursor, so an arbitrarily large forward jump exposes ALL
--    still-unacknowledged crossed thresholds with no per-minute ticking. Reads
--    published state only and mutates nothing.
-- ---------------------------------------------------------------------------
create or replace function public.read_timed_applied_status(
  p_application_id text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_collection jsonb;
  v_record jsonb;
  v_now integer;
  v_applied integer;
  v_ended jsonb;
  v_thr jsonb;
  v_ack_ids text[] := '{}';
  v_entry jsonb;
  v_due jsonb;
  v_ack jsonb := '[]'::jsonb;
  v_due_out jsonb := '[]'::jsonb;
  v_pending_out jsonb := '[]'::jsonb;
  v_t jsonb;
  v_tid text;
  v_due_at integer;
begin
  if not public._rhc_full_id_match(
    p_application_id, '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') then
    raise exception
      'applied-status read requires a stable non-blank application_id token';
  end if;

  v_now := public._rhc_published_clock_elapsed();

  select csg.value into v_collection
    from public.campaign_state_generations csg
    join public.campaign_runtime cr
      on cr.id = 1
     and csg.generation = cr.published_generation
   where csg.key = 'applied_statuses';
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'applied_statuses namespace is unreadable; applied-status read fails closed';
  end if;
  perform public._rhc_validate_applied_statuses_collection(v_collection);

  select public._rhc_normalize_applied_status_record(e)
    into v_record
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'application_id') = p_application_id;

  if v_record is null then
    return jsonb_build_object(
      'read_version', 1,
      'mode', 'timed_applied_status',
      'runtime', public._rhc_dm_runtime_metadata(),
      'application_id', p_application_id,
      'application', null,
      'due_thresholds', '[]'::jsonb,
      'pending_thresholds', '[]'::jsonb
    );
  end if;

  v_applied := (v_record ->> 'applied_at_elapsed_minutes')::integer;
  v_ended := v_record -> 'ended_at_elapsed_minutes';
  v_thr := v_record -> 'thresholds';

  for v_entry in
    select a from jsonb_array_elements(v_record -> 'acknowledged_thresholds') a
  loop
    v_ack_ids := array_append(v_ack_ids, v_entry ->> 'threshold_id');
  end loop;

  for v_t in select t from jsonb_array_elements(v_thr) t loop
    v_tid := v_t ->> 'threshold_id';
    v_due_at := (v_t ->> 'due_at_elapsed_minutes')::integer;
    if array_position(v_ack_ids, v_tid) is not null then
      continue;
    end if;
    if jsonb_typeof(v_ended) is distinct from 'null' then
      continue;
    end if;
    if v_due_at <= v_now then
      v_due_out := v_due_out || jsonb_build_array(jsonb_build_object(
        'threshold_id', v_tid,
        'due_at_elapsed_minutes', v_due_at,
        'overdue_by_elapsed_minutes', v_now - v_due_at
      ));
    else
      v_pending_out := v_pending_out || jsonb_build_array(jsonb_build_object(
        'threshold_id', v_tid,
        'due_at_elapsed_minutes', v_due_at,
        'remaining_elapsed_minutes', v_due_at - v_now
      ));
    end if;
  end loop;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'timed_applied_status',
    'runtime', public._rhc_dm_runtime_metadata(),
    'application_id', p_application_id,
    'application', v_record || jsonb_build_object(
      'age_elapsed_minutes', v_now - v_applied
    ),
    'due_thresholds', v_due_out,
    'pending_thresholds', v_pending_out
  );
end;
$$;

revoke all on function public.read_timed_applied_status(text)
  from public, anon, authenticated;
grant execute on function public.read_timed_applied_status(text) to service_role;

comment on function public.read_timed_applied_status(text) is
  'EV2-13.1: the service-only pure read for one timed applied-status application. Reads only the published applied_statuses namespace and the published Clock elapsed cursor, derives age and every due/pending threshold from elapsed minutes (never from a world date or a per-minute tick), and exposes all still-unacknowledged crossed thresholds after a forward jump. Mutates nothing.';

-- ---------------------------------------------------------------------------
-- 8. Close the generic `applied_statuses` bypass. The namespace is engine-owned:
--    it can never be staged or deleted through the generic routes. This
--    re-declares the HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13 generic routes
--    unchanged except for the added applied_statuses closure and the same-save
--    applied-status/Run-ownership exclusion, preserving every existing
--    dedicated-key closure and the server-owned ordinary-save allowlist exactly.
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
  if p_key = 'applied_statuses' then
    raise exception 'applied_statuses is engine-owned and can only be staged through mutate_applied_status';
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
  if p_key = 'runs'
     and public._rhc_applied_status_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one';
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
  if p_key = 'applied_statuses' then
    raise exception 'applied_statuses is engine-owned and cannot be deleted through the generic route';
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
  if p_key = 'runs'
     and public._rhc_applied_status_staged_in_save() then
    raise exception
      'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one';
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
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1: generic runtime-state staging. Engine-owned campaign_clock, run_reconciliations, inventory, item_custody, item_admissions, entity_state and applied_statuses keys are rejected here and must use their validated routes (applied_statuses via mutate_applied_status). Once a reconciliation is newly staged in the current save, or once this save has staged an inventory mutation, an item custody/admission operation, a mutable entity-state mutation, or a timed applied-status mutation, the runs key is refused for the rest of the save. HWB-02 additionally enforces the server-owned campaign_save allowlist (daily_recap, day_resolution, live_status, dm_meta, narrative_hooks, runs); unknown or undeclared keys fail closed.';
comment on function public.delete_staged_campaign_state(text, text) is
  'RT01-B/RT02/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/EV2-13.1: generic runtime-state deletion with the same dedicated-key closures (including the same-save inventory/custody/admission/entity-state/applied-status and Run-ownership mutual exclusion on runs) and the same server-owned campaign_save allowlist; unknown or undeclared keys fail closed.';

-- ---------------------------------------------------------------------------
-- 9. Close the Campaign-Clock-after-applied-status doorway. The generic `runs`
--    closure above stops same-save Run changes once applied status is staged, but
--    RT02's dedicated Clock route writes `campaign_clock` with a direct INSERT and
--    would bypass it. This re-declares the RT02 route unchanged except for the
--    same-save applied-status guard, so a Clock advance cannot share one candidate
--    save with a status mutation in either ordering. The Clock remains the only
--    elapsed-time authority; nothing about Clock validation changes.
-- ---------------------------------------------------------------------------
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

  -- EV2-13.1 same-save coupling: applied-status anchors were derived from the
  -- published Clock, so advancing the Clock in the same generation would leave
  -- those anchors proven against elapsed truth this save is about to replace.
  if public._rhc_applied_status_staged_in_save() then
    raise exception
      'this save has already staged a timed applied-status mutation; advancing the Campaign Clock in the same save would leave applied-status anchors proven against the wrong elapsed truth, so the Clock write fails closed (advance the Clock and mutate applied status in separate saves)';
  end if;

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

comment on function public.stage_campaign_clock(text, jsonb) is
  'RT02/EV2-13.1: the only validated Clock mutation route. Stages an absolute target Clock after shape + monotonic/coherence validation against the authoritative published Clock. Replay-safe by construction. EV2-13.1 adds the same-save guard: once this save has staged a timed applied-status mutation, a Clock advance fails closed so applied-status anchors are never proven against stale elapsed truth.';

-- ---------------------------------------------------------------------------
-- 10. Close the dedicated RT04 reconciliation-after-applied-status doorway. The
--     generic `runs` closure above stops generic same-save Run changes once
--     applied status has been staged, but `reconcile_run_resolution` writes the
--     `runs` batch with a direct INSERT and would bypass it. This re-declares the
--     RT04 route unchanged except for the same-save applied-status guard (on top
--     of the EV2-10 inventory and EV2-11 custody and EV2-13 entity-state guards),
--     so every Run-ownership-writing doorway fails closed in a save that has
--     staged a timed applied-status mutation. RT04 is not redesigned.
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

  if public._rhc_inventory_staged_in_save() then
    raise exception
      'this save has already staged an inventory mutation; a Run reconciliation would change Run ownership after inventory authority was proven, so reconciliation fails closed (change Run ownership and inventory in separate saves)';
  end if;

  if public._rhc_custody_staged_in_save() then
    raise exception
      'this save has already staged an item custody mutation; a Run reconciliation would change Run ownership after custody authority was proven, so reconciliation fails closed (change Run ownership and item custody in separate saves)';
  end if;

  if public._rhc_entity_state_staged_in_save() then
    raise exception
      'this save has already staged a mutable entity-state mutation; a Run reconciliation would change Run ownership after entity-state authority was proven, so reconciliation fails closed (change Run ownership and mutable entity state in separate saves)';
  end if;

  -- EV2-13.1 same-save coupling: the same law for a staged timed applied-status
  -- mutation. Applied-status controller authority was proven against the
  -- published Run controller, so a later reconciliation must not change Run
  -- ownership in the same generation.
  if public._rhc_applied_status_staged_in_save() then
    raise exception
      'this save has already staged a timed applied-status mutation; a Run reconciliation would change Run ownership after applied-status controller authority was proven, so reconciliation fails closed (change Run ownership and applied status in separate saves)';
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

comment on function public.reconcile_run_resolution(text, jsonb) is
  'RT04/EV2-10/EV2-11/EV2-13/EV2-13.1: validated Run-reconciliation staging route inside the normal RT01 save lifecycle. Resolves the source Run through the RT03 published read, proves it is still the legal controller, translates the accepted EV2-09A objective result into the Run outcome summary and the continuation/collapse ownership law, preserves + reports consequences whose downstream owner has no legal durable surface yet, and records a replay-proof consumption marker. Enforces one reconciliation per source Run per active save and validates the complete candidate Run ownership graph before staging. EV2-13.1 adds the same-save guard for a staged timed applied-status mutation on top of the EV2-10 inventory, EV2-11 custody and EV2-13 entity-state guards. All-or-nothing through the existing gateway.';

-- ============================================================================
-- SOURCE MIGRATION: 20260923000001_post_ev2_1_save_domain_policy_registry.sql
-- ============================================================================

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

-- ============================================================================
-- SOURCE MIGRATION: 20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql
-- ============================================================================

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
