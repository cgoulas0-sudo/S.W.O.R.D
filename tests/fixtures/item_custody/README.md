# tests/fixtures/item_custody/

Non-canonical fixture data for the EV2-11 unique-item custody schema tests. Nothing under
this directory represents a real Rolling High Club campaign entity or item — all names are
fictional placeholders used only to exercise `schemas/item_custody.schema.json` and
`scripts/validate_entities.py --schema schemas/item_custody.schema.json`.

An EV2-11 custody record is exactly `item_id`, `owner_entity_id`, and `holder_entity_id`.
Owner and holder are independent nullable facts; JSON `null` is a real, valid value (the
absence of an owner or holder), distinct from a missing field. The derived human labels are
not stored:

- `held` — `holder_entity_id` is non-null, whether or not owner is the same actor;
- `owned` — owner is non-null and holder is null;
- `treasure` — both owner and holder are null.

- `valid/` — one synthetic split-custody record (`item:test-blade` owned by `character:test-bor`
  but carried by `character:test-fanis`), representative of a theft/loan where owner and holder
  legitimately differ.

The schema-level test suite (`tests/test_item_custody_validation.py`) covers the remaining
approved combinations — owned-and-held, owned-but-uncarried, carried-without-ownership, and
treasure — plus the rejected cases (missing fields, other entity types, malformed IDs, extra
fields) using inline records, since the EV2-11 Surface Budget authorizes exactly one synthetic
fixture file.

No real RHC item identity or custody record is introduced here. Initial admission of real item
identity and first custody is deferred to EV2-12; gameplay mutation never mints a new
`item:` identity.
