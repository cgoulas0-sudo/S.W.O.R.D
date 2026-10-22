# CI-03 — Canon Intake Collision Detection

CI-03 adds the smallest deterministic **collision classifier** for Canon
Intake: before CI-04 may promote an approved candidate, CI-03 decides whether
the incoming candidate is `clear`, `duplicate`, `stale`, `conflict`, or
`unresolved` against current authoritative truth. An approved candidate must
never silently overwrite established RHC truth.

> Architecture sentence: **CI-03 classifies; it never mutates.** It creates
> `schemas/intake_collision.schema.json` and
> `scripts/validate_intake_collisions.py` next to the untouched CI-01
> candidate, CI-02 decision, and CI-02.1 material contracts, which remain
> byte-for-byte unchanged.

## The contract

A collision result record is exactly:

```json
{
  "collision_id": "collision:approve-inn-rumor-check",
  "candidate_id": "candidate:inn-rumor",
  "observation": {
    "target": { "kind": "npc", "reference": "npc-innkeeper" },
    "target_state": "present",
    "target_identity": { "generation": 3, "git_ref": "0123456789abcdef0123456789abcdef01234567" },
    "current_material": "The exact material currently established for npc-innkeeper."
  },
  "result": "conflict",
  "reason": "current target material differs from candidate material",
  "note": "Optional human note."
}
```

- **`collision_id`** — required stable, typed, set-unique identity with the
  strict grammar `collision:<lowercase-slug>`. A duplicate `collision_id`
  within one validated collision set fails closed.
- **`candidate_id`** — required reference to an existing CI-01 candidate
  using the exact candidate grammar. At most one collision result per
  candidate may exist in one validated collision set; a duplicate result for
  the same candidate fails closed.
- **`observation`** — required; exactly one trusted caller-supplied
  observation, embedded in the record so the evidence a result was classified
  from travels with it. See below.
- **`result`** — required, closed vocabulary exactly `clear`, `duplicate`,
  `stale`, `conflict`, or `unresolved`. The validator recomputes the
  classification deterministically and refuses any declared result that does
  not match, or any value outside the vocabulary.
- **`reason`** — required, and it must equal the deterministic reason the
  classifier computes for the same evidence. It is authoritative evidence
  trail, not free-form prose; a caller-authored reason that does not match
  fails closed. Free-form human commentary belongs in `note`.
- **`note`** — optional non-blank human note; logistics metadata only.

## The observation is bound to the candidate's proposed_target

CI-03 is a pure classifier. It performs no repository crawling, no Supabase
networking, no semantic/AI comparison, and owns no new truth store. A trusted
caller/adaptor (CI-04 or later integration, never CI-03) supplies the
observation:

- **`target`** — the proposed target the observation is about (`kind` +
  `reference`, same free-form grammar as CI-02.1 `proposed_target`). The
  validator requires it to match the referenced material envelope's
  `proposed_target` exactly (kind + reference), and forbids it when the
  envelope proposes no target. **One observation therefore cannot clear
  multiple different targets:** an observation for the innkeeper cannot clear
  a candidate proposing the crossroads. Two candidates that propose the same
  target may legitimately share the identical observation.
- **`target_state`** — exactly `absent` (known not to exist), `present`
  (known to exist), or `unknown` (evidence not obtained; stays Unknown and
  classifies `unresolved`). Missing evidence must be reported as `unknown`,
  never guessed as `absent`.
- **`target_identity`** (optional) — caller-known current publication
  identity: a non-negative integer `generation` and/or an exact 40-hex
  lowercase `git_ref`. Strictly validated fail-closed: at least one pin is
  required when present, booleans and malformed numeric types are rejected,
  and unknown fields are refused. Unknown stays absent, never inferred.
- **`current_material`** (optional) — current authoritative target material,
  represented only when the target is present. It may be omitted when the
  caller cannot retrieve it, in which case the classification is
  `unresolved`. It is forbidden when the target state is not `present`.

## Classification precedence

1. INVALID/INELIGIBLE input fails validation.
2. The candidate's CI-02 decision must be an explicit human `approved`;
   anything else (rejected, missing, non-human, unknown candidate) fails
   closed as not eligible for clearance.
3. The observation must be bound to the candidate's `proposed_target`
   (exact kind + reference); a mismatched, missing, or unproposed binding
   fails closed.
4. A known candidate `base_publication` pin (generation and/or git_ref) that
   conflicts with the known current publication classifies `stale` **before**
   any content comparison.
5. Absent `proposed_target` → `unresolved` (nothing to compare).
6. Authoritative target state `unknown` → `unresolved`.
7. Authoritative target known `absent` → `clear`.
8. Present target with unavailable current material → `unresolved`.
9. Present target material exactly equal to candidate material →
   `duplicate`.
10. Present target material differing → `conflict`.

Comparison is exact and deterministic: no normalization, no whitespace
folding, no fuzzy or AI equivalence. The declared `result` and `reason` must
both equal the classifier's computed values. A result of `duplicate`,
`stale`, `conflict`, or `unresolved` is NOT promotion-clear; only `clear` may
continue toward CI-04.

## Re-import law

Re-import is handled through the same target/base evidence: same target +
identical material = `duplicate`/replay; same target + changed material =
`conflict` requiring explicit later reconciliation; older/mismatched base
publication = `stale`; insufficient target/base evidence = `unresolved`. No
separate persistent import-history store is built here; CI-04 promotion
receipts may later provide durable lineage.

## What a collision result is NOT

- **Not canon** — extracted ≠ classified ≠ DM-approved ≠ canon is unchanged.
- **Not published truth** — RT01 remains the only mutable runtime publication
  path; the classifier performs no Save Gateway write and no canon mutation.
- **Not a decision** — CI-02's decision ledger is unchanged and never
  mutated.
- **Not a resolver** — no conflict resolution, no owner reconciliation, no
  automatic fix; conflicting/stale results route to explicit later
  reconciliation.
- **Not a history store** — no durable import-history database; the
  classifier consumes only the supplied current observation.
- **Not an evidence gatherer** — repository/Supabase/network access inside
  the classifier is a STOP condition; the caller gathers evidence.

## Authority / ownership

- CI-01 owns candidate identity/source/provenance/status (untouched).
- CI-02 owns human decision evidence (untouched).
- CI-02.1 owns the candidate material/target/base envelope (untouched).
- CI-03 owns deterministic collision classification only.
- CI-04 owns promotion, legal owner routing, promotion receipts, and the
  evidence-gathering adaptors.
- RT01 retains runtime publication authority; repository canon owners remain
  truth authority. Existing RHC truth outranks incoming candidate
  assumptions.

## Deferred ownership

- **CI-04** — legal owner routing, promotion receipt, Save Gateway/canonical
  writes, read-back, and the adaptors that gather authoritative current
  target/publication evidence from repository/runtime owners.
- Future gate only if evidence requires: durable import-history/reversal/
  merge workflow.
- BTH gates: BTH-specific persistence semantics.
- Gate 36: bulk import. Gate 40: Velare/frontend UX.

## Proof

See `tests/test_intake_collision_validation.py` (inline fixtures only — the
CI-03 Surface Budget authorizes no external fixture directory), the CI-01
suite `tests/test_intake_candidate_validation.py`, the CI-02 suite
`tests/test_intake_decision_validation.py`, the CI-02.1 suite
`tests/test_intake_candidate_material_validation.py`, and the HB-01
regression `tests/test_provenance_validation.py`. The write boundary fence
proves the exact Surface Budget at commit time, and `git diff --check`
proves whitespace cleanliness. No real RHC campaign record is read, written,
classified, or referenced by CI-03.
