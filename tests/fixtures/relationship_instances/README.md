# tests/fixtures/relationship_instances/

Non-canonical synthetic fixture data for EV2-05 Patch 2. Nothing here represents a real
Rolling High Club relationship.

The fixture set proves the minimal lifecycle-bearing relationship-instance contract:

- `valid/` — four records, including the explicitly supported generic case
  `faction -> serves -> location`, one ended historical relationship plus a later active
  relationship with the same `(source_id, kind, target_id)`, and a symmetric kind instance.
- `invalid_schema/` — malformed/missing required fields, bad typed IDs/kind syntax,
  whitespace-only lifecycle labels, whitespace-only `relationship_id`, and an unversioned
  future metadata field (`strength`) that must remain rejected until a later schema version
  explicitly adds it.
- `invalid_duplicate_id/` — two otherwise-valid instances sharing one `relationship_id`.
- `invalid_unknown_kind/` — an instance using a kind absent from the supplied registry.
- `invalid_endpoint_type/` — source and target endpoint-type violations against a restricted
  relationship kind.
- `invalid_duplicate_active/` — two active instances with the same exact
  `(source_id, kind, target_id)` triple.

`started_at` and `ended_at` are intentionally opaque non-blank strings in this foundation.
Patch 2 does not perform campaign-clock arithmetic or chronology checks. Activity is derived
only from whether `ended_at` is absent. Ended records remain as history.

The schema is intentionally strict today (`additionalProperties: false`) but not a dead end:
future fields such as strength, visibility, reason, or provenance may be added through later
versioned schema evolution without replacing the core relationship model.
