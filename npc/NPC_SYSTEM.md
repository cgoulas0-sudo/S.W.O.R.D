# Rolling High Club — NPC System

> Local operating authority for the ordinary NPC subsystem of the Rolling High Club repository.

This document governs how ordinary NPC identity, mutable state, knowledge, relationships and combat references are stored and resolved inside this repository. It is subordinate to `PROJECT_PRIMER.md`. META/NON-META visibility follows `knowledge/META_NON_META_PROTOCOL.md`.

Major recurring villains use the separate flat root `villain/` domain. No NPC file in this repository should depend on another campaign repository or another project's primer in order to be interpreted correctly.

## 1. NPC Layer

The RHC NPC layer separates durable identity from mutable state and combat mechanics.

| Need | Source |
| --- | --- |
| Permanent identity, biography, personality, voice, motives and durable history | `npc/profiles/` |
| Current mutable facts: location, status, assignment, relationship movement, local knowledge and currently available equipment | `npc/npc_state.json` |
| Exact combat mechanics for ordinary combat-capable NPCs | `npc/battle/` |
| Major recurring villain packages | `villain/` |
| Reusable canonical world facts referenced by NPC knowledge | `knowledge/facts.json` |
| Knowledge-locality and fact-reference behavior | `knowledge/KNOWLEDGE_SYSTEM.md` |
| META/NON-META visibility behavior | `knowledge/META_NON_META_PROTOCOL.md` |
| Templates for creating new ordinary NPC entries | `npc/NPC_PROFILE_TEMPLATE.md`, `npc/NPC_STATE_TEMPLATE.json`, `npc/NPC_BATTLE_TEMPLATE.md` |

The templates define structure. This file defines ordinary NPC behavior and interpretation.

## 2. Authority, Canon and Visibility

All NPC information must obey `PROJECT_PRIMER.md`.

Only established RHC canon, explicit Dungeon Master rulings, and clearly identified official D&D / Forgotten Realms material may be treated as factual sources. Missing information remains Unknown or null. Do not invent canon to complete a template.

Planned and Brainstorm material must remain outside canonical NPC state unless the Dungeon Master explicitly promotes it to Canon or it becomes established through play.

META/NON-META is independent from canon status. Hidden biography, motives, secrets, battle mechanics or unrevealed relationships may be Canon and still META.

**Unclassified legacy NPC information defaults to META for player-facing use until reviewed.**

## 3. Permanent Profile

A permanent profile answers: **Who is this NPC?**

Store here:

- identity and affiliations;
- durable biography and history;
- appearance that is actually established;
- personality, values, fears and flaws;
- voice and behavioral principles;
- durable motivations;
- durable relationship history;
- permanent combat capability classification and the pointer to a battle reference;
- source notes that distinguish published material, established RHC facts, user-defined facts and DM-authored mechanical choices.

A permanent profile may contain both META and NON_META sections. Use explicit visibility markers for the smallest practical section when needed. Do not assume that information is player-known merely because it appears in a profile.

Do not store temporary location, pending actions, current equipment availability, temporary injuries, current relationship mood or current knowledge here.

## 4. Mutable NPC State

`npc/npc_state.json` answers: **What is true about this NPC right now?**

Store only established mutable facts:

- current location and status;
- current goal or assignment when established;
- availability;
- pending actions;
- current combat readiness;
- armor, shield, weapons, focus or other equipment actually worn, carried or deployed now;
- current relationship movement;
- local knowledge and beliefs;
- continuity timestamps / update source.

If a current fact is not established, use `null`, `Unknown`, an empty collection, or the relevant unknown enum. Never infer a current fact from a permanent profile merely because it would be plausible.

### Relationship structure

Relationships are not hardcoded to any single character. Use the generic `relationships` object, keyed by the relevant character, NPC, faction or entity slug.

A relationship entry may contain `current_state`, `trend`, and `last_change`.

Durable relationship history belongs in the permanent profile. Only the current movement/state belongs in mutable NPC state.

### Knowledge structure

Knowledge is local to the character who possesses it.

Use:

- `npc_confirmed_knowledge` for facts the NPC actually knows;
- `npc_unconfirmed_beliefs` for suspicions, assumptions or beliefs;
- `observer_knowledge` for established knowledge held by a specific PC, NPC, group or faction about this NPC, keyed by observer slug;
- `protected_secrets_known` only for secrets the NPC is established to know.

When the known information corresponds to a reusable canonical fact in `knowledge/facts.json`, prefer a fact-reference object such as:

```json
{
  "fact_id": "F012",
  "knowledge_level": "confirmed",
  "note": "Learned directly from the ritual inscription.",
  "source": "session_canon"
}
```

Concise local prose is still acceptable when the information is too specific or trivial to deserve a reusable fact ID.

### EV2-14 forward authority vs legacy NPC-local knowledge shape

For **Entity V2 knowledge records**, `schemas/knowledge.schema.json` (EV2-14) and `docs/EV2-14-LOCAL-KNOWLEDGE.md` are the forward authority: entries are owner-local epistemic statements (`confirmed | belief | suspicion`) that hold either a reusable `fact_id` reference or a concise local scalar assertion with its own `visibility`. New Entity V2 records must follow that contract.

