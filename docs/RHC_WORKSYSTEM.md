# Rolling High Club — Runtime Persistence Worksystem

This document defines the current **activated RT01 persistence procedure** for Rolling High Club.

The old repository-only manual save path is retired. RHC now uses a guarded SQL/Supabase published-runtime path with exact Git mirror confirmation. Repository canon/history still matters, but a repository write by itself is never a successful runtime save.

## 1. Authority

Before a read or write that can affect continuity:

1. Follow `PROJECT_PRIMER.md`.
2. Use `docs/DM_CONTROL_ROOM.md` to classify the request.
3. Use the root `README.md` domain router for canon/static owners.
4. Read mutable current operational state through `public.dm_runtime_read()` first.
5. Read only the smallest relevant repository owner when canon/static detail is needed; for mutable fallback detail, read the checkpoint artifact's `state` map at the exact confirmed `runtime-published` ref.
6. Never use another campaign repository to fill missing RHC facts.
7. Missing information remains Unknown until the Dungeon Master establishes it.

The active authority split is:

- **SQL / Supabase** — live operational published-world state.
- Repository **`main`** — implementation truth + campaign-canon truth.
- Exact confirmed **`runtime-published`** — durable checkpoint/provenance evidence and pinned fallback material.

A direct write to `main`, `runtime-published`, or a runtime-owned SQL table is never by itself a completed Save.

## 2. Active Day vs Permanent History

The `daily_recap` domain is the current active-day player-known handoff and next-scene reload point. Operational reads are SQL-first after RT01 activation; `state/daily_recap.json` remains the repository owner/shape and canon source for that domain. The operational fallback for its mutable values is the checkpoint artifact's `state` map at the exact confirmed `runtime-published` ref, not the domain file at that ref.

It is **not** the permanent historical archive.

Permanent finalized day history lives in:

`canon/days/day_XXX.md`

One finalized file exists per explicitly closed in-world campaign day.

Ending a real-world tabletop session does not automatically close the in-world day.

## 3. Save Completion Contract

Every Quicksave, Autosave, Final Save or equivalent durable gameplay mutation uses the guarded RT01 lifecycle:

`BEGIN -> STAGE/DELETE -> ABORT | PUBLISH -> runtime-published mirror -> exact remote read-back -> verifier confirmation -> COMPLETE`

The database owns the candidate generation, lock/save identity and mirror token. The caller does not invent them.

A Save is **not COMPLETE** merely because:

- a repository file was edited or committed;
- SQL staging rows exist;
- SQL publication returned successfully;
- a local Git commit exists;
- the caller knows or predicts a Git SHA;
- `runtime-published` was changed without the guarded worker/verification path.

Completion requires the published SQL generation and the exact real remote `runtime-published` proof to agree and be verifier-confirmed for the same database-owned generation/token.

If SQL publication succeeds but Git mirroring/read-back/confirmation fails, **do not start generation N+1**. Repair/finish the same pending generation through `scripts/runtime_published_mirror.py` until confirmation succeeds or the gate explicitly stops.

## 4. Quicksave / Autosave

`Autosave` is currently an explicit semantic alias for Quicksave. There is no background time-based autosave scheduler unless a later RT gate explicitly implements and activates one.

When the Dungeon Master requests Quicksave / Autosave:

1. Read the current published runtime/checkpoint through `public.dm_runtime_read()`.
2. Determine only the meaningful established deltas since the previous published handoff. Do not infer missing facts.
3. Identify the single owning campaign domains affected by those deltas.
4. Begin the guarded Save Gateway; use the database-owned staging generation and lock token returned by the gateway.
5. Stage only the intended owner values, or explicit deletes, required by this save.
6. Reconcile the semantic owners below before publication.
7. If ownership, canon status, visibility, lifecycle or required coupled state is unclear, **ABORT** rather than weakening the gate or publishing partial truth.
8. Publish the candidate generation through the Save Gateway.
9. Complete/repair the external Git mirror with `scripts/runtime_published_mirror.py` using the live database connection and the real repository remote. The worker must read back the actual remote SHA, prove checkpoint bytes/continuity and complete verifier confirmation.
10. Re-read supported runtime metadata and confirm the expected generation is published and mirror-confirmed with no unresolved active save/staging context.
11. Only then report **saved**.

