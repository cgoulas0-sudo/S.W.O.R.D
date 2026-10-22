-- EV2-12 — First real RHC item admission canary (DM/SAVE only, exactly one item)
-- Rolling High Club one-time human-approved admission of `item:vampire` custody.
--
-- INERT REPOSITORY CONTENT. This file is NOT a migration, is NOT executed by any
-- runner, and is NOT referenced by any migration or workflow. It must only be
-- executed explicitly by a human DM/SAVE operator, in a deliberate session,
-- after EV2-12 is merged and post-merge proof is complete.
--
-- WHAT this script does:
--   * admits EXACTLY ONE persistent item identity, `item:vampire`, into the
--     `item_custody` runtime namespace by running the EXISTING RT01
--     candidate-generation lifecycle: `begin_campaign_save(...)` derives a fresh
--     candidate generation from current published reality, the candidate
--     `item_custody` collection is validated and extended, and
--     `publish_campaign_save(...)` advances the published pointer exactly one
--     generation. The current published generation is NEVER rewritten in place.
--   * seeds the record with `owner_entity_id` null, preserving the established
--     truth that ownership is unknown;
--   * seeds the record with `holder_entity_id` = `character:gork`, because Gork
--     is already established as equipped with and attuned to Vampire and is
--     therefore the known current holder. `character:gork` is only a stable
--     reference to the already-established campaign character; this script does
--     NOT create or admit a `character:gork` Entity V2 record.
--   * validates the COMPLETE existing candidate `item_custody` collection, then
--     builds the resulting collection, then validates the COMPLETE resulting
--     collection, all through the existing EV2-11 `_rhc_validate_item_custody_collection`
--     machinery before anything is staged. Malformed or duplicate unrelated
--     custody truth fails closed.
--
-- WHAT this script does NOT do:
--   * it does not invent a new persistence path, a second save engine, or a
--     second mirror path; it uses the existing RT01 gateway and publication law;
--   * it does not invent an owner (ownership stays unknown);
--   * it does not mint through the gameplay SAVE route (EV2-11's non-minting law
--     is untouched); it is the one authorized out-of-band admission;
--   * it does not admit any second item, any other identity, or bulk data;
--   * it does not create or alter Run ownership, campaign clock, or any other
--     runtime namespace;
--   * it does not rewrite the current published generation in place.
--
-- HOW to execute (later, deliberately, under DM/SAVE authority):
--   1. connect to the published runtime database with an operator role that can
--      execute the RT01 gateway and write the candidate generation (the same
--      break-glass authority the existing save/mirror administration uses);
--   2. set the explicit approval flag for that session:
--        select set_config('rhc.ev212_vampire_admission_approved', 'on', false);
--   3. run this file (for example: psql -f supabase/canaries/ev212_vampire_admission.sql);
--      it publishes exactly one new generation through the existing gateway;
--   4. run the existing external `runtime-published` mirror worker so the new
--      generation receives its Git checkpoint and verifier confirmation, exactly
--      as for any other published save;
--   5. confirm the published `item_custody` namespace then holds exactly one
--      record for `item:vampire` with null owner and holder `character:gork`.
--
-- This script is one-item-only by construction: `item:vampire` is hard-coded and
-- a second execution fails closed.

begin;

do $$
declare
  v_published bigint;
  v_staging bigint;
  v_lock_token text;
  v_lock_expires timestamptz;
  v_existing jsonb;
  v_resulting jsonb;
  v_record jsonb := jsonb_build_object(
    'item_id', 'item:vampire',
    'owner_entity_id', null,
    'holder_entity_id', 'character:gork'
  );
begin
  if current_setting('rhc.ev212_vampire_admission_approved', true) is distinct from 'on' then
    raise exception
      'EV2-12 admission refused: this script is inert until a human DM/SAVE operator explicitly approves it by setting rhc.ev212_vampire_admission_approved = on for this session';
  end if;

  -- Enter the EXISTING RT01 candidate-generation lifecycle. The database mints
  -- the lock_token, derives staging_generation = published_generation + 1, copies
  -- published reality forward into the candidate, and asserts the
  -- transaction-local gated-write guard. The published generation is untouched.
  select published_generation, staging_generation, lock_token, lock_expires_at
    into v_published, v_staging, v_lock_token, v_lock_expires
    from public.begin_campaign_save(30);

  -- Candidate `item_custody` (a BEGIN-time copy of published reality).
  select csg.value into v_existing
    from public.campaign_state_generations csg
   where csg.generation = v_staging
     and csg.key = 'item_custody';
  if v_existing is null then
    v_existing := '[]'::jsonb;
  end if;
  if jsonb_typeof(v_existing) is distinct from 'array' then
    raise exception 'EV2-12 admission refused: item_custody namespace is not a JSON array';
  end if;

  -- Validate the COMPLETE existing collection with the existing EV2-11 validator
  -- before `item:vampire` presence can mean anything. Malformed or duplicate
  -- unrelated custody truth fails closed and is never canonicalized by append.
  perform public._rhc_validate_item_custody_collection(v_existing);

  if exists (
    select 1
      from jsonb_array_elements(v_existing) e
     where jsonb_typeof(e) = 'object'
       and (e ->> 'item_id') = 'item:vampire'
  ) then
    raise exception 'EV2-12 admission refused: item:vampire already has an admitted custody record';
  end if;

  -- Build the resulting collection and validate the COMPLETE resulting
  -- collection before staging anything.
  v_resulting := v_existing || jsonb_build_array(v_record);
  perform public._rhc_validate_item_custody_collection(v_resulting);

  -- Stage the candidate generation directly. The RT01 gateway has asserted the
  -- transaction-local gated-write guard; this is the candidate, not published
  -- reality.
  insert into public.campaign_state_generations (generation, key, value, created_at, updated_at)
  values (v_staging, 'item_custody', v_resulting, now(), now())
  on conflict (generation, key) do update
     set value = excluded.value,
         updated_at = now();

  -- Publish through the existing gateway. This advances the published pointer
  -- exactly one generation and marks the runtime-published mirror pending; the
  -- existing external mirror worker then commits the Git checkpoint and the
  -- verifier confirms it, preserving the ordinary publish/mirror/confirmation
  -- semantics.
  perform public.publish_campaign_save(v_lock_token);

  raise notice 'EV2-12: admitted item:vampire into published generation % with owner unestablished (null) and holder character:gork.', v_staging;
end;
$$;

commit;