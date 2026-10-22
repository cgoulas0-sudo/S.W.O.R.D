# schemas/

JSON Schema definitions for Entity V2 plus the Canon Intake candidate
contract (CI-01), decision ledger (CI-02), candidate material envelope
(CI-02.1), collision classification (CI-03), and the promotion bridge
(CI-04). This directory holds schema documents only — no entity records live
here.

## Shared provenance classification (HB-01)

`entity.schema.json`, `hook.schema.json`, `scenario.schema.json` and
`encounter.schema.json` all carry the same optional `provenance` object:

```json
"provenance": { "classification": "homebrew" }
```

`classification` is exactly one of `official | homebrew | adapted | unknown`
(a closed vocabulary; anything else fails validation). Provenance is
**logistics-level origin metadata for authored definition/preparation records
only**: it grants no canon authority, no reader visibility, no character
knowledge, and no gameplay behavior, and it is never inferred. Classification
of real material is owned by the human DM or an explicit trusted intake
process (CI-00 / later intake).

The field is optional and no bulk migration was performed: legacy records
without `provenance` remain valid, and absence is treated as
**unclassified/Unknown** — never as `official` — until an explicit later
classification event. The `provenance` object accepts `classification` and
nothing else: there is deliberately no supporting text, book/page catalogue,
URL, or publisher registry yet. The four target schemas declare the identical
`provenance` sub-schema so the vocabulary cannot drift per surface. See
`docs/HB-01-PROVENANCE.md` and `tests/test_provenance_validation.py`.

This metadata layer does not extend to state/knowledge/inventory boxes, item
custody, relationships, Runs, or runtime records: authored
definition/preparation surfaces are the initial and only targets.

## reality.schema.json (POST-EV2-4B)

Reality identity + explicit parent-lineage foundation. A reality is one admitted
history and is deliberately **not** an Entity V2 type, a per-subject
availability/scoping list, or a state-copy/override payload.

- `reality_id` — stable identity using the strict grammar `reality:<lower-slug>`
  (`[a-z0-9]+(-[a-z0-9]+)*`), outside the eight `entity_type` values. The one root
  primary reality is `reality:rhc-primary`.
- `display_name` — human-readable name.
- `parent_reality_id` — required on an alternate reality, forbidden on the root.
  Parent lineage is explicit, resolves to an admitted reality, and is acyclic.

**Inheritance first:** a child reality is its parent unchanged unless an explicit
divergence later says otherwise through the real owning domain. Reality identity
alone clones/removes/rewrites/scopes no Entity, Hook, Scenario, Encounter, Run or
system definition. There is no subject-availability map and no generic override
blob. `scripts/validate_realities.py` enforces uniqueness, resolution and
acyclicity; `realities/registry/` holds the root record.

See `docs/POST-EV2-4B-REALITY-INHERITANCE.md` for the full contract and the
rejected availability-scope design it replaces.

## entity.schema.json

The Entity V2 identity layer (EV2-02, realigned by EV2-04, extended by EV2-04.1). Defines the minimal identity record for any campaign entity:

- `entity_id` — stable, typed, unique ID (`<entity_type>:<slug>`)
- `entity_type` — one of `character`, `location`, `faction`, `party`, `creature`, `item`, `ability`, `status_effect` — the permanent identity type
- `subtype` (optional) — a free-text classification/traceability label (e.g. `npc`, `villain`, `ally`, or an ability/status_effect classification such as `spell`, `passive`, `curse`) for filtering and UI only
- `display_name` — human-readable name
- `references` (optional) — array of other entities' `entity_id` values this record structurally points to

`entity_id`'s prefix must match `entity_type`.

`npc` and `villain` are mutable roles, not permanent identity types: they must never be baked into `entity_id` or `entity_type`. A character who is currently a villain's shopkeeper informant is `entity_type: character`, `subtype: npc` (or `villain`, if that fits better) — the identity type and ID stay `character:<slug>` regardless of role. `subtype` is classification metadata only; it must not be relied on as brittle business logic and carries no schema-level effect on `entity_id`.

### ability / status_effect (EV2-04.1)

`ability` is a persistent definition of something an entity can do or inherently has (a spell, trait, feature, action, reaction, passive, etc. — the specific kind is `subtype`, not a separate `entity_type`). `status_effect` is a persistent definition of something that can be applied to an entity (a condition, curse, transformation, buff, debuff, etc. — again `subtype`, not a separate `entity_type`).

Both are **definitions only**, the same posture `item` already takes toward ownership/equip state: this layer does not, and must not be extended in place to, describe activation semantics, action-economy cost, duration, removal/stacking rules, resource pools, trigger grammars, or the runtime application of a `status_effect` to a specific target right now. A character currently afflicted by a `status_effect` is a separate runtime concern, implemented by **EV2-13.1** as the engine-owned `applied_statuses` namespace (`docs/EV2-13-1-TIMED-STATUS-CONTINUITY.md`): a live application references a `status_effect:<slug>` definition identity without minting or mutating it, and carries elapsed-time anchors, thresholds and acknowledgement/end state of its own. It is never modeled by adding fields here or by an entry in `state.schema.json`, whose `entries` values are restricted to plain scalars and cannot hold a structured applied-instance record (source, elapsed anchor, thresholds, acknowledgement state).

