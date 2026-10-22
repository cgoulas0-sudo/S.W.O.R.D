# EV2-10 — Owner-local inventory ownership

EV2-10 evolves the EV2-03 inventory box into the smallest coherent owner-local
inventory model for Characters and Party stash, and adds one guarded runtime
mutation path on the existing RT01 SAVE spine.

It is not a second inventory system and not a second save engine: it is the
approved evolution of the existing box plus a validated doorway to mutate it
durably.

## Mental model

- **Owner locality** — inventory truth belongs to its owner entity. A Character
  inventory and a Party stash are the same model with different owners; Party
  stash is not a separate subsystem.
- **Semantic owner vs. storage envelope** — the runtime collection key
  `inventory` is storage/transport only. `entity_id` on each record remains the
  semantic owner. There is exactly one record per owner; inventory is never
  duplicated per Run.
- **One record contains** ordinary `entries` plus a structurally separate D&D
  `currency`. The box-level `status` (`known` / `unknown` / `not_applicable`) is
  preserved from EV2-03.

## Ordinary entries

Each ordinary entry is exactly:

- `name` — required, a non-blank JSON **string**;
- `description` — required, a non-blank JSON **string**;
- `quantity` — required, explicit integer `>= 1`, using the owning schema's
  Draft 2020-12 semantics: a mathematically integral number, so `1` and `1.0`
  are the same quantity.

A number, boolean, array or object in `name`/`description` is rejected rather
than coerced to text, matching the schema's `type: string`. Ordinary entries are
also unique (`uniqueItems`) under JSON item equality: two entries equal as
`{ name, description, quantity }` are a double-count, not two independent facts,
and `quantity: 1` and `quantity: 1.0` are the same entry. The runtime route
compares canonical JSONB values (numeric equality), not text serialization, so
numerically equal spellings cannot both be stored. There is no
category/taxonomy field in EV2-10. Quantity law:

- quantity is explicit; there is no implicit default of 1;
- `0` means absence/removal and is never stored as an entry (no tombstone);
- negative, non-integral, quoted, boolean, array, object, or missing quantity is
  invalid; a mathematically integral JSON number such as `1.0` is accepted
  exactly as the schema's `type: integer` accepts it.

Ordinary possessions may represent anything the owner currently has — gear,
food, objects, mounts, animals, carts, ships, or other owned assets — without a
taxonomy. Owned assets are ordinary possessions; EV2-10 does not invent a
separate asset-ownership subsystem.

## Currency

Currency stays inside the same owner inventory record but is structurally
separate from ordinary entries, so coin is never encoded as a text item:

- exactly the official D&D denominations `cp`, `sp`, `ep`, `gp`, `pp`;
- balances are non-negative integers with the same Draft 2020-12 integral-number
  semantics as `quantity` (`0` and `0.0` agree; non-integral values fail);
- zero balances are coherent and may be represented structurally;
- `currency` is optional: omitting it is coherent, but when present it must be a
  JSON object, so an explicit `"currency": null` is rejected rather than treated
  as omission.

## Controller / ownership law

An entity has exactly one current mutable gameplay controller: CAMPAIGN MAINRUN
or exactly one RUN #. EV2-10 consumes that law (EV2-08 / RT03) instead of
inventing a second one:

- the caller's controller assertion must be structurally valid before any
  authority branch: `controller.kind` must be a JSON string exactly `mainrun` or
  `run`. A null, missing, number, boolean, array, object, or unknown-string kind
  fails closed, so a malformed assertion can never be interpreted as MAINRUN by
  fallthrough;
- if an authoritative **published** Run currently claims the owner in its
  `mutable_owner_entity_ids`, only that RUN # may author the owner's inventory
  mutation;
- if no authoritative published Run currently claims the owner, MAINRUN is the
  current controller for inventory mutation;
- historical participation, a parked or past Run's continued existence, and
  caller self-assertion never grant mutation authority;
- a **parked** played Run that still lists the owner fails closed — it is not a
  current controller, and its claim means MAINRUN is not provably the controller
  either, so neither assertion is granted;
- a **malformed** authoritative published `runs` batch (a non-object entry, an
  entry without a string `run_id`, or an EV2-08-invalid record) fails closed
  rather than skipping the possible claim and falling through to MAINRUN;
- a **duplicated** authoritative published Run identity fails closed too: if two
  valid records share one `run_id`, Run authority is ambiguous even when only one
  of them lists the requested owner, so no controller is granted (matching the
  canonical RT03 reader);
- two Runs claiming one owner, or a stale/parked Run replaying old inventory
  after ownership moved, fail closed;
- inventory authority is proven against **published** Run truth, so Run-ownership
  changes and inventory mutations are kept out of the same save: if this save has
  already staged a different `runs` batch the mutation fails closed, and once
  this save has staged a successful inventory mutation **every**
  Run-ownership-writing doorway is refused for the rest of the save — the generic
  `runs` key and the dedicated RT04 `reconcile_run_resolution` route alike. Use
  separate saves for an ownership handoff and an inventory change.
- closure keys on the explicit **inventory-staging operation fact**, not on final
  inventory value equality: re-staging an absolute target that already equals the
  published value, or mutating away and back, still counts as a staging operation
  and still closes every Run-writing doorway. The marker is bound to the save's
  own database-minted lock token, so it never leaks into a later save.

## Durable mutation path

`public.mutate_owner_inventory(<lock_token>, <request>)` is the only way to
stage the engine-owned `inventory` runtime namespace. It runs inside the normal
campaign save lifecycle:

```
begin_campaign_save -> mutate_owner_inventory -> publish_campaign_save
                    -> existing mirror / confirmation handshake
```

The caller supplies an `owner_entity_id`, a `controller`, and the **absolute**
target `inventory` record. The absolute target makes replay of one logical
update idempotent. The complete candidate namespace is validated before
anything is staged, and the caller's single transaction plus the existing
gateway laws make the accepted mutation all-or-nothing.

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes
reject the `inventory` key (the same dedicated-key closure pattern as
`campaign_clock` and `run_reconciliations`), so a caller/model cannot bypass the
validated route with a raw generic runtime write, and the HWB-02 ordinary-save
allowlist is not widened. The same-save Run-ownership mutual exclusion described
above is also enforced on the generic `runs` key, so neither ordering — staging
a handoff before or after the inventory mutation — can publish a stale
controller's inventory update.

## What EV2-10 deliberately does not build

- **EV2-11** — unique-item identity/custody: explicit individual `item:`
  identity, transfer, missing/unowned semantics, and duplicate-custody
  prevention. Ordinary inventory does not self-promote into an `item:` entity,
  and no identity is inferred from rarity, magic, price, wording, or narrative
  importance.
- **EV2-12** — first tiny real RHC data canary.
- **RT04 inventory-consequence application** — automatic translation of
  preserved Run-resolution inventory consequences only if/when separately
  authorized.
- **HB workstream** — Official/Homebrew/Adapted provenance.
- **Later equipment/mechanics gates** — equipped/attuned state, encumbrance,
  containers, ammunition consumption, pricing/economy, crafting/durability,
  richer taxonomy.
- **EV2-04.1 follow-up** — old box-schema owner-id type-alternation alignment
  for ability/status_effect.
