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
