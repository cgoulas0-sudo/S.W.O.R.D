# EV2-08 — Run record foundation

EV2-08 defines the smallest persistent record for an actual campaign occurrence.

## Mental model

- **Hook** = narrative purpose / quest thread.
- **Scenario** = prepared playable situation tied to exactly one Primary Hook.
- **Encounter** = prepared scene inside that Scenario.
- **Run** = one execution branch / occurrence anchored to an exact shared campaign reality.

The Run does not duplicate `hook_id`: its `scenario_id` resolves to a Scenario whose
Primary Hook already supplies the narrative purpose.

The normal authoritative gameplay lane of that shared campaign reality is the
**CAMPAIGN MAINRUN** (**MAINRUN**). A Run is a temporary continuation lane inside that
same campaign reality; it is not a parallel reality, alternate continuity, or save slot.

## Run contract

A Run has:

- stable `R<number>` identity;
- `execution_mode`: `played` or `off_screen`;
- `control_state`: `active` / `parked` for played Runs, `not_applicable` for off-screen Runs;
- exactly one `scenario_id`;
- zero or more `occurred_encounter_ids`, each of which must belong to that Scenario;
- optional `party_id`;
- historical `participant_entity_ids`;
- current `mutable_owner_entity_ids`;
- zero or more actual/relevant `location_ids`;
- `campaign_anchor` containing the exact Git `base_commit` and an opaque non-blank
  `campaign_time` label;
- optional non-blank `outcome_summary`.

The exact Git commit is the world-revision side of the branch analogy: it records which
shared campaign truth this Run branched from. The anchor is valid only when that commit is
reachable from canonical Git `main` history; an unmerged or abandoned branch commit is not a
shared-canon anchor even if the Git object still exists locally. EV2-08 deliberately does
no campaign-time arithmetic.

## Participation vs. mutable ownership

Participation/history is not ownership.

An actor can remain in a Run's `participant_entity_ids` forever as historical truth while
being removed from `mutable_owner_entity_ids` when control transfers elsewhere. Across a
validated Run batch, one actor may appear in many historical participant lists but in at
most one `mutable_owner_entity_ids` list. Mutable write authority is exclusive: an entity
may be mutable in exactly one current gameplay lane, and that lane is either MAINRUN or
exactly one RUN #.

This lets a parked Run survive a real-session roster change. Example: Madma can remain a
historical participant in Run A while Run A releases his mutable ownership and Run B
acquires it. Run A remains structurally valid and can later be closed/reconciled without
reasserting stale Madma state. Parking a Run does not by itself release mutable ownership;
an old Run preserves history after handoff but does not retain mutable authority.

`control_state` is deliberately not a lifecycle. `parked` means the played Run is not
currently being played; it does not mean resolved, abandoned, synchronized, or canonized.

## Hard boundary

EV2-08 does **not** define:

- Run closure/synchronization lifecycle;
- structured world-change deltas;
- off-screen d20 resolution;
- stale-anchor/conflict policy;
- exactly-once/idempotent reconciliation;
- atomic merge-back;
- canon mutation;
- Run registry/reservations/locks or write-scope collision machinery;
- inventory custody expansion;
- RAG;
- real RHC Run migration.

Those convergence semantics belong to EV2-09 and later gates.
