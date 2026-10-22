# EV2-14 — Owner-Local Knowledge / Secrets Model

EV2-14 evolves the EV2-03 knowledge box into the smallest coherent owner-local
knowledge model. It distinguishes confirmed knowledge, belief/suspicion,
reusable world-fact references and concise local assertions, and it gives the
model safe human-reader exposure semantics — without automatic propagation,
runtime mutation, or a second truth system.

It is an in-place evolution of `schemas/knowledge.schema.json`, not a new
subsystem, and it carries no real RHC data: proof is synthetic only.

## Mental model

For every piece of information, RHC answers three independent questions, and no
answer implies another:

1. **Is it true in the world?** — owned by repository canon; reusable truth
   lives in `knowledge/facts.json`.
2. **Who knows/believes/suspects it in-world?** — owned by each knower's own
   Entity V2 knowledge record.
3. **May the human player/reader see it?** — owned by the underlying
   information's `META`/`NON_META` exposure classification
   (`knowledge/META_NON_META_PROTOCOL.md`).

Core pins, preserved by construction:

- **Knowledge belongs to the knower.** A record answers only "what does this
  `entity_id` know, believe or suspect?" — never "what is true?" and never
  "who else knows it?"
- **Truth ≠ epistemic state ≠ reader visibility.**
- **Unknown stays Unknown.** The EV2-03 box-level tri-state
  (`known | unknown | not_applicable`) is unchanged; `unknown`/`not_applicable`
  still forbid `entries`.
- **No automatic propagation.** A fact existing in `facts.json`, DM knowledge,
  another entity's knowledge, party membership, NON_META visibility or a
  Beyond the Heroes publication never grants knowledge to anyone.
- **Belief/suspicion does not create world truth.** Misunderstandings and
  hunches stay local assertions; they never receive a canonical `fact_id`
  merely because a character believes them.
- **The EV2-03 scalar player-agency boundary survives.** Local assertion
  values are plain scalars, so structured action/directive payloads cannot be
  stored as knowledge data.

## Record shape

Owner-local, unchanged at box level:

- `entity_id` — the knower;
- `status` — `known | unknown | not_applicable`; `entries` (non-empty) only
  when `known`.

Each entry is one of exactly two content modes:

### A. Reusable fact reference

```json
{
  "topic": "ritual_inscription_truth",
  "epistemic_status": "confirmed",
  "fact_id": "F012",
  "note": "Learned directly from the ritual inscription.",
  "source": "session_canon"
}
```

- Use when the knower's information corresponds to an established reusable
  world fact. The knower references truth instead of duplicating it.
- `visibility` is structurally forbidden here: reader exposure of the
  **referenced fact itself** is inherited from that fact at read time and can
  never drift from the fact owner through a copied classification.
- `topic`, `note`, and `source` remain knower-local authoring/provenance
  annotations. They may contain META context even when the referenced fact is
  `non_meta`, so a player-facing fact projection MUST NOT expose those local
  annotations by default. A player-facing projection of a fact reference
  resolves and exposes only the referenced fact's player-safe content; the
  full entry remains available to DM/internal reads.
- A knower may hold an established fact with `epistemic_status: belief` or
  `suspicion` when it does not yet treat it as established for itself; the
  fact's own truth is unaffected. Belief/suspicion entries never promote the
  fact or the knower's stance into world truth.

### B. Concise local assertion

```json
{
  "topic": "crystal_ball_private_theory",
  "epistemic_status": "belief",
  "value": "the crystal ball listens when spoken to",
  "visibility": "meta"
}
```

- Use when the information is too specific, trivial or subjective to deserve a
  reusable `fact_id`, or when the knower believes/suspects something that is
  not established world truth.
- `value` is a plain scalar (string/number/boolean) — the player-agency
  structural boundary from EV2-03.
- `visibility` (`meta | non_meta`) is **required**, because the assertion
  itself is the underlying information: there is no other owner to inherit
  exposure from, and an unclassified assertion is not admitted.

Optional concise `note` / `source` are allowed on either shape only when
actually established; blank values are rejected. On a fact-reference entry,
`topic`, `note`, and `source` are knower-local internal annotations and
are not included in the default player-facing fact projection.

