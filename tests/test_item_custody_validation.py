"""EV2-11 unique-item custody schema validation proof.

Proves the shape and boundary law of `schemas/item_custody.schema.json`:
  * the record requires exactly `item_id`, `owner_entity_id`, `holder_entity_id`;
  * there is no stored `status` field (or any other extra field);
  * `item_id` accepts only valid `item:` identities;
  * `owner_entity_id` / `holder_entity_id` each accept exactly JSON null or a valid
    `character:` / `party:` identity, and reject missing fields, other entity
    types, malformed IDs, and non-string scalars;
  * all four approved owner/holder combinations validate, including treasure
    (null/null) and a split owner/holder (theft/loan);
  * missing vs. null is unambiguous: a missing required field fails while an
    explicit JSON null is a valid value.

The synthetic `valid/` fixture is proven through the same batch validator the
Entity V2 identity workflow uses; the remaining cases are inline records, since
the EV2-11 Surface Budget authorizes exactly one synthetic fixture file.
"""

import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records, load_schema, validate_paths  # noqa: E402

SCHEMA = ROOT / "schemas" / "item_custody.schema.json"

BOR = "character:test-bor"
FANIS = "character:test-fanis"
PARTY = "party:test-stash"
BLADE = "item:test-blade"


def errors_for(record):
    validator = jsonschema.Draft202012Validator(load_schema(SCHEMA))
    return list(validator.iter_errors(record))


def record(item_id=BLADE, owner=BOR, holder=FANIS):
    return {
        "item_id": item_id,
        "owner_entity_id": owner,
        "holder_entity_id": holder,
    }


def test_synthetic_fixture_passes_as_a_batch():
    paths = load_records(FIXTURES / "item_custody" / "valid")

    errors_by_path = validate_paths(paths, schema_path=SCHEMA)

    assert errors_by_path == {}


def test_exactly_the_three_approved_combinations_validate():
    combinations = [
        (BOR, BOR),      # owned and held by the same actor
        (BOR, None),     # owned but not currently carried
        (None, FANIS),   # carried without established ownership
        (None, None),    # treasure
        (BOR, FANIS),    # theft / loan: owner and holder differ
        (PARTY, BOR),    # party-owned, character-held
        (BOR, PARTY),    # character-owned, party-held
    ]

    for owner, holder in combinations:
        assert errors_for(record(owner=owner, holder=holder)) == []


def test_missing_item_id_is_rejected():
    bad = record()
    del bad["item_id"]

    assert errors_for(bad)


def test_missing_owner_is_rejected_but_explicit_null_is_valid():
    missing_owner = record()
    del missing_owner["owner_entity_id"]
    assert errors_for(missing_owner)

    assert errors_for(record(owner=None, holder=BOR)) == []


def test_missing_holder_is_rejected_but_explicit_null_is_valid():
    missing_holder = record()
    del missing_holder["holder_entity_id"]
    assert errors_for(missing_holder)

    assert errors_for(record(owner=BOR, holder=None)) == []


def test_stored_status_field_is_rejected():
    bad = record()
    bad["status"] = "held"

    assert errors_for(bad)


@pytest.mark.parametrize(
    "item_id",
    [
        "character:test-bor",
        "party:test-stash",
        "item:Test-Blade",
        "item:",
        "test-blade",
        "item:test blade",
        "item:test-blade\n",
    ],
)
def test_item_id_accepts_only_valid_item_identities(item_id):
    assert errors_for(record(item_id=item_id))


@pytest.mark.parametrize(
    "actor",
    [
        "location:tavern",
        "faction:guild",
        "creature:wolf",
        "item:other-blade",
        "ability:smite",
        "status_effect:cursed",
        "character:Test-Bor",
        "party:",
        "bor",
        "character:test-bor\n",
    ],
)
def test_owner_rejects_other_entity_types_and_malformed_ids(actor):
    assert errors_for(record(owner=actor))


@pytest.mark.parametrize(
    "actor",
    [
        "location:tavern",
        "faction:guild",
        "creature:wolf",
        "item:other-blade",
        "ability:smite",
        "status_effect:cursed",
        "character:Test-Bor",
        "party:",
        "fanis",
        "character:test-fanis\n",
    ],
)
def test_holder_rejects_other_entity_types_and_malformed_ids(actor):
    assert errors_for(record(holder=actor))


@pytest.mark.parametrize("actor", [7, True, ["character:test-bor"], {"id": BOR}])
def test_owner_rejects_non_string_non_null_scalars(actor):
    assert errors_for(record(owner=actor))


@pytest.mark.parametrize("actor", [7, True, ["character:test-fanis"], {"id": FANIS}])
def test_holder_rejects_non_string_non_null_scalars(actor):
    assert errors_for(record(holder=actor))


def test_unknown_extra_field_is_rejected():
    bad = record()
    bad["quantity"] = 1

    assert errors_for(bad)