### Semantic reconciliation checklist

Save meaningful persistent continuity, not every line of dialogue.

- `daily_recap` — player-known developments and next-scene handoff only.
- NPC current state — location/status/goal/assignment/knowledge/relationship/equipment only when it actually changed.
- Player Character persistent state — only when a tracked mutable owner exists and a durable value changed.
- Location state — only when persistent place state changed.
- `narrative_hooks` — new, advanced, dormant or closed multi-day threads; it remains the single owner of Hook lifecycle indexes.
- Knowledge / Who-Knows-What — only for durable world or character-knowledge changes.
- Beyond the Heroes — only DM-established backstage events that actually occurred or materially advanced; never promote `ideas/` automatically.
- `live_status`, `day_resolution` and configured mechanics — only when those domains actually changed.
- `campaign_clock` — the Campaign Clock day/phase/elapsed/Long-Rest facts (see `docs/CAMPAIGN_TIME.md`), staged **only** through the validated `stage_campaign_clock` route, never through generic `stage_campaign_state`; `campaign_runtime.published_day` is derived from it at publication.
- `dm_meta` — committed hidden DM handoff only; never leak it into player-known recap.

Repository files define canon/static ownership and may require their own protected repository update when a procedure changes permanent canon/history. Such a repository change must describe the same established facts, but it does **not** replace the runtime publication receipt.

Ordinary Quicksave does not create or rewrite a permanent `canon/days/day_XXX.md` file.

## 5. Knowledge Reconciliation

For a meaningful event, ask:

- Who directly observed it?
- Who was directly told?
- Who received a credible report?
- Who can reasonably infer it from established evidence?

Do not propagate knowledge automatically to allies, organizations, nearby NPCs or all Player Characters.

Reusable world truth belongs in `knowledge/facts.json` when useful. Character-local knowledge remains local to the character/NPC state.

A Beyond the Heroes entry may be established world truth while remaining unknown to every Player Character. Reader/DM knowledge is never automatic character knowledge.

## 6. NPC / Character Reconciliation

Update current state only when it actually changed.

Examples:

- current location;
- current status / availability;
- current goal / assignment;
- pending actions;
- persistent injury/effect;
- current equipment or attunement when tracked;
- relationship movement;
- durable knowledge change.

Completed or cancelled assignments must not remain pending after the save.

Do not infer a current location, loadout or intention merely because it would be plausible.

## 7. Hook Reconciliation

`quests/narrative_hooks.json` is the **single semantic owner** of current Hook lifecycle indexes.

`daily_recap` may contain an immutable snapshot of which Hooks carried into the day, but it must not maintain competing current active/dormant/closed lists.

Rules:

- A Hook represents a meaningful multi-day thread, not every conversation.
- A Hook may exist without a prepared Scenario.
- A persisted Scenario should identify exactly one Primary Hook that owns its campaign lifecycle.
- A Beyond the Heroes entry may create causal pressure or suggest a Hook, but it does not become a competing Hook ledger. If a real multi-day Hook exists, link/reconcile it in the Hook owner.
- When a Hook closes during the active day, it may remain in `closed_hooks_today` until Final Save.
- After Final Save, its permanent resolution belongs in that day's canonical record.

## 8. Final Save

Final Save closes an **in-world campaign day**. It is not triggered merely because the real-world session ends.

Perform the Quicksave reconciliation first, then:

