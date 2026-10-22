# tests/fixtures/entities/

Non-canonical fixture data for Entity V2 identity schema tests (EV2-02). Nothing under this
directory represents a real Rolling High Club campaign entity — all names are fictional
placeholders (`test-hero`, `test-shopkeep`, etc.) used only to exercise
`schemas/entity.schema.json` and `scripts/validate_entities.py`.

- `valid/` — one record per entity type, individually schema-valid, plus cross-entity
  `references` to prove structurally valid ID references. Two additional `character`
  records (`character-test-shopkeep`, `character-test-mastermind`) use the optional
  `subtype` field (`npc`, `villain`) to prove that mutable roles are classification
  metadata, not separate identity types or ID prefixes. `ability-test-spark` and
  `status_effect-test-chill` (EV2-04.1) cover the two persistent-definition types added
  alongside the original six; `ability-test-spark` also uses `subtype` (`spell`) and
  `references` a `status_effect` record to prove the same subtype/reference mechanics
  apply uniformly to the new types, not just the original six.
- `invalid_schema/` — records that each violate exactly one schema rule (missing field, bad
  `entity_id` pattern, `entity_type`/`entity_id` prefix mismatch, unknown type, malformed
  reference, disallowed extra property, duplicate reference items). EV2-04.1 adds one
  focused case (`ability_status_effect_prefix_mismatch`) proving the prefix-mismatch rule
  also rejects an `ability`/`status_effect` cross-mismatch, not only mismatches among the
  original six types.
- `invalid_duplicate/` — two otherwise-valid records sharing one `entity_id`, to prove
  cross-file uniqueness rejection.

The first real RHC entity record migration is out of scope for EV2-02 and belongs to a later
gate.
