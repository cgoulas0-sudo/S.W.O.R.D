# CI-01 — Canon Intake Candidate Contract

CI-01 adds the smallest repository-side **candidate contract** for Canon
Intake: a structured object that represents *material extracted from a source
and awaiting human review* without becoming canon, runtime truth, or a
parallel persistence system.

## The contract

A candidate record is exactly:

```json
{
  "candidate_id": "candidate:inn-rumor",
  "summary": "A rumor about a lost caravan, as printed in an unnamed adventure.",
  "status": "extracted",
  "source": {
    "kind": "published_adventure",
    "reference": "example-published-adventure-volume-1",
    "locator": "chapter 2",
    "origin": "original adventure author",
    "label": "Optional human-readable source label"
  },
  "provenance": { "classification": "official" }
}
```

- **`candidate_id`** — required stable, typed, batch-unique identity with the
  strict grammar `candidate:<lowercase-slug>`. A candidate is not an Entity V2
  entity; the `candidate:` prefix cannot collide with the eight entity types.
- **`summary`** — required non-blank human-readable description of the
  extracted material, enough for later review to know what the candidate is.
- **`status`** — required, exactly `extracted` or `classified` (see below).
- **`source`** — required attachment object with required non-blank `kind`
  and `reference`; optional non-blank `locator` (source-local locator or
  excerpt reference), `origin` (author/importer context), and `label`. Blank
  identifiers are rejected everywhere. No URL registry, publisher catalogue,
  book/page database, copyright system, or source verification is built here.
- **`provenance`** — reuses the exact HB-01 classification vocabulary
  (`official | homebrew | adapted | unknown`), shape, and closed-enum
  behavior; no competing provenance enum exists.

## Lifecycle: extracted vs classified

CI-01 owns pre-decision candidate states only. The two states map directly
onto HB-01's absence semantics:

- **`extracted`** — material produced/identified from a source but not yet
  classified. `provenance` must be **absent** (HB-01: absence is treated as
  unclassified/unknown, never as a stronger classification).
- **`classified`** — the classification event happened: `provenance` is
  **required** with an explicit HB-01 classification. `unknown` stays a legal
  explicit outcome; nothing infers a stronger classification from names, lore,
  source text, or AI confidence.

No `approved`, `published`, `canon`, or accepted-as-truth state exists in
this schema — the enum is closed, so such states are structurally impossible.
Human/DM approval authority and any decision ledger belong to CI-02 and later
gates.

## What a candidate is NOT

- **Not canon** — candidate state is never canonical or runtime authority;
  extracted ≠ classified ≠ DM-approved ≠ canon.
- **Not published truth** — RT01 / WDR-006: candidate material remains
  noncanonical until later reconciliation through the existing Save Gateway.
  CI-01 introduces no publish route and no second mutation path.
- **Not a content store** — the candidate carries identity, summary, source
  attachment, state, and classification only. Any payload/temporary-storage
  decision belongs to CI-02.
- **Not a persistence system** — no SQL/runtime/Supabase surface, no Save
  Gateway mutation route.

## Deferred ownership

- **CI-02** — decision ledger, per-item/grouped approve/reject, temporary
  storage/container decision.
- **CI-03** — duplicate/collision/re-import detection and overwrite
  prevention (CI-01 only rejects duplicate IDs within one validated batch).
- **CI-04** — promotion bridge to existing Save Gateway / canonical owner
  writes.
- Source licensing/catalogue verification, intake UX, and bulk history import
  belong to their own later gates.

## Proof

See `tests/test_intake_candidate_validation.py` (inline fixtures only — the
CI-01 Surface Budget authorizes no external fixture directory), the existing
`tests/test_provenance_validation.py` HB-01 regression, and
`schemas/README.md`. No real RHC campaign record is read, written, or
classified by CI-01.
