# EV2-07 — Scenario + Encounter foundation

EV2-07 defines the prepared-story layer between Hooks and future Runs.

## Mental model

- **Hook** = persistent quest / multi-day story thread.
- **Scenario** = a prepared playable situation that expresses story possibility.
- **Encounter** = one concrete prepared scene inside a Scenario.
- **Run** = a later record of what actually occurred.

Prepared Scenario/Encounter records are not canon outcomes.

## Scenario contract

A Scenario has a stable `S<number>` ID, title, premise, objective, trigger condition,
exactly one `primary_hook_id`, optional `related_hook_ids`, and related Entity V2 IDs.

The Primary Hook must resolve to a persisted Hook. Related Hooks must also resolve and
must not duplicate the Primary Hook.

A Hook may exist without a Scenario. EV2-07 does not require a one-Hook-to-one-Scenario
reverse uniqueness rule.

## Encounter contract

An Encounter has a stable `E<number>` ID, belongs to exactly one persisted Scenario,
and records a title, scene type (`social`, `exploration`, `combat`, or `mixed`), setup,
immediate objective, and related Entity V2 IDs.

The Scenario owns no duplicated Encounter backlink list in this patch. Encounter
membership is authoritative from `encounter.scenario_id`.

## Hard boundary

EV2-07 does not store actual occurrence state, outcomes, rewards/consequences,
campaign time, Run deltas, off-screen resolution, RAG, relationship expansion,
inventory mechanics, or real RHC campaign data. Those remain later gates.
