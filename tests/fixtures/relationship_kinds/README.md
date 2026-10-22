# tests/fixtures/relationship_kinds/

Non-canonical fixture data for the Entity V2 relationship kind registry (EV2-05 Patch 1).
Nothing under this directory represents a real Rolling High Club relationship — all kinds
are generic labels (`serves`, `guards`, `mentors`, ...) used only to exercise
`schemas/relationship_kind.schema.json` and `scripts/validate_relationship_kinds.py`.

- `valid/` — four records proving the registry's structural metadata: `serves` (a plain
  kind with no inverse), `parent_of`/`child_of` (an asymmetric pair proving `inverse_of`
  consistency plus `allowed_source_types`/`allowed_target_types`), and `allied_with` (a
  symmetric kind, proving `symmetric: true` needs no separate `inverse_of`).
- `invalid_schema/` — records that each violate exactly one schema rule (missing `kind`,
  disallowed extra property, bad `kind` pattern, `symmetric` + `inverse_of` together, empty
  `allowed_source_types`, bad `inverse_of` pattern, duplicate `allowed_source_types` entry,
  an `allowed_target_types` value outside the closed `entity_type` set).
- `invalid_duplicate/` — two otherwise-valid records sharing one `kind`, to prove cross-file
  kind uniqueness rejection.
- `invalid_dangling_inverse/` — one record whose `inverse_of` names a kind that does not
  exist anywhere in the batch.
- `invalid_self_inverse/` — one record whose `inverse_of` names its own `kind` (should use
  `symmetric: true` instead of a self-referential `inverse_of`).
- `invalid_asymmetric_inverse/` — a three-record batch (`guards` -> `guarded_by` ->
  `commands` -> `guarded_by`) where `guarded_by` and `commands` correctly point back at each
  other but `guards` does not get pointed back to, isolating a mutual-inconsistency failure
  onto exactly one record.
- `invalid_reversed_endpoints/` — a mutually-consistent `inverse_of` pair (`mentors` /
  `mentored_by`) whose `allowed_source_types`/`allowed_target_types` are not reversed between
  the two records, proving the registry rejects endpoint constraints that don't mirror across
  an inverse pair.
- `invalid_one_sided_endpoints/` — a mutually-consistent `inverse_of` pair (`guards` /
  `guarded_by`) where `guards` declares endpoint restrictions and `guarded_by` declares none
  at all, proving the registry rejects a restriction on one side of an inverse pair that has
  no matching mirror declared on the other, rather than silently treating the missing side as
  an acceptable (unrestricted) mirror.
- `invalid_symmetric_endpoint_mismatch/` — a `symmetric: true` kind (`allied_with`) whose
  `allowed_source_types` and `allowed_target_types` describe different domains, proving the
  registry rejects endpoint domains that don't match on a kind that reads the same in both
  directions.
- `invalid_malformed_endpoint_items/` — a `symmetric: true` kind (`guards`) whose
  `allowed_source_types` contains an unhashable nested object instead of a string, proving the
  registry-level endpoint-mirroring check reports a clean schema error instead of crashing on
  `set()` construction.

Relationship *instances* are implemented separately by EV2-05 Patch 2 in
`schemas/relationship_instance.schema.json`, with their own synthetic fixture set under
`tests/fixtures/relationship_instances/`. No real RHC relationship data is stored in either
fixture tree.
