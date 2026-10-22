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
