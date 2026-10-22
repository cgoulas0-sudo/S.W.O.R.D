# EV2-12 — First real RHC item canary

EV2-12 establishes the first tiny real Rolling High Club Entity V2 item canary:
the already-canonical **Vampire**, normalized to current D&D 2024 / 5.5e wording,
admitted as the first real `item:` identity, and paired with one explicit,
narrow, human-approved admission script for the later DM/SAVE live-world custody
action. It builds no generalized intake framework and migrates no broader data.

## What this Mission is (and is not)

EV2-10 built owner-local ordinary inventory and EV2-11 built unique-item custody
with synthetic data only. EV2-12 proves that chain with one real RHC item before
any broader canon/data intake.

- It **is** the first real Entity V2 item identity (`item:vampire`), the
  normalization of the canonical Vampire mechanics, and the preparation of one
  inert admission script.
- It **is not** a generalized identity-intake framework, a live-data migration,
  an equipped/attuned state model, a second item, or any change to the EV2-11
  non-minting gameplay law.

## First real identity

`entities/items/vampire.json` is the first real Entity V2 record validated
against `schemas/entity.schema.json`:

```json
{
  "entity_id": "item:vampire",
  "entity_type": "item",
  "display_name": "Vampire"
}
```

Identity and custody remain separate concepts. This record declares identity
only; it establishes no owner, holder, equipment, or attunement fact. The static
definition in `inventory/weapons/vampire.md` describes what the item is and how
it works and, per `inventory/README.md`, does not by itself establish custody.

The Entity V2 identity workflow validates the real canary as its own step
(`python scripts/validate_entities.py entities/items`), separate from the
synthetic `tests/fixtures/entities/valid` fixtures. `tests/ev212/` additionally
proves the real identity against duplicate and malformed data.

## Approved 2024 mechanics normalization

The canonical Vampire definition duplicated legacy wording in
`inventory/weapons/vampire.md` and `villain/gork.md`. Both files were normalized
together so the rules text cannot split-brain:

- Legendary +3 Greatsword, 2d6 Slashing, Heavy, Two-Handed, attunement required.
- Removed `Versatile (1d10)` (a greatsword is already two-handed).
- Removed the Fighters / Paladins / Barbarians / Warlocks compatibility list.
- Removed the special `19–20 / ×2` critical wording; normal D&D critical-hit
  rules apply.
- Replaced second-based stack/cooldown wording with turn/round vocabulary. The
  two 15-second durations map to the Architecture Pin's explicit conversion,
  **"until the end of the wielder's second turn"**: Blood Stacks expire then
  without another successful melee hit, and Blood Release cannot be used again
  until then after use.
- Preserved Blood Hunger, Executioner's Balance, Blood Parry, Blood Memory, and
  the existing three-stack escalation unchanged.

`villain/gork.md` continues to defer all Vampire mechanics to the dedicated
weapon file and no longer restates a special critical range or a seconds-based
cooldown.

## Custody admission is separate, explicit, and deferred

`supabase/canaries/ev212_vampire_admission.sql` is the one explicit,
human-approved admission script. It:

- admits exactly one identity, `item:vampire`, and refuses a second run or any
  other item;
- runs the **existing RT01 candidate-generation lifecycle** rather than rewriting
  the current published generation in place: `begin_campaign_save(...)` derives a
  fresh candidate generation from published reality, the candidate is extended,
  and `publish_campaign_save(...)` advances the published pointer exactly one
  generation and marks the existing `runtime-published` mirror pending for the
  existing external mirror/confirmation worker. No new persistence, save, or
  mirror path is invented;
- validates the **complete existing** candidate `item_custody` collection with
  the existing EV2-11 validator, then builds the resulting collection and
  validates the **complete resulting** collection before staging, so malformed or
  duplicate unrelated custody truth fails closed;
- seeds the `item:vampire` record with **`owner_entity_id` null** (ownership
  remains unknown, not invented) and **`holder_entity_id` = `character:gork`**,
  because repository truth already establishes Gork as equipped with and attuned
  to Vampire and therefore as the known current holder. `character:gork` is only a
  stable reference to the already-established campaign character; no
  `character:gork` Entity V2 record is created or admitted;
- is **inert repository content**: it is not a migration, is not referenced by
  any migration or workflow, requires an explicit session approval flag, and
  cannot execute automatically.

Actual live-world execution of the admission remains a later explicit DM/SAVE
action after merge and post-merge proof. Once admitted, the EV2-11 gameplay
route `public.mutate_item_custody(...)` can update that record; it still cannot
mint or append any new `item:` identity.

## Deferred ownership

- Actual live-world execution of Vampire admission/custody: DM/SAVE after merge
  and proof.
- Generalized persistent item identity intake: a later dedicated gate.
- Equipped/attuned runtime state model: a later dedicated state/equipment gate.
- Broad real entity migration: a later Canon Intake / dedicated migration gate.
- Homebrew / Official / Adapted provenance: the HB workstream.
- Any second real item: later authorization.

## Proof

- `entities/items/vampire.json` validates against `schemas/entity.schema.json`
  and participates correctly in duplicate/malformed rejection.
- The Entity V2 identity workflow validates the real canary separately from the
  synthetic fixtures.
- Vampire legacy `Versatile`, the class compatibility list, the special
  `19–20` critical wording, and seconds-based timing are absent from the
  authoritative mechanics, and `villain/gork.md` is consistent.
- The admission script is narrow, one-item-only, preserves unknown ownership,
  seeds the known holder `character:gork` without creating a character entity
  record, and cannot execute automatically.
- `tests/ev212/` proves the admission script on real PostgreSQL, including that
  it advances the published generation through the candidate lifecycle (never
  rewriting the prior generation in place) and leaves the mirror pending, that
  malformed or duplicate unrelated custody truth fails closed, that the admitted
  record can then be updated by the non-minting gameplay route, and that a
  different item still fails closed.
- Existing Entity V2 and EV2-11 proofs remain green.