1. Confirm the exact campaign day number being closed.
2. Prepare the finalized history from `canon/days/DAY_TEMPLATE.md` as `canon/days/day_XXX.md` using only established facts.
3. Record the meaningful events, NPC/character developments, durable knowledge/reveals, mechanical consequences, Hook changes, location changes and other continuity-worthy facts for that day.
4. Preserve unresolved active/dormant Hooks; move current-day closures into the finalized day record and clear the current-day closure bucket for the next day.
5. Preserve meaningful Beyond the Heroes consequences that occurred that day when useful to complete world history, while keeping unrevealed information out of player-known recap.
6. Point the next handoff's `previous_day_record` at the finalized day file.
7. Initialize the next active-day handoff only after the Dungeon Master confirms the new in-world day has begun.
8. Add a milestone to `canon/timeline.md` only when the day contains a genuinely useful long-term milestone.
9. Publish the coherent runtime day-closure candidate through the guarded RT01 Save Gateway and complete exact Git mirror confirmation under the normal Save Completion Contract.
10. Land the finalized repository canon/history on `main` through the SAVE-owned repository write path below. A repo commit alone is not runtime Save completion, and a runtime receipt alone does not magically create a missing finalized canon day file.

### SAVE-owned repository canon/history write path

The `canon/days/day_XXX.md` artifact (and any `canon/timeline.md` milestone) is repository canon truth, so it lands on `main` — never on `runtime-published`, which the mirror worker owns and which changes only `runtime/published-checkpoint.json`. SAVE owns this path without loading BUILD/JOHNNY machinery:

1. Create a focused SAVE branch from current `main` (for example `save/day-XXX-final`).
2. Add only the finalized canon/history artifacts: `canon/days/day_XXX.md`, plus a `canon/timeline.md` milestone when warranted.
3. Do not change runtime code, SQL, tests, workflows, or mutable state-domain files on this branch.
4. Commit locally.
5. Push the branch and open a pull request against `main`.
6. The Dungeon Master owns canon and approves the pull request; no JOHNNY, Builder lifecycle, Codex review, or Flight Control machinery is loaded.
7. Merge that exact branch into `main`, then confirm the finalized day file exists at the merged `main` HEAD.

An ordinary Final Save repository candidate adds **exactly one** new finalized
day. That one-day contract is never widened into a bulk or multi-day writer:
when one authoritative source document spans several already-played in-world
days, the DM agent partitions it into individual completed campaign days
first, then finalizes each day separately through this same ordinary one-day
path in chronological order (see Multi-Day Authoritative Gameplay Intake
below).

Final Save is complete only when the required runtime publication is confirmed and the required permanent canon artifact exists. If one side fails, stop and reconcile; do not invent a weaker success rule.

Never overwrite an existing finalized day file merely to make a new day fit. A correction to finalized canon should be an explicit Dungeon Master correction/retcon with clear provenance.

### Begin Day / Start-of-Day (POST-EV2-11)

After Final Save has finalized in-world Day N into `canon/days/day_N.md`, the
explicit `DM note: begin day` request opens Day N+1 through the POST-EV2-11
Begin Day conductor (`scripts/begin_day.py`, see
`docs/POST-EV2-11-BEGIN-DAY.md`):

1. Read the current published day-boundary bundle through the service-only
   `public.dm_begin_day_read()` and require a coherent, known published Day N.
2. Require the requested day to be exactly N+1 (a retry of an already-published
   day rehydrates and never rerolls) and require the finalized Day N file to
   exist.
3. Initialize only the existing day-boundary owners (`daily_recap`,
   `day_resolution`, `narrative_hooks`, plus `live_status`/`dm_meta` when active)
   and advance the Campaign Clock day through the validated RT02 route, changing
   no other fact — no invented elapsed time, phase, chronology or Rest.
4. Dispatch only configured daily consumers in deterministic bounded order,
   routing every required roll through `scripts/dice_resolver.py` (POST-EV2-8);
   zero configured consumers means zero RNG.
5. Publish once through the normal RT01 Save Gateway and complete the existing
   `runtime-published` mirror/read-back/verifier confirmation.
