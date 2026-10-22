# Rolling High Club 1

Canonical knowledge base and GitHub worksystem for the **Rolling High Club tabletop Dungeons & Dragons campaign**.

**Rolling High Club is the primary tabletop continuity.** Simulations, Sequel Missions, alternate timelines and hypothetical continuations are separate and non-canon by default. Nothing from another repository enters RHC unless the Dungeon Master explicitly imports it.

## Start Here

1. Read [`PROJECT_PRIMER.md`](PROJECT_PRIMER.md) for canon, visibility and cross-repository rules.
2. Read [`docs/DM_CONTROL_ROOM.md`](docs/DM_CONTROL_ROOM.md) to classify the request and choose the smallest source.
3. Read [`docs/RHC_WORKSYSTEM.md`](docs/RHC_WORKSYSTEM.md) before Quicksave, Autosave, Final Save or day rollover.
4. Use the smallest relevant domain below.

## Authority Split After RT01 Activation

- **SQL / Supabase** is the live operational published-world surface for current mutable runtime state.
- Repository **`main`** remains implementation truth and campaign-canon truth.
- Exact confirmed **`runtime-published`** checkpoints are durable publication/provenance evidence and a pinned fallback surface; the branch is not a normal write target.
- Supported operational reads go through `public.dm_runtime_read()`. If SQL is insufficient, follow only the exact confirmed Git ref returned by trusted runtime metadata and read the needed value from the checkpoint artifact's `state` map at that ref — not from mutable state-domain files at that ref.
- Durable gameplay mutation goes through the guarded RT01 Save Gateway and is not complete until the same database-owned generation is published, mirrored to the real remote, read back at the exact SHA and verifier-confirmed.

## Domain Router

| Need | Primary source |
| --- | --- |
| DM request classification / navigation | `docs/DM_CONTROL_ROOM.md` |
| Repository governance / canon boundary | `PROJECT_PRIMER.md` |
| Reality identity / parent-lineage inheritance registry | `realities/` |
| Published current operational state / checkpoint metadata | Supabase `public.dm_runtime_read()` |
| Save workflow / day handoff / Final Save | `docs/RHC_WORKSYSTEM.md` |
| Beyond the Heroes backstage narrative / hook brainstorming | `beyond_the_heroes/` |
| Active-day player-known recap and next-scene handoff domain | `state/daily_recap.json` (repository canon/shape owner; operational reads are SQL-first) |
| Finalized day history | `canon/days/day_XXX.md` |
| Other established canon | `canon/` |
| Player Character permanent sheets | `characters/` |
| Player Character mutable-state template | `characters/CHARACTER_STATE_TEMPLATE.json` |
| Normal NPC permanent identity | `npc/profiles/` |
| Normal NPC mutable state | `npc/npc_state.json` |
| Normal NPC combat references | `npc/battle/` |
| Major recurring villains | `villain/` |
| Current multi-day Hooks | `quests/narrative_hooks.json` |
| Hook rules | `quests/README.md` |
| Canonical world facts / Who-Knows-What | `knowledge/` |
| META / NON-META visibility | `knowledge/META_NON_META_PROTOCOL.md` |
| Older / project-wide story retrieval | `scripts/story_retrieval.py` + `docs/POST-EV2-6-STORY-RETRIEVAL.md` |
| Permanent location profiles | `locations/profiles/` |
| Mutable location continuity | `locations/state/` |
| Important item definitions | `inventory/` |
| General current campaign state / assets / persistent effects domain | `state/live_status.json` (repository canon/shape owner; operational reads are SQL-first) |
| Current-day RNG and mechanical resolutions domain | `state/day_resolution.json` (repository canon/shape owner; operational reads are SQL-first) |
| Committed hidden DM handoff domain | `state/dm_meta.json` (repository canon/shape owner; operational reads are SQL-first where exposed) |
| Reusable business/economy configuration templates | `config/` |
| Combat Academy / encounter templates | `systems/combat_academy/` |
| Future DM plans | `planned/` |
| Uncommitted ideas / experiments | `brainstorm/` |
| Disposable non-canon brainstorm lab (Prequel / Sequel / What-If) | `docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md` |

## Day History Rule

`state/daily_recap.json` defines the repository owner/shape for the **live handoff domain**, not the permanent archive. Operational current-state reads are SQL-first after RT01 activation.

When the Dungeon Master explicitly performs **Final Save** for an in-world campaign day, that day is finalized into a new standalone file:

`canon/days/day_XXX.md`

There is one finalized file per campaign day. Ending a real-world play session does **not** automatically mean the in-world day is closed.

## Template Rule

Files named `*_TEMPLATE.*` define reusable structure only. Blank fields, `null`, empty arrays and empty objects are not campaign facts. A template never creates canon merely by existing.

## Storage Boundary

RHC now uses the activated **RT01 published-runtime contract**. SQL/Supabase owns live operational published state; repository `main` owns implementation and campaign canon; exact confirmed `runtime-published` commits provide durable checkpoint/provenance proof.

A raw write to `main`, `runtime-published`, or a runtime-owned SQL table is never by itself a successful save. Quicksave, Autosave, Final Save and equivalent durable gameplay mutations must use the guarded procedure in `docs/RHC_WORKSYSTEM.md`. Save success requires verified publication/receipt, not merely a file write or an API call.

## Core Principle

**The repository stores the knowledge. The Dungeon Master creates the story.**
