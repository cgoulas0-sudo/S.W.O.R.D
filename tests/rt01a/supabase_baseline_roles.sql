-- PROOF-ONLY scaffolding — NOT a production migration.
--
-- Supabase provisions the roles `anon`, `authenticated` and `service_role` as
-- part of its baseline. Vanilla PostgreSQL does not. To prove the RT01-A
-- migrations' real role/privilege behavior against a disposable PostgreSQL
-- instance, this file creates those baseline roles as NOLOGIN roles (exactly the
-- Supabase shape used with SET ROLE in tests).
--
-- This file must never be applied as production schema and must never become a
-- second architecture. It only stands up Supabase's baseline roles locally.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;
