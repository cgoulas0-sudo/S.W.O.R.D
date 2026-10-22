# tests/fixtures/state/

Non-canonical fixture data for the EV2-03 state schema tests. Nothing under this directory
represents a real Rolling High Club campaign entity — all names are fictional placeholders
(`test-bor-state`, `test-unknown-state`, etc.) used only to exercise `schemas/state.schema.json`
and `scripts/validate_entities.py --schema schemas/state.schema.json`.

- `valid/` — one record per box-level status (`known` with entries covering all three
  entry-level statuses, `unknown`, `not_applicable`).
- `invalid_schema/` — records that each violate exactly one schema rule: `known` without
  `entries`, `entries` present while box status isn't `known`, an entry missing `value` while
  `known`, an entry carrying `value` while not `known`, an entry `value` that is a structured
  object instead of a scalar (the player-agency structural boundary — see
  `schemas/README.md`), and a malformed `entity_id`.
- `invalid_duplicate/` — two otherwise-valid records sharing one `entity_id`, to prove
  cross-file uniqueness rejection.

The first real RHC state record is out of scope for EV2-03 and belongs to a later gate.