`state.schema.json`, `knowledge.schema.json`, and `inventory.schema.json` still hard-code the original six-type `entity_id` alternation and were deliberately left unchanged by EV2-04.1 (out of scope for this patch) — they do not yet recognize `ability:`/`status_effect:` IDs. Realigning them is follow-up work, not a defect to route around here.

## Scope

This schema covers identity only. It does not describe, and must not be extended in place to describe, owner state, knowledge, inventory/item custody, relationships, generated links or indexes, Hooks, Scenarios, Runs, or RAG — those are later Entity V2 gates.

The synthetic fixture layer (`scripts/validate_entities.py` and `tests/fixtures/entities/`) still proves the schema shape, and EV2-12 now adds the **first real RHC Entity V2 record**, `entities/items/vampire.json` (`item:vampire`), validated against this schema by its own workflow step. It declares identity only; broader real entity migration remains a later gate.

## relationship_kind.schema.json (EV2-05 Patch 1)

Entity V2's relationship layer is a human design decision split into two pieces:

1. **relationship kind** — a small, data-driven controlled-vocabulary entry describing a
   *label* a relationship instance can use (`serves`, `parent_of`, `allied_with`, ...) plus
   structural metadata about that label. This is what `relationship_kind.schema.json`
   defines. A kind is **not** an Entity V2 `entity_type` and never gets an `entity_id` — it
   has no independent lifecycle, no display variety, and no need to be pointed at by
   `references`.
2. **relationship instance** — the lifecycle-bearing fact that a specific source entity and
   target entity are connected by a given kind (e.g. "Gork serves Larloch," with a start
   and, eventually, an end). EV2-05 Patch 2 defines this separately in
   `relationship_instance.schema.json`.

### Fields

- `kind` (required) — lowercase snake_case slug identifying the relation label.
- `symmetric` (optional, boolean) — true if the relation reads the same in both directions
  (e.g. `allied_with`); a symmetric kind must not also declare `inverse_of`, since it is its
  own inverse.
- `inverse_of` (optional) — the kind slug naming this relation's opposite direction for an
  asymmetric pair (e.g. `parent_of` / `child_of`). Both members of a pair should exist as
  their own registry entries and point back at each other; `scripts/validate_relationship_kinds.py`
  checks this across a batch, and also that `inverse_of` resolves to a kind present in the
  batch at all.