The `knowledge_boundaries` collections in `npc/npc_state.json` (`npc_confirmed_knowledge`, `npc_unconfirmed_beliefs`, `observer_knowledge`, `protected_secrets_known`) remain **readable legacy NPC-local shapes**, not a second equal Entity V2 knowledge authority. Interpretation for any future interpretation/migration (EV2-14 itself performs none):

- `npc_confirmed_knowledge` maps semantically to owner-local confirmed knowledge.
- `npc_unconfirmed_beliefs` maps to belief/suspicion only where the legacy content establishes which.
- `observer_knowledge` is subject-centered storage for observer-owned knowledge: knowledge about subject B conceptually belongs under observer A's own record. It must NOT be blindly carried forward under the observed subject, and it is not Entity V2 owner-local authority.
- `protected_secrets_known` is not a separate secret database and must not survive as a new first-class Entity V2 collection; it should normally reduce to ordinary knower-owned knowledge of underlying META information.

No destructive migration of `npc/npc_state.json` occurs in EV2-14; real-record intake and any safe migration belong to a later gate.

Visibility belongs to the underlying information, not to the fact that a particular NPC knows it. An NPC may know a META fact. NON_META does not automatically grant knowledge to any character.

Do not copy a secret from one character to another without an established in-world reason. Do not use omniscient campaign knowledge as NPC knowledge. The existence of a fact in `knowledge/facts.json` never grants that knowledge automatically.

## 5. Combat References

A battle reference answers: **How is this NPC resolved when mechanics matter?**

Use current D&D 5.5e / revised fifth-edition material when an appropriate direct official source exists. When the Dungeon Master has explicitly authorized a campaign-specific NPC build, identify it as `rhc_build` or a more specific RHC source status such as `user_defined_rhc_cr_build`.

Preferred generic source statuses:

- `official_published_current`
- `legacy_official_fallback`
- `rhc_build`
- `user_defined_rhc_cr_build`
- `none`

Do not silently combine incompatible stat blocks or rules generations.

**Battle references are META by default** unless the Dungeon Master explicitly marks specific information NON_META.

The battle reference stores baseline mechanics and permanent combat identity. The live state decides what equipment is actually worn, carried or deployed when a scene begins. Never grant an item retroactively merely because it appears on a battle reference.

Combat doctrine is a tactical default, not a script. Current goals, fear, loyalty, terrain, injury, relationships and moral limits may change the NPC's decisions naturally.

## 6. Villain Routing

Major recurring villains live in the top-level `villain/` domain, not inside `npc/`.

The villain root is intentionally flat:

- `villain/<villain_slug>.md` — self-contained recurring villain card;
- `villain/<villain_slug>_lair.md` — optional flat companion file if a lair needs substantial reusable mechanics.

Do **not** create `villain/<villain_slug>/` nested subdomains and do not recreate `npc/villain/`.

Villain files are META by default. Mutable villain facts that can change independently between scenes may still use `npc/npc_state.json` when the villain is tracked as a current in-world entity. The static villain card does not overwrite live state.

## 7. Natural NPC Resolution

When an NPC acts:

1. Read the relevant permanent profile, or the relevant top-level villain file for a major villain.
2. Read `npc/npc_state.json` for established mutable state when a tracked entry exists.
3. Resolve referenced `fact_id` values through `knowledge/facts.json` only when needed.
4. Apply the knowledge boundary: the NPC may act only on what they know, believe or can reasonably perceive/infer in-world.
5. Weigh immediate circumstances, obligations, relationships, alignment, personality, goals, fears and moral limits.
6. Resolve a reaction that is consistent with the character without forcing a predetermined outcome.
7. If combat begins, use the battle reference or villain combat chassis together with the actual live equipment/readiness state.

META information may preserve consistency internally but must not be exposed in normal player-facing use until legitimately revealed.

Reputation, alignment and combat doctrine are inputs, not overrides. They never erase established history, duty, secrets, fear, relationships or player-driven consequences.

## 8. Update Discipline

Permanent profile changes require a durable established fact.

Mutable state changes may come from `quicksave`, `dm_meta`, `finalized_canon`, or `explicit_user_canon_update`.

Use the source that actually established the fact. An uncommitted DM idea is not an NPC fact.

When a temporary fact becomes durable history, it may be promoted from state into the permanent profile while preserving the appropriate current state separately.

When a newly established piece of knowledge is useful across several entities, create or reuse a canonical `fact_id` and point the relevant character knowledge entries to it rather than duplicating long prose.

When hidden information becomes legitimately revealed, update its META/NON_META classification without duplicating the fact or rewriting unrelated NPC knowledge.

## 9. Template Routing

All NPC templates and generated NPC files in this repository must follow this document for subsystem behavior.

- `NPC_PROFILE_TEMPLATE.md` defines ordinary NPC profile shape only.
- `NPC_STATE_TEMPLATE.json` defines mutable-state shape only.
- `NPC_BATTLE_TEMPLATE.md` defines ordinary battle-reference shape only.
- `../villain/VILLAIN_TEMPLATE.md` defines major recurring villain shape.

If future NPC architecture requires a new category, update this system document first, then update the templates that depend on it.
