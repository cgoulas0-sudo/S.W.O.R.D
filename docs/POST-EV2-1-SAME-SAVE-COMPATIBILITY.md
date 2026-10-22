# POST-EV2-1 — Save Gateway basement, Patch 1B: Same-save compatibility dispatcher

POST-EV2-1 owns the **modular inside of the single Save Gateway**. Patch 1A
centralized *domain admission* — which runtime state keys the generic route may
write and which are engine-owned. Patch 1B centralizes the other distributed
decision: **may two already-legal mutation domains coexist in the same active
save?** It adds one server-owned, machine-readable compatibility contract and
routes every existing cross-domain exclusion through it, with **no semantic
behavior change**.

> Architecture sentence: **POST-EV2-1 owns the modular INSIDE of the single Save
> Gateway. RT01 begin/publish/abort, generation, lease/lock, mirror and
> confirmation remain central and unchanged; dedicated semantic routes keep their
> domain behavior; Patch 1A's admission registry remains intact and is not
> duplicated; and the "same-save compatibility" decision stops being a growing
> set of hand-coded cross-domain branches in each doorway and becomes the output
> of one deterministic server-owned contract.**

## Why this exists

Patch 1A (JOHNNY #124, PR #125) removed the growing hard-coded *admission* branch
per new runtime domain. The same accretion risk remained for **compatibility**:
the same-save exclusions were correct but repeated as inline guards in the generic
`runs` stage/delete routes, the dedicated RT04 reconciliation route, and each
dedicated domain route. Every new mutation domain added another pair of
hand-coded cross-domain guards and another chance for an asymmetric ordering hole
(one ordering blocked, the reverse left open).

Patch 1B arrests that accretion at the compatibility seam. It changes only *where
the decision comes from*; every rule, ordering and exact fail-closed message is
preserved.

## The contract

Three internal functions under `public.`:

### `_rhc_same_save_compatibility_policy(p_operation text) returns jsonb`

The single machine-readable declaration of every audited cross-domain
incompatibility. For one operation it returns:

```json
{
  "operation": "stage_runs",
  "domain": "runs",
  "known": true,
  "edges": [
    {"blocked_by": "run_reconciliations", "detector": "reconciliation_new_in_save", "error": "the runs batch is engine-owned ..."},
    {"blocked_by": "inventory", "detector": "inventory_staged_in_save", "error": "the runs batch cannot be changed ..."},
    {"blocked_by": "item_custody", "detector": "custody_staged_in_save", "error": "..."},
    {"blocked_by": "entity_state", "detector": "entity_state_staged_in_save", "error": "..."},
    {"blocked_by": "applied_statuses", "detector": "applied_status_staged_in_save", "error": "..."}
  ]
}
```

It consumes **only the operation name**, reads no table and selects no mutable
store, so the policy can never be caller-supplied or caller-controlled. Unknown
operations report `known: false`. The `error` field is the *exact* message the
operation must raise, so the metadata is truthful and exhaustive rather than
merely suggestive (the standard Patch 1A's review set).

### `_rhc_same_save_compatibility(p_operation, p_staging_generation, p_published_generation) returns jsonb`

Evaluates the declared policy against the active save and returns a
machine-readable decision:

```json
{"operation": "stage_runs", "domain": "runs", "known": true,
 "compatible": false, "blocked_by": "inventory", "error": "..."}
```

It answers **only** whether already-legal operations may coexist in this save; it
never judges whether the mutation itself is semantically valid. Unknown
operations and unknown detectors **fail closed**.

### `_rhc_require_same_save_compatibility(...) returns void`

The thin internal enforcement helper every doorway calls. It delegates to the
decision and raises the exact message when incompatible. A doorway supplies only
its own hard-coded operation name; it never supplies, overrides, disables or
reinterprets a rule.

All three are internal-only: execute is revoked from `public`, `anon`,
`authenticated` and `service_role`.

## The audited compatibility edges

| Requested operation | Ordered blocking facts |
| --- | --- |
| `stage_runs` (generic stage) | `run_reconciliations`, `inventory`, `item_custody`, `entity_state`, `applied_statuses` |
| `delete_runs` (generic delete) | same, with the reconciliation message phrased for deletion |
| `reconcile_runs` (RT04) | `inventory`, `item_custody`, `entity_state`, `applied_statuses` |
| `mutate_inventory` | `runs` changed in this save |
| `mutate_item_custody` | `runs` changed in this save |
| `admit_item_identity` | `runs` changed in this save |
| `mutate_entity_state` | `runs` changed in this save |
| `mutate_applied_status` | `runs` changed in this save, then `campaign_clock` changed in this save |
| `stage_campaign_clock` | `applied_statuses` |

These cover the six Mission-audited incompatibilities, each represented once:
`runs ↔ run_reconciliations`, `runs ↔ inventory`, `runs ↔ item_custody / item
admission custody effects`, `runs ↔ entity_state`, `runs ↔ applied_statuses`, and
`campaign_clock ↔ applied_statuses`.

The order of blocking facts is preserved from the pre-Patch-1B inline guards, so
when several facts are present the **first** declared blocker and its exact
message are unchanged.

## Why two detectors are used

The `runs`-side and domain-side directions of an edge intentionally use different
detectors, exactly as before:

- The **`runs`-writing doorways** (`stage_runs`, `delete_runs`, `reconcile_runs`)
  are blocked by another domain's **explicit staging operation fact**
  (`_rhc_*_staged_in_save()`), which is bound to the save's own database-minted
  lock token. A value-equal replay of an absolute target still records the fact,
  so it still closes every `runs` doorway; the marker never leaks into a later
  save.
- The **domain-writing doorways** are blocked by a same-save `runs`/`campaign_clock`
  **change** (`_rhc_state_key_changed_in_save`), because their authority was
  proven against *published* Run/Clock truth: if this save is about to publish a
  different `runs` batch or Clock, that published proof would be stale.

Patch 1B preserves both mechanisms exactly; it only moves the decision into the
shared contract.

## What this patch changes

| Surface | Change |
| --- | --- |
| `public._rhc_same_save_compatibility_policy(text)` | created |
| `public._rhc_same_save_compatibility(text, bigint, bigint)` | created |
| `public._rhc_require_same_save_compatibility(text, bigint, bigint)` | created |
| `public.stage_campaign_state(text, text, jsonb)` | re-declared: `runs` guard delegates |
| `public.delete_staged_campaign_state(text, text)` | re-declared: `runs` guard delegates |
| `public.reconcile_run_resolution(text, jsonb)` | re-declared: guards delegate |
| `public.stage_campaign_clock(text, jsonb)` | re-declared: guard delegates |
| `public.mutate_applied_status(text, jsonb)` | re-declared: guards delegate |
| `public.mutate_owner_inventory(text, jsonb)` | re-declared: guard delegates |
| `public.mutate_item_custody(text, jsonb)` | re-declared: guard delegates |
| `public.admit_item_identity(text, jsonb)` | re-declared: guard delegates |
| `public.mutate_entity_state(text, jsonb)` | re-declared: guard delegates |

Every other byte of every function body, every existing dedicated-key closure,
the HWB-02 ordinary-save allowlist, all semantic validation, and Patch 1A's
registry are preserved exactly. No historical migration is edited.

The two generic doorways derive their *admission* from Patch 1A's registry, so
the migration re-declares them only when that registry is present; in the forward
chain it always is. This keeps Patch 1B from silently dropping or duplicating
Patch 1A's admission decision against a chain that predates Patch 1A.

## Authority and boundary

- **Compatibility policy is deterministic infrastructure**, never
  caller-selectable authority. Callers may identify the requested legal
  operation through existing mutation APIs but cannot supply, override, disable
  or reinterpret a rule. Unknown operations/detectors fail closed.
- **No second publication authority.** `begin_campaign_save`,
  `publish_campaign_save`, `abort_campaign_save`, generation, lease/lock, mirror
  and confirmation are untouched.
- **Dedicated domain semantics move nowhere.** Clock, RT04 reconciliation,
  Inventory, Custody/Admission, Entity State and Applied Status validation remain
  in their existing routes. The contract classifies compatibility only.
- **Patch 1A admission policy is intact and not duplicated.**
- **Operation-fact closure is preserved.** Final-value equality is not sufficient
  compatibility evidence.

## Deferred ownership (must not be absorbed here)

- durable `ORCHESTRATOR.md` / JOHNNY mutation-domain memory + workflow proof →
  Patch 1C;
- clean bootstrap/baseline equivalence and any later baseline/squash mechanism →
  Patch 1D;
- dedicated domain semantics/validation and new runtime mutation domains → their
  existing routes or a later bounded Mission;
- future Run registry/reservations, Run impact/collision mechanics, true
  chronology/time-travel, selective context/RAG, real campaign data import, BTH,
  frontend/UI and production Supabase activation → their later gates.

## Proof

`tests/post_ev2_1/test_same_save_compatibility_dispatcher.py` proves, on real
PostgreSQL 15 and 17 with disposable schemas and synthetic data only:

1. the policy truthfully declares every audited operation, domain and ordered
   edge, and invents none;
2. every declared edge is reachable and its declared `error` is byte-exact
   against the real doorway (metadata truthfulness);
3. both orderings of every symmetric exclusion fail closed;
4. the first declared blocker wins when several facts coexist;
5. generic `runs` stage/delete, RT04 `reconcile_run_resolution`, and every
   dedicated domain route consult the shared contract and preserve current
   failures;
6. `stage_campaign_clock` and applied-status mutation preserve their two-way
   same-save exclusion;
7. operation-fact closure is lock-token/save scoped: a value-equal replay still
   closes the edge, a later save does not inherit it, and an unchanged `runs`
   batch does not trip the domain-side guard;
8. Patch 1A's registry classifications and generic-route rejection of dedicated
   keys are unchanged;
9. the contract has exactly one fixed signature per function and is not
   executable by caller roles, so policy cannot be supplied or overridden;
10. RT01 begin/abort/publish lifecycle is unchanged;
11. a fresh full replay (repository `main` + Patch 1B) reaches the **same exact
    compatibility outcome** for the full operation × fact matrix as the
    pre-Patch-1B chain.
