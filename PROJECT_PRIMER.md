# Rolling High Club — Project Primer

## Purpose

This repository is the permanent knowledge base and GitHub worksystem for the **Rolling High Club (RHC)** tabletop Dungeons & Dragons campaign played by the Dungeon Master and the in-person player group.

It exists to preserve continuity, campaign history, world state, characters, places, factions, important items, world facts, character knowledge, DM planning, mechanical handoffs and controlled information visibility without mixing different continuity layers.

## Canon Boundary — Mandatory Rule

**Rolling High Club is the primary tabletop campaign canon.**

Any AI simulation, Sequel Mission, alternate timeline, combat stress test, hypothetical scene, or experimental project is separate continuity and is **not** Rolling High Club canon unless the Dungeon Master explicitly chooses to import a specific result into RHC.

No event, NPC development, relationship, organization, asset, economy, world change, rule, or other information originating from a separate simulation may be treated as Rolling High Club canon without that explicit promotion.

Information must never be transferred automatically between repositories.

## Current Source Rule

Canonical source material for Rolling High Club is the set of authoritative RHC campaign sources, events established at the physical table, and later information explicitly declared **Canon** by the Dungeon Master.

Only information originating from those RHC sources may be migrated into canonical repository layers.

Knowledge from unrelated chats, memories, simulations, Sequel Missions, or assumptions must not be used to fill missing RHC information.

If information is missing, leave it unknown or ask the Dungeon Master. **Do not invent canon to complete a template.**

## Information States

Every campaign entry must belong to one of three states.

### Canon

Information that has happened in the tabletop campaign, exists in an authoritative RHC source file, or has been explicitly declared canon by the Dungeon Master.

### Planned

Future DM plans, intended developments, possible encounters, unrevealed story structure, or other material intended for future use. Planned material is **not canon** until it occurs in play or the Dungeon Master explicitly promotes it to Canon.

### Brainstorm / Ideas

Uncommitted concepts, alternatives, experiments, research notes, and creative possibilities. Brainstorm material is **not canon** and must never be presented as established campaign fact.

## META / NON-META Visibility

Information state and visibility are separate dimensions.

Every knowledge-bearing entry may also be classified as:

- **META** — not safe for normal player-facing disclosure;
- **NON_META** — safe to expose in normal player-facing use.

A Canon fact can still be META if the players have not legitimately learned it. NON_META does not mean every PC or NPC knows the information; individual in-world knowledge remains tracked separately.

The repository-wide visibility authority is `knowledge/META_NON_META_PROTOCOL.md`.

**Safe default: any unclassified legacy knowledge is treated as META until explicitly classified.**

## Repository Structure

- `/canon/` — finalized established history and canon records that do not belong more naturally to a dedicated subsystem.
- `/canon/days/` — one permanent `day_XXX.md` record for each explicitly finalized in-world campaign day.
- `/characters/` — permanent Player Character sheets and reusable PC templates. Player agency always remains with the human player.
- `/npc/` — ordinary NPC profiles, mutable NPC state, local knowledge, relationships and combat references.
- `/villain/` — **single flat major-villain root**. One villain file per recurring major villain; optional flat companion files such as `<villain_slug>_lair.md`. Do not create `villain/<villain_name>/` subdomains or a competing `npc/villain/` root.
- `/knowledge/` — canonical reusable world facts, META/NON-META visibility rules and Who-Knows-What behavior.
- `/locations/` — location subsystem. Permanent cards live in `locations/profiles/`; mutable location continuity lives in `locations/state/` only when needed.
- `/inventory/` — important item and weapon definitions. Ownership/equipped state belongs to the owning character/NPC state rather than the static item definition.
- `/quests/` — mutable multi-day Narrative Hook ledger and Hook templates.
- `/state/` — active-day handoff and other current mutable campaign-state ledgers; repository owner/shape definitions for state that is served operationally from the published runtime after RT01 activation.
- `/realities/` — reality identity and explicit parent-lineage registry. `reality:rhc-primary` is the one root primary reality; alternate realities declare one admitted parent and inherit it unchanged by default.
- `/config/` — reusable mechanics configuration templates such as economy/business and organization schemas. Templates are inert until explicitly instantiated for RHC.
- `/systems/` — reusable gameplay/DM support systems such as Combat Academy encounter templates.
- `/planned/` — future DM plans and unrevealed development; META by default.
- `/brainstorm/` — ideas, alternatives, experiments and research concepts; META by default.
- `/docs/` — repository workflow contracts and reusable system documentation.
- `/PROJECT_PRIMER.md` — repository-wide governance and continuity authority.

