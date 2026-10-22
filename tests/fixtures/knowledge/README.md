# tests/fixtures/knowledge/

Non-canonical fixture data for the EV2-14 knowledge schema tests. Nothing under
this directory represents a real Rolling High Club campaign entity or fact —
all names, topics and `fact_id` values are fictional placeholders used only to
exercise `schemas/knowledge.schema.json` and
`scripts/validate_entities.py --schema schemas/knowledge.schema.json`.

EV2-14 evolves the EV2-03 entry shape: every entry holds exactly one content
mode (a reusable `fact_id` reference OR a concise local scalar `value`), an
explicit `epistemic_status` (`confirmed | belief | suspicion`), and — for
local assertions — a required `visibility` (`meta | non_meta`). Fact
references must not carry a `visibility` (exposure is inherited from the
referenced fact at read time); the EV2-03 entry-level `status` tri-state is no
longer valid. See `docs/EV2-14-LOCAL-KNOWLEDGE.md` and `schemas/README.md`.

- `valid/` — one record per box-level status: `known` with entries covering
  both content modes across confirmed/belief/suspicion
  (`character-test-bor-knowledge.json`), `unknown`
  (`creature-test-unknown-knowledge.json`), `not_applicable`
  (`location-test-na-knowledge.json`).
- `invalid_schema/` — records that each violate exactly one schema rule:
  `known` without `entries`, a malformed `entity_id`, and a local assertion
  `value` that is a structured object instead of a scalar (the player-agency
  structural boundary — see `schemas/README.md`). Broader EV2-14 rejection
  cases (copied/missing visibility, both/neither content modes, unsupported
  epistemic states, blank topic/fact_id, legacy entry-status shape, box-level
  unknown/not_applicable with entries, duplicate exact entries) are proved by
  temporary records inside `tests/test_state_knowledge_inventory_validation.py`
  rather than by additional fixture files.
- `invalid_duplicate/` — two otherwise-valid records sharing one `entity_id`,
  to prove cross-file uniqueness rejection.

The first real RHC knowledge record is out of scope for EV2-14 and belongs to
a later real-data intake gate.
