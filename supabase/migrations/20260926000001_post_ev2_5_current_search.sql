-- POST-EV2-5 -- Current published-world exact-focus search
--
-- WHAT this migration changes:
--   1. `public.dm_current_search(<focus>, <limit>)` -- one service-only, stable,
--      read-only search over the CURRENT published runtime generation for one
--      exact entity-like focus.
--
-- CORE RULE:
--   Search decides relevance. Existing engine owners decide validity.
--   For one exact focus this read:
--     1. fetches ONLY the published namespace(s) that can contribute to that
--        focus kind, each fetched individually by its exact runtime key --
--        the whole published generation is never aggregated and filtered
--        later;
--     2. validates each namespace through its EXISTING owning whole-collection
--        validator (or, for Runs, the existing canonical published Run-truth
--        reader that already applies the RT03/EV2-08 validation path),
--        including the owner's declared cross-collection law: the
--        `item_admissions` owner contract is complete only with the existing
--        EV2-12.1 `_rhc_validate_item_admission_custody_linkage` invariant
--        proven against the validated published `item_custody` collection;
--     3. only after validation, filters by the owner's exact stable
--        identity/relation fields;
--     4. returns bounded matching hits grouped by owning domain.
--
--   A malformed authoritative namespace fails closed through its owner contract.
--   POST-EV2-5 invents no weaker per-record validation, no second state reader,
--   no fuzzy/semantic matching, and no recursive hydration. Published-runtime
--   first: only `campaign_runtime.published_generation` is read; staged/future
--   rows never participate.
--
-- This migration adds no table, runtime key, mutation route, validator
-- framework, cache, index, graph/vector store or other persistence. It creates
-- exactly one function and grants it to `service_role` only.
--
-- Bounds: one focus per call; `p_limit` defaults to 20 and is clamped to
-- [1, 50]; output is deterministic; a multi-hit domain that exceeds the limit
-- returns its bounded hits plus `truncated: true`; IDs inside a hit are never
-- recursively hydrated.

-- ---------------------------------------------------------------------------
-- 0. Migration boundary guard: refuse the upgrade while a save is in flight,
--    consistent with the RT01-D/RT02/RT03/RT04/EV2 forward-only install pattern.
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
      'POST-EV2-5 migration refused: resolve the active campaign save before installing current search';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. The supported service-facing current-world exact-focus search.
