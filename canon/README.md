# Canon

This directory contains established **Rolling High Club tabletop campaign canon**.

Only material supported by authoritative RHC source files, events that occurred at the physical game table, or information explicitly declared Canon by the Dungeon Master belongs here.

Material from simulations, Sequel Missions, alternate timelines, hypothetical continuations, or other experimental repositories must never be placed here unless the Dungeon Master explicitly imports a specific element into RHC canon.

## Finalized Day Archive

`canon/days/` is the permanent day-by-day narrative archive.

When the Dungeon Master explicitly performs **Final Save** for an in-world day, create exactly one new file:

`canon/days/day_XXX.md`

Use `canon/days/DAY_TEMPLATE.md` as the structural starting point. The finalized day record preserves what permanently happened that day. It does not replace current-state owners such as `npc/npc_state.json`, `quests/narrative_hooks.json`, location state, character state or `state/live_status.json`.

`state/daily_recap.json` is the active-day handoff and must not become a competing historical archive.

When one authoritative source document spans several already-played campaign
days, the DM agent partitions it into individual completed campaign days and
each day is finalized separately: exactly one new `canon/days/day_XXX.md` per
ordinary Final Save, in chronological order, through the existing one-day
Final Save path. Several completed days are never collapsed into one
finalized-day record, existing finalized days are never silently overwritten
or retconned (an explicit Dungeon Master correction/retcon with clear
provenance remains allowed through the existing correction path), and Begin
Day is never invoked merely to replay already-played days. Ambiguous day
boundaries or canon status go back to the Dungeon Master rather than being
invented.