6. Return a derived Fresh-Day DM Boot Packet (yesterday's full finalized record +
   compact current published context + today's resolved mechanics). The packet is
   read output and is never persisted as truth.

Begin Day is a conductor: it owns no new state, Hook lifecycle, Rest semantics or
rules. If the day sequence, previous-day finalization or owner coherence cannot
be verified, or publication succeeds but mirror confirmation fails, it fails
closed and preserves the last healthy published checkpoint.

### Multi-Day Authoritative Gameplay Intake

Real tabletop play may already have covered several in-world campaign days
that RHC has not yet finalized, and one authoritative source document may
carry all of them. The AI is the semantic layer that recognizes the completed
day boundaries; existing deterministic SAVE machinery owns persistence:

1. **Partition before persistence.** The DM agent separates the supplied
   established gameplay into individual completed campaign days — anchored by
   the existing finalized-day archive and established facts only — before any
   persistence begins.
2. **One day per Final Save, in chronological order.** Each recognized
   completed day is then processed as its own individual Final Save through
   the normal Save Completion Contract and the ordinary one-day
   repository-history path above — never collapsed with any other day into
   one finalized-day record. POST-EV2-11.5 owns only the semantic
   partitioning of multi-day authoritative gameplay; reconciliation and
   persistence are owned entirely by the existing ordinary Final Save
   semantics and run unchanged for each recognized day.
3. **No Begin Day replay.** Already-played days are established outcomes.
   Begin Day is live `N -> N+1` progression only: never open, rerun or
   otherwise invoke Begin Day mechanics merely to persist already-played
   history, and execute no live RNG, Rest, Business or Combat mechanics for
   those days.
4. **Ask, do not invent.** If day boundaries, day numbering or canon status
   are ambiguous, stop and ask the Dungeon Master. Do not invent missing
   boundaries, days or facts to complete the batch.
5. **No new engine.** There is deliberately no dedicated Historical Sync
   engine, bulk-history admission lane, archive/import subsystem, second
   Save Gateway or second Campaign Day authority for this intake. Existing
   Final Save/SAVE machinery persists each recognized day.

## 9. Business / Economy Mechanics

`config/ECONOMY_TEMPLATE.json` and `config/ORGANIZATION_TEMPLATE.json` are reusable schemas only.

To activate a business/economy system for RHC:

1. Create named configuration files from the templates.
2. Populate only Dungeon-Master-approved values and rules.
3. Explicitly identify the configuration as Canon or a mechanical rule for RHC.
4. Store mutable money/assets/effects in current-state owners, published through the guarded runtime path once that system is activated.

The existence of a template does not create a company, workforce, income, reputation score or asset in canon.

## 10. Useful DM Commands

These are **semantic requests**. The Dungeon Master should not need to supply generation IDs, lock tokens, SQL helper names or Git SHAs.

- `DM note: quicksave` — reconcile meaningful current continuity and execute the complete guarded Save Gateway + mirror-confirmation transaction.
- `DM note: autosave` — currently the same semantic action as Quicksave; no background scheduler is implied.
- `DM note: final save` — close the explicitly confirmed in-world day, publish the coherent runtime closure and create the permanent `canon/days/day_XXX.md` history artifact.
- `DM note: begin day` — open exactly the next live in-world day from a finalized previous day through the POST-EV2-11 Begin Day conductor and return a Fresh-Day DM Boot Packet.
- Multi-day already-played gameplay — not a separate command: partition the supplied authoritative record into individual completed campaign days and finalize each chronologically through ordinary `DM note: final save` (see Multi-Day Authoritative Gameplay Intake); Begin Day never replays them.
- `DM note: canon ...` — explicit canon update, routed to the relevant owner and through the required durable publication path when current runtime state changes.
- `DM note: plan ...` — DM planning only; route to `planned/` or `dm_meta` depending on whether it is an uncommitted future plan or already committed hidden DM handoff.
- `DM note: beyond the heroes idea ...` — backstage brainstorming proposal only; route to `beyond_the_heroes/ideas/`.
- `DM note: beyond the heroes occurred ...` — explicitly establish a backstage event; route to `beyond_the_heroes/entries/` and reconcile affected owners through the normal save path when it becomes durable current truth.

## 11. Failure Rule

If the correct destination, day number, canon status, visibility or required coupled mutation cannot be determined safely, **do not guess and do not publish**. Abort the candidate if one exists, preserve the last healthy confirmed checkpoint, and ask the Dungeon Master.

A blocked persistence gate blocks mutation/publication, not narration.