--
--    Focus identity space (exactly one):
--      character: | creature: | location: | faction: | party: | item:
--
--    Routed namespaces by focus kind (only namespaces that can contribute are
--    ever read; each is validated by its EXISTING owner contract before any
--    filtering):
--      entity_state     -> character, creature          (exact entity_id)
--      inventory        -> any owner identity           (exact entity_id)
--      item_custody     -> character, party, item       (exact owner/holder, or item_id)
--      item_admissions  -> item                         (exact item_id)
--      applied_statuses -> all kinds                    (exact target/source)
--      entity_knowledge -> all kinds                    (exact knower entity_id)
--      runs             -> character, creature, location, party
--
--    Output:
--      {
--        "read_version": 1,
--        "mode": "current_search",
--        "focus": "<focus>",
--        "runtime": <RT01-D runtime metadata envelope>,
--        "results": {
--          "<domain>": { "hits": [ <validated current records> ],
--                        "truncated": <bool> }, ...
--        }
--      }
--    Only domains with at least one hit appear (sparse output).
-- ---------------------------------------------------------------------------
create or replace function public.dm_current_search(
  p_focus text,
  p_limit integer default 20
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_focus text;
  v_kind text;
  v_limit integer;
  v_results jsonb := '{}'::jsonb;
  v_ns jsonb;
  v_custody_ns jsonb;
  v_hits jsonb;
  v_total integer;
begin
  v_focus := coalesce(p_focus, '');
  if not public._rhc_full_id_match(
       v_focus,
       '^(character|creature|location|faction|party|item):[a-z0-9]+(-[a-z0-9]+)*$') then
    raise exception
      'current search focus must be one stable character:/creature:/location:/faction:/party:/item: identity';
  end if;
  v_kind := split_part(v_focus, ':', 1);
  v_limit := greatest(1, least(coalesce(p_limit, 20), 50));

  -- Selective read path: every routed namespace is fetched individually by its
  -- exact runtime key at the current published generation, and only when it
  -- can contribute to this focus kind. The whole published generation is never
  -- aggregated and filtered later; a namespace that cannot contribute is never
  -- read at all. (Runs stay inside the existing canonical published Run-truth
  -- reader, which is itself key-selective.)

  -- entity_state: mutable actors only. Exact entity_id. Owner contract:
  -- _rhc_validate_entity_state_collection. Routed only for character/creature.
  if v_kind in ('character', 'creature') then
    select csg.value into v_ns
      from public.campaign_runtime cr
      left join public.campaign_state_generations csg
        on csg.generation = cr.published_generation
       and csg.key = 'entity_state'
     where cr.id = 1;
    v_ns := coalesce(v_ns, '[]'::jsonb);
    perform public._rhc_validate_entity_state_collection(v_ns);
    select count(*) into v_total
      from jsonb_array_elements(v_ns) e
     where e ->> 'entity_id' = v_focus;
    if v_total > 0 then
      select coalesce(jsonb_agg(h order by h ->> 'entity_id'), '[]'::jsonb)
        into v_hits
        from (
          select e as h
            from jsonb_array_elements(v_ns) e
           where e ->> 'entity_id' = v_focus
           order by e ->> 'entity_id'
           limit v_limit
        ) q;
      v_results := v_results || jsonb_build_object(
        'entity_state',
        jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
    end if;
  end if;

  -- inventory: exact owner entity_id. Owner contract:
  -- _rhc_validate_inventory_collection. Routed for every focus kind: an
  -- inventory owner may be any of the schema's allowed owner identities.
  select csg.value into v_ns
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'inventory'
   where cr.id = 1;
  v_ns := coalesce(v_ns, '[]'::jsonb);
  perform public._rhc_validate_inventory_collection(v_ns);
  select count(*) into v_total
    from jsonb_array_elements(v_ns) e
   where e ->> 'entity_id' = v_focus;
  if v_total > 0 then
    select coalesce(jsonb_agg(h order by h ->> 'entity_id'), '[]'::jsonb)
      into v_hits
      from (
        select e as h
          from jsonb_array_elements(v_ns) e
         where e ->> 'entity_id' = v_focus
         order by e ->> 'entity_id'
         limit v_limit
      ) q;
    v_results := v_results || jsonb_build_object(
      'inventory',
      jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
  end if;

  -- item_custody: exact item_id (item focus) or exact owner/holder
  -- (character/party focus). Owner contract:
  -- _rhc_validate_item_custody_collection. Routed only for character/party/item.
  if v_kind in ('character', 'party', 'item') then
    select csg.value into v_custody_ns
      from public.campaign_runtime cr
      left join public.campaign_state_generations csg
        on csg.generation = cr.published_generation
       and csg.key = 'item_custody'
     where cr.id = 1;
    v_custody_ns := coalesce(v_custody_ns, '[]'::jsonb);
    perform public._rhc_validate_item_custody_collection(v_custody_ns);
    if v_kind = 'item' then
      select count(*) into v_total
        from jsonb_array_elements(v_custody_ns) e
       where e ->> 'item_id' = v_focus;
      if v_total > 0 then
        select coalesce(jsonb_agg(h order by h ->> 'item_id'), '[]'::jsonb)
          into v_hits
          from (
            select e as h
              from jsonb_array_elements(v_custody_ns) e
             where e ->> 'item_id' = v_focus
             order by e ->> 'item_id'
             limit v_limit
          ) q;
        v_results := v_results || jsonb_build_object(
          'item_custody',
          jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
      end if;
    else
      select count(*) into v_total
        from jsonb_array_elements(v_custody_ns) e
       where e ->> 'owner_entity_id' = v_focus
          or e ->> 'holder_entity_id' = v_focus;
      if v_total > 0 then
        select coalesce(jsonb_agg(h order by h ->> 'item_id'), '[]'::jsonb)
          into v_hits
          from (
            select e as h
              from jsonb_array_elements(v_custody_ns) e
             where e ->> 'owner_entity_id' = v_focus
                or e ->> 'holder_entity_id' = v_focus
             order by e ->> 'item_id'
             limit v_limit
          ) q;
        v_results := v_results || jsonb_build_object(
          'item_custody',
          jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
      end if;
    end if;
  end if;

  -- item_admissions: exact item_id. Owner contract is the COMPLETE existing
  -- EV2-12.1 contract, not only structural collection validation: after the
  -- whole-collection validator, the existing
  -- _rhc_validate_item_admission_custody_linkage cross-collection invariant
  -- must also hold against the validated published `item_custody` collection
  -- before any admission receipt can be returned as authoritative. The owner
  -- contract is reused whole; POST-EV2-5 invents no weaker partial validation.
  if v_kind = 'item' then
    select csg.value into v_ns
      from public.campaign_runtime cr
      left join public.campaign_state_generations csg
        on csg.generation = cr.published_generation
       and csg.key = 'item_admissions'
     where cr.id = 1;
    v_ns := coalesce(v_ns, '[]'::jsonb);
    perform public._rhc_validate_item_admissions_collection(v_ns);
    perform public._rhc_validate_item_admission_custody_linkage(v_custody_ns, v_ns);
    select count(*) into v_total
      from jsonb_array_elements(v_ns) e
     where e ->> 'item_id' = v_focus;
    if v_total > 0 then
      select coalesce(jsonb_agg(h order by h ->> 'item_id'), '[]'::jsonb)
        into v_hits
        from (
          select e as h
            from jsonb_array_elements(v_ns) e
           where e ->> 'item_id' = v_focus
           order by e ->> 'item_id'
           limit v_limit
        ) q;
      v_results := v_results || jsonb_build_object(
        'item_admissions',
        jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
    end if;
  end if;

  -- applied_statuses: exact target (character/creature only, per the schema's
  -- typed target) or exact source (any permitted source identity). Owner
  -- contract: _rhc_validate_applied_statuses_collection. Routed for every
  -- focus kind: a status source may be any permitted source identity.
  select csg.value into v_ns
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'applied_statuses'
   where cr.id = 1;
  v_ns := coalesce(v_ns, '[]'::jsonb);
  perform public._rhc_validate_applied_statuses_collection(v_ns);
  if v_kind in ('character', 'creature') then
    select count(*) into v_total
      from jsonb_array_elements(v_ns) e
     where e ->> 'target_entity_id' = v_focus
        or e ->> 'source_entity_id' = v_focus;
    if v_total > 0 then
      select coalesce(jsonb_agg(h order by h ->> 'application_id'), '[]'::jsonb)
        into v_hits
        from (
          select e as h
            from jsonb_array_elements(v_ns) e
           where e ->> 'target_entity_id' = v_focus
              or e ->> 'source_entity_id' = v_focus
           order by e ->> 'application_id'
           limit v_limit
        ) q;
      v_results := v_results || jsonb_build_object(
        'applied_statuses',
        jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
    end if;
  else
    select count(*) into v_total
      from jsonb_array_elements(v_ns) e
     where e ->> 'source_entity_id' = v_focus;
    if v_total > 0 then
      select coalesce(jsonb_agg(h order by h ->> 'application_id'), '[]'::jsonb)
        into v_hits
        from (
          select e as h
            from jsonb_array_elements(v_ns) e
           where e ->> 'source_entity_id' = v_focus
           order by e ->> 'application_id'
           limit v_limit
        ) q;
      v_results := v_results || jsonb_build_object(
        'applied_statuses',
        jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
    end if;
  end if;

  -- entity_knowledge: exact knower entity_id. Owner contract:
  -- _rhc_validate_knowledge_collection. Knowledge stays with the knower; no
  -- propagation to any other entity. Routed for every focus kind: a knower may
  -- be any of the schema's allowed knower identities.
  select csg.value into v_ns
    from public.campaign_runtime cr
    left join public.campaign_state_generations csg
      on csg.generation = cr.published_generation
     and csg.key = 'entity_knowledge'
   where cr.id = 1;
  v_ns := coalesce(v_ns, '[]'::jsonb);
  perform public._rhc_validate_knowledge_collection(v_ns);
  select count(*) into v_total
    from jsonb_array_elements(v_ns) e
   where e ->> 'entity_id' = v_focus;
  if v_total > 0 then
    select coalesce(jsonb_agg(h order by h ->> 'entity_id'), '[]'::jsonb)
      into v_hits
      from (
        select e as h
          from jsonb_array_elements(v_ns) e
         where e ->> 'entity_id' = v_focus
         order by e ->> 'entity_id'
         limit v_limit
      ) q;
    v_results := v_results || jsonb_build_object(
      'entity_knowledge',
      jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
  end if;

  -- runs: existing canonical published Run truth / RT03 validation path.
  -- Reuses `_rhc_published_runs_truth()`, which is itself key-selective (it
  -- fetches only the published `runs` key) and proves every entry is an
  -- EV2-08-valid Run with a unique string run_id and the cross-Run
  -- mutable-owner uniqueness invariant; no Run validation or uniqueness rule is
  -- duplicated here. Exact relations only: participant/mutable-owner
  -- (character/creature), location_ids (location), party_id (party).
  if v_kind in ('character', 'creature', 'location', 'party') then
    v_ns := public._rhc_published_runs_truth();
    if v_kind = 'location' then
      select count(*) into v_total
        from jsonb_array_elements(v_ns) e
       where (e -> 'location_ids') ? v_focus;
      if v_total > 0 then
        select coalesce(jsonb_agg(h order by h ->> 'run_id'), '[]'::jsonb)
          into v_hits
          from (
            select e as h
              from jsonb_array_elements(v_ns) e
             where (e -> 'location_ids') ? v_focus
             order by e ->> 'run_id'
             limit v_limit
          ) q;
        v_results := v_results || jsonb_build_object(
          'runs',
          jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
      end if;
    elsif v_kind = 'party' then
      select count(*) into v_total
        from jsonb_array_elements(v_ns) e
       where e ->> 'party_id' = v_focus;
      if v_total > 0 then
        select coalesce(jsonb_agg(h order by h ->> 'run_id'), '[]'::jsonb)
          into v_hits
          from (
            select e as h
              from jsonb_array_elements(v_ns) e
             where e ->> 'party_id' = v_focus
             order by e ->> 'run_id'
             limit v_limit
          ) q;
        v_results := v_results || jsonb_build_object(
          'runs',
          jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
      end if;
    else
      select count(*) into v_total
        from jsonb_array_elements(v_ns) e
       where (e -> 'participant_entity_ids') ? v_focus
          or (e -> 'mutable_owner_entity_ids') ? v_focus;
      if v_total > 0 then
        select coalesce(jsonb_agg(h order by h ->> 'run_id'), '[]'::jsonb)
          into v_hits
          from (
            select e as h
              from jsonb_array_elements(v_ns) e
             where (e -> 'participant_entity_ids') ? v_focus
                or (e -> 'mutable_owner_entity_ids') ? v_focus
             order by e ->> 'run_id'
             limit v_limit
          ) q;
        v_results := v_results || jsonb_build_object(
          'runs',
          jsonb_build_object('hits', v_hits, 'truncated', v_total > v_limit));
      end if;
    end if;
  end if;

  return jsonb_build_object(
    'read_version', 1,
    'mode', 'current_search',
    'focus', v_focus,
    'runtime', public._rhc_dm_runtime_metadata(),
    'results', v_results
  );
end;
$$;

revoke all on function public.dm_current_search(text, integer)
  from public, anon, authenticated;
grant execute on function public.dm_current_search(text, integer) to service_role;

comment on function public.dm_current_search(text, integer) is
  'POST-EV2-5: service-only exact-focus search over the current published runtime generation. Fetches only the published namespaces that can contribute to the focus kind, each individually by its exact runtime key (the whole generation is never aggregated and filtered later), validates each through its EXISTING owner whole-collection validator including the declared cross-collection law for item_admissions (_rhc_validate_item_admission_custody_linkage) and the existing canonical published Run-truth reader for runs, then returns bounded deterministic hits grouped by owning domain with per-domain truncation metadata. Unsupported/malformed focus, an unreadable routed namespace, a namespace that fails its owner contract, or an admission receipt whose custody linkage is missing fail closed. Read-only, stable, non-mutating; the RT01-D metadata envelope is returned in every mode.';