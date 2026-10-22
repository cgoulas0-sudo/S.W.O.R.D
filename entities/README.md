# entities/ — Real RHC Entity V2 identity records

This directory holds **real Rolling High Club Entity V2 identity records**. It is
the repository home for the actual campaign identities, kept deliberately
separate from:

- `schemas/` — the JSON Schema *definitions* (no records live there);
- `tests/fixtures/entities/` — non-canonical synthetic fixtures used only to
  exercise the schema.

An identity record answers only **"what is this thing and what is it called?"**
(`entity_id`, `entity_type`, and `display_name`), matching
`schemas/entity.schema.json`. It does **not** establish ownership, custody,
equipment, attunement, inventory, or any other mutable state. A static
definition file elsewhere in the repository (for example
`inventory/weapons/vampire.md`) describes *what an item is and how it works*; it
does **not** by itself establish that the item has a persistent `item:` identity
or who holds it.

## Layout

- `items/` — real persistent `item:<slug>` identities.

## First real canary (EV2-12)

`items/vampire.json` is the first real RHC Entity V2 item identity:

```json
{
  "entity_id": "item:vampire",
  "entity_type": "item",
  "display_name": "Vampire"
}
```

It declares identity only. Custody (owner / holder) is a separate concept owned
by the EV2-11 `item_custody` runtime namespace, and no ownership or holding fact
is established by this file or by the static weapon definition. The first
custody admission is a separate, explicit, human-approved DM/SAVE action prepared
under `supabase/canaries/ev212_vampire_admission.sql`; it is inert repository
content until deliberately executed. See `docs/EV2-12-FIRST-REAL-CANARY.md`.

## Generalized admission (EV2-12.1)

EV2-12.1 adds one reusable, explicitly authorized runtime action,
`public.admit_item_identity(...)`, for admitting an *already-approved* concrete
persistent `item:` instance onto the existing RT01 save/publish/mirror spine. It
does **not** create a repository identity file automatically, and it does not
make a repository definition or a static mechanics file prove live identity or
custody.

`definition != instance != custody != provenance`. A repository definition
describes what an item is and how it works; it may correspond to zero, one, or
many persistent instances. The stable instance identity is the `item:` ID, never
a display name or type, so two identical items remain two distinct IDs. EV2-12.1
is forward-only for its bounded admission receipts: the EV2-12 `item:vampire`
admission predates the action and has no receipt. Every admission receipt is
paired with exactly one custody record for the same `item:` ID; a
receipt-without-custody fails closed, while the legacy `item:vampire`
custody-only asymmetry remains valid. See
`docs/EV2-12.1-GENERALIZED-ITEM-ADMISSION.md`.

## Validation

Every record here is validated with the same schema validator the Entity V2
identity workflow uses:

```
python scripts/validate_entities.py entities/items
```

This runs as its own workflow step, separate from the synthetic
`tests/fixtures/entities/valid` fixture validation, so the real canary is graded
on its own. Cross-file `entity_id` uniqueness is enforced within the validated
batch; the real canary is additionally proven against duplicate and malformed
data by `tests/ev212/`.

Adding a second real item is still a later, separately authorized Mission. EV2-12.1
provides the reusable authorized admission *mechanism*; it does not itself admit
any real item, and it does not turn a static definition file into identity or
custody.
