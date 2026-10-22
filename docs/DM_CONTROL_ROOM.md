# Rolling High Club — DM Control Room

> Agent entry protocol and navigation cockpit. This document is a router, not a source of truth, a campaign snapshot, or a save system.

## The Sun Rule

**Classify first. Read the smallest authoritative RHC source. Then use only that path.**

Once the route is clear, stop browsing and play the world.

## 1. Classify the Request

| Request | First read | Route |
| --- | --- | --- |
| Scene / question about mutable current state | `public.dm_runtime_read()` | Read the published operational state/checkpoint first; if more mutable detail is needed, hydrate from the checkpoint artifact's `state` map at the exact confirmed ref, not stale state-domain files. |
| Scene / question about canon, rules, static definitions or history | `README.md`, then the smallest listed domain source | Load what the scene needs, then play. |
| Narration-only beat | No repository/runtime read unless a stop sign applies | Play freely. No persistence is needed. |
| Madma long-term story architecture | `characters/madma/NARRATIVE_DIRECTION.md` | Use it as protagonist-direction only; factual claims still require the smallest canonical source. |
| Beyond the Heroes brainstorm / cutaway | `beyond_the_heroes/README.md` | Keep proposals in `ideas/`; only DM-established backstage events belong in `entries/`. |
| Durable campaign change | `docs/RHC_WORKSYSTEM.md`, then affected domain owners | Use the guarded RT01 SAVE procedure. Do not substitute a raw repo or SQL write. |
| Exact canon / rules conflict | Smallest relevant canon record or official source | Verify before establishing a fact. |
| Planned idea | `planned/` | Keep it non-canon and META. |
| Brainstorm / experiment | `brainstorm/` | Keep it non-canon and META. |
| System, template or workflow change | `PROJECT_PRIMER.md` and relevant `docs/` file | Engineering work; use a focused branch and review. |
| Unclear / retcon | Smallest relevant canonical source | Do not guess; ask the Dungeon Master. |

## 2. Authority

- `PROJECT_PRIMER.md` defines RHC canon, visibility, cross-repository boundaries and the activated RT01 authority split.
- Root `README.md` is the domain router.
- `docs/RHC_WORKSYSTEM.md` defines Quicksave, Autosave, Final Save and day-flow persistence.
- **SQL / Supabase is the live operational published-world surface** for mutable current state.
- `public.dm_runtime_read()` is the supported service-facing read facade; staging/future rows are not a read authority.
- Repository `main` remains implementation truth + campaign-canon truth.
- Exact confirmed `runtime-published` commits are durable checkpoint/provenance evidence and pinned fallback material, not a normal mutation target.
- `characters/madma/NARRATIVE_DIRECTION.md` defines Madma's protagonist-direction only; it is not evidence for in-world facts, powers, destiny or history.
- `beyond_the_heroes/ideas/` contains proposals only; `beyond_the_heroes/entries/` contains DM-established backstage events.
- `canon/days/day_XXX.md` is finalized history, not current operational state.
- Mission10, chat memory, old copies and templates do not fill missing RHC facts.

## 3. Play First

**Green:** atmosphere, gestures, dialogue, incidental reactions and natural rhythm. Play; no lookup or save.

**Yellow:** a promise, relationship movement, new detail or operational fact that may matter later. Verify or mark it honestly when it becomes durable.

**Red:** canon conflict, exact mechanics, major reveal, durable change, lifecycle transition, Quicksave or Final Save. Read the correct owner before persisting.

A lookup is a scalpel, not a heart monitor. Do not reopen the repository or runtime for every small beat.

## 4. Backstage Boundaries

- NPCs know only what they saw, heard, learned or could reasonably infer.
- META information, hidden hooks, unrevealed mechanics and DM planning stay backstage.
- Madma's narrative-center status grants narrative direction, not mechanical superiority, plot armor, automatic success or authority over other Player Characters.
- Unknown aspects of Madma remain unknown until established through gameplay or explicit brainstorming followed by normal canonization.
- `Beyond the Heroes` may contain world events the heroes never witnessed. An occurred backstage event is not automatically hero knowledge.
- A proposed Beyond the Heroes idea is not canon until the Dungeon Master establishes that it occurred.
- A fact being NON_META does not grant it to every character.
- A blocked or unclear persistence decision never blocks normal narration.

## 5. Published Runtime Persistence

RHC uses the activated **RT01 guarded persistence path**.

- **Quicksave / Autosave:** reconcile meaningful current continuity, stage it through the Save Gateway, publish one database-owned generation, then complete the exact `runtime-published` Git mirror/read-back/verifier handshake.
- **Final Save:** performs the same guarded runtime publication and also closes the explicitly confirmed in-world day into permanent repository history according to `docs/RHC_WORKSYSTEM.md`.
- Ending a real-world session does not automatically close an in-world day.
- **Multi-day authoritative gameplay** — one source document spanning several already-played in-world days is not a separate engine path: partition it into individual completed campaign days, then finalize each chronologically through the ordinary one-day Final Save procedure (see `docs/RHC_WORKSYSTEM.md`). Ambiguous day boundaries or canon status go back to the Dungeon Master.
- If the correct owner, day number, canon state or visibility is unclear: do not guess and do not publish; ask the Dungeon Master.
- A raw write to `main`, `runtime-published`, or a runtime-owned SQL table is never by itself a successful save.
- Never claim a save happened until the publication is verifier-confirmed at the exact remote Git ref for the same generation/token. If Git/confirmation fails after SQL publication, repair that same generation rather than starting another save.

## 6. Load Once, Then Play

At a scene boundary, load the smallest useful published context first when mutable state matters: current generation/checkpoint metadata, current day/location when known, present characters, immediate objective, relevant Hooks and due persistent consequences. Hydrate additional detail only when the scene actually needs it — the smallest repository owner for canon/static material, or the checkpoint artifact's `state` map at the exact confirmed fallback ref for mutable state. Re-check only when uncertainty or a meaningful boundary appears.

**The repository stores the knowledge. The Dungeon Master creates the story.**
