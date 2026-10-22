# HB-01 — Shared Provenance Metadata Foundation

HB-01 adds the smallest reusable **provenance classification contract** for
authored RHC definition/preparation records so the system can distinguish
official, homebrew, adapted and unknown material — without creating a homebrew
rules engine and without touching real campaign data.

## The contract

Each target record may carry one optional `provenance` object with exactly one
field:

```json
"provenance": { "classification": "homebrew" }
```

`classification` is exactly one of:

| Value | Meaning |
| --- | --- |
| `official` | Published, officially produced material. |
| `homebrew` | Original fan/DM-authored material. |
| `adapted` | Derived from existing published material with changes. |
| `unknown` | Origin is explicitly unestablished. |

- The vocabulary is closed: any other value, casing, or spelling fails
  validation.
- The field is **optional**. A record without `provenance` remains valid.
- Absence is **not** `official`. Legacy records with no `provenance` are
  treated as *unclassified / Unknown* until an explicit later classification
  event.
- `unknown` stays `unknown`; nothing infers a stronger classification from
  names, lore, source text, or AI confidence.
- No supporting provenance text, book/page catalogue, URL, or publisher
  registry exists in this foundation: the `provenance` object accepts
  `classification` and nothing else. Any additional key (including blank or
  whitespace-only text) fails validation.

## Target surfaces

The same bounded semantics apply to the authored definition/preparation
surfaces only:

- Entity V2 identity/definition records — `schemas/entity.schema.json`
- Hooks — `schemas/hook.schema.json`
- Scenarios — `schemas/scenario.schema.json`
- Encounters — `schemas/encounter.schema.json`

The four schemas carry the identical `provenance` sub-schema
(`classification`-only, same four-state enum) so the contract cannot drift
into subtly different enums per surface.

## What provenance is NOT

Provenance is **logistics metadata**, and it grants no authority of any other
kind:

- It is **not canon status** — a `homebrew` label may still be accepted canon,
  and an `official` label is not automatically canon.
- It is **not reader visibility** — it says nothing about META/NON_META
  exposure.
- It is **not character knowledge** — it never informs who knows what
  (knowledge facts and their `source` fields remain a separate system).
- It is **not runtime/source-event evidence** — relationship occurrences, Run
  state, inventory/custody and runtime records are not provenance targets
  here.
- It is **not gameplay legality** — the mechanics of homebrew spells/items/
  conditions stay with the gameplay/rules gates.

Validators enforce the declared vocabulary and shape only. Classification of
real material is owned by the human DM or an explicit trusted intake process
(CI-00 / later intake); nothing infers it.

## Backward compatibility

No bulk migration is required or performed. Existing records — including the
real `item:vampire` canary — remain valid unchanged because `provenance` is
optional on every target surface. Real RHC campaign records were not edited in
this foundation.

## Deliberately deferred

- **CI-00** owns the real intake classification workflow and explicit
  candidate → approval → canon routing.
- **Gate 36** owns bulk migration/classification of legacy RHC material.
- Any future supporting provenance text (source notes, citations) must be
  designed when a real consumer exists; this foundation deliberately exposes
  none.
- Knowledge/fact source evidence, relationship-event evidence provenance,
  Run/runtime-state provenance, and licensing/commercial metadata belong to
  their own systems.

## Proof

See `tests/test_provenance_validation.py` (shared vocabulary identity across
all four schemas, four-state acceptance, invalid rejection, legacy
compatibility, no semantic effect on identity/lifecycle/semantics), the
existing Entity/Hook/Scenario/Encounter suites (regressions), and
`schemas/README.md`.
