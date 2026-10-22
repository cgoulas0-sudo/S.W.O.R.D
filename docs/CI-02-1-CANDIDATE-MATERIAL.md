# CI-02.1 — Canon Intake Candidate Material + Target Envelope

CI-02.1 completes the CI-02 responsibility accidentally left unbuilt: each
CI-01 candidate can now carry a separate, non-canon **material envelope**
containing the actual candidate material plus enough target/base context for
the later CI-03 collision/re-import checks. CI-01 stores identity, summary,
source attachment, provenance and status; CI-02 stores the human decision;
neither stored the material CI-03 must compare against established truth.
The original CI-00 design explicitly assigned temporary candidate
container/storage to CI-02. This patch restores that missing responsibility
without redesigning the series.

> Architecture sentence: **CI-02.1 adds a sidecar, never a source of truth.**
> It creates `schemas/intake_candidate_material.schema.json` and
> `scripts/validate_intake_candidate_material.py` next to the untouched CI-01
> candidate and CI-02 decision contracts; the CI-01 candidate schema and the
> CI-02 decision schema remain byte-for-byte unchanged.

## The contract

A material envelope is exactly:

```json
{
  "candidate_id": "candidate:inn-rumor",
  "material_type": "lore_text",
  "material": "The exact extracted excerpt carried for CI-03 comparison.",
  "proposed_target": {
    "kind": "npc",
    "reference": "npc-innkeeper",
    "label": "Optional human-readable target label"
  },
  "base_publication": {
    "generation": 1,
    "git_ref": "0123456789abcdef0123456789abcdef01234567"
  }
}
```

- **`candidate_id`** — required reference to an existing CI-01 candidate,
  using the exact `intake_candidate.schema.json` grammar
  (`candidate:<lowercase-slug>`).
  `scripts/validate_intake_candidate_material.py` resolves every reference
  against the CI-01 candidate batch (itself validated by the CI-01 contract
  first) and fails closed on an unknown candidate or on an invalid candidate
  batch. The envelope references and never rewrites the candidate. Exactly
  one material envelope per candidate may exist in one validated material
  set; a duplicate envelope for the same candidate fails closed.
- **`material_type`** — required non-blank free-form label for the
  material's type/kind, sufficient for later routing/comparison. No type
  taxonomy is declared law: free-form by design, like `source.kind` in CI-01.
- **`material`** — required non-blank actual candidate material/payload: the
  extracted content itself, preserved outside the CI-01 candidate identity
  envelope. Free-form text by design; CI-02.1 owns no domain-specific
  payload schema.
- **`proposed_target`** — optional proposed target/owner intent, represented
  only when actually known (`kind` + `reference` required, optional
  `label`; all non-blank). Proposed intent is **not** reconciled owner
  truth and never becomes authority by being recorded; an unknown target
  stays explicitly absent, never guessed or inferred.
- **`base_publication`** — optional base-publication pin for later
  stale/re-import context, represented only when actually known: a
  non-negative RT01 `generation` (0 is the empty pre-activation world,
  matching the runtime floor) and/or the exact 40-hex published checkpoint
  commit SHA as `git_ref` (matching the RT01 exact-read-back contract). At
  least one pin is required when the object is present; an empty pin object
  fails closed. Unknown stays explicitly absent, never inferred; CI-03 may
  later classify material without a usable pin as unresolved/not
  collision-clear.

## Material law

- **Sidecar, never source of truth** — the payload is candidate material,
  not authoritative state: it grants no canon authority, reader visibility,
  character knowledge, or gameplay behavior, and is never auto-promoted.
- **Non-canon and non-runtime** — extracted ≠ classified ≠ DM-approved ≠
  canon is unchanged; RT01 remains the only mutable runtime publication
  path, and the envelope adds no persistence route.
- **Source/provenance stay owned by CI-01** — they are resolved through
  `candidate_id` and are deliberately not duplicated into the envelope
  (`additionalProperties: false` rejects any attempt).
- **No new state** — the envelope adds no approved/rejected/published/canon
  state: CI-02's decision ledger stays the only decision surface and CI-04
  stays the only promotion bridge.
- **No collision result** — CI-03 owns duplicate/collision/re-import
  classification; this patch only gives CI-03 deterministic comparison
  input.
- **No eligibility rule invented** — material may exist for `extracted` and
  `classified` candidates alike; material presence never influences decision
  eligibility.

## What a material envelope is NOT

- **Not canon** — the payload is non-canon candidate material until CI-04
  promotion succeeds.
- **Not published truth** — RT01 / WDR-006: candidate material remains
  non-authoritative until existing gated publication.
- **Not a decision** — CI-02's decision ledger is unchanged; the envelope
  carries no outcome.
- **Not a collision detector** — no candidate-vs-canon/runtime comparison
  happens here (CI-03).
- **Not persistence** — no SQL/runtime/Supabase surface, no Save Gateway
  mutation route, no second persistence engine/store.

## Authority / ownership

- CI-01 owns candidate identity/source/provenance/status (untouched).
- CI-02 owns human decision evidence (untouched).
- CI-02.1 owns only the candidate material/target/base envelope.
- CI-03 owns duplicate/collision/re-import classification.
- CI-04 owns promotion/routing into canonical/runtime owners.
- RT01 remains runtime publication authority; repository canonical owners
  remain truth authority.

## Deferred ownership

- **CI-03** — actual candidate-vs-repository/runtime duplicate, collision
  and re-import detection; stale/conflict classification, including
  classification of material whose target/base pin is absent or unusable.
- **CI-04** — reconciled owner routing and durable promotion.
- Future gate only if evidence requires: durable Session Journal/workflow
  storage/recovery semantics.
- Gate 30: first BTH live canary. Gate 36: bulk import. Gate 40: Velare /
  frontend UX.

## Proof

See `tests/test_intake_candidate_material_validation.py` (inline fixtures
only — the CI-02.1 Surface Budget authorizes no external fixture directory),
the CI-01 candidate suite `tests/test_intake_candidate_validation.py`, the
CI-02 decision suite `tests/test_intake_decision_validation.py`, and the
HB-01 regression `tests/test_provenance_validation.py`. The write boundary
fence proves the exact Surface Budget at commit time, and `git diff --check`
proves whitespace cleanliness. No real RHC campaign record is read, written,
or referenced by CI-02.1.
