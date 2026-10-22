# Rolling High Club — Narrative Hook Domain

`quests/narrative_hooks.json` is the **single current ledger** for meaningful multi-day narrative continuity.

`state/daily_recap.json` may describe the active scene and may preserve an immutable carryover snapshot, but it must not duplicate the current active/dormant/closed Hook indexes.

## What Belongs Here

- the next permanent Hook ID;
- current active Hooks;
- dormant/prepared Hooks with a real activation condition;
- Hooks closed during the current active day until Final Save;
- optional Scenario ownership links;
- related NPC, character and location references useful for continuity.

## What Does Not Belong Here

- generic scene handoff → `state/daily_recap.json`;
- unrevealed committed DM truth → `state/dm_meta.json`;
- permanent prior-day Hook resolutions → `canon/days/day_XXX.md`;
- every conversation, fact, joke or relationship beat.

## Lifecycle

- **Active:** meaningful multi-day thread currently in motion.
- **Dormant / Prepared:** valid future thread with a concrete activation condition, not yet active.
- **Closed Today:** resolved during the active day and awaiting Final Save archival.

A new Hook should be created only when the thread is worth future continuity tracking.

## Hook ↔ Scenario Invariant

- A Hook may have no Scenario.
- A persisted Scenario should have exactly one **Primary Hook** that owns its lifecycle.
- Related Hooks may provide context but do not all close when one Scenario resolves.
- Scenario completion closes the Primary Hook only after the objective/outcome and durable consequences have been resolved and persisted.

Use `HOOK_ENTRY_TEMPLATE.json` for the shape of a new Hook entry.
