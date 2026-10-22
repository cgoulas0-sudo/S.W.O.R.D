-- POST-EV2-9 -- Character vitals + resources runtime
-- Rolling High Club validated character-mechanics owner for a tracked character,
-- on the existing RT01 SAVE / publish / mirror / confirm spine.
--
-- This migration is NOT a second save engine, NOT a second controller/ownership
-- ledger and NOT a new persistence/mirror path. It adds ONE dedicated runtime
-- namespace (`character_mechanics`) carrying the bounded machine-readable
-- mechanical capacities/metadata plus the current expendable values for one
-- tracked character, ONE validated controller-safe absolute mutation route, and
-- ONE supported service-only published read. Controller authority is resolved
-- only from authoritative published Run truth.
--
-- Architecture sentence:
--   POST-EV2-9 does not create a new save system. It creates the bounded durable
--   character-vitals/resources mutation surface on top of the existing RT01
--   SAVE / publish / mirror / confirm spine, with controller authority resolved
--   only from authoritative published Run truth.
--
-- WHAT this migration changes:
--   1. `public.mutate_character_mechanics(p_lock_token, p_request)` -- the ONLY
--      way to stage the engine-owned `character_mechanics` runtime namespace. It
--      runs INSIDE the normal campaign save lifecycle, proves the caller's
--      asserted controller (MAINRUN or exactly one RUN #) against authoritative
--      PUBLISHED Run truth for the target character, validates the absolute
--      bounded mechanical snapshot, and stages exactly one record per character.
--   2. The engine-owned `character_mechanics` runtime namespace is a JSON array
--      holding exactly one authoritative record per `character:<slug>`. Definition
--      /capacity and current expendable state live in the SAME record so the
--      backend can validate current <= capacity and a later Rest gate can consume
--      bounded recharge metadata without a second ledger. It is not a history/
--      event subsystem and not a second ownership ledger.
--   3. The generic `stage_campaign_state` / `delete_staged_campaign_state` routes
--      reject the `character_mechanics` key through the existing Patch 1A
--      contract, so a caller/model cannot bypass the validated route with a raw
--      generic runtime write. The HWB-02 ordinary-save allowlist is preserved.
--   4. Patch 1A registers `character_mechanics` as `dedicated` with the exact
--      writer set `[mutate_character_mechanics]`.
--   5. Patch 1B gains the `mutate_character_mechanics` operation (blocked by a
--      same-save `runs` change) plus a trailing `character_mechanics` edge on
--      `stage_runs` / `delete_runs` / `reconcile_runs`, closed through the
--      explicit save-scoped character-mechanics-staging operation fact so a
--      value-equal replay still closes every Run-ownership-writing doorway and
--      the marker never leaks into a later save.
--   6. `public.dm_runtime_read_character_mechanics(p_character_id)` is the
--      supported service-only published read by exact character identity. It
--      reads only the current published generation and returns truthful absence
--      for an untracked character.
--
-- CHARACTER-MECHANICS MODEL (mirrors schemas/character_mechanics.schema.json):
--   * a record is exactly `character_id` + `hp` + `hit_dice` + `spell_slots` +
--     `resources`;
--   * every section carries an explicit `known | unknown | not_applicable`
--     status, so Unknown is never collapsed into zero/empty; a `known` section's
--     empty pool/counter list means "known to be none";
--   * HP: whole non-negative `current` / `maximum` with current <= maximum, plus
--     optional `temporary` (current state, deliberately not capacity-bounded);
--   * Hit Dice: one or more distinct pools (`pool_id`, `die_faces`, `current`,
--     `maximum`) so multiclass / multiple die sizes are representable;
--   * spell slots: distinct pools keyed by `pool_id` (never by `slot_level`, so
--     multiple pools at the same level are representable) with `slot_level`,
--     `current`, `maximum` and bounded `recharge_on`;
--   * limited resources: stable `resource_id`, human `label`, `current`,
--     `maximum` and bounded `recharge_on`;
--   * `recharge_on` is a unique subset of `short_rest` / `long_rest`; empty is
--     legal for a non-Rest-based generic tracked counter (POST-EV2-10 owns the
--     Rest rules it acts on);
--   * values are whole non-negative integers; current <= maximum for every
--     bounded pool/counter; stable local IDs are unique within a record.
--   The record deliberately contains no Markdown mirror, no class/subclass/feat/
--   spell-selection engine, no combat resolution, no death saves, no conditions,
--   no rest lifecycle and no item-owned charge state.
--
-- CONTROLLER LAW (consumes EV2-08/RT03 truth via the shared EV2-10 resolver;
-- invents nothing):
--   * the asserted controller is the ONLY current controller of the target
--     character, and it must match authoritative PUBLISHED Run truth;
--   * under a MAINRUN assertion the character must currently be unclaimed by any
--     published Run; under a RUN # assertion the character must currently be
--     controlled by exactly that RUN #;
--   * a parked played Run that still claims the character, two Runs claiming one
--     character, a malformed published `runs` batch and a duplicated
--     authoritative Run identity all fail closed rather than falling through;
--   * there is no stored controller authority: a former/stale controller write
--     fails closed because published Run truth no longer grants it authority.
--
-- REPLAY / CRASH LAW:
--   The target is ABSOLUTE and canonically ordered, so replaying one logical
--   update is idempotent and cannot drift. A crash/abort before publication
--   leaves no durable record; retry converges on exactly one record. A retry
--   after publication replaces the same character's single record, never
--   creating a second authoritative copy.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/
--    EV2-13.1/POST-EV2-3/POST-EV2-4A forward-only install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'POST-EV2-9 migration refused: resolve the active campaign save before installing the character-vitals/resources route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Small bounded-value validators (internal). Whole non-negative integer,
--    stable local slug ID, human label and bounded Rest-recharge metadata.
--    Unknown stays Unknown: nothing is defaulted or synthesized.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_character_mechanics_nonneg_int(
  p_value jsonb,
  p_label text
)
returns numeric
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_num numeric;
begin
  if p_value is null or jsonb_typeof(p_value) is distinct from 'number' then
    raise exception 'character mechanics % must be a whole non-negative integer', p_label;
  end if;
  v_num := (p_value #>> '{}')::numeric;
  if v_num <> trunc(v_num) then
    raise exception 'character mechanics % must be a whole integer, not fractional', p_label;
  end if;
  if v_num < 0 then
    raise exception 'character mechanics % must be a non-negative integer', p_label;
  end if;
  -- Canonical integer spelling (1.0 -> 1) so equivalent logical targets compare
  -- stably and replay cannot drift on numeric formatting.
  return trim_scale(v_num);
end;
$$;

revoke all on function public._rhc_character_mechanics_nonneg_int(jsonb, text)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_character_mechanics_local_id(
  p_value jsonb,
  p_label text
)
returns text
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_id text;
begin
  if jsonb_typeof(p_value) is distinct from 'string' then
    raise exception 'character mechanics % must be a JSON string', p_label;
  end if;
  v_id := p_value #>> '{}';
  if not public._rhc_full_id_match(v_id, '^[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'character mechanics % must be a non-blank lower-case slug identifier', p_label;
  end if;
  return v_id;
end;
$$;

revoke all on function public._rhc_character_mechanics_local_id(jsonb, text)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_character_mechanics_label(
  p_value jsonb,
  p_label text
)
returns text
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_text text;
begin
  if jsonb_typeof(p_value) is distinct from 'string' then
    raise exception 'character mechanics % must be a JSON string', p_label;
  end if;
  v_text := p_value #>> '{}';
  if v_text !~ '\S' then
    raise exception 'character mechanics % must be a non-blank JSON string', p_label;
  end if;
  return v_text;
end;
$$;

revoke all on function public._rhc_character_mechanics_label(jsonb, text)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_character_mechanics_recharge_on(
  p_value jsonb,
  p_label text
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_item jsonb;
  v_out jsonb := '[]'::jsonb;
  v_count integer;
  v_distinct integer;
begin
  if p_value is null or jsonb_typeof(p_value) is distinct from 'array' then
    raise exception 'character mechanics % must be a JSON array of short_rest/long_rest', p_label;
  end if;
  select count(*), count(distinct e)
    into v_count, v_distinct
    from jsonb_array_elements(p_value) e;
  if v_distinct < v_count then
    raise exception 'character mechanics % must not contain duplicate recharge entries', p_label;
  end if;
  for v_item in
    select e from jsonb_array_elements(p_value) e order by e #>> '{}'
  loop
    if jsonb_typeof(v_item) is distinct from 'string'
       or (v_item #>> '{}') not in ('short_rest', 'long_rest') then
      raise exception
        'character mechanics % may contain only short_rest or long_rest', p_label;
    end if;
    v_out := v_out || jsonb_build_array(v_item);
  end loop;
  return v_out;
end;
$$;

revoke all on function public._rhc_character_mechanics_recharge_on(jsonb, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Section normalization (internal). Each capability section carries its own
--    explicit known/unknown/not_applicable status. A known section requires its
--    payload (possibly an empty list = known to be none); unknown/not_applicable
--    forbids it. Bounded values, unique stable IDs and current <= maximum are
--    enforced here.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_character_mechanics_hp(
  p_section jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_current numeric;
  v_maximum numeric;
  v_temporary numeric;
  v_out jsonb;
begin
  if p_section is null or jsonb_typeof(p_section) is distinct from 'object' then
    raise exception 'character mechanics hp must be a JSON object';
  end if;
  if (p_section - 'status' - 'current' - 'maximum' - 'temporary') <> '{}'::jsonb then
    raise exception
      'character mechanics hp contains fields outside the contract (status, current, maximum, temporary)';
  end if;
  if not (p_section ? 'status') then
    raise exception 'character mechanics hp requires a status';
  end if;
  if jsonb_typeof(p_section -> 'status') is distinct from 'string' then
    raise exception 'character mechanics hp status must be a JSON string';
  end if;
  v_status := p_section ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception 'character mechanics hp status must be known, unknown or not_applicable';
  end if;

  if v_status = 'known' then
    if not (p_section ?& array['current', 'maximum']) then
      raise exception 'known character mechanics hp requires current and maximum';
    end if;
    v_current := public._rhc_character_mechanics_nonneg_int(p_section -> 'current', 'hp current');
    v_maximum := public._rhc_character_mechanics_nonneg_int(p_section -> 'maximum', 'hp maximum');
    if v_current > v_maximum then
      raise exception 'character mechanics hp current cannot exceed maximum';
    end if;
    v_out := jsonb_build_object(
      'status', v_status, 'current', v_current, 'maximum', v_maximum);
    if p_section ? 'temporary' then
      v_temporary := public._rhc_character_mechanics_nonneg_int(
        p_section -> 'temporary', 'hp temporary');
      v_out := v_out || jsonb_build_object('temporary', v_temporary);
    end if;
    return v_out;
  end if;

  if p_section ?| array['current', 'maximum', 'temporary'] then
    raise exception
      'an unknown or not_applicable character mechanics hp must not carry current, maximum or temporary';
  end if;
  return jsonb_build_object('status', v_status);
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_hp(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_normalize_character_mechanics_hit_dice(
  p_section jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_pools jsonb;
  v_pool jsonb;
  v_out_pools jsonb := '[]'::jsonb;
  v_pool_id text;
  v_seen text[] := '{}';
  v_die numeric;
  v_current numeric;
  v_maximum numeric;
begin
  if p_section is null or jsonb_typeof(p_section) is distinct from 'object' then
    raise exception 'character mechanics hit_dice must be a JSON object';
  end if;
  if (p_section - 'status' - 'pools') <> '{}'::jsonb then
    raise exception
      'character mechanics hit_dice contains fields outside the contract (status, pools)';
  end if;
  if not (p_section ? 'status') then
    raise exception 'character mechanics hit_dice requires a status';
  end if;
  if jsonb_typeof(p_section -> 'status') is distinct from 'string' then
    raise exception 'character mechanics hit_dice status must be a JSON string';
  end if;
  v_status := p_section ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception 'character mechanics hit_dice status must be known, unknown or not_applicable';
  end if;

  if v_status <> 'known' then
    if p_section ? 'pools' then
      raise exception
        'an unknown or not_applicable character mechanics hit_dice must not carry pools';
    end if;
    return jsonb_build_object('status', v_status);
  end if;

  if not (p_section ? 'pools') then
    raise exception 'known character mechanics hit_dice requires a pools array';
  end if;
  v_pools := p_section -> 'pools';
  if jsonb_typeof(v_pools) is distinct from 'array' then
    raise exception 'character mechanics hit_dice pools must be a JSON array';
  end if;

  for v_pool in select e from jsonb_array_elements(v_pools) e loop
    if jsonb_typeof(v_pool) is distinct from 'object' then
      raise exception 'character mechanics hit_dice pool must be a JSON object';
    end if;
    if (v_pool - 'pool_id' - 'die_faces' - 'current' - 'maximum') <> '{}'::jsonb then
      raise exception
        'character mechanics hit_dice pool contains fields outside the contract (pool_id, die_faces, current, maximum)';
    end if;
    if not (v_pool ?& array['pool_id', 'die_faces', 'current', 'maximum']) then
      raise exception
        'character mechanics hit_dice pool requires pool_id, die_faces, current and maximum';
    end if;
    v_pool_id := public._rhc_character_mechanics_local_id(v_pool -> 'pool_id', 'hit_dice pool_id');
    if array_position(v_seen, v_pool_id) is not null then
      raise exception
        'character mechanics hit_dice holds duplicate pool_id %; exact one pool per stable ID is required',
        v_pool_id;
    end if;
    v_seen := array_append(v_seen, v_pool_id);
    v_die := public._rhc_character_mechanics_nonneg_int(v_pool -> 'die_faces', 'hit_dice die_faces');
    if v_die not in (4, 6, 8, 10, 12) then
      raise exception
        'character mechanics hit_dice die_faces must be one of 4, 6, 8, 10 or 12';
    end if;
    v_current := public._rhc_character_mechanics_nonneg_int(v_pool -> 'current', 'hit_dice current');
    v_maximum := public._rhc_character_mechanics_nonneg_int(v_pool -> 'maximum', 'hit_dice maximum');
    if v_current > v_maximum then
      raise exception
        'character mechanics hit_dice current cannot exceed maximum for pool %', v_pool_id;
    end if;
    v_out_pools := v_out_pools || jsonb_build_array(jsonb_build_object(
      'pool_id', v_pool_id,
      'die_faces', v_die,
      'current', v_current,
      'maximum', v_maximum));
  end loop;

  select coalesce(jsonb_agg(e order by e ->> 'pool_id'), '[]'::jsonb)
    into v_out_pools
    from jsonb_array_elements(v_out_pools) e;
  return jsonb_build_object('status', v_status, 'pools', v_out_pools);
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_hit_dice(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_normalize_character_mechanics_spell_slots(
  p_section jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_pools jsonb;
  v_pool jsonb;
  v_out_pools jsonb := '[]'::jsonb;
  v_pool_id text;
  v_seen text[] := '{}';
  v_level numeric;
  v_current numeric;
  v_maximum numeric;
  v_recharge jsonb;
begin
  if p_section is null or jsonb_typeof(p_section) is distinct from 'object' then
    raise exception 'character mechanics spell_slots must be a JSON object';
  end if;
  if (p_section - 'status' - 'pools') <> '{}'::jsonb then
    raise exception
      'character mechanics spell_slots contains fields outside the contract (status, pools)';
  end if;
  if not (p_section ? 'status') then
    raise exception 'character mechanics spell_slots requires a status';
  end if;
  if jsonb_typeof(p_section -> 'status') is distinct from 'string' then
    raise exception 'character mechanics spell_slots status must be a JSON string';
  end if;
  v_status := p_section ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception 'character mechanics spell_slots status must be known, unknown or not_applicable';
  end if;

  if v_status <> 'known' then
    if p_section ? 'pools' then
      raise exception
        'an unknown or not_applicable character mechanics spell_slots must not carry pools';
    end if;
    return jsonb_build_object('status', v_status);
  end if;

  if not (p_section ? 'pools') then
    raise exception 'known character mechanics spell_slots requires a pools array';
  end if;
  v_pools := p_section -> 'pools';
  if jsonb_typeof(v_pools) is distinct from 'array' then
    raise exception 'character mechanics spell_slots pools must be a JSON array';
  end if;

  for v_pool in select e from jsonb_array_elements(v_pools) e loop
    if jsonb_typeof(v_pool) is distinct from 'object' then
      raise exception 'character mechanics spell_slots pool must be a JSON object';
    end if;
    if (v_pool - 'pool_id' - 'slot_level' - 'current' - 'maximum' - 'recharge_on') <> '{}'::jsonb then
      raise exception
        'character mechanics spell_slots pool contains fields outside the contract (pool_id, slot_level, current, maximum, recharge_on)';
    end if;
    if not (v_pool ?& array['pool_id', 'slot_level', 'current', 'maximum', 'recharge_on']) then
      raise exception
        'character mechanics spell_slots pool requires pool_id, slot_level, current, maximum and recharge_on';
    end if;
    v_pool_id := public._rhc_character_mechanics_local_id(v_pool -> 'pool_id', 'spell_slots pool_id');
    if array_position(v_seen, v_pool_id) is not null then
      raise exception
        'character mechanics spell_slots holds duplicate pool_id %; multiple pools at one slot level stay distinct only by stable pool_id',
        v_pool_id;
    end if;
    v_seen := array_append(v_seen, v_pool_id);
    v_level := public._rhc_character_mechanics_nonneg_int(v_pool -> 'slot_level', 'spell_slots slot_level');
    if v_level < 1 or v_level > 9 then
      raise exception 'character mechanics spell_slots slot_level must be between 1 and 9';
    end if;
    v_current := public._rhc_character_mechanics_nonneg_int(v_pool -> 'current', 'spell_slots current');
    v_maximum := public._rhc_character_mechanics_nonneg_int(v_pool -> 'maximum', 'spell_slots maximum');
    if v_current > v_maximum then
      raise exception
        'character mechanics spell_slots current cannot exceed maximum for pool %', v_pool_id;
    end if;
    v_recharge := public._rhc_character_mechanics_recharge_on(
      v_pool -> 'recharge_on', 'spell_slots recharge_on');
    v_out_pools := v_out_pools || jsonb_build_array(jsonb_build_object(
      'pool_id', v_pool_id,
      'slot_level', v_level,
      'current', v_current,
      'maximum', v_maximum,
      'recharge_on', v_recharge));
  end loop;

  select coalesce(jsonb_agg(
      e order by (e ->> 'slot_level')::integer, e ->> 'pool_id'), '[]'::jsonb)
    into v_out_pools
    from jsonb_array_elements(v_out_pools) e;
  return jsonb_build_object('status', v_status, 'pools', v_out_pools);
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_spell_slots(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_normalize_character_mechanics_resources(
  p_section jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_items jsonb;
  v_item jsonb;
  v_out_items jsonb := '[]'::jsonb;
  v_resource_id text;
  v_seen text[] := '{}';
  v_label text;
  v_current numeric;
  v_maximum numeric;
  v_recharge jsonb;
begin
  if p_section is null or jsonb_typeof(p_section) is distinct from 'object' then
    raise exception 'character mechanics resources must be a JSON object';
  end if;
  if (p_section - 'status' - 'items') <> '{}'::jsonb then
    raise exception
      'character mechanics resources contains fields outside the contract (status, items)';
  end if;
  if not (p_section ? 'status') then
    raise exception 'character mechanics resources requires a status';
  end if;
  if jsonb_typeof(p_section -> 'status') is distinct from 'string' then
    raise exception 'character mechanics resources status must be a JSON string';
  end if;
  v_status := p_section ->> 'status';
  if v_status not in ('known', 'unknown', 'not_applicable') then
    raise exception 'character mechanics resources status must be known, unknown or not_applicable';
  end if;

  if v_status <> 'known' then
    if p_section ? 'items' then
      raise exception
        'an unknown or not_applicable character mechanics resources must not carry items';
    end if;
    return jsonb_build_object('status', v_status);
  end if;

  if not (p_section ? 'items') then
    raise exception 'known character mechanics resources requires an items array';
  end if;
  v_items := p_section -> 'items';
  if jsonb_typeof(v_items) is distinct from 'array' then
    raise exception 'character mechanics resources items must be a JSON array';
  end if;

  for v_item in select e from jsonb_array_elements(v_items) e loop
    if jsonb_typeof(v_item) is distinct from 'object' then
      raise exception 'character mechanics resources item must be a JSON object';
    end if;
    if (v_item - 'resource_id' - 'label' - 'current' - 'maximum' - 'recharge_on') <> '{}'::jsonb then
      raise exception
        'character mechanics resources item contains fields outside the contract (resource_id, label, current, maximum, recharge_on)';
    end if;
    if not (v_item ?& array['resource_id', 'label', 'current', 'maximum', 'recharge_on']) then
      raise exception
        'character mechanics resources item requires resource_id, label, current, maximum and recharge_on';
    end if;
    v_resource_id := public._rhc_character_mechanics_local_id(v_item -> 'resource_id', 'resources resource_id');
    if array_position(v_seen, v_resource_id) is not null then
      raise exception
        'character mechanics resources holds duplicate resource_id %; one counter per stable resource is required',
        v_resource_id;
    end if;
    v_seen := array_append(v_seen, v_resource_id);
    v_label := public._rhc_character_mechanics_label(v_item -> 'label', 'resources label');
    v_current := public._rhc_character_mechanics_nonneg_int(v_item -> 'current', 'resources current');
    v_maximum := public._rhc_character_mechanics_nonneg_int(v_item -> 'maximum', 'resources maximum');
    if v_current > v_maximum then
      raise exception
        'character mechanics resources current cannot exceed maximum for resource %', v_resource_id;
    end if;
    v_recharge := public._rhc_character_mechanics_recharge_on(
      v_item -> 'recharge_on', 'resources recharge_on');
    v_out_items := v_out_items || jsonb_build_array(jsonb_build_object(
      'resource_id', v_resource_id,
      'label', v_label,
      'current', v_current,
      'maximum', v_maximum,
      'recharge_on', v_recharge));
  end loop;

  select coalesce(jsonb_agg(e order by e ->> 'resource_id'), '[]'::jsonb)
    into v_out_items
    from jsonb_array_elements(v_out_items) e;
  return jsonb_build_object('status', v_status, 'items', v_out_items);
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_resources(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Full body + record + whole-collection validation (internal). The body is
--    the schema box minus `character_id`. The complete candidate collection is
--    validated before anything is staged, and a duplicate character record is an
--    ambiguity that fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_character_mechanics_body(
  p_body jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_body is null or jsonb_typeof(p_body) is distinct from 'object' then
    raise exception 'character mechanics body must be a JSON object';
  end if;
  if (p_body - 'hp' - 'hit_dice' - 'spell_slots' - 'resources') <> '{}'::jsonb then
    raise exception
      'character mechanics body contains fields outside the POST-EV2-9 contract (hp, hit_dice, spell_slots, resources)';
  end if;
  if not (p_body ?& array['hp', 'hit_dice', 'spell_slots', 'resources']) then
    raise exception
      'character mechanics body requires hp, hit_dice, spell_slots and resources sections';
  end if;

  return jsonb_build_object(
    'hp', public._rhc_normalize_character_mechanics_hp(p_body -> 'hp'),
    'hit_dice', public._rhc_normalize_character_mechanics_hit_dice(p_body -> 'hit_dice'),
    'spell_slots', public._rhc_normalize_character_mechanics_spell_slots(p_body -> 'spell_slots'),
    'resources', public._rhc_normalize_character_mechanics_resources(p_body -> 'resources')
  );
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_body(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_normalize_character_mechanics_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_character text;
  v_body jsonb;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'character mechanics record must be a JSON object';
  end if;
  if not (p_record ? 'character_id') then
    raise exception 'character mechanics record requires character_id';
  end if;
  if jsonb_typeof(p_record -> 'character_id') is distinct from 'string' then
    raise exception 'character mechanics character_id must be a JSON string character identity';
  end if;
  v_character := p_record ->> 'character_id';
  if not public._rhc_full_id_match(
    v_character, '^character:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'character mechanics character_id must be a character:<slug> identity';
  end if;

  v_body := public._rhc_normalize_character_mechanics_body(p_record - 'character_id');
  return jsonb_build_object('character_id', v_character) || v_body;
end;
$$;

revoke all on function public._rhc_normalize_character_mechanics_record(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_validate_character_mechanics_collection(
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
  v_character text;
  v_seen text[] := '{}';
begin
  if p_collection is null or jsonb_typeof(p_collection) is distinct from 'array' then
    raise exception 'character_mechanics namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_character_mechanics_record(v_entry);
    v_character := v_norm ->> 'character_id';
    if array_position(v_seen, v_character) is not null then
      raise exception
        'character_mechanics namespace holds duplicate records for %; exactly one authoritative record per character is required',
        v_character;
    end if;
    v_seen := array_append(v_seen, v_character);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_character_mechanics_collection(jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Explicit same-save character-mechanics staging marker (internal). Closure
--    keys on the operation fact, not final JSON equality: an absolute target can
--    be re-staged to a value equal to published reality (a replay), or mutated
--    away and back, and the final value would look unchanged even though a
--    successful staging operation occurred. The save locator records the
--    lock_token that staged character mechanics; the database mints a fresh
--    lock_token at every BEGIN, so the marker can only match the CURRENT save and
--    never leaks into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists character_mechanics_staged_lock_token text;

create or replace function public._rhc_character_mechanics_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.character_mechanics_staged_lock_token is not null
            and cr.character_mechanics_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_character_mechanics_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.character_mechanics_staged_lock_token is
  'POST-EV2-9 internal operation fact: the lock_token of the save that most recently staged a successful character vitals/resources mutation. Matched against the active lock_token so the same-save character-mechanics/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 5. POST-EV2-1 Patch 1A: extend the domain policy registry with the dedicated
--    `character_mechanics` namespace and its exact writer set. Every existing
--    classification and exact message is preserved verbatim; the generic
--    stage/delete routes consult this registry, so they reject the key with no
--    further change.
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
    when 'entity_knowledge' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_entity_knowledge');
      v_stage_error := 'entity_knowledge is engine-owned and can only be staged through mutate_entity_knowledge';
      v_delete_error := 'entity_knowledge is engine-owned and cannot be deleted through the generic route';
    when 'temporal_positions' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_temporal_position');
      v_stage_error := 'temporal_positions is engine-owned and can only be staged through mutate_temporal_position';
      v_delete_error := 'temporal_positions is engine-owned and cannot be deleted through the generic route';
    when 'character_mechanics' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_character_mechanics');
      v_stage_error := 'character_mechanics is engine-owned and can only be staged through mutate_character_mechanics';
      v_delete_error := 'character_mechanics is engine-owned and cannot be deleted through the generic route';
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
  'POST-EV2-1 Patch 1A (extended through POST-EV2-9): the single server-owned, machine-readable runtime state key policy registry. Consumes only the key and returns admission (generic | dedicated | forbidden), the exhaustive array `dedicated_routes` of every legal writer for engine-owned keys, and the exact fail-closed messages. POST-EV2-9 adds character_mechanics=[mutate_character_mechanics] as dedicated. Unknown/undeclared keys are `forbidden` and expose `dedicated_routes=[]`. No caller-supplied policy, no table, no mutable store. Internal-only.';

-- ---------------------------------------------------------------------------
-- 6. POST-EV2-1 Patch 1B: extend the same-save compatibility policy with the new
--    `character_mechanics` edges. The `mutate_character_mechanics` operation is
--    blocked by a same-save `runs` change; the Run-ownership-writing operations
--    (`stage_runs`, `delete_runs`, `reconcile_runs`) gain a trailing
--    `character_mechanics` edge. Every existing edge and exact message is
--    preserved verbatim, and no other compatibility edge is invented.
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
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a RUN-scoped temporal/timespace placement; RUN lane authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'character_mechanics',
          'detector', 'character_mechanics_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a character vitals/resources mutation; character-mechanics controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'the runs batch cannot be changed in a save that has already staged a timed applied-status mutation; applied-status controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged an owner-local knowledge mutation; knowledge controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a RUN-scoped temporal/timespace placement; RUN lane authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'character_mechanics',
          'detector', 'character_mechanics_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a character vitals/resources mutation; character-mechanics controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'this save has already staged a timed applied-status mutation; a Run reconciliation would change Run ownership after applied-status controller authority was proven, so reconciliation fails closed (change Run ownership and applied status in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'entity_knowledge',
          'detector', 'knowledge_staged_in_save',
          'error', 'this save has already staged an owner-local knowledge mutation; a Run reconciliation would change Run ownership after knowledge controller authority was proven, so reconciliation fails closed (change Run ownership and knowledge in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'temporal_positions',
          'detector', 'temporal_position_staged_in_save',
          'error', 'this save has already staged a RUN-scoped temporal/timespace placement; a Run reconciliation would change Run ownership after RUN lane authority was proven, so reconciliation fails closed (change Run ownership and temporal placement in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'character_mechanics',
          'detector', 'character_mechanics_staged_in_save',
          'error', 'this save has already staged a character vitals/resources mutation; a Run reconciliation would change Run ownership after character-mechanics controller authority was proven, so reconciliation fails closed (change Run ownership and character vitals/resources in separate saves)')
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
    when 'mutate_entity_knowledge' then
      v_domain := 'entity_knowledge';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; knowledge controller cannot be proven against published Run truth, so owner-local knowledge mutation fails closed (change Run ownership and knowledge in separate saves)')
      );
    when 'mutate_temporal_position' then
      v_domain := 'temporal_positions';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; RUN lane authority cannot be proven against published Run truth, so RUN-scoped temporal placement fails closed (change Run ownership and RUN-scoped temporal placement in separate saves)')
      );
    when 'mutate_character_mechanics' then
      v_domain := 'character_mechanics';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; character-mechanics controller cannot be proven against published Run truth, so character vitals/resources mutation fails closed (change Run ownership and character vitals/resources in separate saves)')
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
  'POST-EV2-1 Patch 1B (extended through POST-EV2-9): the single server-owned, machine-readable same-save compatibility policy. POST-EV2-9 adds the `mutate_character_mechanics` operation (blocked by a same-save runs change) and a trailing `character_mechanics` edge on stage_runs/delete_runs/reconcile_runs. Every previous edge and exact message is preserved; no other edge is invented. Unknown operations report known=false. Internal-only.';

-- ---------------------------------------------------------------------------
-- 7. POST-EV2-1 Patch 1B: extend the compatibility decision with the
--    `character_mechanics_staged_in_save` detector. Every existing detector and
--    the fail-closed unknown-detector behavior are preserved.
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
      when 'knowledge_staged_in_save' then
        public._rhc_entity_knowledge_staged_in_save()
      when 'temporal_position_staged_in_save' then
        public._rhc_temporal_position_staged_in_save()
      when 'character_mechanics_staged_in_save' then
        public._rhc_character_mechanics_staged_in_save()
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
  'POST-EV2-1 Patch 1B (extended through POST-EV2-9): the server-owned same-save compatibility decision. Evaluates the declared policy for one operation against the active save''s staging/published generations and returns {operation, domain, known, compatible, blocked_by, error}. It answers only whether already-legal operations may coexist in this save; it never judges a mutation''s own semantic validity. Unknown operations/detectors fail closed. Internal-only; no caller-supplied policy.';

-- ---------------------------------------------------------------------------
-- 8. The validated atomic character-vitals/resources mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_character_mechanics(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "character_id": "character:<slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "mechanics": {
--          "hp": { "status": "known", "current": 28, "maximum": 28 },
--          "hit_dice": { "status": "known", "pools": [ ... ] },
--          "spell_slots": { "status": "not_applicable" },
--          "resources": { "status": "known", "items": [ ... ] }
--        }
--      }
--
--    `character_id`, `controller` and `mechanics` are required. The target is
--    ABSOLUTE, not a delta, so replaying one logical update is idempotent.
-- ---------------------------------------------------------------------------
create or replace function public.mutate_character_mechanics(
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
  v_character text;
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
  -- contract owns the Run-ownership exclusion decision. Character-mechanics
  -- authority is proven against published Run truth, so a same-save staged runs
  -- change fails this mutation closed.
  perform public._rhc_require_same_save_compatibility(
    'mutate_character_mechanics', r.staging_generation, r.published_generation);

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'character-mechanics mutation request must be a JSON object';
  end if;
  if not p_request ?& array['character_id', 'controller', 'mechanics'] then
    raise exception
      'character-mechanics mutation request requires character_id, controller and mechanics';
  end if;
  if (p_request - 'character_id' - 'controller' - 'mechanics') <> '{}'::jsonb then
    raise exception
      'character-mechanics mutation request contains fields outside the POST-EV2-9 contract';
  end if;

  -- character_id: a tracked character identity. Never inferred from prose, and
  -- not any other entity type.
  if jsonb_typeof(p_request -> 'character_id') is distinct from 'string' then
    raise exception
      'character-mechanics mutation character_id must be a JSON string character identity';
  end if;
  v_character := p_request ->> 'character_id';
  if not public._rhc_full_id_match(
    v_character, '^character:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'character-mechanics mutation character_id must be a character:<slug> identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch so
  -- a null, missing, non-string or unknown kind can never fall through to
  -- MAINRUN. (Identical law to EV2-10/11/13.)
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
  v_current := public._rhc_inventory_controller_for_owner(v_character);
  if v_kind = 'run' then
    if v_current is null then
      raise exception
        'no published Run currently controls %; a Run controller cannot assert character-mechanics authority',
        v_character;
    end if;
    if v_current is distinct from v_run_id then
      raise exception
        'published Run % currently controls %; asserted Run % does not own it, so this character-mechanics mutation crosses controllers and fails closed',
        v_current, v_character, v_run_id;
    end if;
  else
    if v_current is not null then
      raise exception
        'published Run % currently controls %; MAINRUN may not mutate that character''s vitals/resources (route the cross-controller handoff through the existing reconciliation boundary)',
        v_current, v_character;
    end if;
  end if;

  -- Validate + canonicalize the absolute bounded mechanical target.
  if not (p_request ? 'mechanics') then
    raise exception 'character-mechanics mutation requires a mechanics object';
  end if;
  v_body := public._rhc_normalize_character_mechanics_body(p_request -> 'mechanics');
  v_record := jsonb_build_object('character_id', v_character) || v_body;

  -- Candidate namespace: this save's staged value, else published reality, else
  -- the truthful empty envelope. The candidate begins as a copy of published
  -- reality via BEGIN, so this only fills the never-yet-created case.
  select csg.value into v_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'character_mechanics';
  if v_collection is null then
    select csg.value into v_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'character_mechanics';
  end if;
  if v_collection is null then
    v_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_collection) is distinct from 'array' then
    raise exception 'character_mechanics namespace is unreadable; mutation fails closed';
  end if;

  -- Validate the EXISTING namespace before anything is staged. Malformed or
  -- duplicate unrelated truth fails closed and is never canonicalized by
  -- overwrite.
  perform public._rhc_validate_character_mechanics_collection(v_collection);

  -- Replace the character's single record, or append it when the character is new.
  select
    coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'character_id') = v_character
           then v_record else e end
    ), '[]'::jsonb),
    count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'character_id') = v_character
    )
    into v_new_collection, v_matches
    from jsonb_array_elements(v_collection) e;

  if v_matches = 0 then
    v_new_collection := v_new_collection || jsonb_build_array(v_record);
  elsif v_matches > 1 then
    raise exception
      'character_mechanics namespace already holds duplicate records for %; failing closed',
      v_character;
  end if;

  -- Prove the complete candidate namespace before staging anything.
  perform public._rhc_validate_character_mechanics_collection(v_new_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'character_mechanics', v_new_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Record the operation fact: a successful character-mechanics staging happened
  -- in this save, independent of whether the staged value differs from published
  -- reality. This closes every Run-ownership-writing doorway for the rest of the
  -- save, even for a value-equal replay.
  update public.campaign_runtime
     set character_mechanics_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'character_mechanics_mutation_version', 1,
    'character_id', v_character,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'mechanics', v_body
  );
end;
$$;

revoke all on function public.mutate_character_mechanics(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_character_mechanics(text, jsonb) to service_role;

comment on function public.mutate_character_mechanics(text, jsonb) is
  'POST-EV2-9: the ONLY way to stage the engine-owned character_mechanics runtime namespace. Runs inside the normal RT01 save lifecycle, proves the asserted controller (MAINRUN or exactly one RUN #) against authoritative published Run truth for the target character via the shared EV2-10 resolver, validates the absolute bounded mechanical snapshot (HP, Hit Dice pools, spell-slot pools and limited resources with explicit known/unknown/not_applicable section status and current <= maximum), validates the complete existing and resulting candidate collection, and stages exactly one record per character. Absolute and replay-safe; service_role only.';

-- ---------------------------------------------------------------------------
-- 9. The supported service-only published read by exact character identity.
--    Consumes only the current published generation; returns truthful absence
--    for an untracked character; never reads staged/future state as authority.
-- ---------------------------------------------------------------------------
create or replace function public.dm_runtime_read_character_mechanics(
  p_character_id text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_character text;
  v_collection jsonb;
  v_record jsonb;
begin
  v_character := p_character_id;
  if not public._rhc_full_id_match(
    v_character, '^character:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'character-mechanics read requires one exact character:<slug> identity';
  end if;

  select csg.value into v_collection
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'character_mechanics'
   where cr.id = 1;
  v_collection := coalesce(v_collection, '[]'::jsonb);

  -- The whole published namespace is validated through the existing owner
  -- contract before any record is returned; malformed authoritative truth fails
  -- closed rather than being filtered around.
  perform public._rhc_validate_character_mechanics_collection(v_collection);

  select e into v_record
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'character_id') = v_character
   limit 1;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'character_mechanics',
    'character_id', v_character,
    'runtime', public._rhc_dm_runtime_metadata(),
    'record', v_record
  );
end;
$$;

revoke all on function public.dm_runtime_read_character_mechanics(text)
  from public, anon, authenticated;
grant execute on function public.dm_runtime_read_character_mechanics(text) to service_role;

comment on function public.dm_runtime_read_character_mechanics(text) is
  'POST-EV2-9: service-only published read of one character-mechanics record by exact character:<slug> identity. Reads only the current published generation, validates the whole published namespace through the existing owner contract, and returns the RT01-D runtime metadata envelope plus the single record, or record=null as truthful absence for an untracked character. Stable, read-only, non-mutating; staged/future state is never read as authority.';