- `allowed_source_types` / `allowed_target_types` (optional) — arrays drawn from the same
  closed `entity_type` enum as `entity.schema.json`, restricting which entity types may sit
  on either end of an instance of this kind. Absence on both sides of a pair means fully
  unrestricted. For an `inverse_of` pair, these must mirror in reverse (this kind's
  `allowed_source_types` equals the inverse's `allowed_target_types`, and vice versa) —
  a restriction declared on only one side, with no matching mirror declared on the other,
  is also rejected, since an undeclared mirror is wider than the declared side and so does
  not actually mirror it. For a `symmetric` kind, `allowed_source_types` and
  `allowed_target_types` must describe the same domain when either is declared (a relation
  that reads the same in both directions can't restrict one endpoint differently from the
  other). `scripts/validate_relationship_kinds.py` enforces all of this across a batch.
- `notes` (optional) — free-text authoring documentation.

### `references` vs. relationship kind/instance — the boundary

`entity.schema.json`'s `references` array and the EV2-05 relationship layer are deliberately
two different mechanisms, not overlapping ones:

- **`references`** stays the mechanism for a **permanent, non-lifecycle, structural**
  pointer that is really a property of the definition itself — it has no start, no end, and
  is not tracked as a world event. EV2-05 does not change this or migrate existing
  `references` usage.
- **Relationship kind + instance** is for a **semantic, lifecycle-bearing** fact between two
  entities in the world — it can start, end, and its history matters.

If a proposed connection has no lifecycle worth tracking, it belongs on `references`, not in
the relationship layer. Do not migrate existing `references` usage into relationship
instances, and do not extend `references` to carry lifecycle/temporal data — that is what the
relationship instance layer is for.

### Scope (Patch 1)

Patch 1 covers the relationship **kind registry**, proven with tiny non-canonical fixture
kinds. It does not contain relationship instances or real RHC relationship data. See
`scripts/validate_relationship_kinds.py` and `tests/fixtures/relationship_kinds/`.

## relationship_instance.schema.json (EV2-05 Patch 2)

A relationship instance is one lifecycle-bearing fact connecting a `source_id` to a
`target_id` through one registered `kind`.

### Fields and invariants

- `relationship_id` — required, stable, unique across the validated instance batch. It is a
  human-chosen stable string; Patch 2 deliberately imposes no UUID or prefix grammar.
- `source_id` / `target_id` — typed Entity V2 IDs using the current eight identity types.
  Patch 2 validates endpoint **types** against the selected relationship kind when that kind
  declares `allowed_source_types` / `allowed_target_types`. It does not yet require a real
  entity record to exist, because real RHC migration is still a later gate.
- `kind` — required and must exist in the supplied Patch 1 relationship-kind registry.
- `started_at` / `ended_at` — optional, non-blank opaque strings. Patch 2 intentionally does
  no campaign-clock parsing, ordering, or date arithmetic.
- **active/current** is derived only from the absence of `ended_at`; there is no stored
  `active` boolean.
- At most one active instance may exist for the same exact
  `(source_id, kind, target_id)` triple.
- Ending a relationship preserves the record as history; ended records are not deleted, and
  multiple ended historical records for the same triple are allowed.

`relationship_instance.schema.json` is strict today (`additionalProperties: false`) so typos
or invented fields cannot silently become data. That strictness is **not** a closed design:
later versioned schema evolution may add fields such as `strength`, `visibility`, `reason`,
or provenance/source without replacing the core relationship model.

### Scope (Patch 2)

Patch 2 is fixture-only foundation. No real Rolling High Club relationship instance is added
or migrated. It does not absorb current location, inventory custody, knowledge/belief,
applied status instances, Run participation, spell/ability mechanics, Hooks, Scenarios,
generated backlinks/indexes, or RAG.

See `scripts/validate_relationship_instances.py`,
`tests/test_relationship_instance_validation.py`, and
`tests/fixtures/relationship_instances/` for proof.

## hook.schema.json (EV2-06)

A Hook is RHC's quest / multi-day story-thread record: a meaningful objective or unresolved
thread worth continuity tracking. It is **not** an Entity V2 entity and does not replace
Scenario, Encounter, Run, canon status, or META/NON_META visibility.

### Fields and lifecycle

- `hook_id` — required stable permanent Hook ID using the `H<number>` shape.
- `title` / `objective` — required non-blank human-readable quest identity and purpose.
- `status` — exactly one of `dormant`, `active`, `resolved`, `retired`.
- `activation_condition` — required non-blank statement of what makes the Hook active.
- `resolution_condition` — required non-blank statement of what counts as a valid conclusion.
- `related_entity_ids` — required unique array of typed Entity V2 IDs using the current eight identity types. EV2-06 validates ID shape/type only; real entity resolution remains later migration work.
- `retirement_reason` — required only when status is `retired`, and forbidden otherwise. Retirement means the objective can no longer be meaningfully completed or has become invalid/irrelevant; it is preserved as history rather than silently deleted.

The approved lifecycle is `dormant -> active -> resolved`, with `dormant -> retired` and
`active -> retired` as terminal failure/invalidity paths. EV2-06 defines record shape and
validation only; mutation procedures and campaign-clock semantics are not implemented here.

### Scope

Fixture-only foundation. No real Rolling High Club Hook is added or migrated. Scenario
ownership/links are deliberately deferred to EV2-07, and EV2-06 does not implement Encounter,
Run, RAG, automatic Hook creation, current-day ledgers, or campaign-time machinery.

See `scripts/validate_hooks.py`, `tests/test_hook_validation.py`, and
`tests/fixtures/hooks/` for proof.

## state.schema.json / knowledge.schema.json / inventory.schema.json

EV2-03: three minimal, generic "boxes" any Entity V2 entity can be given, one JSON Schema each. All three require `entity_id` (same typed pattern as `entity.schema.json`) and a box-level `status` of `known`, `unknown`, or `not_applicable` — this is the one tri-state placement that is coherent for every box, so it is the layer that is always required.

- **state** — what is true for this entity now. When `status` is `known`, `entries` is a required, non-empty list of `{ attribute, status, value }`, where each entry's own `status` is independently `known` / `unknown` / `not_applicable` and `value` (a plain string/number/boolean only) is present only when that entry's `status` is `known`. Entry-level status is meaningful here because state decomposes into independent attributes that can each individually apply, not apply, or be unestablished.
- **knowledge** — what this entity knows, believes or suspects (EV2-14; see below). The box-level placement is unchanged from EV2-03: `entity_id` plus the tri-state `status`, with a non-empty `entries` list only when `status` is `known`.
- **inventory** — what this entity currently has. When `status` is `known`, `entries` is a required list — no per-entry status — and may be empty (`known` + `entries: []` means the inventory is known to be empty, a distinct fact from `unknown`). EV2-10 replaced the EV2-03 flat `{ item }` entry with the explicit ordinary possession `{ name, description, quantity }` plus a structurally separate D&D `currency` object (see below). An inventory entry's presence in the list *is* the known-established fact; unlike a state/knowledge attribute, there is no coherent meaning for an individual item slot being independently unknown or not-applicable, so entry-level status is deliberately not offered here. The box-level `status` alone carries "we haven't tracked this" (`unknown`) or "this entity doesn't have an inventory concept" (`not_applicable`).

When `status` is `known`, `entries` is required (non-empty for state/knowledge; may be empty for inventory). When `status` is `unknown` or `not_applicable`, `entries` must be absent — schema-enforced, not just documented. `currency` follows the same rule: it is only meaningful on a `known` inventory and is forbidden otherwise.

### inventory.schema.json (EV2-10)

EV2-10 evolves the EV2-03 inventory box in place into the smallest coherent owner-local inventory model for Characters and Party stash; it does not create a second inventory system. The record stays owner-local: `entity_id` is the semantic owner (a Character inventory and a Party stash are the same model with different owners), and the record still carries the box-level tri-state `status`.

When `status` is `known`:

- **`entries`** (required, may be empty) — ordinary possessions. Each entry is exactly `name` (non-blank JSON string), `description` (non-blank JSON string), and `quantity` (an explicit integer `>= 1`). Quantity is never implicit: `0` means absence/removal and is not stored as an entry; negative and fractional quantities are invalid. `name`/`description` are JSON strings, never coerced from numbers/booleans/objects, and entries are unique (`uniqueItems`) under JSON numeric equality: an equal `{ name, description, quantity }` entry cannot be counted twice, and `quantity: 1` and `quantity: 1.0` are the same entry, not two. There is no category/taxonomy field. Owned assets such as mounts, carts, or ships are represented as ordinary possessions rather than through a separate asset-ownership subsystem.
- **`currency`** (optional) — D&D money, structurally separate from ordinary entries so coin is never encoded as a text item. The only allowed denominations are `cp`, `sp`, `ep`, `gp`, `pp`; each balance is a non-negative integer, and zero balances are coherent and may be represented structurally. Omitting `currency` is valid; when the property is present it must be an object, so an explicit `"currency": null` is invalid rather than a synonym for omission.

Individual persistent item identity is deliberately **not** inferred or minted here: an ordinary inventory entry does not self-promote into an `item:` entity, and the schema exposes no identity/custody field on an entry. Explicit individual identity, custody, and transfer belong to the later EV2-11 gate. EV2-10 also does not model custody transfer, equipped/attuned state, encumbrance/weight, containers, ammunition, pricing/economy, crafting/durability, or provenance.

The guarded runtime mutation route for this model is `public.mutate_owner_inventory(...)` on the RT01 save spine — see `docs/EV2-10-INVENTORY.md` and `supabase/README.md`. Ordinary inventory records also remain representable as fixture-only schema data; no real RHC inventory record is migrated by EV2-10.

### knowledge.schema.json (EV2-14)

EV2-14 evolves the EV2-03 knowledge box in place into the smallest coherent owner-local knowledge model. The record stays owner-local — `entity_id` is the knower, and knowledge always belongs to the knower — and the box-level tri-state `status` is preserved: when `status` is `unknown` or `not_applicable`, `entries` is still forbidden; when `status` is `known`, `entries` is required and non-empty.

Each entry holds **exactly one content mode** and is one of two shapes:

1. **Reusable fact reference** — `fact_id` (a stable reusable world fact from `knowledge/facts.json`), plus the required `topic`/`epistemic_status` pair and optional concise `note`/`source`. The knower record references world truth instead of duplicating it. Its reader visibility is **inherited from the referenced fact at read time and must not be copied into the knower record**: `visibility` is structurally forbidden on a fact-reference entry so it cannot drift from the fact owner.
2. **Concise local assertion** — a plain scalar `value` (the EV2-03 player-agency boundary survives: no objects/arrays, so no structured directive becomes knowledge data), plus the required `topic`/`epistemic_status` pair, a **required** `visibility` (`meta | non_meta`) because the assertion itself is the underlying information, and optional concise `note`/`source`.

`epistemic_status` is exactly `confirmed | belief | suspicion` and describes only this knower's stance: `confirmed` means the knower treats the information as established knowledge; `belief` means the knower currently accepts it without the repository promoting it to world truth; `suspicion` means the knower considers it possible/likely but not established. Misunderstandings and false beliefs remain local assertions with `belief`/`suspicion`; they never receive a canonical `fact_id` solely because a character believes them, and belief/suspicion never creates world truth. An entry without `epistemic_status`, a blank topic or `fact_id`, an unsupported epistemic state, an entry with both `fact_id` and `value`, and an entry with neither are all rejected. The EV2-03 entry-level `status` tri-state is intentionally replaced by `epistemic_status` — entries are statements this knower holds, not independently unknown topic slots.

There is no per-entry knowledge identity, no runtime mutation, and no automatic knowledge propagation from facts, DM knowledge, other entities, party membership, reader visibility or Beyond the Heroes publication: the existence of a reusable fact never grants knowledge to anyone, and a player-visible fact is not known by every character. Safe read semantics (DM/internal read vs player-facing exposure read) are the durable contract defined in `docs/EV2-14-LOCAL-KNOWLEDGE.md` and `knowledge/KNOWLEDGE_SYSTEM.md`. Legacy NPC knowledge shapes in `npc/npc_state.json` remain readable but are not the target authority model and are not destructively migrated; `observer_knowledge` and `protected_secrets_known` do not become new first-class Entity V2 collections. No real RHC knowledge record exists yet — see `tests/fixtures/knowledge/` for the synthetic proof; real records and any safe legacy migration belong to a later intake gate.



### Player-agency boundary (state/knowledge only)

An entry may record an established fact about a Player Character, but must never prescribe or constrain that player's next action or choice. What EV2-03 actually enforces is structural: an entry `value` is restricted to a plain scalar (string/number/boolean), so a structured action-prescription payload (e.g. `{"action": "attack", "target": "goblin"}`) cannot be stored as data — see `tests/test_state_knowledge_inventory_validation.py::test_entry_value_restricted_to_scalars`. This does **not** and cannot detect prescriptive language written inside a plain string; that remains a documented authoring rule, not a schema-enforced one, until a later dedicated state gate takes on real content review.

### Scope

Same boundary as the identity layer: no HP/resources/conditions/goals/relationships, no detailed equipment/custody/transfer mechanics, no Homebrew/provenance, no generated links/indexes, no Hooks/Scenarios/Runs/RAG. The knowledge box's detailed model is now carried by EV2-14 (above) within its own boundary — no runtime mutation, propagation, retrieval or second truth system; see `docs/EV2-14-LOCAL-KNOWLEDGE.md`. No real RHC campaign entity is validated against these schemas yet — see `tests/fixtures/state/`, `tests/fixtures/knowledge/`, `tests/fixtures/inventory/` for the fixture-based proof of this layer.

## item_custody.schema.json (EV2-11)

EV2-11 adds unique-item custody for already-declared persistent `item:`
identities. It is deliberately separate from ordinary `inventory`: an ordinary
inventory entry stays identity-free, and an item's custody is recorded here once
an authorized source has admitted its `item:` identity. This schema does not
admit or mint identities; the first real identity (`item:vampire`) is declared in
`entities/items/vampire.json`, and its first custody admission is prepared as an
explicit, inert DM/SAVE script in `supabase/canaries/ev212_vampire_admission.sql`
(EV2-12). See `docs/EV2-12-FIRST-REAL-CANARY.md`.

A custody record is exactly:

- `item_id` — required, a valid `item:<slug>` identity;
- `owner_entity_id` — required, either JSON `null` or a valid `character:` /
  `party:` identity;
- `holder_entity_id` — required, either JSON `null` or a valid `character:` /
  `party:` identity.

Owner and holder are two independent nullable facts. `character:` covers PCs,
NPCs and villains because those are role/classification differences, not separate
identity types; `party:` supports party-held/party-owned custody. There is no
stored status field: `held` (holder non-null), `owned` (owner non-null, holder
null) and `treasure` (both null) are derived labels only. Legitimate combinations
include owned-and-held, stolen/loaned (owner and holder differ),
owned-but-carried-by-none, carried-without-established-ownership, and treasure.
Every field is required and `additionalProperties` is false, so a missing field
and an explicit JSON `null` are unambiguous and a stored `status` (or any other
invented field) cannot become data.

This schema and its guarded runtime route (`public.mutate_item_custody(...)`) are
the authoritative unique-item custody truth; ordinary `inventory` is not required
to mirror it. Equipped/attuned state, encumbrance, containers, ammunition,
pricing/economy, crafting/durability, provenance, location/faction/creature
custody, and alternate save-slot/reality architecture are out of scope. See
`docs/EV2-11-ITEM-CUSTODY.md`, `tests/test_item_custody_validation.py` and
`tests/fixtures/item_custody/` for proof.

## character_mechanics.schema.json (POST-EV2-9)

The bounded operational character-mechanics record for one tracked
`character:<slug>`. It carries the normalized machine-readable mechanical
capacities/metadata a runtime consumer needs together with the current expendable
values, in ONE owner record — the durable runtime surface for character vitals
and resources. It is deliberately **not** a full Markdown character-sheet mirror
and owns no controller authority.

A record is exactly `character_id` plus four required capability sections, each
with its own `known | unknown | not_applicable` status so Unknown is never
collapsed into zero/empty:

- **`hp`** — when `known`, whole non-negative `current` / `maximum` with
  `current <= maximum` (the cross-field inequality is enforced by the
  engine-owned route, not by JSON Schema) plus optional `temporary` (current
  state, deliberately not capacity-bounded);
- **`hit_dice`** — when `known`, one or more distinct pools of `{ pool_id,
  die_faces, current, maximum }`; `die_faces` is bounded to `4, 6, 8, 10, 12`;
- **`spell_slots`** — when `known`, distinct pools keyed by `pool_id` (never by
  `slot_level`, so multiple pools at the same spell level are representable)
  with `slot_level` 1..9, `current`, `maximum` and bounded `recharge_on`;
- **`resources`** — when `known`, limited counters of `{ resource_id, label,
  current, maximum, recharge_on }`.

When a section is `unknown` or `not_applicable`, its payload is forbidden.
`recharge_on` is a unique subset of `short_rest` / `long_rest`; an empty list is
legal for a non-Rest-based generic tracked counter (POST-EV2-10 owns the Rest
rules it acts on). Stable local IDs are lower-slug and unique within a record
(enforced by the runtime route). Records are canonically ordered so equivalent
logical absolute targets compare stably.

The schema enforces structural shape, whole non-negative integers, bounded
vocabularies, stable local IDs and `uniqueItems`. The engine-owned route
(`public.mutate_character_mechanics(...)`) additionally enforces `current <=
maximum`, unique stable IDs and exactly one record per character; the supported
service-only read is `public.dm_runtime_read_character_mechanics(...)`. See
`docs/POST-EV2-9-CHARACTER-VITALS-RESOURCES.md` and
`tests/post_ev2_9/test_character_vitals_resources.py` for proof. No real RHC
character-mechanics record is seeded by BUILD proof; the schema layer is
exercised with synthetic records only. This record deliberately does not model
class/subclass/feat/spell selection, combat damage/healing, death saves,
conditions, Rest lifecycle or item-owned charges.

## character_rests.schema.json (POST-EV2-10)

The bounded per-character Rest lifecycle record for one tracked
`character:<slug>`. One character owns exactly one Rest record; a shared camp
scene contains several independent records, never one shared mechanical Rest
record. It carries only Rest lifecycle state and authoritative elapsed-time
anchors — **never** HP, Hit Dice, spell slots or feature charges, which POST-EV2-9
owns. Progress is derived from RT02 elapsed campaign minutes plus this bounded
state; no minute-by-minute ticks are persisted.

A record is exactly `character_id` + `schema_version` + `status`, `rest_kind`,
`started_at_elapsed_minutes`, `required_minutes`,
`completed_at_elapsed_minutes`, `last_long_rest_completed_at_elapsed_minutes`,
`interruptions` and `short_benefit_granted`. The lifecycle is `idle ->
active(short|long) -> completed | interrupted`: a Short Rest interruption ends it
as `interrupted` with no benefits, while a Long Rest interruption keeps it
`active` and adds 60 required minutes per `interruptions` entry (at most 1000,
matching the engine-owned SQL normalizer). A Short Rest
requires 60 required minutes; a Long Rest requires 480 plus 60 per interruption.
Anchors are engine-derived from authoritative published RT02 elapsed time and are
never caller-invented wall-clock values; JSON Schema enforces structural shape and
the engine-owned route (`public.mutate_character_rest(...)`) enforces the
cross-field rules (required-duration arithmetic, exactly one record per
character). The supported service-only read is
`public.dm_runtime_read_character_rest(...)`. See
`docs/POST-EV2-10-CHARACTER-REST.md` and
`tests/post_ev2_10/test_character_rest.py`. No real RHC Rest record is seeded by
BUILD proof.

## intake_candidate.schema.json (CI-01)

The Canon Intake candidate contract: the smallest repository-side envelope
for *material extracted from a source and awaiting human review*. A candidate
is not canon, runtime, or published truth and carries no content payload.

- `candidate_id` — required stable typed identity (`candidate:<slug>`),
  unique across a validated batch (`scripts/validate_intake_candidates.py`).
  The `candidate:` prefix is deliberately outside the eight entity types.
- `summary` — required non-blank description of the extracted material.
- `status` — exactly `extracted` or `classified`. No approval, publication,
  or canon state exists in CI-01: approval authority stays with the human DM
  and later Canon Intake gates (CI-02+).
- `source` — required attachment with required non-blank `kind` and
  `reference`, plus optional non-blank `locator` / `origin` / `label`. No URL
  registry, publisher catalogue, or source verification.
- `provenance` — the exact HB-01 classification vocabulary
  (`official | homebrew | adapted | unknown`), state-conditional: forbidden
  while `extracted` (classification not yet performed), required once
  `classified` (an explicit classification event happened; `unknown` stays a
  legal explicit outcome).

See `docs/CI-01-CANDIDATE-CONTRACT.md` and
`tests/test_intake_candidate_validation.py` (inline fixtures only; no
fixture directory is authorized in CI-01).

## intake_decision.schema.json (CI-02)

The Canon Intake decision contract: a sidecar record of one **explicit
human approve/reject decision** over one CI-01 classified candidate. The
decision ledger never changes candidate state or canon/runtime truth.

- `decision_id` — required stable typed identity (`decision:<slug>`),
  unique across one validated decision set
  (`scripts/validate_intake_decisions.py`). Stable identity is what makes
  deterministic duplicate/replay detection possible at the contract layer;
  duplicate `decision_id` fails closed.
- `candidate_id` — required reference to an existing CI-01 candidate using
  the exact `candidate:<slug>` grammar. Only a `classified` candidate is
  decision-eligible; the validator resolves every reference against the
  CI-01 candidate batch (validated by the CI-01 contract first) and fails
  closed on unknown candidates and on decisions against `extracted`
  candidates. The decision never mutates the referenced candidate.
- `outcome` — required, exactly `approved` or `rejected`. Both outcomes are
  equally non-canon: approved candidates stay non-canon until CI-04
  promotion succeeds, and rejected candidates cannot be treated as truth.
- `authority` — required, exactly `human`. Approval authority is explicitly
  human; AI may propose, never decide.
- `decided_by` — required non-blank reference to the accountable human
  authority (for example the DM).
- `note` — optional non-blank human note/reason.
- `batch_label` — optional non-blank, **non-authoritative** grouping/batch
  label. A grouped review is only a container for multiple independent
  candidate decisions: it inherits no outcome, imposes no uniform outcome,
  and mixed approved/rejected outcomes in one labeled group are legal.
  There is no "approve all" semantics.

Set-level law (enforced by the validator, all fail closed): duplicate
`decision_id` across the set fails; more than one decision for the same
`candidate_id` fails, whether the outcomes agree (replay) or conflict. There
is no durable cross-run idempotency storage in CI-02 — contract-level stable
IDs plus deterministic rejection are the owned replay-safety boundary. No
SQL/runtime persistence, collision resolution, promotion route, or second
mutation path exists here.

See `docs/CI-02-DECISION-LEDGER.md` and
`tests/test_intake_decision_validation.py` (inline fixtures only; no
fixture directory is authorized in CI-02).

## intake_candidate_material.schema.json (CI-02.1)

The Canon Intake candidate material contract: a **sidecar envelope** keyed to
one CI-01 candidate that preserves the actual candidate material plus enough
proposed-target intent and base-publication context for the later CI-03
collision/re-import checks. The CI-01 candidate schema stays untouched — the
envelope is separate, never a new field on the candidate.

- `candidate_id` — required reference to an existing CI-01 candidate using
  the exact `candidate:<slug>` grammar. The envelope references and never
  rewrites the candidate; the validator resolves every reference against the
  CI-01 candidate batch (validated by the CI-01 contract first) and fails
  closed on unknown candidates and on an invalid candidate batch. Exactly
  one envelope per candidate per validated set; a duplicate envelope fails
  closed (`scripts/validate_intake_candidate_material.py`).
- `material_type` — required non-blank free-form label for the material's
  type/kind, sufficient for later routing/comparison. No type taxonomy is
  declared law (free-form by design, like `source.kind` in CI-01).
- `material` — required non-blank actual candidate material/payload: the
  extracted content itself, preserved outside the CI-01 candidate identity
  envelope. Free-form text by design; CI-02.1 owns no domain-specific
  payload schema.
- `proposed_target` — optional proposed target/owner intent (`kind` +
  `reference` required, optional `label`; all non-blank). Proposed intent is
  **not** reconciled owner truth and never becomes authority by being
  recorded; an unknown target stays explicitly absent, never guessed.
- `base_publication` — optional base-publication pin for later
  stale/re-import context: a non-negative RT01 `generation` (0 is the empty
  pre-activation world) and/or the exact 40-hex published checkpoint commit
  SHA as `git_ref`. At least one pin is required when the object is present;
  unknown stays absent, never inferred.

Sidecar law (all fail closed): the payload is candidate material, not
authoritative state — non-canon and non-runtime, no approved/rejected/
published/canon state, no collision/re-import detection (CI-03), no
promotion (CI-04), and no persistence route. Source/provenance stay owned by
the referenced CI-01 candidate and are deliberately not duplicated into the
envelope.

See `docs/CI-02-1-CANDIDATE-MATERIAL.md` and
`tests/test_intake_candidate_material_validation.py` (inline fixtures only;
no fixture directory is authorized in CI-02.1).

## intake_collision.schema.json (CI-03)

The Canon Intake collision contract: the deterministic collision classifier
result comparing one **human-approved** CI-01 candidate (with its CI-02.1
material envelope) against one trusted caller-supplied authoritative
current-target/publication observation. CI-03 classifies; it never mutates.

- `collision_id` — required stable typed identity (`collision:<slug>`),
  unique across one validated collision set; a duplicate fails closed
  (`scripts/validate_intake_collisions.py`).
- `candidate_id` — required reference to an existing CI-01 candidate using
  the exact `candidate:<slug>` grammar. At most one collision result per
  candidate per validated set; a duplicate result for the same candidate
  fails closed. Only a candidate with an explicit human `approved` CI-02
  decision is eligible for collision clearance; anything else fails closed.
- `observation` — required; exactly one trusted caller-supplied observation
  embedded in the record. Its `target` (`kind` + `reference`) is bound to the
  referenced material envelope's `proposed_target` and must match it exactly,
  so one observation cannot clear multiple different targets; it is forbidden
  when the envelope proposes none. `target_state` is exactly `absent`,
  `present`, or `unknown`. Optional `target_identity` carries caller-known
  current publication identity (`generation` non-negative integer and/or
  40-hex lowercase `git_ref`) and is strictly validated: booleans, malformed
  numeric types, bad SHAs, empty objects, and unknown fields fail closed.
  Optional `current_material` is the current target material, allowed only
  for a present target and omittable (classifying `unresolved`) when the
  caller cannot retrieve it.
- `result` — required closed vocabulary: exactly `clear`, `duplicate`,
  `stale`, `conflict`, or `unresolved`. The validator recomputes the
  classification deterministically and refuses any declared result that does
  not match or any value outside the vocabulary. Only `clear` is
  promotion-eligible; `duplicate`/`stale`/`conflict`/`unresolved` all fail
  closed for CI-04 promotion.
- `reason` — required; it must equal the deterministic reason the classifier
  computes for the same evidence (authoritative evidence trail, not
  free-form prose; a mismatched caller reason fails closed).
- `note` — optional non-blank human note; logistics metadata only.

Classification precedence (exact comparison only; no normalization, no
fuzzy/AI equivalence): the observation must be bound to the candidate's
`proposed_target` or it fails closed; known base-publication pin conflicting
with known current publication classifies `stale` before any content
comparison; absent `proposed_target`, unknown target state, or present target
with unavailable current material classifies `unresolved`; target known
absent classifies `clear`; exact material match classifies `duplicate`;
differing material classifies `conflict`. Re-import is handled through the
same target/base evidence — no separate import-history store is built (CI-04
receipts may later provide durable lineage).

The caller (CI-04/later integration, never CI-03) is responsible for
gathering authoritative evidence from the correct repository/runtime owner:
no repository crawling, no Supabase networking, no semantic comparison, no
conflict resolution, no promotion, no canon/runtime mutation, and no second
truth store exists here. See `docs/CI-03-COLLISION-DETECTION.md` and
`tests/test_intake_collision_validation.py` (inline fixtures only; no
fixture directory is authorized in CI-03).

## intake_promotion.schema.json (CI-04)

The Canon Intake promotion instruction: a deterministic plan that binds one
CI-01 candidate, its explicit CI-02 human approval, its CI-02.1 material
envelope, and its CI-03 collision result into a legal owner route for the later
authoritative write. An instruction is intent, not a write — it carries no
persistence mechanism, no SQL/Git executor, and no second generation counter.

- `promotion_id` — required stable typed identity (`promotion:<slug>`),
  set-unique; a duplicate fails closed, as does a second instruction for the
  same candidate (`scripts/validate_intake_promotions.py`).
- `candidate_id` — required reference to a CI-01 candidate using the exact
  `candidate:<slug>` grammar. Only a `classified` candidate with a valid
  explicit human `approved` CI-02 decision and a CI-03 `clear` result is
  promotion-eligible; source/provenance lineage stays attached through
  `candidate_id` and is never duplicated here.
- `route` — required closed vocabulary: exactly `runtime_save` (existing RT01
  Save Gateway authority) or `repository_canon` (existing repository-
  authorized canon owner path). Unknown routes fail closed and the route is
  never inferred from material prose.
- `resolved_target` — required explicit owner/target (`kind` + `reference`);
  it must equal the referenced CI-02.1 envelope's `proposed_target` exactly, so
  a proposed target cannot be silently rerouted.
- `material_type` — required linkage equal to the enrolled envelope's
  `material_type`.
- `decision_id` / `collision_id` — required references that must resolve to a
  decision and collision result bound to the same `candidate_id`; the collision
  result must be exactly `clear`.
- `expected_collision_result` — required, exactly `clear`.
- `note` — optional non-blank human note.

## intake_promotion_receipt.schema.json (CI-04)

The Canon Intake promotion receipt: the record of what authoritative route an
instruction invoked and the authoritative read-back evidence that route
returned. A receipt is evidence, not authority.

- `receipt_id` — required stable typed identity (`receipt:<slug>`), set-unique;
  a duplicate fails closed.
- `promotion_id` / `candidate_id` / `route` — required references that must
  resolve to a valid instruction in the same set; the candidate and route must
  equal that instruction's values (a receipt records the route actually used).
- `outcome` — required, exactly `success` or `failure`; there is no third
  outcome.
- `evidence` — authoritative verification/read-back evidence. Required for a
  success receipt and forbidden for a failure receipt. It is route-conditional:
  `runtime_publication` needs a positive `generation` plus the exact confirmed
  40-hex `git_ref`; `repository_commit` needs the exact 40-hex repository
  `commit`. `confirmed` is exactly `true`. A success with no confirmed
  read-back, and a failure carrying success evidence, both fail closed, so
  false success is impossible.
- Replay/idempotency fails closed: duplicate `receipt_id` and more than one
  success receipt for the same promotion both fail.

Only a classified, explicitly human-approved, CI-03-`clear` candidate can form
an instruction; runtime mutations route only through the existing RT01/SAVE
authority and repository mutations only through the existing repository-
authorized path. CI-04 is a bridge, never a second publisher, and promotes no
real RHC campaign candidate. See `docs/CI-04-PROMOTION-BRIDGE.md` and
`tests/test_intake_promotion_validation.py` (inline fixtures only; no fixture
directory is authorized in CI-04).
