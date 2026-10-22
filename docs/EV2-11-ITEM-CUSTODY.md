# EV2-11 — Unique-item custody

EV2-11 adds the smallest coherent custody layer for already-declared persistent
`item:` identities. It evolves no inventory box and creates no second save
engine: it is a dedicated authoritative `item_custody` runtime namespace plus one
guarded, atomic custody-mutation path on the existing RT01 SAVE spine.

## Mental model

- **Identity is admitted elsewhere; EV2-11 owns custody behavior.** A human/DM
  declaration or another already-authorized canonical source owns the decision
  that something has persistent individual `item:` identity. EV2-11 owns only the
  custody facts of identities that source has already admitted.
- **Owner and holder are independent nullable facts.** `owner_entity_id` is who
  the item belongs to; `holder_entity_id` is who currently carries it. Collapsing
  them into one fact would make theft and loans impossible to represent.
- **No stored status.** `held`, `owned`, and `treasure` are derived human labels
  only; they are never persisted.

## Record shape

Each `item_custody` record is exactly:

- `item_id` — required stable `item:<slug>` identity;
- `owner_entity_id` — required field, either JSON `null` or a `character:` /
  `party:` identity;
- `holder_entity_id` — required field, either JSON `null` or a `character:` /
  `party:` identity.

`character:` covers PCs, NPCs and villains because those are role/classification
differences, not separate identity types. `party:` supports party-held /
party-owned custody. There is no stored `status` field.

## Derived labels

| Label | Condition |
| --- | --- |
| `held` | `holder_entity_id` is non-null (whether or not owner is the same actor) |
| `owned` | owner is non-null and holder is null |
| `treasure` | both owner and holder are null |

Examples:

- owned and held by Bor: `owner=Bor, holder=Bor`;
- stolen from Bor by Fanis: `owner=Bor, holder=Fanis`;
- Bor owns it but nobody currently carries it: `owner=Bor, holder=null`;
- Fanis carries an item whose ownership is not established: `owner=null,
  holder=Fanis`;
- treasure: `owner=null, holder=null`.

## One authoritative record per item

`item_custody` is a JSON array with exactly one record per `item_id`. A second
record for the same identity is an ambiguity and fails closed. `item_custody` is
the authoritative unique-item custody truth; ordinary `inventory` is **not**
required to mirror it and must not become the unique-item authority surface.

## Durable mutation path

`public.mutate_item_custody(<lock_token>, <request>)` is the only way to stage
the engine-owned `item_custody` runtime namespace. It runs inside the normal
campaign save lifecycle:

```
begin_campaign_save -> mutate_item_custody -> publish_campaign_save
                    -> existing mirror / confirmation handshake
```

Request shape:

```json
{
  "item_id": "item:<slug>",
  "controller": { "kind": "mainrun" },
  "owner_entity_id": null,
  "holder_entity_id": null
}
```

`controller` is either `{ "kind": "mainrun" }` or
`{ "kind": "run", "run_id": "R##" }`. `owner_entity_id` and `holder_entity_id`
are required keys so a missing field (SQL `NULL`) is never confused with an
explicit JSON `null` (a real absence fact).

The target is an **absolute** replacement for one existing record, atomic across
both fields, so replaying one logical update is idempotent. Gifts/trades may
change owner + holder together in one mutation; theft/loan/pickup/drop changes
only the facts that actually changed; no intermediate half-transfer is
published.

### Non-minting law

Gameplay mutation updates an already-admitted custody record only. An existing
`item_id` counts as admission proof only after the current custody
record/collection satisfies the EV2-11 contract; malformed current truth fails
closed and is never canonicalized into a valid identity by overwriting it. If no
current admitted record exists for the requested `item_id`, the route fails
closed and stages nothing. Gameplay SAVE can never append a new custody record or
mint a new `item:` identity, and no rarity, magic, price, wording or narrative
importance can promote an object into a unique item. Initial admission/seeding of
real item identity + first custody is deferred to EV2-12 / a later authorized
identity intake flow.

## Controller / authority law

Authority follows the current controllers of the actors whose ownership/holding
facts are relinquished or newly assigned. The union of every non-null actor
across current owner, current holder, new owner and new holder must resolve
compatibly under the one asserted current controller:

- under a `mainrun` assertion, every involved actor must currently be unclaimed
  by any published Run;
- under a `run` assertion, every involved actor must be controlled by exactly
  that RUN #;
- a mutation that would cross incompatible MAINRUN/RUN controllers fails closed
  and must route through the existing handoff/reconciliation boundary rather than
  shortcutting authority.

Controller truth is proven against **published** Run truth (the RT03 `runs`
namespace), reusing the shared EV2-10 resolver, never caller prose. This proof
runs for every custody mutation, including the no-actor treasure case
(`owner=null`, `holder=null`), so an empty actor set cannot bypass controller
validation: a malformed or duplicated published `runs` batch fails closed, and a
Run assertion must still name an existing, non-parked authoritative Run. The
full published Run batch must also satisfy the existing EV2-08 cross-Run
mutable-owner uniqueness invariant (one mutable actor claimed by at most one
authoritative Run), so two distinct valid Runs claiming the same
`mutable_owner_entity_id` fail closed — duplicate `run_id` rejection alone is not
sufficient. A malformed published `runs` batch, a parked Run that still claims an
actor, two Runs claiming one actor, and a duplicated authoritative Run identity
all fail closed rather than falling through to MAINRUN.

## Same-save Run-ownership exclusion

Custody authority is proven against published Run truth, so Run-ownership changes
and custody mutations are mutually exclusive within one save:

- `mutate_item_custody` fails closed when this save has already staged a
  different `runs` batch;
- once this save has staged a successful custody mutation, every
  Run-ownership-writing doorway is refused for the rest of the save — the generic
  `runs` key and the dedicated RT04 `reconcile_run_resolution` route alike.

Closure keys on the explicit **custody-staging operation fact**, not on final
value equality, so a value-equal replay (or a mutate-away-and-back) still closes
every doorway. The marker is bound to the save's own database-minted lock token
and never leaks into a later save. Use separate saves for an ownership handoff
and a custody change.

## Bypass closure

The generic `stage_campaign_state` / `delete_staged_campaign_state` routes reject
the `item_custody` key (the same dedicated-key closure pattern as
`campaign_clock`, `run_reconciliations` and `inventory`), so a caller/model cannot
bypass the validated route with a raw generic runtime write. The HWB-02
ordinary-save allowlist is preserved unchanged.

## What EV2-11 deliberately does not build

- **EV2-12** — the first tiny real RHC item identity + custody canary and its
  explicit human-approved admission/seeding path.
- **Future identity intake** — generalized authorized creation/admission of new
  persistent `item:` identities; gameplay SAVE remains non-minting.
- **Ordinary inventory** — remains EV2-10 owner-local ordinary possessions and
  currency, not unique custody.
- **RT04 custody-consequence automation** — later/separate authorization.
- **HB workstream** — Official/Homebrew/Adapted provenance.
- **Later equipment/mechanics** — equipped/attuned, encumbrance, containers,
  ammunition, pricing/economy, crafting/durability, richer taxonomy.
- **Later world-custody expansion** — location/faction/creature custody only if a
  future product need justifies it.
- **Alternate save-slot/reality architecture** — POST-EV2 HOLD only.

## Proof

See `schemas/item_custody.schema.json`, `tests/test_item_custody_validation.py`,
and `tests/ev211/` (real PostgreSQL, full forward migration chain, through the
real save/publication/mirror-confirmation spine). No real RHC entity or item data
is introduced.
