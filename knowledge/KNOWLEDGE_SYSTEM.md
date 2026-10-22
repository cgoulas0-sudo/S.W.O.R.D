# Rolling High Club — Knowledge System

> Local operating authority for reusable world facts and character knowledge inside the Rolling High Club repository.

This system is subordinate to `PROJECT_PRIMER.md` and uses `knowledge/META_NON_META_PROTOCOL.md` for visibility handling.

## 1. Purpose

The knowledge layer separates four things that must never be confused:

1. **World truth** — what is actually true in RHC canon.
2. **Character knowledge** — what a specific NPC, PC, group or faction actually knows.
3. **Belief / suspicion** — what a character thinks may be true but has not confirmed.
4. **Visibility** — whether information is META or NON_META for player-facing use.

The repository may know a canonical fact while every character in the campaign remains unaware of it. Likewise, a fact may be Canon but remain META until legitimately revealed.

For the durable Entity V2 knowledge record contract (schema, entry shapes, epistemic vocabulary and read semantics), see `docs/EV2-14-LOCAL-KNOWLEDGE.md` and `schemas/README.md`; this document owns the campaign-level knowledge law the contract enforces.

## 2. Canonical Facts

Reusable world facts are stored in `knowledge/facts.json`.

A fact should receive a stable `fact_id` when it is useful across multiple NPCs, locations, items or campaign records. Do not create fact IDs for trivial prose that will never need to be referenced again.

Each fact may contain:

- `fact_id`
- `title`
- `statement`
- `status`
- `domain`
- `visibility`
- `related_entities`
- `source_status`
- `source_note`
- optional reveal metadata

Recommended `source_status` values:

- `rhc_canon`
- `explicit_dm_canon`
- `official_forgotten_realms`
- `official_dnd_rules`
- `mixed_rhc_and_official`

A fact entry records truth and visibility, not who knows it.

If `visibility` is absent, treat the fact as META according to the repository-wide safe default.

## 3. META / NON-META

Use `knowledge/META_NON_META_PROTOCOL.md` as the repository-wide authority.

- `meta` means the information is not safe for ordinary player-facing disclosure.
- `non_meta` means the information is safe to expose in player-facing use.

Visibility does not replace Canon/Planned/Brainstorm state and does not replace Who-Knows-What.

A reveal may change visibility from `meta` to `non_meta` without changing the truth of the fact.

## 4. Who-Knows-What

Who-knows-what remains local to the character or entity that possesses the knowledge.

Knowledge always belongs to the knower: a knowledge record answers only "what does this `entity_id` know, believe or suspect?" — never "what is true?" and never "who else knows it?".

### Entity V2 knowledge records (EV2-14)

New Entity V2 knowledge records follow `schemas/knowledge.schema.json` (EV2-14) and `docs/EV2-14-LOCAL-KNOWLEDGE.md`. Each entry holds exactly one content mode:

- **Reusable fact reference** — `{ "topic", "epistemic_status", "fact_id", optional "note"/"source" }`. The knower references the established reusable fact instead of duplicating it; reader visibility of the referenced fact is inherited from that fact at read time and is never copied into the knower record. The entry's `topic`, `note`, and `source` remain knower-local internal annotations and are not part of the default player-facing fact projection.
- **Concise local assertion** — `{ "topic", "epistemic_status", scalar "value", "visibility" , optional "note"/"source" }`. Used when the information is too specific/trivial/subjective to deserve a reusable `fact_id`, or when the knower believes/suspects something that is not established world truth. The assertion itself is the underlying information, so it carries its own META/NON_META `visibility`.

`epistemic_status` is exactly `confirmed | belief | suspicion` for this knower only. Misunderstandings and false beliefs stay local assertions with `belief` or `suspicion`; they do not receive a canonical `fact_id` solely because a character believes them, and belief/suspicion never promotes into world truth.

Example Entity V2 fact-reference entry:

```json
{
  "topic": "ritual_inscription_truth",
  "epistemic_status": "confirmed",
  "fact_id": "F012",
  "note": "Learned directly from the ritual inscription."
}
```

### Legacy NPC-local knowledge shape

For legacy NPCs, `npc/npc_state.json` remains readable according to `npc/NPC_SYSTEM.md`, using its own `npc_confirmed_knowledge` / `npc_unconfirmed_beliefs` / `observer_knowledge` / `protected_secrets_known` collections and the legacy `knowledge_level` naming. That shape is historical/legacy campaign data, not a second Entity V2 knowledge authority; EV2-14 performs no destructive migration of it. See `npc/NPC_SYSTEM.md` for the forward-authority interpretation.

### Safe read semantics (EV2-14)

Reading knowledge and reading exposure are two separate questions:

- **DM/internal knowledge read** — may inspect all entries of the selected knower's record.
- **Player-facing knowledge read** — may expose only underlying information that is NON_META. For a fact-reference entry, resolve exposure from the referenced fact in `knowledge/facts.json`; when that fact is `non_meta`, expose the referenced fact's player-safe content only and keep the knower-local `topic`, `note`, and `source` internal by default. Local assertions use their own `visibility`.

Reading a player-visible fact never implies that any character knows it. Querying "what does Madma know?" reads Madma's owner-local record only. Querying "what may the player see?" is a separate exposure question. Beyond the Heroes may surface reader-visible world truth even when no hero knowledge record references it.

## 5. Knowledge Is Local

Never propagate knowledge automatically.

A character knows a fact only when an authoritative source establishes that they learned it, already knew it, directly perceived it, or could unquestionably infer it from information they possess.

When inference is uncertain, store it as belief/suspicion or leave it unknown.

The following are not valid reasons to grant knowledge:

- the DM knows it;
- another NPC knows it;
- it exists in `facts.json`;
- it is NON_META;
- it would be convenient for the story;
- it is common knowledge unless the setting/source actually supports that assumption.

## 6. Locations and Facts

Location files may reference relevant `fact_id` values for durable truths about the place.

Location-specific secrets remain canonical facts only if they are actually established as true. Their META/NON_META state is handled separately from who knows those secrets.

## 7. External Lore

Official Forgotten Realms or D&D information may be stored as a fact when it materially helps the RHC knowledge base.

Always distinguish published lore from table-established RHC canon through `source_status` and `source_note`.

External lore supplements RHC canon; it does not silently overwrite an explicit RHC ruling.

External publication does not automatically make information NON_META inside the campaign. Use the visibility protocol and actual table knowledge.

## 8. Update Discipline

Create or update a canonical fact only when the underlying truth is supported by an authoritative RHC source, an explicit DM canon ruling, or clearly identified official material.

When new session information changes what a character knows, update the relevant character state rather than rewriting the canonical fact unless the truth itself changed or was corrected.

When a secret becomes legitimately revealed, update its visibility where appropriate instead of duplicating it as a second fact.

The goal is a compact graph of reusable truth, controlled visibility and local knowledge — not an exhaustive database of every sentence ever spoken.
