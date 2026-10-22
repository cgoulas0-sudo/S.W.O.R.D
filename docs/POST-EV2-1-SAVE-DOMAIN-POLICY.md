# POST-EV2-1 — Save Gateway basement, Patch 1A: Save domain policy registry

POST-EV2-1 owns the **modular inside of the single Save Gateway**. The RT01
persistence spine stays singular and authoritative; this patch changes only where
the generic route gets its *admission decision* from. It adds **one server-owned,
machine-readable policy registry** and routes the generic
`stage_campaign_state` / `delete_staged_campaign_state` generic-vs-dedicated
admission and the HWB-02 ordinary-save allowlist through it, with **no semantic
behavior change**.

> Architecture sentence: **POST-EV2-1 owns the modular INSIDE of the single Save
> Gateway. RT01 begin/publish/abort, generation, lease/lock, mirror and
> confirmation remain central and unchanged; dedicated semantic routes keep their
> domain behavior; and the generic route's admission policy stops being a growing
> set of hard-coded branches.**

## Why this exists

The audit (JOHNNY #124) confirmed a real coupling risk, not a hypothetical one:
the two generic entry points had been rewritten in ten migrations each, and each
new runtime domain added another hard-coded protected-key branch and, for some
domains, same-save coupling. The singular gateway was healthy, but domain growth
propagated by editing the central gateway. Patch 1A arrests that accretion at the
smallest seam: the admission decision.

## The registry

`public._rhc_save_domain_policy(p_key text) returns jsonb` is the single
server-owned registry. It consumes **only the key** and returns:

```json
{
  "key": "item_custody",
  "admission": "dedicated",
  "dedicated_routes": ["mutate_item_custody", "admit_item_identity"],
  "stage_error": "item_custody is engine-owned and can only be staged through mutate_item_custody or admit_item_identity",
  "delete_error": "item_custody is engine-owned and cannot be deleted through the generic route"
}
```

- `generic` — admitted by the generic route and on the ordinary-save allowlist:
  `daily_recap`, `day_resolution`, `live_status`, `dm_meta`, `narrative_hooks`,
  `runs`. Exposes `dedicated_routes: []`.
- `dedicated` — engine-owned; the generic route must refuse it and the registry
  must name **every** legal writer exhaustively (an array, never a single
  misleading route): `campaign_clock` → `[stage_campaign_clock]`;
  `run_reconciliations` → `[reconcile_run_resolution]`; `inventory` →
  `[mutate_owner_inventory]`; `item_custody` →
  `[mutate_item_custody, admit_item_identity]`; `item_admissions` →
  `[admit_item_identity]`; `entity_state` → `[mutate_entity_state]`;
  `applied_statuses` → `[mutate_applied_status]`.
- `forbidden` — unknown/undeclared; the generic route fails closed with the exact
  HWB-02 allowlist message. Exposes `dedicated_routes: []`.

`dedicated_routes` is deliberately plural and explicit. A singular writer field
would falsely imply a complete writer set for a domain with more than one legal
writer (`item_custody`), so no singular `dedicated_route` field is exposed. The
audit of all seven current dedicated domains found `item_custody` to be the only
multi-writer domain; every other dedicated domain has exactly one legal writer.

The function takes no caller-supplied policy, reads no table, and selects no
mutable store, so the decision can never become caller-controlled authority. It
is internal-only: execute is revoked from `public`, `anon`, `authenticated` and
`service_role`.

## Authority and boundary

- **Registry/compatibility policy is deterministic infrastructure**, never
  caller-selectable authority. Unknown/unregistered domains fail closed.
- **No second publication authority.** `begin_campaign_save`,
  `publish_campaign_save`, `abort_campaign_save`, generation, lease/lock, mirror
  and confirmation are untouched.
- **Dedicated domain semantics move nowhere.** Clock, RT04 reconciliation,
  Inventory, Custody/Admission, Entity State and Applied Status validation remain
  in their existing routes. The registry classifies admission only.
- **The `runs` same-save compatibility guards remain inline in this patch.**
  Centralizing the cross-domain compatibility edges is Patch 1B and is
  deliberately not done here.

## What this patch changes

| Surface | Change |
| --- | --- |
| `public._rhc_save_domain_policy(text)` | created (registry) |
| `public.stage_campaign_state(text, text, jsonb)` | re-declared to consult the registry |
| `public.delete_staged_campaign_state(text, text)` | re-declared to consult the registry |

Every existing dedicated-key closure message, the `runs` same-save coupling
guards, the `engineering_release` refusal and the server-owned ordinary-save
allowlist are preserved byte-for-byte in effect.

## Deferred ownership (must not be absorbed here)

- same-save compatibility dispatcher and cross-domain edge centralization → Patch 1B;
- durable `ORCHESTRATOR.md` / JOHNNY mutation-domain memory + workflow proof → Patch 1C;
- clean bootstrap/baseline equivalence and any later baseline/squash mechanism → Patch 1D;
- dedicated domain semantics/validation and new runtime mutation domains → their existing routes or a later bounded Mission;
- real campaign data import, BTH, Story/RAG, frontend/UI and production Supabase activation/migration → their later gates.

## Proof

`tests/post_ev2_1/` proves, on real PostgreSQL 15 and 17:

1. all six generic keys are classified `generic` and stage/delete symmetrically;
2. all seven dedicated keys are classified `dedicated` and are rejected by the
   generic routes with the exact historical messages;
3. the machine-readable dedicated-writer metadata is exhaustive for every current
   dedicated domain (`item_custody` lists both `mutate_item_custody` and
   `admit_item_identity`), is always an explicit array, and exposes no misleading
   singular `dedicated_route`; every advertised writer is a real public function;
4. unknown/near-miss keys are `forbidden` and fail closed;
5. the registry has exactly one key-only signature and is not executable by
   caller roles, so policy cannot be supplied or overridden by the caller;
6. the `runs` same-save reconciliation coupling guard remains behaviorally
   identical;
7. the dedicated Clock route still works;
8. begin/abort/publish lifecycle, raw-DML guards and role privileges are unchanged;
9. a fresh full replay (repository `main` + Patch 1A) reaches the **same exact
   stage/delete outcome for a key matrix** as the pre-Patch-1A chain.
