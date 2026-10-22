# CI-02 — Canon Intake Decision Ledger

CI-02 adds the smallest repository-side **decision contract** for Canon
Intake: a sidecar decision ledger/packet that records explicit human
approve/reject decisions for CI-01 classified candidates, individually or in
a safe grouped review, without changing candidate state or canon/runtime
truth.

## The contract

A decision record is exactly:

```json
{
  "decision_id": "decision:approve-inn-rumor",
  "candidate_id": "candidate:inn-rumor",
  "outcome": "approved",
  "authority": "human",
  "decided_by": "the DM",
  "note": "Optional human note/reason.",
  "batch_label": "Optional non-authoritative review batch label"
}
```

- **`decision_id`** — required stable, typed, set-unique identity with the
  strict grammar `decision:<lowercase-slug>`. Stable identity is what makes
  deterministic duplicate/replay detection possible at the contract layer;
  a duplicate `decision_id` within one validated decision set fails closed.
- **`candidate_id`** — required reference to an existing CI-01 candidate,
  using the exact `intake_candidate.schema.json` grammar
  (`candidate:<lowercase-slug>`). The decision references and never
  rewrites or stores the candidate; source/provenance truth stays attached
  through the referenced candidate.
- **`outcome`** — required, exactly `approved` or `rejected`. No other
  value, casing, or free-form decision is legal.
- **`authority`** — required, exactly `human`. Approval authority is
  explicitly human; AI may propose material but never decides it.
- **`decided_by`** — required non-blank reference to the human authority who
  made the decision (for example the DM). Blank/whitespace identities are
  rejected, so a decision can never silently lack an accountable human.
- **`note`** — optional non-blank human note/reason.
- **`batch_label`** — optional non-blank, non-authoritative grouping/batch
  label for review convenience.

## Decision law

**Eligibility.** Only a candidate currently represented as `classified` is
decision-eligible. `scripts/validate_intake_decisions.py` resolves every
`candidate_id` against the CI-01 candidate batch (itself validated by the
CI-01 contract first) and fails closed on an unknown candidate or on a
decision against an `extracted` candidate. A decision never mutates the
candidate: validated candidates remain byte- and semantically unchanged.

**Selective approval.** A grouped review is only a container/convenience for
multiple independent candidate decisions (the optional `batch_label`). It
MUST NOT create one inherited outcome that silently applies to all members:
mixed approve/reject outcomes in one labeled group are legal and must remain
possible. There is no "approve all" semantics anywhere in CI-02.

**Replay/conflict.** Within one validated decision set:

- duplicate `decision_id` fails closed;
- more than one decision for the same `candidate_id` fails closed, whether
  the outcomes agree (replay) or conflict;
- there is no durable cross-run idempotency storage in CI-02: contract-level
  stable IDs plus deterministic duplicate/conflict rejection are the owned
  replay-safety boundary.

## What a decision is NOT

- **Not a candidate state** — CI-01's candidate status enum stays exactly
  `extracted | classified`; no `approved`/`rejected` value is added to it.
- **Not canon** — extracted ≠ classified ≠ DM-approved ≠ canon. Approved
  candidates also remain non-canon until CI-04 promotion succeeds; rejected
  candidates remain non-canon and cannot be treated as truth.
- **Not published truth** — a decision is evidence of human intent only. It
  does not mean published, reconciled, conflict-free, or runtime-applied.
  RT01 remains the only mutable runtime publication path.
- **Not a conflict resolver** — CI-02 does not decide whether approved
  content conflicts with established truth; CI-03 owns collision/duplicate/
  re-import detection and conflict classification.
- **Not a persistence system** — no SQL/runtime/Supabase surface, no durable
  workflow engine, no Save Gateway route, no second mutation path.

## Authority / ownership

- Human/DM owns approval/rejection decisions; CI-02 owns only the
  decision-record shape, validation, grouping semantics, and fail-closed
  duplicate/conflict handling.
- CI-01 retains candidate shape/lifecycle ownership; HB-01 retains the
  provenance vocabulary; CI-03 owns collision/duplicate/re-import detection;
  CI-04 owns promotion into legal canonical/runtime write paths; RT01
  retains runtime publication authority; repository canon owners remain
  truth authority.

## Deferred ownership

- **CI-03** — candidate-vs-canon/runtime duplicate, collision and re-import
  detection; stale replay against established truth.
- **CI-04** — approved-candidate promotion into the existing Save Gateway /
  canonical owner paths, with promotion receipt/read-back.
- Durable decision-history reversal/amendment semantics or persistent
  workflow storage belong to a future gate if evidence requires them; until
  then recorded decisions are human evidence, not a mutable workflow state
  machine.

## Proof

See `tests/test_intake_decision_validation.py` (inline fixtures only — the
CI-02 Surface Budget authorizes no external fixture directory), the CI-01
candidate suite `tests/test_intake_candidate_validation.py`, and the HB-01
regression `tests/test_provenance_validation.py`. No real RHC campaign
record is read, written, or decided by CI-02.
