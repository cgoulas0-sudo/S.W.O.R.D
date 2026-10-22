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