`epistemic_status` is exactly `confirmed | belief | suspicion` and describes
only this knower's stance. The EV2-03 entry-level `status` tri-state is
intentionally replaced: entries are statements this knower holds, not
independently unknown topic slots — if the knower does not know, there is no
entry.

Rejected by construction: an entry with both `fact_id` and `value`; an entry
with neither; a missing `epistemic_status`; an unsupported epistemic state; a
blank topic or `fact_id`; a copied `visibility` on a fact reference; a missing
`visibility` on a local assertion; structured (object/array) values; duplicate
exact entries; duplicate topics within one record.

There is no per-entry knowledge identity. Runtime mutation identity is not
designed pre-emptively; a later real consumer Mission owns writes.

## Safe read semantics (durable contract, not a runtime API)

- **DM/internal knowledge read** may inspect all entries of the selected
  knower's record.
- **Player-facing knowledge read** may expose only information whose underlying
  content is NON_META:
  - for a fact-reference entry, resolve exposure from the referenced fact in
    `knowledge/facts.json`. If that fact is `non_meta`, the default
    player-facing projection exposes the referenced fact's player-safe content
    only. It does **not** expose the knower-local `topic`, `note`, or
    `source` annotations, because those annotations have no independent
    player-facing classification and may contain META context;
  - local assertions use their own `visibility`. Their entry content is the
    underlying information being classified.
- Reading a player-visible fact never implies that any character knows it.
- Querying "what does Madma know?" reads Madma's owner-local record only.
- Querying "what may the player see?" is a separate exposure question.
- Beyond the Heroes may surface reader-visible world truth even when no hero
  knowledge record references it.

## Acceptance scenario: Beyond the Heroes

A BTH event may be true RHC canon, deliberately exposed to human readers by
the anthology, and still unknown to every hero. In the EV2-14 model this needs
no special machinery: the event exists as a reusable fact (true, `non_meta` if
reader-visible), and simply **no hero knowledge record references its
`fact_id`** unless an explicit knower-owned event establishes that knowledge.
Publication is reader exposure as an artifact; it is never a knowledge
mutation. See `knowledge/META_NON_META_PROTOCOL.md` §2b and the synthetic
proofs `test_ev214_bth_reader_visible_event_does_not_create_hero_knowledge`
and `test_ev214_fact_existence_does_not_create_knower_record` in
`tests/test_state_knowledge_inventory_validation.py`.

## Legacy compatibility

The legacy NPC knowledge shape in `npc/npc_state.json`
(`npc_confirmed_knowledge`, `npc_unconfirmed_beliefs`, `observer_knowledge`,
`protected_secrets_known`) remains readable historical/legacy campaign data
under `npc/NPC_SYSTEM.md`. It is not a second equal Entity V2 authority, and
EV2-14 performs no destructive migration. Key interpretations:

- `observer_knowledge` is subject-centered storage for observer-owned
  knowledge: knowledge about subject B conceptually belongs under observer A
  and must not be blindly carried forward under the observed subject.
- `protected_secrets_known` should normally reduce to ordinary knower-owned
  knowledge of underlying META information; it is not a separate future secret
  authority collection.

Real records and any safe legacy migration belong to a later intake gate.

## Scope and non-goals

EV2-14 does not add: runtime/Supabase knowledge mutation or persistence; RAG,
embeddings, search or retrieval; BTH persistence/SAVE integration; automatic
discovery propagation; a repository-wide `META`/`NON_META` rename (current
names are compatibility exposure terminology; see
`knowledge/META_NON_META_PROTOCOL.md` §2a); UI/frontend code; homebrew
provenance; or real-data migration. Later owners own all of these.

## Proof

`pytest tests/test_state_knowledge_inventory_validation.py -v` pins the schema
lock and the synthetic acceptance scenarios;
`python scripts/validate_entities.py --schema schemas/knowledge.schema.json
tests/fixtures/knowledge/valid` proves the fixture batch; the fixture layout
is described in `tests/fixtures/knowledge/README.md`.
