# Rolling High Club — Current State

This directory stores **current mutable campaign handoff state**, not permanent history.

## Current Ledgers

- `daily_recap.json` — player-known active-day recap and next-scene handoff.
- `day_resolution.json` — current-day RNG/mechanical resolutions that must survive the handoff.
- `live_status.json` — generic current campaign resources, assets and persistent effects when tracked. Its `businesses` map is the single Business mutable-state owner for the POST-EV2-12 series: a state-shape declaration that may carry each Business's current active/disabled state, fund balances, stock/byproduct quantities, Reputation score and Business-owned duration-in-resolution-days effects. POST-EV2-12.1 leaves it empty and creates no company, balance or Business state.
- `dm_meta.json` — committed hidden runtime truth / durable DM-only handoff; META by default. Its optional `run_claims` field is DM coordination metadata only: existing Run IDs mapped to arrays of stable semantic IDs (never repository paths, filenames or write permissions). It records what a Run is currently concerned with and grants no ownership or write authority; `runs` remains the only authoritative Run/controller registry. See `docs/POST-EV2-2-HOT-RUN-REGISTRY.md`.

## Rules

- Finalized narrative history belongs in `canon/days/day_XXX.md`.
- Current Hook lifecycle belongs only in `quests/narrative_hooks.json`.
- Permanent NPC identity belongs in `npc/profiles/`; mutable NPC state remains in `npc/npc_state.json`.
- Permanent location identity belongs in `locations/profiles/`; persistent mutable place state belongs in `locations/state/`.
- Do not duplicate the same current truth across several ledgers merely for convenience.
- Blank/uninitialized state files create no canon.
- `daily_recap`, `day_resolution`, `live_status`, `dm_meta` and `quests/narrative_hooks.json` carry a day-boundary `current_day` field while active. POST-EV2-11 Begin Day advances only those day-boundary fields (plus the RT02 Campaign Clock day) when opening the next live day; it never grants Rest, invents elapsed time, or rewrites unrelated content. It sets `daily_recap.previous_day_record` to the finalized prior `canon/days/day_XXX.md` and `daily_recap.carryover_active_hooks_at_start` to an immutable snapshot taken from the Hook owner.
