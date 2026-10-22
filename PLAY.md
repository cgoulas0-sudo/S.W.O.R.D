# PLAY.md — PLAY Cockpit

You are in **Rolling High Club (RHC)**, in the PLAY lane: actively running or continuing the tabletop campaign — live scenes, narration, and in-session DM work. You reached here from the universal Dropgate in [`AGENT_HANDOFF.md`](./AGENT_HANDOFF.md). A **standalone** canon / rules / state look-up that changes nothing is the **READ** lane, not PLAY; durable persistence is the **SAVE** lane. PLAY points at those authorities and owns neither.

**PLAY is not BUILD.** This cockpit never loads engineering machinery — no JOHNNY, no Flight Control, no `CHANGELOG.md` / `ENGINE_CHANGELOG.md`, no validators, no BUILD branch lifecycle. If the request is actually to change repository docs, workflow, code, schema, or tests, that is BUILD: return to the Dropgate and route to `ORCHESTRATOR.md` / `BUILDER.md` instead.

## Authority

This cockpit is a thin lane router. It owns no campaign truth of its own and duplicates none. The real authorities are:

- [`docs/DM_CONTROL_ROOM.md`](./docs/DM_CONTROL_ROOM.md) — agent entry protocol: classify the request and read the smallest authoritative source, then play.
- [`PROJECT_PRIMER.md`](./PROJECT_PRIMER.md) — canon, visibility (META/NON-META), cross-repository boundaries and the activated RT01 authority split.
- [`README.md`](./README.md) — the domain router to the single owning source for each kind of campaign truth.
- `public.dm_runtime_read()` — supported SQL-first read surface for published mutable operational state and checkpoint metadata.
- `public.dm_current_search('<focus>')` — service-only exact-focus search over the current published world for one `character:` / `creature:` / `location:` / `faction:` / `party:` / `item:` focus; returns bounded, directly relevant current records grouped by owning domain.
- `scripts/story_retrieval.py` — POST-EV2-6 project-wide/history retrieval. Search may be broad; hydration is bounded and passes an explicit reader-profile admission gate. Mixed/ambiguous visibility fails closed for ordinary authoritative/player-safe hydration.
- [`docs/RHC_WORKSYSTEM.md`](./docs/RHC_WORKSYSTEM.md) — the guarded RT01 Quicksave / Autosave / Final Save procedure.
- [`docs/POST-EV2-11-BEGIN-DAY.md`](./docs/POST-EV2-11-BEGIN-DAY.md) — POST-EV2-11 Begin Day / Start-of-Day (`DM note: begin day`). It opens exactly the next live day from a finalized previous day and returns a Fresh-Day DM Boot Packet; it is a SAVE-owned conductor, not a second day owner, and never grants Rest.
- Multi-day already-played gameplay has no separate engine or command: the DM agent partitions it into individual completed campaign days, then finalizes each chronologically through ordinary Final Save via [`docs/RHC_WORKSYSTEM.md`](./docs/RHC_WORKSYSTEM.md); Begin Day is never invoked merely to replay already-played days.

## Play

1. **Classify first** using `docs/DM_CONTROL_ROOM.md`, then load only the smallest authoritative RHC source the scene needs. Load once, then play the world.
2. For mutable current operational state, prefer the supported published runtime read facade. For canon, rules, static definitions or historical material, use the smallest repository owner through the domain router.
3. **Narration-only beats** need no repository read and no persistence.
4. **Canon / rules questions** are answered from the smallest owning source; never invent canon to fill a template, and default unknown visibility to META.
5. **Never propagate knowledge automatically** — world truth, visibility, and character knowledge are different things.

## Rolls come from the shared resolver, never from invention

A **mechanically required roll** — any random outcome the rules require, such as an attack, check, save or damage roll — must be produced by executing RHC's shared resolver (`scripts/dice_resolver.py`), not invented or narrated. A model must never fabricate a die value, improvise an ad-hoc `random` call, or supply an unexplained modifier: mechanically required randomness comes from the resolver, and every static modifier, bonus/penalty die and Advantage/Disadvantage source it accepts declares a non-empty source.

The resolver owns randomness and declared roll arithmetic only. Whether a roll is required, which ability/skill/save applies, the DC, success/failure and any consequence remain DM/rules decisions. Rolling never saves or mutates state by itself; a result worth keeping still follows the SAVE lane.

Character Rest is the same rule: a Short Rest's optional Hit Point Die spending is a mechanically required roll, so `scripts/character_rest.py` sends it through this shared resolver and the durable Rest lifecycle is applied through the SAVE lane's `mutate_character_rest` route — no raw `random` call, guessed Constitution modifier, or invented elapsed time.

## Save is the SAVE lane — re-route, do not own it

PLAY is **not** a save cockpit. The moment intent becomes explicit **Save / Quicksave / Autosave / Final Save** — or any durable campaign-continuity write — that is the **SAVE lane**: re-route through the Dropgate to [`docs/RHC_WORKSYSTEM.md`](./docs/RHC_WORKSYSTEM.md), the single canonical persistence authority, and follow the guarded RT01 procedure defined there. PLAY keeps only the pointer; it **does not restate or own the save procedure**.

A repository write, raw SQL mutation, or chat claim is never enough to say "saved." The SAVE lane owns publication and confirmation.

## Read

Reading inside a running session changes nothing and stays part of PLAY. For mutable current operational state, use `public.dm_runtime_read()` first; if it says more detail is needed, follow only the exact confirmed Git ref from trusted runtime metadata and read the value from the checkpoint artifact's `state` map at that ref (not from stale state-domain files at that ref). When one exact entity-like focus matters now, `public.dm_current_search('<focus>')` returns the smallest bounded set of already-authoritative current records relevant to that focus; it never recursively hydrates the IDs inside those hits. For static canon/rules/history, read the smallest repository owner.

A **standalone** canon / rules / state question that is not part of continuing a live session is the **READ** lane at the Dropgate, not PLAY. Either way, reading never writes a file, never commits, and never performs a save; if answering would require a write, it is a SAVE decision, not a read.

**The repository stores the knowledge. The Dungeon Master creates the story.**
