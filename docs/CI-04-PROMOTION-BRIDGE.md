# CI-04 — Canon Intake Promotion Bridge

CI-04 adds the smallest reusable **promotion bridge** for Canon Intake. A
classified CI-01 candidate, its explicit CI-02 human approval, its CI-02.1
material envelope, and its CI-03 collision result are bound into one
deterministic **promotion instruction**. That instruction is handed to an
already-authoritative owner route, and the route returns a **promotion
receipt**. CI-04 prepares the truth and the receipt contract; it never becomes
a second publisher.

> Architecture sentence: **CI prepares truth. CI never becomes a second
> publisher.** CI-04 creates `schemas/intake_promotion.schema.json`,
> `schemas/intake_promotion_receipt.schema.json`, and
> `scripts/validate_intake_promotions.py` next to the untouched CI-01
> candidate, CI-02 decision, CI-02.1 material, and CI-03 collision contracts,
> which remain byte-for-byte unchanged.

## The promotion instruction

A promotion instruction is exactly:

```json
{
  "promotion_id": "promotion:inn-rumor",
  "candidate_id": "candidate:inn-rumor",
  "route": "runtime_save",
  "resolved_target": { "kind": "npc", "reference": "npc-innkeeper" },
  "material_type": "lore_text",
  "decision_id": "decision:approve-inn-rumor",
  "collision_id": "collision:inn-rumor-check",
  "expected_collision_result": "clear",
  "note": "Optional human note."
}
```

- **`promotion_id`** — required stable, typed, set-unique identity
  (`promotion:<lowercase-slug>`). A duplicate `promotion_id` fails closed, and
  a second distinct instruction for the same candidate also fails closed.
- **`candidate_id`** — required reference to a CI-01 candidate, using the exact
  candidate grammar. The instruction references and never rewrites the
  candidate; source/provenance lineage stays attached through `candidate_id`
  and is deliberately not duplicated here (`additionalProperties: false`).
- **`route`** — required explicit route class, exactly `runtime_save` or
  `repository_canon`. Unknown routes fail closed and the route is never
  inferred from material prose or target names.
- **`resolved_target`** — required explicit resolved owner/target (`kind` +
  `reference`). It must equal the referenced CI-02.1 `proposed_target`
  (kind + reference) exactly; a mismatch is a silent reroute and fails closed.
- **`material_type`** — required material linkage; it must equal the
  referenced material envelope's `material_type`.
- **`decision_id`** — required CI-02 decision reference. It must resolve to a
  valid decision whose `candidate_id` is the same candidate and whose outcome
  is a human `approved`.
- **`collision_id`** — required CI-03 collision reference. It must resolve to
  a valid collision whose `candidate_id` is the same candidate and whose
  `result` is exactly `clear`.
- **`expected_collision_result`** — required, exactly `clear`: the explicit
  declared expectation that the referenced collision result is collision-clear.
- **`note`** — optional non-blank human note; logistics only.

## The promotion receipt

A promotion receipt is exactly:

```json
{
  "receipt_id": "receipt:inn-rumor-success",
  "promotion_id": "promotion:inn-rumor",
  "candidate_id": "candidate:inn-rumor",
  "route": "runtime_save",
  "outcome": "success",
  "evidence": {
    "kind": "runtime_publication",
    "generation": 4,
    "git_ref": "0123456789abcdef0123456789abcdef01234567",
    "confirmed": true
  }
}
```

- **`receipt_id`** — required stable, typed, set-unique identity
  (`receipt:<lowercase-slug>`). A duplicate fails closed.
- **`promotion_id`** — required reference to a valid instruction in the same
  set; an unresolved `promotion_id` fails closed.
- **`candidate_id`** — required; it must equal the resolved instruction's
  `candidate_id`.
- **`route`** — required; it must equal the resolved instruction's `route`.
  A receipt records the route actually used.
- **`outcome`** — required, exactly `success` or `failure`. No third outcome.
- **`evidence`** — authoritative verification/read-back evidence. A success
  receipt **requires** it and it must be route-sufficient and verifier
  confirmed; a failure receipt must **not** carry it. Two route-specific
  identities exist:
  - `runtime_publication`: a positive `generation` plus the exact confirmed
    40-hex `git_ref` for the same database-owned runtime generation;
  - `repository_commit`: the exact 40-hex durable repository `commit`.
- **`failure_reason`** / **`note`** — optional non-blank metadata only.

## Eligibility law

A promotion instruction fails closed unless all of the following hold
(validator-enforced against the CI-01/02/02.1/03 sets, each validated by its
own contract first):

- the referenced candidate resolves and is `classified`;
- the referenced candidate has a valid explicit human `approved` CI-02
  decision (rejected/missing/non-human candidates are not eligible);
- `decision_id` resolves to a valid decision bound to the same candidate;
- `collision_id` resolves to a valid CI-03 result bound to the same candidate
  with `result == "clear"` (every `duplicate`/`stale`/`conflict`/`unresolved`
  fails closed);
- a valid CI-02.1 material envelope exists, `material_type` matches, and
  `resolved_target` equals the envelope's `proposed_target` exactly;
- `route` is explicit and registered.

## Route classes and the bridge boundary

Use only the smallest route vocabulary justified by current architecture:

