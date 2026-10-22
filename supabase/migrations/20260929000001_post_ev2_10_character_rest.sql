-- POST-EV2-10 -- Character Rest / Long Rest Lifecycle
-- Rolling High Club per-character Short Rest / Long Rest lifecycle owner on the
-- existing RT01 SAVE / publish / mirror / confirm spine.
--
-- This migration is NOT a second save engine, NOT a second controller/ownership
-- ledger and NOT a new persistence/mirror path. It adds ONE dedicated runtime
-- namespace (`character_rests`) carrying the bounded per-character Rest
-- lifecycle/eligibility state, ONE validated controller-safe mutation route
-- (`public.mutate_character_rest`) and ONE supported service-only published read.
-- Controller authority is resolved only from authoritative published Run truth.
--
-- Architecture sentence:
--   POST-EV2-10 does not create a new save system. It creates the bounded durable
--   per-character Rest lifecycle on top of the existing RT01 SAVE / publish /
--   mirror / confirm spine, with RT02 elapsed time as the only time source,
--   POST-EV2-8 as the only RNG root, POST-EV2-9 as the only HP/Hit-Dice/resource
--   owner, and controller authority resolved only from authoritative published
--   Run truth.
--
-- WHAT this migration changes:
--   1. `public.mutate_character_rest(p_lock_token, p_request)` -- the ONLY way to
--      stage the engine-owned `character_rests` runtime namespace. It runs INSIDE
--      the normal campaign save lifecycle, proves the asserted controller
--      (MAINRUN or exactly one RUN #) against authoritative PUBLISHED Run truth
--      for the target character, validates the absolute bounded Rest state
--      transition against the authoritative published elapsed cursor, applies
--      only supported official Short/Long Rest consequences to POST-EV2-9
--      `character_mechanics`, and stages exactly one Rest record per character.
--   2. The engine-owned `character_rests` runtime namespace is a JSON array
--      holding exactly one authoritative record per `character:<slug>`. Rest state
--      never duplicates HP, Hit Dice, spell slots or feature charges. Progress is
--      derived from RT02 elapsed minutes plus this bounded state; no minute-by-
--      minute ticks are persisted.
--   3. The generic `stage_campaign_state` / `delete_staged_campaign_state` routes
--      reject the `character_rests` key through the existing Patch 1A contract.
--      The HWB-02 ordinary-save allowlist is preserved.
--   4. Patch 1A registers `character_rests` as `dedicated` with the exact writer
--      set `[mutate_character_rest]`.
--   5. Patch 1B gains the `mutate_character_rest` operation (blocked by a
--      same-save `runs` change) plus a trailing `character_rests` edge on
--      `stage_runs` / `delete_runs` / `reconcile_runs`, closed through the
--      explicit save-scoped character-rest-staging operation fact so a value-
--      equal replay still closes every Run-ownership-writing doorway and the
--      marker never leaks into a later save. No exclusion is invented between
--      `character_rests` and `campaign_clock` / `character_mechanics`: a legal
--      Rest transaction may coexist with them in one save.
--   6. `public.dm_runtime_read_character_rest(p_character_id)` is the supported
--      service-only published read by exact character identity.
--
-- REST MODEL (mirrors schemas/character_rests.schema.json):
--   * a record is exactly `character_id` + lifecycle fields (status, rest_kind,
--     started/required/completed/last-long anchors, interruptions,
--     short_benefit_granted);
--   * lifecycle: `idle -> active(short|long) -> completed | interrupted`; a Short
--     Rest interruption ends it as `interrupted` with no benefits, while a Long
--     Rest interruption keeps it `active` and adds 60 required minutes;
--   * Short Rest requires >= 1 HP and 60 elapsed minutes; Long Rest requires >= 1
--     HP, 480 elapsed minutes plus 60 per interruption, and a personal 16-hour
--     wait after the last successful Long Rest;
--   * every anchor is derived from authoritative published RT02
--     `elapsed_campaign_minutes`; no wall-clock and no caller-supplied elapsed
--     time is trusted;
--   * Hit Point Die spending adds the die result plus a sourced Constitution
--     modifier (minimum 1 per die) and can never exceed the current maximum;
--   * feature/resource recharge is metadata-driven from POST-EV2-9 `recharge_on`
--     (`short_rest` / `long_rest`); there is no class-specific recharge switchboard
--     and no universal reset;
--   * an `unknown` character-mechanics section fails closed rather than being
--     silently ignored as though fully resolved.
--
-- REPLAY / CRASH LAW:
--   The Rest target is ABSOLUTE and canonically ordered. Re-sending the exact
--   current record is an idempotent replay (no double-spend, no duplicate
--   interruption hour, no double recovery). A crash/abort before publication
--   leaves no durable record; retry converges on exactly one record per character.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT02/RT03/RT04/HWB-02/EV2-10/EV2-11/EV2-12.1/EV2-13/
--    EV2-13.1/POST-EV2-3/POST-EV2-4A/POST-EV2-9 forward-only install pattern.
-- ---------------------------------------------------------------------------
do $$
declare
  r public.campaign_runtime%rowtype;
begin
  perform pg_advisory_xact_lock(hashtext('rhc_campaign_save'));
  select * into r from public.campaign_runtime where id = 1 for update;
  if r.save_in_progress then
    raise exception
      'POST-EV2-10 migration refused: resolve the active campaign save before installing the character Rest route';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Small bounded-value validators (internal). Whole non-negative integer and
--    nullable elapsed anchor. Unknown stays Unknown: nothing is defaulted.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_character_rest_nonneg_int(
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
    raise exception 'character rest % must be a whole non-negative integer', p_label;
  end if;
  v_num := (p_value #>> '{}')::numeric;
  if v_num <> trunc(v_num) then
    raise exception 'character rest % must be a whole integer, not fractional', p_label;
  end if;
  if v_num < 0 then
    raise exception 'character rest % must be a non-negative integer', p_label;
  end if;
  return trim_scale(v_num);
end;
$$;

revoke all on function public._rhc_character_rest_nonneg_int(jsonb, text)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_character_rest_elapsed(
  p_value jsonb,
  p_label text
)
returns numeric
language plpgsql
immutable
security definer
set search_path = ''
as $$
begin
  if p_value is null or jsonb_typeof(p_value) = 'null' then
    return null;
  end if;
  return public._rhc_character_rest_nonneg_int(p_value, p_label);
end;
$$;

revoke all on function public._rhc_character_rest_elapsed(jsonb, text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Rest record normalization + whole-collection validation (internal). The
--    complete candidate collection is validated before anything is staged, and a
--    duplicate character record is an ambiguity that fails closed.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_normalize_character_rest_record(
  p_record jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_char text;
  v_status text;
  v_kind text;
  v_start numeric;
  v_req numeric;
  v_comp numeric;
  v_last numeric;
  v_ints jsonb;
  v_int jsonb;
  v_out_ints jsonb := '[]'::jsonb;
  v_cause text;
  v_at numeric;
  v_granted boolean;
  v_n integer;
begin
  if p_record is null or jsonb_typeof(p_record) is distinct from 'object' then
    raise exception 'character rest record must be a JSON object';
  end if;
  if (p_record - 'character_id' - 'schema_version' - 'status' - 'rest_kind'
        - 'started_at_elapsed_minutes' - 'required_minutes'
        - 'completed_at_elapsed_minutes'
        - 'last_long_rest_completed_at_elapsed_minutes' - 'interruptions'
        - 'short_benefit_granted') <> '{}'::jsonb then
    raise exception
      'character rest record contains fields outside the POST-EV2-10 contract';
  end if;
  if not (p_record ?& array['character_id', 'schema_version', 'status', 'rest_kind',
        'started_at_elapsed_minutes', 'required_minutes',
        'completed_at_elapsed_minutes',
        'last_long_rest_completed_at_elapsed_minutes', 'interruptions',
        'short_benefit_granted']) then
    raise exception
      'character rest record requires character_id, schema_version, status, rest_kind, started_at_elapsed_minutes, required_minutes, completed_at_elapsed_minutes, last_long_rest_completed_at_elapsed_minutes, interruptions and short_benefit_granted';
  end if;

  if jsonb_typeof(p_record -> 'character_id') is distinct from 'string' then
    raise exception 'character rest character_id must be a JSON string character identity';
  end if;
  v_char := p_record ->> 'character_id';
  if not public._rhc_full_id_match(
    v_char, '^character:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception 'character rest character_id must be a character:<slug> identity';
  end if;

  if jsonb_typeof(p_record -> 'schema_version') is distinct from 'number'
     or (p_record ->> 'schema_version')::numeric <> 1 then
    raise exception 'character rest schema_version must be 1';
  end if;

  if jsonb_typeof(p_record -> 'status') is distinct from 'string' then
    raise exception 'character rest status must be a JSON string';
  end if;
  v_status := p_record ->> 'status';
  if v_status not in ('idle', 'active', 'completed', 'interrupted') then
    raise exception 'character rest status must be idle, active, completed or interrupted';
  end if;

  if jsonb_typeof(p_record -> 'rest_kind') = 'null' then
    v_kind := null;
  elsif jsonb_typeof(p_record -> 'rest_kind') = 'string'
        and (p_record ->> 'rest_kind') in ('short', 'long') then
    v_kind := p_record ->> 'rest_kind';
  else
    raise exception 'character rest rest_kind must be null, short or long';
  end if;

  v_start := public._rhc_character_rest_elapsed(
    p_record -> 'started_at_elapsed_minutes', 'started_at_elapsed_minutes');
  v_req := public._rhc_character_rest_elapsed(
    p_record -> 'required_minutes', 'required_minutes');
  v_comp := public._rhc_character_rest_elapsed(
    p_record -> 'completed_at_elapsed_minutes', 'completed_at_elapsed_minutes');
  v_last := public._rhc_character_rest_elapsed(
    p_record -> 'last_long_rest_completed_at_elapsed_minutes',
    'last_long_rest_completed_at_elapsed_minutes');

  if jsonb_typeof(p_record -> 'interruptions') is distinct from 'array' then
    raise exception 'character rest interruptions must be a JSON array';
  end if;
  for v_int in select e from jsonb_array_elements(p_record -> 'interruptions') e loop
    if jsonb_typeof(v_int) is distinct from 'object' then
      raise exception 'character rest interruption must be a JSON object';
    end if;
    if (v_int - 'cause' - 'at_elapsed_minutes') <> '{}'::jsonb then
      raise exception
        'character rest interruption contains fields outside the contract (cause, at_elapsed_minutes)';
    end if;
    if not (v_int ?& array['cause', 'at_elapsed_minutes']) then
      raise exception 'character rest interruption requires cause and at_elapsed_minutes';
    end if;
    if jsonb_typeof(v_int -> 'cause') is distinct from 'string'
       or (v_int ->> 'cause') not in ('initiative', 'spell', 'damage', 'exertion') then
      raise exception
        'character rest interruption cause must be initiative, spell, damage or exertion';
    end if;
    v_cause := v_int ->> 'cause';
    v_at := public._rhc_character_rest_nonneg_int(
      v_int -> 'at_elapsed_minutes', 'interruption at_elapsed_minutes');
    v_out_ints := v_out_ints || jsonb_build_array(
      jsonb_build_object('cause', v_cause, 'at_elapsed_minutes', v_at));
  end loop;
  v_n := jsonb_array_length(v_out_ints);
  if v_n > 1000 then
    raise exception
      'character rest interruptions may hold at most 1000 entries (schema maximum)';
  end if;

  if jsonb_typeof(p_record -> 'short_benefit_granted') is distinct from 'boolean' then
    raise exception 'character rest short_benefit_granted must be a boolean';
  end if;
  v_granted := (p_record ->> 'short_benefit_granted')::boolean;

  if v_status = 'idle' then
    if v_kind is not null or v_start is not null or v_req is not null
       or v_comp is not null or v_n <> 0 or v_granted then
      raise exception 'an idle character rest must not hold an active/completed rest';
    end if;
  else
    if v_kind is null then
      raise exception 'a % character rest requires a rest_kind', v_status;
    end if;
    if v_start is null or v_req is null then
      raise exception
        'a % character rest requires started_at_elapsed_minutes and required_minutes',
        v_status;
    end if;
    if v_kind = 'short' then
      if v_req <> 60 then
        raise exception 'a short rest requires exactly 60 required minutes';
      end if;
      if v_status = 'interrupted' then
        if v_n < 1 then
          raise exception
            'an interrupted short rest must record the interruption that ended it';
        end if;
      elsif v_n <> 0 then
        raise exception 'a short rest cannot hold long-rest interruptions';
      end if;
    else
      if v_req <> 480 + 60 * v_n then
        raise exception
          'a long rest requires 480 required minutes plus 60 minutes per interruption';
      end if;
    end if;

    if v_status = 'active' then
      if v_comp is not null then
        raise exception
          'an active character rest must not have completed_at_elapsed_minutes';
      end if;
    elsif v_status = 'completed' then
      if v_comp is null then
        raise exception
          'a completed character rest requires completed_at_elapsed_minutes';
      end if;
      if v_comp < v_start then
        raise exception 'a completed character rest cannot complete before it started';
      end if;
    elsif v_status = 'interrupted' then
      if v_kind <> 'short' then
        raise exception 'only a short rest is left interrupted; a long rest resumes';
      end if;
      if v_comp is not null then
        raise exception
          'an interrupted character rest must not have completed_at_elapsed_minutes';
      end if;
      if v_granted then
        raise exception 'an interrupted short rest cannot grant a short-rest benefit';
      end if;
    end if;
  end if;

  return jsonb_build_object(
    'character_id', v_char,
    'schema_version', 1,
    'status', v_status,
    'rest_kind', v_kind,
    'started_at_elapsed_minutes', v_start,
    'required_minutes', v_req,
    'completed_at_elapsed_minutes', v_comp,
    'last_long_rest_completed_at_elapsed_minutes', v_last,
    'interruptions', v_out_ints,
    'short_benefit_granted', v_granted
  );
end;
$$;

revoke all on function public._rhc_normalize_character_rest_record(jsonb)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_validate_character_rests_collection(
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
    raise exception 'character_rests namespace must be a JSON array';
  end if;
  for v_entry in select e from jsonb_array_elements(p_collection) e loop
    v_norm := public._rhc_normalize_character_rest_record(v_entry);
    v_character := v_norm ->> 'character_id';
    if array_position(v_seen, v_character) is not null then
      raise exception
        'character_rests namespace holds duplicate records for %; exactly one authoritative record per character is required',
        v_character;
    end if;
    v_seen := array_append(v_seen, v_character);
  end loop;
  return true;
end;
$$;

revoke all on function public._rhc_validate_character_rests_collection(jsonb)
  from public, anon, authenticated, service_role;

-- Canonical idle record for a character with no persisted Rest state yet.
create or replace function public._rhc_character_rest_idle(p_character text)
returns jsonb
language sql
immutable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'character_id', p_character,
    'schema_version', 1,
    'status', 'idle',
    'rest_kind', null,
    'started_at_elapsed_minutes', null,
    'required_minutes', null,
    'completed_at_elapsed_minutes', null,
    'last_long_rest_completed_at_elapsed_minutes', null,
    'interruptions', '[]'::jsonb,
    'short_benefit_granted', false
  )
$$;

revoke all on function public._rhc_character_rest_idle(text)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Official Rest consequence application to POST-EV2-9 `character_mechanics`
--    (internal). Rest applies only supported consequences; an `unknown`
--    rest-sensitive section fails closed rather than being silently ignored.
--    Feature/resource recharge is metadata-driven from `recharge_on`.
-- ---------------------------------------------------------------------------
create or replace function public._rhc_rest_recharge_section(
  p_section jsonb,
  p_on text
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_key text;
  v_entry jsonb;
  v_out jsonb := '[]'::jsonb;
begin
  if (p_section ->> 'status') <> 'known' then
    return p_section;
  end if;
  if p_section ? 'pools' then
    v_key := 'pools';
  elsif p_section ? 'items' then
    v_key := 'items';
  else
    return p_section;
  end if;
  for v_entry in select e from jsonb_array_elements(p_section -> v_key) e loop
    if (v_entry -> 'recharge_on') ? p_on then
      v_entry := jsonb_set(v_entry, '{current}', to_jsonb((v_entry ->> 'maximum')::numeric));
    end if;
    v_out := v_out || jsonb_build_array(v_entry);
  end loop;
  return jsonb_build_object('status', 'known', v_key, v_out);
end;
$$;

revoke all on function public._rhc_rest_recharge_section(jsonb, text)
  from public, anon, authenticated, service_role;

create or replace function public._rhc_apply_rest_benefits(
  p_body jsonb,
  p_rest_kind text,
  p_spending jsonb,
  p_con jsonb
)
returns jsonb
language plpgsql
immutable
security definer
set search_path = ''
as $$
declare
  v_hp jsonb := p_body -> 'hp';
  v_hd jsonb := p_body -> 'hit_dice';
  v_ss jsonb := p_body -> 'spell_slots';
  v_res jsonb := p_body -> 'resources';
  v_status text;
  v_con_val integer;
  v_spend_entry jsonb;
  v_pool_id text;
  v_rolls jsonb;
  v_roll jsonb;
  v_faces numeric;
  v_cur numeric;
  v_cnt integer;
  v_spent numeric;
  v_recovered numeric := 0;
  v_seen text[] := '{}';
  v_pool jsonb;
  v_new_pools jsonb := '[]'::jsonb;
  v_new_hp jsonb;
  v_new_hd jsonb;
  v_new_ss jsonb;
  v_new_res jsonb;
begin
  if p_rest_kind not in ('short', 'long') then
    raise exception 'character rest benefit application requires a short or long rest';
  end if;

  -- Unknown is truthful but cannot be resolved into official consequences.
  foreach v_status in array array[
    v_hp ->> 'status', v_hd ->> 'status', v_ss ->> 'status', v_res ->> 'status'
  ] loop
    if v_status = 'unknown' then
      raise exception
        'character rest cannot resolve an unknown character-mechanics section; unsupported rest-sensitive state fails closed rather than being silently ignored';
    end if;
  end loop;
  if (v_hp ->> 'status') <> 'known' then
    raise exception 'character rest requires known hit points to apply Rest consequences';
  end if;
  if (v_hd ->> 'status') <> 'known' then
    raise exception 'character rest requires known Hit Dice to apply Rest consequences';
  end if;

  if p_spending is not null and jsonb_typeof(p_spending) is distinct from 'array' then
    raise exception 'hit_die_spending must be a JSON array';
  end if;
  if p_spending is not null and jsonb_typeof(p_spending) = 'array'
     and jsonb_array_length(p_spending) > 0 then
    if p_con is null or jsonb_typeof(p_con) is distinct from 'object' then
      raise exception
        'Hit Point Die spending requires a con_modifier with declared source provenance';
    end if;
    if not (p_con ?& array['value', 'source'])
       or (p_con - 'value' - 'source') <> '{}'::jsonb then
      raise exception 'con_modifier requires exactly value and source';
    end if;
    if jsonb_typeof(p_con -> 'source') is distinct from 'string'
       or (p_con ->> 'source') !~ '\S' then
      raise exception 'con_modifier source must be a non-blank authoritative source string';
    end if;
    if jsonb_typeof(p_con -> 'value') is distinct from 'number'
       or (p_con ->> 'value') !~ '^-?[0-9]+$' then
      raise exception 'con_modifier value must be an integer';
    end if;
    v_con_val := (p_con ->> 'value')::integer;
  end if;

  -- Validate every declared die against the declared pool; compute recovery.
  for v_spend_entry in
    select e from jsonb_array_elements(coalesce(p_spending, '[]'::jsonb)) e
  loop
    if jsonb_typeof(v_spend_entry) is distinct from 'object' then
      raise exception 'hit_die_spending entry must be a JSON object';
    end if;
    if (v_spend_entry - 'pool_id' - 'rolls') <> '{}'::jsonb then
      raise exception
        'hit_die_spending entry contains fields outside the contract (pool_id, rolls)';
    end if;
    if not (v_spend_entry ?& array['pool_id', 'rolls']) then
      raise exception 'hit_die_spending entry requires pool_id and rolls';
    end if;
    if jsonb_typeof(v_spend_entry -> 'pool_id') is distinct from 'string' then
      raise exception 'hit_die_spending pool_id must be a JSON string';
    end if;
    v_pool_id := v_spend_entry ->> 'pool_id';
    if array_position(v_seen, v_pool_id) is not null then
      raise exception 'hit_die_spending declares pool % more than once', v_pool_id;
    end if;
    v_seen := array_append(v_seen, v_pool_id);
    v_rolls := v_spend_entry -> 'rolls';
    if jsonb_typeof(v_rolls) is distinct from 'array'
       or jsonb_array_length(v_rolls) < 1 then
      raise exception
        'hit_die_spending rolls must be a non-empty array for pool %', v_pool_id;
    end if;

    select (p ->> 'die_faces')::numeric, (p ->> 'current')::numeric
      into v_faces, v_cur
      from jsonb_array_elements(v_hd -> 'pools') p
     where (p ->> 'pool_id') = v_pool_id;
    if not found then
      raise exception 'hit_die_spending names unknown Hit Die pool %', v_pool_id;
    end if;
    v_cnt := jsonb_array_length(v_rolls);
    if v_cnt > v_cur then
      raise exception
        'hit_die_spending spends % dice from pool % but only % remain',
        v_cnt, v_pool_id, v_cur;
    end if;

    for v_roll in select e from jsonb_array_elements(v_rolls) e loop
      if jsonb_typeof(v_roll) is distinct from 'number' then
        raise exception 'hit_die_spending rolls must contain only numbers';
      end if;
      if (v_roll #>> '{}')::numeric <> trunc((v_roll #>> '{}')::numeric)
         or (v_roll #>> '{}')::numeric < 1
         or (v_roll #>> '{}')::numeric > v_faces then
        raise exception
          'hit_die_spending roll % for pool % is outside the valid 1..% range',
          v_roll #>> '{}', v_pool_id, v_faces;
      end if;
      v_recovered := v_recovered
        + greatest(1, (v_roll #>> '{}')::numeric + v_con_val);
    end loop;
  end loop;

  if p_rest_kind = 'long' then
    -- All lost HP restored, all spent Hit Dice restored, Long-Rest recharge only.
    -- A completed Long Rest also clears any current Temporary Hit Points.
    v_new_hp := jsonb_build_object(
      'status', 'known',
      'current', (v_hp ->> 'maximum')::numeric,
      'maximum', (v_hp ->> 'maximum')::numeric);
    if v_hp ? 'temporary' then
      v_new_hp := v_new_hp || jsonb_build_object('temporary', 0);
    end if;
    for v_pool in
      select e from jsonb_array_elements(v_hd -> 'pools') e order by e ->> 'pool_id'
    loop
      v_new_pools := v_new_pools || jsonb_build_array(jsonb_build_object(
        'pool_id', v_pool ->> 'pool_id',
        'die_faces', (v_pool ->> 'die_faces')::numeric,
        'current', (v_pool ->> 'maximum')::numeric,
        'maximum', (v_pool ->> 'maximum')::numeric));
    end loop;
    v_new_hd := jsonb_build_object('status', 'known', 'pools', v_new_pools);
    v_new_ss := public._rhc_rest_recharge_section(v_ss, 'long_rest');
    v_new_res := public._rhc_rest_recharge_section(v_res, 'long_rest');
  else
    -- Short Rest: optional Hit Point Die spending + Short-Rest recharge only.
    v_new_hp := jsonb_build_object(
      'status', 'known',
      'current', least(
        (v_hp ->> 'maximum')::numeric,
        (v_hp ->> 'current')::numeric + v_recovered),
      'maximum', (v_hp ->> 'maximum')::numeric);
    if v_hp ? 'temporary' then
      v_new_hp := v_new_hp
        || jsonb_build_object('temporary', (v_hp ->> 'temporary')::numeric);
    end if;
    for v_pool in
      select e from jsonb_array_elements(v_hd -> 'pools') e order by e ->> 'pool_id'
    loop
      select coalesce(sum(jsonb_array_length(s -> 'rolls')), 0)
        into v_spent
        from jsonb_array_elements(coalesce(p_spending, '[]'::jsonb)) s
       where (s ->> 'pool_id') = (v_pool ->> 'pool_id');
      v_new_pools := v_new_pools || jsonb_build_array(jsonb_build_object(
        'pool_id', v_pool ->> 'pool_id',
        'die_faces', (v_pool ->> 'die_faces')::numeric,
        'current', greatest(0, (v_pool ->> 'current')::numeric - v_spent),
        'maximum', (v_pool ->> 'maximum')::numeric));
    end loop;
    v_new_hd := jsonb_build_object('status', 'known', 'pools', v_new_pools);
    v_new_ss := public._rhc_rest_recharge_section(v_ss, 'short_rest');
    v_new_res := public._rhc_rest_recharge_section(v_res, 'short_rest');
  end if;

  return jsonb_build_object(
    'hp', v_new_hp,
    'hit_dice', v_new_hd,
    'spell_slots', v_new_ss,
    'resources', v_new_res
  );
end;
$$;

revoke all on function public._rhc_apply_rest_benefits(jsonb, text, jsonb, jsonb)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Explicit same-save character-rest staging marker (internal). Closure keys
--    on the operation fact, not final JSON equality: an absolute target can be
--    re-staged to a value equal to published reality (a replay). The save locator
--    records the lock_token that staged a character Rest; the database mints a
--    fresh lock_token at every BEGIN, so the marker can only match the CURRENT
--    save and never leaks into a later save. Internal-only.
-- ---------------------------------------------------------------------------
alter table public.campaign_runtime
  add column if not exists character_rests_staged_lock_token text;

create or replace function public._rhc_character_rests_staged_in_save()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select cr.character_rests_staged_lock_token is not null
            and cr.character_rests_staged_lock_token = cr.lock_token
       from public.campaign_runtime cr
      where cr.id = 1),
    false)
$$;

revoke all on function public._rhc_character_rests_staged_in_save()
  from public, anon, authenticated, service_role;

comment on column public.campaign_runtime.character_rests_staged_lock_token is
  'POST-EV2-10 internal operation fact: the lock_token of the save that most recently staged a successful character Rest mutation. Matched against the active lock_token so the same-save character-rest/Run-ownership exclusion keys on the staging operation, not on final value equality. Never inherited across saves.';

-- ---------------------------------------------------------------------------
-- 5. POST-EV2-1 Patch 1A: extend the domain policy registry with the dedicated
--    `character_rests` namespace and its exact writer set. Every existing
--    classification and exact message is preserved verbatim.
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
    when 'character_rests' then
      v_admission := 'dedicated';
      v_routes := jsonb_build_array('mutate_character_rest');
      v_stage_error := 'character_rests is engine-owned and can only be staged through mutate_character_rest';
      v_delete_error := 'character_rests is engine-owned and cannot be deleted through the generic route';
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
  'POST-EV2-1 Patch 1A (extended through POST-EV2-10): the single server-owned, machine-readable runtime state key policy registry. POST-EV2-10 adds character_rests=[mutate_character_rest] as dedicated. Every previous classification and exact message is preserved; unknown/undeclared keys are `forbidden`. Internal-only.';

-- ---------------------------------------------------------------------------
-- 6. POST-EV2-1 Patch 1B: extend the same-save compatibility policy with the new
--    `character_rests` edges. `mutate_character_rest` is blocked by a same-save
--    `runs` change; the Run-ownership-writing operations gain a trailing
--    `character_rests` edge. No edge is invented between `character_rests` and
--    `campaign_clock` / `character_mechanics`.
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
          'error', 'the runs batch cannot be changed in a save that has already staged a character vitals/resources mutation; character-mechanics controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'character_rests',
          'detector', 'character_rests_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a character Rest mutation; Rest controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'the runs batch cannot be changed in a save that has already staged a character vitals/resources mutation; character-mechanics controller authority would become stale against the changed Run ownership, so abort this save and start a new one'),
        jsonb_build_object(
          'blocked_by', 'character_rests',
          'detector', 'character_rests_staged_in_save',
          'error', 'the runs batch cannot be changed in a save that has already staged a character Rest mutation; Rest controller authority would become stale against the changed Run ownership, so abort this save and start a new one')
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
          'error', 'this save has already staged a character vitals/resources mutation; a Run reconciliation would change Run ownership after character-mechanics controller authority was proven, so reconciliation fails closed (change Run ownership and character vitals/resources in separate saves)'),
        jsonb_build_object(
          'blocked_by', 'character_rests',
          'detector', 'character_rests_staged_in_save',
          'error', 'this save has already staged a character Rest mutation; a Run reconciliation would change Run ownership after Rest controller authority was proven, so reconciliation fails closed (change Run ownership and character Rest in separate saves)')
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
    when 'mutate_character_rest' then
      v_domain := 'character_rests';
      v_edges := jsonb_build_array(
        jsonb_build_object(
          'blocked_by', 'runs',
          'detector', 'runs_changed_in_save',
          'error', 'this save has staged a different runs batch; Rest controller cannot be proven against published Run truth, so character Rest mutation fails closed (change Run ownership and character Rest in separate saves)')
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
  'POST-EV2-1 Patch 1B (extended through POST-EV2-10): the single server-owned, machine-readable same-save compatibility policy. POST-EV2-10 adds the `mutate_character_rest` operation (blocked by a same-save runs change) and a trailing `character_rests` edge on stage_runs/delete_runs/reconcile_runs. Every previous edge and exact message is preserved; no other edge is invented. Internal-only.';

-- ---------------------------------------------------------------------------
-- 7. POST-EV2-1 Patch 1B: extend the compatibility decision with the
--    `character_rests_staged_in_save` detector.
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
      when 'character_rests_staged_in_save' then
        public._rhc_character_rests_staged_in_save()
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
  'POST-EV2-1 Patch 1B (extended through POST-EV2-10): the server-owned same-save compatibility decision. Unknown operations/detectors fail closed. Internal-only; no caller-supplied policy.';

-- ---------------------------------------------------------------------------
-- 8. The validated atomic character Rest mutation route.
--
--    Caller contract (normal save lifecycle):
--      begin_campaign_save(...) -> mutate_character_rest(token, request)
--      -> publish_campaign_save(token) -> existing mirror/confirmation handshake
--
--    Request shape:
--      {
--        "character_id": "character:<slug>",
--        "controller": { "kind": "mainrun" }
--                    | { "kind": "run", "run_id": "<R##>" },
--        "rest": <absolute character-rests target record>,
--        "hit_die_spending": [ { "pool_id": "<slug>", "rolls": [1, 7] } ],  // optional
--        "con_modifier": { "value": 3, "source": "<authoritative source>" } // required with spending
--      }
--
--    `character_id`, `controller` and `rest` are required. The target is ABSOLUTE,
--    not a delta. Re-sending the exact current record is an idempotent replay (no
--    double-spend, no duplicate interruption hour, no double recovery).
-- ---------------------------------------------------------------------------
create or replace function public.mutate_character_rest(
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
  v_current_controller text;
  v_now integer;
  v_rest_collection jsonb;
  v_current jsonb;
  v_target jsonb;
  v_t_status text;
  v_c_status text;
  v_t_kind text;
  v_c_kind text;
  v_t_start numeric;
  v_c_start numeric;
  v_t_req numeric;
  v_c_req numeric;
  v_t_comp numeric;
  v_c_comp numeric;
  v_t_last numeric;
  v_c_last numeric;
  v_t_ints jsonb;
  v_c_ints jsonb;
  v_t_granted boolean;
  v_c_granted boolean;
  v_expected_ints jsonb;
  v_append jsonb;
  v_append_at numeric;
  v_mech_collection jsonb;
  v_mech_record jsonb;
  v_mech_body jsonb;
  v_new_body jsonb;
  v_new_rest_collection jsonb;
  v_new_mech_collection jsonb;
  v_matches integer;
  v_replay boolean := false;
begin
  r := public._rhc_require_active_save(p_lock_token);
  if r.staging_save_kind = 'engineering_release' then
    raise exception 'engineering_release forbids campaign state mutation';
  end if;

  -- Same-save compatibility (Patch 1B): Rest authority is proven against
  -- published Run truth, so a same-save staged runs change fails closed. Rest may
  -- legally coexist with a Campaign Clock change and a character-mechanics change
  -- in one save; no exclusion is invented between those domains.
  perform public._rhc_require_same_save_compatibility(
    'mutate_character_rest', r.staging_generation, r.published_generation);

  -- Bounded request contract.
  if p_request is null or jsonb_typeof(p_request) is distinct from 'object' then
    raise exception 'character rest mutation request must be a JSON object';
  end if;
  if not (p_request ?& array['character_id', 'controller', 'rest']) then
    raise exception
      'character rest mutation request requires character_id, controller and rest';
  end if;
  if (p_request - 'character_id' - 'controller' - 'rest'
        - 'hit_die_spending' - 'con_modifier') <> '{}'::jsonb then
    raise exception
      'character rest mutation request contains fields outside the POST-EV2-10 contract';
  end if;

  if jsonb_typeof(p_request -> 'character_id') is distinct from 'string' then
    raise exception
      'character rest mutation character_id must be a JSON string character identity';
  end if;
  v_character := p_request ->> 'character_id';
  if not public._rhc_full_id_match(
    v_character, '^character:[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'character rest mutation character_id must be a character:<slug> identity';
  end if;

  -- Controller-kind type/enum validation happens BEFORE any authority branch.
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
  -- claim and a duplicated authoritative Run identity all fail closed there).
  v_current_controller := public._rhc_inventory_controller_for_owner(v_character);
  if v_kind = 'run' then
    if v_current_controller is null then
      raise exception
        'no published Run currently controls %; a Run controller cannot assert Rest authority',
        v_character;
    end if;
    if v_current_controller is distinct from v_run_id then
      raise exception
        'published Run % currently controls %; asserted Run % does not own it, so this character Rest mutation crosses controllers and fails closed',
        v_current_controller, v_character, v_run_id;
    end if;
  else
    if v_current_controller is not null then
      raise exception
        'published Run % currently controls %; MAINRUN may not mutate that character''s Rest state (route the cross-controller handoff through the existing reconciliation boundary)',
        v_current_controller, v_character;
    end if;
  end if;

  -- Normalize the absolute target Rest record.
  v_target := public._rhc_normalize_character_rest_record(p_request -> 'rest');
  if (v_target ->> 'character_id') <> v_character then
    raise exception
      'character rest target character_id must match the mutation character_id';
  end if;

  -- Candidate Rest namespace: this save's staged value, else published reality,
  -- else the truthful empty envelope.
  select csg.value into v_rest_collection
    from public.campaign_state_generations csg
   where csg.generation = r.staging_generation
     and csg.key = 'character_rests';
  if v_rest_collection is null then
    select csg.value into v_rest_collection
      from public.campaign_state_generations csg
     where csg.generation = r.published_generation
       and csg.key = 'character_rests';
  end if;
  if v_rest_collection is null then
    v_rest_collection := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_rest_collection) is distinct from 'array' then
    raise exception 'character_rests namespace is unreadable; mutation fails closed';
  end if;
  perform public._rhc_validate_character_rests_collection(v_rest_collection);

  select e into v_current
    from jsonb_array_elements(v_rest_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'character_id') = v_character
   limit 1;
  if v_current is null then
    v_current := public._rhc_character_rest_idle(v_character);
  else
    v_current := public._rhc_normalize_character_rest_record(v_current);
  end if;

  v_t_status := v_target ->> 'status';
  v_c_status := v_current ->> 'status';
  v_t_kind := v_target ->> 'rest_kind';
  v_c_kind := v_current ->> 'rest_kind';
  v_t_start := (v_target ->> 'started_at_elapsed_minutes')::numeric;
  v_c_start := (v_current ->> 'started_at_elapsed_minutes')::numeric;
  v_t_req := (v_target ->> 'required_minutes')::numeric;
  v_c_req := (v_current ->> 'required_minutes')::numeric;
  v_t_comp := (v_target ->> 'completed_at_elapsed_minutes')::numeric;
  v_c_comp := (v_current ->> 'completed_at_elapsed_minutes')::numeric;
  v_t_last := (v_target ->> 'last_long_rest_completed_at_elapsed_minutes')::numeric;
  v_c_last := (v_current ->> 'last_long_rest_completed_at_elapsed_minutes')::numeric;
  v_t_ints := v_target -> 'interruptions';
  v_c_ints := v_current -> 'interruptions';
  v_t_granted := (v_target ->> 'short_benefit_granted')::boolean;
  v_c_granted := (v_current ->> 'short_benefit_granted')::boolean;

  -- Idempotent absolute replay: the exact current target is a no-op. This is the
  -- only path that does not require authoritative elapsed time, so a retry after
  -- uncertain publication cannot double-apply anything.
  if v_target = v_current then
    v_replay := true;
    -- A value-equal replay is still a successful staging operation fact: it must
    -- close every Run-ownership-writing doorway for the rest of the save even
    -- though the staged value matches published reality.
    update public.campaign_runtime
       set character_rests_staged_lock_token = r.lock_token
     where id = 1;
    return jsonb_build_object(
      'character_rest_mutation_version', 1,
      'character_id', v_character,
      'controller', v_controller,
      'runtime', public._rhc_dm_runtime_metadata(),
      'replay', true,
      'record', v_target
    );
  end if;

  -- Every genuine transition anchors to authoritative published elapsed time.
  v_now := public._rhc_published_clock_elapsed();

  v_new_body := null;

  -- --- start ---------------------------------------------------------------
  if v_t_status = 'active'
     and v_c_status in ('idle', 'completed', 'interrupted') then
    if v_t_start <> v_now then
      raise exception
        'character rest start must anchor to the authoritative published elapsed time';
    end if;
    if jsonb_array_length(v_t_ints) <> 0 or v_t_granted then
      raise exception 'a newly started character rest must not carry interruptions or a granted short benefit';
    end if;
    if v_t_last is distinct from v_c_last then
      raise exception
        'starting a character rest must preserve the personal last-successful-Long-Rest anchor';
    end if;

    -- At least 1 HP is required to start any Rest.
    select csg.value into v_mech_collection
      from public.campaign_state_generations csg
     where csg.generation = r.staging_generation
       and csg.key = 'character_mechanics';
    if v_mech_collection is null then
      select csg.value into v_mech_collection
        from public.campaign_state_generations csg
       where csg.generation = r.published_generation
         and csg.key = 'character_mechanics';
    end if;
    if v_mech_collection is null or jsonb_typeof(v_mech_collection) is distinct from 'array' then
      raise exception
        'character % has no readable character_mechanics record; Rest cannot verify the at-least-1-HP start requirement',
        v_character;
    end if;
    perform public._rhc_validate_character_mechanics_collection(v_mech_collection);
    select e into v_mech_record
      from jsonb_array_elements(v_mech_collection) e
     where jsonb_typeof(e) = 'object'
       and (e ->> 'character_id') = v_character
     limit 1;
    if v_mech_record is null then
      raise exception
        'character % has no character_mechanics record; Rest cannot verify the at-least-1-HP start requirement',
        v_character;
    end if;
    v_mech_body := v_mech_record - 'character_id';
    if (v_mech_body -> 'hp' ->> 'status') <> 'known'
       or (v_mech_body -> 'hp' ->> 'current')::numeric < 1 then
      raise exception
        'character % must have at least 1 current hit point to start a Rest',
        v_character;
    end if;

    -- Long Rest may not start until 16 hours after that character's last success.
    if v_t_kind = 'long' and v_c_last is not null
       and v_now - v_c_last < 960 then
      raise exception
        'character % must wait at least 16 hours (960 elapsed minutes) after a successful Long Rest before starting another',
        v_character;
    end if;

  -- --- complete ------------------------------------------------------------
  elsif v_t_status = 'completed' and v_c_status = 'active' then
    if v_t_kind <> v_c_kind or v_t_start <> v_c_start or v_t_req <> v_c_req
       or v_t_ints <> v_c_ints or v_t_granted <> v_c_granted then
      raise exception
        'a completed character rest must preserve its active rest identity and timing';
    end if;
    if v_t_comp <> v_now then
      raise exception
        'character rest completion must anchor to the authoritative published elapsed time';
    end if;
    if v_now - v_c_start < v_c_req then
      raise exception
        'character rest cannot complete before its official minimum duration of % elapsed minutes',
        v_c_req;
    end if;

    select csg.value into v_mech_collection
      from public.campaign_state_generations csg
     where csg.generation = r.staging_generation
       and csg.key = 'character_mechanics';
    if v_mech_collection is null then
      select csg.value into v_mech_collection
        from public.campaign_state_generations csg
       where csg.generation = r.published_generation
         and csg.key = 'character_mechanics';
    end if;
    if v_mech_collection is null or jsonb_typeof(v_mech_collection) is distinct from 'array' then
      raise exception
        'character % has no readable character_mechanics record; Rest consequences cannot be applied',
        v_character;
    end if;
    perform public._rhc_validate_character_mechanics_collection(v_mech_collection);
    select e into v_mech_record
      from jsonb_array_elements(v_mech_collection) e
     where jsonb_typeof(e) = 'object'
       and (e ->> 'character_id') = v_character
     limit 1;
    if v_mech_record is null then
      raise exception
        'character % has no character_mechanics record; Rest consequences cannot be applied',
        v_character;
    end if;
    v_mech_body := v_mech_record - 'character_id';

    if v_t_kind = 'short' then
      if v_t_last is distinct from v_c_last then
        raise exception
          'a completed Short Rest must preserve the personal last-successful-Long-Rest anchor';
      end if;
      v_new_body := public._rhc_apply_rest_benefits(
        v_mech_body, 'short',
        p_request -> 'hit_die_spending', p_request -> 'con_modifier');
    else
      if v_t_last <> v_now then
        raise exception
          'a successful Long Rest must record the authoritative completion anchor';
      end if;
      if p_request ? 'hit_die_spending' then
        raise exception
          'Hit Point Die spending is a Short Rest benefit and is not valid for a Long Rest';
      end if;
      v_new_body := public._rhc_apply_rest_benefits(
        v_mech_body, 'long', null, null);
    end if;

  -- --- Long Rest interruption (resumes, +1 required hour) -------------------
  elsif v_t_status = 'active' and v_c_status = 'active'
        and v_c_kind = 'long' and v_t_kind = 'long' then
    if v_t_start <> v_c_start then
      raise exception 'a resumed Long Rest must preserve its original start anchor';
    end if;
    if v_t_last is distinct from v_c_last then
      raise exception
        'a resumed Long Rest must preserve the personal last-successful-Long-Rest anchor';
    end if;
    if jsonb_array_length(v_t_ints) <> jsonb_array_length(v_c_ints) + 1 then
      raise exception 'a Long Rest interruption must add exactly one interruption';
    end if;
    v_append := v_t_ints -> (jsonb_array_length(v_t_ints) - 1);
    v_expected_ints := v_c_ints || jsonb_build_array(v_append);
    if v_t_ints <> v_expected_ints then
      raise exception
        'a Long Rest interruption must only append to the existing interruption list';
    end if;
    v_append_at := (v_append ->> 'at_elapsed_minutes')::numeric;
    if v_append_at <> v_now then
      raise exception
        'a Long Rest interruption must anchor to the authoritative published elapsed time';
    end if;

    if v_now - v_c_start >= 60 and not v_c_granted then
      if not v_t_granted then
        raise exception
          'a Long Rest interrupted after at least 1 elapsed hour must grant Short Rest benefits';
      end if;
      select csg.value into v_mech_collection
        from public.campaign_state_generations csg
       where csg.generation = r.staging_generation
         and csg.key = 'character_mechanics';
      if v_mech_collection is null then
        select csg.value into v_mech_collection
          from public.campaign_state_generations csg
         where csg.generation = r.published_generation
           and csg.key = 'character_mechanics';
      end if;
      if v_mech_collection is null or jsonb_typeof(v_mech_collection) is distinct from 'array' then
        raise exception
          'character % has no readable character_mechanics record; Rest consequences cannot be applied',
          v_character;
      end if;
      perform public._rhc_validate_character_mechanics_collection(v_mech_collection);
      select e into v_mech_record
        from jsonb_array_elements(v_mech_collection) e
       where jsonb_typeof(e) = 'object'
         and (e ->> 'character_id') = v_character
       limit 1;
      if v_mech_record is null then
        raise exception
          'character % has no character_mechanics record; Rest consequences cannot be applied',
          v_character;
      end if;
      v_new_body := public._rhc_apply_rest_benefits(
        v_mech_record - 'character_id', 'short',
        p_request -> 'hit_die_spending', p_request -> 'con_modifier');
    else
      if v_t_granted <> v_c_granted then
        raise exception
          'Short Rest benefits are not yet due for this Long Rest interruption';
      end if;
    end if;

  -- --- Short Rest interruption (ends, no benefit) ---------------------------
  elsif v_t_status = 'interrupted' and v_c_status = 'active' and v_c_kind = 'short' then
    if v_t_start <> v_c_start or v_t_req <> v_c_req then
      raise exception
        'an interrupted Short Rest must preserve its start anchor and required duration';
    end if;
    if v_t_last is distinct from v_c_last then
      raise exception
        'an interrupted Short Rest must preserve the personal last-successful-Long-Rest anchor';
    end if;
    if jsonb_array_length(v_t_ints) <> jsonb_array_length(v_c_ints) + 1 then
      raise exception 'a Short Rest interruption must add exactly one interruption';
    end if;
    v_append := v_t_ints -> (jsonb_array_length(v_t_ints) - 1);
    v_expected_ints := v_c_ints || jsonb_build_array(v_append);
    if v_t_ints <> v_expected_ints then
      raise exception
        'a Short Rest interruption must only append to the existing interruption list';
    end if;
    v_append_at := (v_append ->> 'at_elapsed_minutes')::numeric;
    if v_append_at <> v_now then
      raise exception
        'a Short Rest interruption must anchor to the authoritative published elapsed time';
    end if;
    if v_t_granted then
      raise exception 'an interrupted Short Rest grants no benefit';
    end if;

  -- --- abort ---------------------------------------------------------------
  elsif v_t_status = 'idle' and v_c_status = 'active' then
    if v_t_last is distinct from v_c_last then
      raise exception
        'aborting a character rest must preserve the personal last-successful-Long-Rest anchor';
    end if;

  else
    raise exception
      'illegal character rest transition from % to %', v_c_status, v_t_status;
  end if;

  -- Replace the character's single record, or append it when the character is new.
  select
    coalesce(jsonb_agg(
      case when jsonb_typeof(e) = 'object' and (e ->> 'character_id') = v_character
           then v_target else e end
    ), '[]'::jsonb),
    count(*) filter (
      where jsonb_typeof(e) = 'object' and (e ->> 'character_id') = v_character
    )
    into v_new_rest_collection, v_matches
    from jsonb_array_elements(v_rest_collection) e;
  if v_matches = 0 then
    v_new_rest_collection := v_new_rest_collection || jsonb_build_array(v_target);
  elsif v_matches > 1 then
    raise exception
      'character_rests namespace already holds duplicate records for %; failing closed',
      v_character;
  end if;
  perform public._rhc_validate_character_rests_collection(v_new_rest_collection);

  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (r.staging_generation, 'character_rests', v_new_rest_collection, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Apply supported official consequences to POST-EV2-9 when this transition
  -- grants them. Every durable `character_mechanics` change flows through
  -- POST-EV2-9's dedicated owner (`mutate_character_mechanics`), so its operation
  -- marker and exhaustive-writer contract remain the only way character_mechanics
  -- is staged; this route never writes the collection directly.
  if v_new_body is not null then
    v_new_body := public._rhc_normalize_character_mechanics_body(v_new_body);
    perform public.mutate_character_mechanics(
      r.lock_token,
      jsonb_build_object(
        'character_id', v_character,
        'controller', v_controller,
        'mechanics', v_new_body
      )
    );
  end if;

  -- Record the operation fact: a successful Rest staging happened in this save,
  -- independent of whether the staged value differs from published reality. This
  -- closes every Run-ownership-writing doorway for the rest of the save.
  update public.campaign_runtime
     set character_rests_staged_lock_token = r.lock_token
   where id = 1;

  return jsonb_build_object(
    'character_rest_mutation_version', 1,
    'character_id', v_character,
    'controller', v_controller,
    'runtime', public._rhc_dm_runtime_metadata(),
    'replay', false,
    'record', v_target,
    'mechanics_applied', (v_new_body is not null)
  );
end;
$$;

revoke all on function public.mutate_character_rest(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.mutate_character_rest(text, jsonb) to service_role;

comment on function public.mutate_character_rest(text, jsonb) is
  'POST-EV2-10: the ONLY way to stage the engine-owned character_rests runtime namespace. Runs inside the normal RT01 save lifecycle, proves the asserted controller (MAINRUN or exactly one RUN #) against authoritative published Run truth for the target character via the shared EV2-10 resolver, validates the absolute Rest lifecycle transition against authoritative published RT02 elapsed time, routes every supported official Short/Long Rest consequence to POST-EV2-9 through its dedicated mutate_character_mechanics owner (never writing character_mechanics directly), and stages exactly one Rest record per character. Absolute and replay-safe; service_role only.';

-- ---------------------------------------------------------------------------
-- 9. The supported service-only published read by exact character identity.
-- ---------------------------------------------------------------------------
create or replace function public.dm_runtime_read_character_rest(
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
      'character-rest read requires one exact character:<slug> identity';
  end if;

  select csg.value into v_collection
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'character_rests'
   where cr.id = 1;
  v_collection := coalesce(v_collection, '[]'::jsonb);

  perform public._rhc_validate_character_rests_collection(v_collection);

  select e into v_record
    from jsonb_array_elements(v_collection) e
   where jsonb_typeof(e) = 'object'
     and (e ->> 'character_id') = v_character
   limit 1;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'character_rest',
    'character_id', v_character,
    'runtime', public._rhc_dm_runtime_metadata(),
    'record', v_record
  );
end;
$$;

revoke all on function public.dm_runtime_read_character_rest(text)
  from public, anon, authenticated;
grant execute on function public.dm_runtime_read_character_rest(text) to service_role;

comment on function public.dm_runtime_read_character_rest(text) is
  'POST-EV2-10: service-only published read of one character Rest record by exact character:<slug> identity. Reads only the current published generation, validates the whole published namespace through the existing owner contract, and returns the RT01-D runtime metadata envelope plus the single record, or record=null as truthful absence for an untracked character. Stable, read-only, non-mutating; staged/future state is never read as authority.';