Subsystem documents are subordinate to this Project Primer. Use subsystem files to define **storage and interpretation**, not to dictate what story the Dungeon Master must tell.

## Active State vs Permanent History

RHC separates current operational state, repository canon and permanent history.

After RT01 activation, supported reads of mutable current operational state are **SQL-first** through `public.dm_runtime_read()`. The published runtime is the live operational surface. Repository domain files such as `state/daily_recap.json`, `state/live_status.json`, `state/day_resolution.json`, `state/dm_meta.json` and `quests/narrative_hooks.json` remain the owning campaign-domain definitions/canon/shape sources; they are not a reason to bypass a newer confirmed published generation. When a confirmed published generation lacks the mutable detail a read needs, the operational fallback is the checkpoint artifact's `state` map at the exact confirmed `runtime-published` ref, not the state-domain file at that ref (ordinary saves update only that artifact).

`state/daily_recap.json` defines the active-day player-known recap and next-scene handoff domain. It is intentionally temporary/current-state data, not the permanent archive.

When the Dungeon Master explicitly closes an in-world day with **Final Save**, that day becomes a new permanent file at `canon/days/day_XXX.md`. The finalized day file is historical authority for that closed day; live-state domains continue to own what is true now.

A real-world session ending does not automatically close the in-world campaign day.

The operational save rules are defined in `docs/RHC_WORKSYSTEM.md`.

## Campaign Run Terminology

RHC distinguishes its gameplay lane from Git engineering terms.

- **CAMPAIGN MAINRUN** (short form **MAINRUN**) is the normal authoritative Rolling High Club gameplay lane — the current mutable-authority lane for the campaign.
- **RUN #** is a temporary continuation/execution lane inside the same RHC campaign reality. A Run is not a parallel reality, alternate continuity, or save slot.
- Repository **`main`** is a Git branch and engineering term only; it is never the gameplay lane.
- **PREQUEL / SEQUEL** are separate campaign continuities, not ordinary Runs.

The `Prequel/Main Canon` wording in the Cross-Repository Rule below is cross-continuity source/canon language: it means the primary/source canon for a separate continuity and is **not** the MAINRUN concept.

## Reality Identity and Inheritance (POST-EV2-4B)

RHC has one canonical tabletop continuity with one explicit root reality,
`reality:rhc-primary` (see `/realities/`). An alternate reality is explicitly
authored and names exactly one admitted parent reality; parent lineage resolves
and is acyclic.

**Inheritance first: a child reality is its parent unchanged unless an explicit
divergence later says otherwise through the real owning domain.** A different
reality means a different history because a divergence exists or may exist — not
because inherited content was exhaustively re-scoped.

Reality identity alone clones, removes, rewrites or scopes no Entity, Hook,
Scenario, Encounter, Run, item, ability, status or system definition, and never
mutates the parent/source reality merely by existing. There is deliberately no
"what exists in this reality?" subject-availability list, and no generic reality
override/state-copy payload. Ordinary RUN creation and time/timespace travel do
not create a reality. External PREQUEL / SEQUEL / simulation content remains
non-canon and separately owned.

## Disposable Non-Canon Brainstorm Lab (POST-EV2-14)

A **disposable brainstorm lab** is an engine-side, explicitly NON-CANON
Prequel / Sequel / What-If exploration rooted at a caller-supplied scratch root
outside canonical campaign/runtime authority (see
[`docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md`](docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md)).
A lab is not a reality, not a Run, not a save slot, and not canon: it begins
from an exact trusted origin receipt, is writable only while active, and is
closed or reset to a verified clean baseline. There is deliberately no
automatic merge-back — a good lab idea reaches canon only through a separate,
later, DM-authorized intake/canon decision.

## Single-Owner Domain Rule

Do not store the same mutable truth in multiple competing ledgers.

Examples:

- current Hook indexes belong only to `quests/narrative_hooks.json`, not duplicated in `state/daily_recap.json`;
- permanent NPC identity belongs in `npc/profiles/`, while current mutable NPC facts belong in `npc/npc_state.json`;
- permanent location identity belongs in `locations/profiles/`, while persistent mutable place state belongs in `locations/state/`;
- static item mechanics belong in `inventory/`, while ownership/equipped/attunement state belongs to the owning character/NPC state;
- permanent day history belongs in `canon/days/`, while next-scene handoff belongs in `state/daily_recap.json`.

The runtime may publish these owners as a generation-aware operational state map, but publication does not create a second semantic owner. Domain ownership remains exactly where this Primer and the subsystem contracts say it lives.

## Template Rule

Files named `*_TEMPLATE.*` are reusable schemas, not populated campaign records.

- `null`, empty arrays, empty objects and instructional placeholder text are not canon.
- A template must never be read as an active character, NPC, location, Hook, organization, economy or encounter.
- Create a separate named file from the template only when the relevant campaign entity or system is actually established.
- Missing values remain unknown; never fill them by assumption merely to make a template look complete.

## Canon Promotion Rule

Information becomes Canon only when at least one of the following is true:

1. It appears in an authoritative Rolling High Club canonical source.
2. It occurs during the actual tabletop campaign.
3. The Dungeon Master explicitly declares it Canon.

A Planned or Brainstorm entry must never silently become Canon.

A META → NON_META reveal is **not** a Canon promotion; it changes visibility only.

## Conflict Rule

When information conflicts:

1. An explicit current ruling by the Dungeon Master takes priority.
2. Authoritative canonical RHC sources take priority over development notes.
3. Canon takes priority over Planned.
4. Planned takes priority over Brainstorm only for planning purposes; neither is established world fact.
5. External simulation or Sequel Mission material has no authority over Rolling High Club canon.

Visibility conflicts are resolved according to `knowledge/META_NON_META_PROTOCOL.md`. When visibility is genuinely unknown, default to META.

## External Lore

Rolling High Club uses the Forgotten Realms and Dungeons & Dragons as its setting and rules foundation where applicable.

Official D&D / Forgotten Realms material may be researched when needed, but external lore must be clearly distinguished from established RHC campaign canon. External lore must not overwrite an explicit RHC canonical fact.

Published lore may support a world-fact entry when useful, but the entry should identify its source status so official setting knowledge is not confused with facts established specifically by the RHC table.

Published availability does not automatically make a piece of lore NON_META inside the campaign.

## Knowledge Locality

**World truth, visibility and character knowledge are different things.**

A fact may be true in RHC canon and remain META because it has not been revealed. A NON_META fact may still be known by only one character. Conversely, a character may hold an unconfirmed belief that is not world truth.

Reusable canonical facts belong in `knowledge/facts.json`. Who actually knows, suspects, misunderstands or has discovered those facts belongs in the relevant NPC/character knowledge state.

Never propagate knowledge automatically merely because a fact exists in the repository or because it is NON_META.

## Cross-Repository Rule

If a separate Sequel Mission repository reads RHC as its Prequel/Main Canon source, the relationship is one-way by default:

```text
RHC CANON
   │
   │ read / bootstrap
   ▼
SEPARATE SEQUEL MISSION
```

A Sequel Mission may inherit established RHC truth up to its chosen divergence point. It must not write results back into this repository automatically.

## Storage / Engineering Boundary

RT01 is activated. The authority model is now explicit:

- **SQL / Supabase** = live operational published-world surface for mutable runtime state.
- Repository **`main`** = implementation truth + campaign-canon truth.
- Exact confirmed **`runtime-published`** commits = durable checkpoint/provenance evidence and pinned fallback material.

These surfaces are complementary, not interchangeable. A raw write to any one of them is not automatically a valid save. Durable gameplay mutation must use the guarded RT01 Save Gateway and complete the external Git mirror/read-back/verifier handshake described in `docs/RHC_WORKSYSTEM.md`. Engineering changes still use focused branches, tests/CI, review and PRs rather than the gameplay save path.

## Operating Principle

**The repository stores the knowledge. The Dungeon Master creates the story.**

The purpose of this database is to protect continuity, preserve secrets and reduce the Dungeon Master's memory burden, not to restrict creativity, automate the tabletop game, or decide what becomes canon without the Dungeon Master.
