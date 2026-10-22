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
