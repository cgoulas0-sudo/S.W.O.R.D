# Rolling High Club — META / NON-META Protocol

> Repository-wide visibility protocol for knowledge-bearing information.

This protocol is subordinate to `PROJECT_PRIMER.md` and applies across Canon, Characters, NPCs, Villains, Locations, Inventory, Facts, Hooks, State, Planned material, Brainstorm material and any future knowledge domain.

## 1. Purpose

Every piece of information in the RHC repository has two separate questions:

1. **Is it true / what information state does it belong to?** — Canon, Planned, Brainstorm, official source, belief, unknown, etc.
2. **Is it safe to expose in normal player-facing use?** — META or NON_META.

These dimensions must never be conflated.

A fact can be Canon and still be META because the players have not discovered it yet. A fact can be NON_META without being known by every individual character. Who-knows-what remains a separate local knowledge question.

## 2. Visibility Classes

### META

Information that must not be revealed, implied as established player knowledge, or used to answer player-facing questions unless the Dungeon Master explicitly requests DM/meta information or the information becomes legitimately revealed in play.

Typical META information includes:

- unrevealed canon truth;
- villain motives, hidden plans and secrets;
- undiscovered location properties;
- hidden item properties;
- encounter preparation;
- future DM plans;
- brainstorm material;
- exact NPC knowledge that players have not learned;
- stat-block information not legitimately available to the players.

### NON_META

Information that has been legitimately revealed, established at the table, explicitly declared player-safe by the Dungeon Master, or is otherwise safe to use in normal player-facing RHC discussion.

NON_META does **not** mean every PC or NPC automatically knows it. Individual knowledge remains governed by the Who-Knows-What system.

## 2a. Terminology note: exposure is not tabletop "meta knowledge"

RHC's `META`/`NON_META` names are a **player-facing exposure classification**, and this naming is preserved as compatibility terminology. In ordinary tabletop speech, "meta knowledge" often means information a player has picked up that their character should not act on. That is a different concept:

- RHC `NON_META` answers: **may the human player/reader be exposed to this information in normal player-facing use?** It is a property of the underlying information.
- Tabletop "meta knowledge" answers: **does a player know something their character does not?** It is a situation at the table, not a classification of the information.

Never read RHC `NON_META` as "every character knows this" or as permission for a character to act on information their knower record does not establish. Knowledge in-world always comes from an explicit knower-owned event, never from exposure classification.

## 2b. Beyond the Heroes separation

A Beyond the Heroes entry may simultaneously be:

1. **true RHC canon** (world truth, owned by the canon layer and, when reusable, by `knowledge/facts.json`);
2. **reader-visible** (the anthology deliberately exposes the event to human readers; exposure may be `non_meta` while the underlying knowledge stays unknown); and
3. **unknown to every hero** (no hero knowledge record references it).

BTH publication is reader exposure as an artifact. It is never a knowledge mutation: publishing a BTH entry does not create, imply or propagate knowledge for any character. A hero knows a BTH event only when a separate, explicitly knower-owned Entity V2 knowledge event establishes that knowledge. The Entity V2 knowledge contract that enforces this separation is `schemas/knowledge.schema.json` (EV2-14); see `docs/EV2-14-LOCAL-KNOWLEDGE.md`.

Player-account exposure of an occurred/published BTH entry is additionally gated by an explicit spoiler acknowledgement: in normal player-facing use such an entry is presented to player accounts only after the human reader has explicitly acknowledged the spoiler. Acknowledging the spoiler changes human reader exposure only — it is still never a knowledge mutation and never grants, implies or propagates character knowledge. The deterministic request-time access seam that enforces this reader-exposure rule, together with owner-aware DM/player campaign-context and owner-local knowledge admission, is `scripts/context_access.py`, documented in `docs/BTH-01-PLAYER-DM-ACCESS.md`.

## 3. Safe Default

**Unclassified knowledge defaults to META.**

This is a leak-prevention rule, not a claim that the information is secret forever. Existing legacy content does not need to be deleted or rewritten before this protocol can take effect. Until an entry or section is explicitly classified, treat it as META in player-facing use.

## 4. Atomic Classification

Classify the smallest practical knowledge unit rather than forcing an entire mixed file into one visibility state.

### JSON

Use:

```json
"visibility": "meta"
```

or

```json
"visibility": "non_meta"
```

### Markdown

A whole file or section may declare:

```text
**Visibility:** META
```

or

```text
**Visibility:** NON_META
```

If a section contains both kinds of information, classify the relevant subsection or bullet explicitly. The nearest explicit classification wins. Otherwise inherit the parent/file classification; if none exists, use the safe default META.

## 5. Reveal / Promotion

When information is legitimately discovered or explicitly made player-safe, its visibility may change from META to NON_META without changing the underlying canon truth.

A reveal is a visibility transition, not a canon promotion.

Where useful, record:

- `revealed_in_session`
- `revealed_to`
- `reveal_note`

Do not automatically convert related facts to NON_META merely because one connected fact was revealed.

## 6. Who-Knows-What Is Separate

Visibility answers: **may this information be exposed in normal player-facing use?**

Who-Knows-What answers: **which character, NPC, PC, group or faction actually knows or believes it in-world?**

Examples:

- A secret may be META while Gork knows it.
- A NON_META fact may be known by Madma but not by Sa’arpa.
- A player may have accidentally seen META information; it remains META in-world until revealed legitimately.

Never grant in-world knowledge merely because visibility is NON_META.

## 7. Domain Defaults

Unless explicitly classified otherwise:

- `planned/` → META
- `brainstorm/` → META
- `npc/battle/` → META
- `villain/` → META
- `state/dm_meta.json` → META
- hidden NPC motives / secrets → META
- unrevealed location secrets → META
- hidden item properties → META
- encounter preparation → META
- established table-facing history → may be NON_META when explicitly marked

Folders do not override an explicit more-specific classification.

## 8. Retrieval Rule

For ordinary player-facing RHC questions, use NON_META information only.

META information may be read internally to preserve consistency, but it must not be leaked, hinted at as known, or used to give the player unfair knowledge.

When the Dungeon Master explicitly asks for DM notes, hidden truth, planning, secrets, villain information, or repository maintenance, META information may be surfaced as appropriate.

## 9. Migration Rule

Do not delete or rebuild canonical information solely to introduce this system.

Existing content should be migrated incrementally:

1. protect all unclassified legacy content through the META default;
2. classify reusable facts and major sections first;
3. mark known player-facing canon NON_META where supported;
4. preserve hidden truth as META;
5. never guess visibility when the source does not establish whether players learned something.

The goal is reliable information separation with minimal duplication and no destructive rewrite.
