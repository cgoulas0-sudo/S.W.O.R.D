# tests/fixtures/inventory/

Non-canonical fixture data for the inventory schema tests. Nothing under this directory
represents a real Rolling High Club campaign entity or item — all names are fictional
placeholders used only to exercise `schemas/inventory.schema.json` and
`scripts/validate_entities.py --schema schemas/inventory.schema.json`.

EV2-10 evolves the EV2-03 flat `{ item }` entry into an explicit ordinary possession
(`name` + `description` + `quantity >= 1`) plus a structurally separate D&D `currency`
object (`cp`/`sp`/`ep`/`gp`/`pp`, non-negative integers). The fixtures below were migrated
to the EV2-10 shape; the schema no longer accepts the legacy `{ item }` entry.

- `valid/` — one record per box-level status (`known` with ordinary entries + currency,
  `known` with zero entries — a known-empty inventory whose zero coin balances are still
  represented structurally, distinct from `unknown` — `unknown`, `not_applicable`).
- `invalid_schema/` — records that each violate exactly one schema rule: `known` without
  `entries`, `entries` present while box status isn't `known`, an entry carrying a `status`
  field (rejected by design — see `schemas/README.md` on why inventory entries are
  presence-only and don't get the same per-entry tri-state as state/knowledge), an entry
  missing the required `name`/`description`/`quantity` payload, and a malformed `entity_id`.
  The entry-shaped fixtures are EV2-10-shaped so each fails for its stated rule alone rather
  than also for a missing payload; `unknown_with_entries.json` carries a valid ordinary entry
  purely to prove that any `entries` are forbidden when the box status is not `known`.
- `invalid_duplicate/` — two otherwise-valid records sharing one `entity_id`, to prove
  cross-file uniqueness rejection.

The first real RHC inventory record is out of scope for EV2-03/EV2-10 and belongs to a later
gate. Per-item identity/custody is EV2-11.