- **`runtime_save`** — mutable operational state. It routes only to the
  existing **RT01 Save Gateway** authority and its exact
  publish/mirror/confirm lifecycle.
- **`repository_canon`** — static/authored/canon owner updates. It routes only
  to the existing **repository-authorized canon owner path**.

The module exposes an explicit, fixed route registry
(`ROUTE_AUTHORITIES`) and a `PromotionRouteAdapter` interface plus
`dispatch_promotion(...)`. The bridge resolves an explicit route to an
already-authoritative adapter and exposes only a validated copy of its receipt.
CI-04 contains no write executor: it has no raw SQL DML, does not push to
`runtime-published`, mints no second generation counter, and invents no second
repository authority. Real adapters belong to their authoritative lane; tests
use synthetic adapters that emulate success/failure/read-back.

### Dispatch is gated on full validation

A raw/unvalidated instruction is never handed to an adapter. `build_context`
first validates the CI-01/02/02.1/03 input sets and exactly one promotion
instruction, then issues an opaque, immutable `PromotionContext` backed by a
private snapshot of those validated records and instruction. A manually
constructed context, a changed instruction, or a mutated context cannot
authorize dispatch. Before the adapter runs, `dispatch_promotion` re-proves
the complete CI-04 eligibility chain against that frozen snapshot: classified
candidate, explicit human approval, exact CI-03 `clear` result, correctly bound
candidate/material/decision/collision lineage, a `resolved_target` matching the
proposed target, and a legal explicit route. A rejected/non-clear/rerouted
instruction fails closed before any adapter executes.

After the adapter returns, its result is frozen to canonical bytes
**immediately, before validation**: the adapter still owns the object it
returned, so CI-04 must never validate that live object and then read or copy
it again. Validation runs against the frozen snapshot — `receipt_id` shape,
exact `promotion_id` plus candidate/route binding, and, for success,
route-sufficient confirmed authoritative read-back evidence — and that exact
snapshot is what CI-04 exposes. A later mutation of the adapter-owned object
(including `promotion_id`, candidate, route, outcome, or evidence) therefore
cannot change the exposed result. A malformed, incomplete, unserializable, or
forged success receipt fails closed and is never returned as promotion success.

## False success is impossible

A success receipt can never validate without authoritative read-back evidence:
`runtime_save` success requires a confirmed `generation` + `git_ref`, and
`repository_canon` success requires a confirmed `commit`. A write attempt with
no confirmed read-back is failure/incomplete, never success. A `failure`
receipt carrying success evidence fails closed, so failure can never
masquerade as success.

## Replay / idempotency

Within one validated promotion set, all fail closed: duplicate `promotion_id`,
a second instruction for the same candidate, duplicate `receipt_id`, and more
than one success receipt for the same promotion. Contract-level stable IDs
plus deterministic rejection are the owned replay-safety boundary; there is no
durable persistent promotion journal in CI-04.

## What a promotion is NOT

- **Not canon** — extracted ≠ classified ≠ DM-approved ≠ collision-clear ≠
  promoted/canon is unchanged. An instruction or receipt is not truth.
- **Not a publisher** — RT01 remains the only mutable runtime publication
  authority; repository canon owners remain the static/canon authority.
- **Not a second persistence engine** — no SQL/runtime/Supabase schema, no
  durable promotion history beyond the authoritative receipts returned by the
  existing routes, no generic direct-write executor.
- **Not a resolver** — CI-03 `conflict`/`stale`/`duplicate`/`unresolved` are
  never auto-resolved; they route to explicit later reconciliation.
- **Not a real promotion** — no real RHC campaign candidate is promoted in
  this patch; the first real live candidate belongs to the later BTH canary
  sequence.

## Authority / ownership

- CI-01 owns candidate identity/source/provenance/status (untouched).
- CI-02 owns human decision evidence (untouched).
- CI-02.1 owns the candidate material/target/base envelope (untouched).
- CI-03 owns deterministic collision classification (untouched).
- CI-04 owns eligibility, explicit owner-route resolution, the promotion
  instruction, and the promotion receipt/read-back contract.
- RT01/SAVE owns mutable runtime publication; the existing repository
  owner/workflow owns static/canon repository mutation; the human DM owns
  creative/canon approval.

## Deferred ownership

- BTH-00+: BTH-specific owner mapping/persistence semantics.
- Gate 30: first real BTH Canon Intake + persistence canary.
- Gate 36: bulk history/import. Gate 40: Velare/frontend approval/promotion UX.
- Future gate only if evidence requires: a durable persistent promotion
  journal/history beyond the authoritative receipts already returned by the
  existing routes.

## Proof

See `tests/test_intake_promotion_validation.py` (inline fixtures only — the
CI-04 Surface Budget authorizes no external fixture directory), the CI-01
suite `tests/test_intake_candidate_validation.py`, the CI-02 suite
`tests/test_intake_decision_validation.py`, the CI-02.1 suite
`tests/test_intake_candidate_material_validation.py`, the CI-03 suite
`tests/test_intake_collision_validation.py`, and the HB-01 regression
`tests/test_provenance_validation.py`. The write boundary fence proves the
exact Surface Budget at commit time, and `git diff --check` proves whitespace
cleanliness. No real RHC campaign record is read, written, or referenced.
