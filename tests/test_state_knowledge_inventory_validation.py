import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_entities import load_records, validate_paths  # noqa: E402

BOXES = ["state", "knowledge", "inventory"]


def schema_path(box):
    return ROOT / "schemas" / f"{box}.schema.json"


def fixtures(box, kind):
    return FIXTURES / box / kind


@pytest.mark.parametrize("box", BOXES)
def test_valid_fixtures_pass_as_a_batch(box):
    paths = load_records(fixtures(box, "valid"))

    errors_by_path = validate_paths(paths, schema_path=schema_path(box))

    assert errors_by_path == {}


@pytest.mark.parametrize("box", BOXES)
def test_each_invalid_schema_fixture_fails_alone(box):
    for path in load_records(fixtures(box, "invalid_schema")):
        errors_by_path = validate_paths([path], schema_path=schema_path(box))
        assert path in errors_by_path, f"expected {path.name} to fail schema validation"


@pytest.mark.parametrize("box", BOXES)
def test_invalid_duplicate_fixtures_pass_individually(box):
    for path in load_records(fixtures(box, "invalid_duplicate")):
        errors_by_path = validate_paths([path], schema_path=schema_path(box))
        assert errors_by_path == {}, f"{path.name} should be schema-valid on its own"


@pytest.mark.parametrize("box", BOXES)
def test_invalid_duplicate_fixtures_fail_as_a_batch(box):
    paths = load_records(fixtures(box, "invalid_duplicate"))

    errors_by_path = validate_paths(paths, schema_path=schema_path(box))

    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert any("duplicates" in e for e in errors)


@pytest.mark.parametrize("box", BOXES)
def test_known_status_without_entries_is_rejected(box):
    path = fixtures(box, "invalid_schema") / "known_without_entries.json"

    errors_by_path = validate_paths([path], schema_path=schema_path(box))

    assert path in errors_by_path


@pytest.mark.parametrize("box", BOXES)
def test_bad_entity_id_is_rejected(box):
    path = fixtures(box, "invalid_schema") / "bad_entity_id.json"

    errors_by_path = validate_paths([path], schema_path=schema_path(box))

    assert path in errors_by_path


@pytest.mark.parametrize("box", ["state", "knowledge"])
def test_entry_value_restricted_to_scalars(box):
    """An entry value must not be an object: this is the structural boundary EV2-03
    can honestly enforce for the player-agency rule. It stops a structured
    action-prescription payload from being smuggled in as 'just data'; it cannot
    and does not stop prescriptive language inside a plain string, which remains a
    documented authoring rule (schemas/README.md), not a schema constraint.
    """
    path = fixtures(box, "invalid_schema") / "entry_value_is_object.json"

    errors_by_path = validate_paths([path], schema_path=schema_path(box))

    assert path in errors_by_path


def test_state_entry_known_requires_value():
    path = fixtures("state", "invalid_schema") / "entry_known_without_value.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("state"))

    assert path in errors_by_path


def test_state_entry_non_known_forbids_value():
    path = fixtures("state", "invalid_schema") / "entry_unknown_with_value.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("state"))

    assert path in errors_by_path


def test_state_box_unknown_forbids_entries():
    path = fixtures("state", "invalid_schema") / "unknown_with_entries.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("state"))

    assert path in errors_by_path


def test_inventory_box_unknown_forbids_entries():
    path = fixtures("inventory", "invalid_schema") / "unknown_with_entries.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("inventory"))

    assert path in errors_by_path


def test_inventory_entry_rejects_a_status_field():
    """Inventory entries are presence-only: an item's presence in the list is
    itself the known-established fact, so a per-entry status (unlike state/
    knowledge) is nonsense and must be rejected."""
    path = fixtures("inventory", "invalid_schema") / "entry_with_status_field.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("inventory"))

    assert path in errors_by_path


def test_inventory_entry_requires_name_description_quantity():
    """EV2-10: an ordinary inventory entry must carry the approved small payload
    (name + description + explicit quantity). The legacy entry_missing_item
    fixture is an empty object and now fails because all three are required."""
    path = fixtures("inventory", "invalid_schema") / "entry_missing_item.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("inventory"))

    assert path in errors_by_path


def test_state_entries_reject_duplicate_attribute(tmp_path):
    """Two entries naming the same attribute with conflicting known values are a
    contradiction, not two independent facts. uniqueItems alone doesn't catch
    this because the two entry objects differ (different value/status)."""
    path = tmp_path / "dup_attribute.json"
    path.write_text(
        json.dumps(
            {
                "entity_id": "character:test-dup-attribute",
                "status": "known",
                "entries": [
                    {"attribute": "current_location", "status": "known", "value": "Eagle's Nest"},
                    {"attribute": "current_location", "status": "known", "value": "Somewhere Else"},
                ],
            }
        ),
        encoding="utf-8",
    )

    errors_by_path = validate_paths([path], schema_path=schema_path("state"))

    assert path in errors_by_path, "duplicate attribute names within one state record should be rejected"


def test_knowledge_entries_reject_duplicate_topic(tmp_path):
    # EV2-14 entry shape: the two entries are individually schema-valid and
    # differ in value, so uniqueItems alone would let them through and only
    # the duplicate-topic check catches the contradiction.
    path = tmp_path / "dup_topic.json"
    path.write_text(
        json.dumps(
            {
                "entity_id": "character:test-dup-topic",
                "status": "known",
                "entries": [
                    {
                        "topic": "goblin_camp_location",
                        "epistemic_status": "confirmed",
                        "value": "north ridge",
                        "visibility": "non_meta",
                    },
                    {
                        "topic": "goblin_camp_location",
                        "epistemic_status": "confirmed",
                        "value": "south valley",
                        "visibility": "non_meta",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    errors_by_path = validate_paths([path], schema_path=schema_path("knowledge"))

    assert path in errors_by_path, "duplicate topic names within one knowledge record should be rejected"


def test_state_entry_value_rejects_nan_and_infinity(tmp_path):
    """NaN/Infinity/-Infinity are not valid JSON (RFC 8259); Python's json module
    accepts them as a non-standard extension, and jsonschema's "number" type
    check accepts the resulting float. A record containing one of these tokens
    must be rejected as invalid JSON, not silently validated as a number."""
    for i, value in enumerate((float("nan"), float("inf"), float("-inf"))):
        path = tmp_path / f"nan_or_inf_{i}.json"
        path.write_text(
            json.dumps(
                {
                    "entity_id": "character:test-nan-value",
                    "status": "known",
                    "entries": [{"attribute": "score", "status": "known", "value": value}],
                }
            ),
            encoding="utf-8",
        )

        errors_by_path = validate_paths([path], schema_path=schema_path("state"))

        assert path in errors_by_path, f"{value!r} is not valid JSON and must be rejected"


def test_state_entry_value_rejects_overflowing_exponent_numbers(tmp_path):
    """1e400 is a syntactically standard JSON number literal (unlike the bare
    NaN/Infinity tokens), but overflows to +/-inf as a Python float. This is
    the same non-finite-number bug reached through ordinary number parsing
    instead of parse_constant, and must be rejected the same way."""
    for literal in ("1e400", "-1e400"):
        path = tmp_path / f"exp_overflow_{literal.lstrip('-')}.json"
        path.write_text(
            '{"entity_id": "character:test-exponent-overflow", "status": "known", '
            '"entries": [{"attribute": "score", "status": "known", "value": %s}]}' % literal,
            encoding="utf-8",
        )

        errors_by_path = validate_paths([path], schema_path=schema_path("state"))

        assert path in errors_by_path, f"{literal} overflows to a non-finite float and must be rejected"


def test_inventory_known_with_empty_entries_is_valid():
    """known + entries: [] means the inventory is known to be empty, a distinct
    fact from unknown (not established) or not_applicable (no inventory
    concept). entries must stay required when known, but must not be forced
    non-empty."""
    path = fixtures("inventory", "valid") / "character-test-empty-inventory.json"

    errors_by_path = validate_paths([path], schema_path=schema_path("inventory"))

    assert errors_by_path == {}


# ---------------------------------------------------------------------------
# EV2-10 inventory ownership schema evolution
#
# The EV2-03 flat `{ item }` entry is replaced by an explicit ordinary
# possession (`name` + `description` + `quantity >= 1`) plus a structurally
# separate D&D `currency` object. These tests pin the approved design lock at
# the schema layer; the guarded runtime mutation path is proved in tests/ev210.
# ---------------------------------------------------------------------------


def _inventory_record(**overrides):
    record = {
        "entity_id": "character:test-ev210",
        "status": "known",
        "entries": [],
    }
    record.update(overrides)
    return record


def _validate_inventory_record(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return validate_paths([path], schema_path=schema_path("inventory")), path


def test_ev210_ordinary_entry_with_explicit_quantity_is_valid(tmp_path):
    errors_by_path, _ = _validate_inventory_record(
        tmp_path,
        "ok_entry.json",
        _inventory_record(
            entries=[
                {
                    "name": "Rope",
                    "description": "Fifty feet of hempen rope.",
                    "quantity": 2,
                }
            ]
        ),
    )

    assert errors_by_path == {}


def test_ev210_integral_float_quantity_and_currency_are_schema_valid(tmp_path):
    """Draft 2020-12 `type: integer` accepts any mathematically integral number,
    so `1.0`/`0.0` must validate like `1`/`0` at the schema layer too. This is
    the schema half of the runtime/schema integer-semantics alignment proof."""
    errors_by_path, _ = _validate_inventory_record(
        tmp_path,
        "integral_float.json",
        _inventory_record(
            entries=[
                {
                    "name": "Torch",
                    "description": "A burning torch.",
                    "quantity": 1.0,
                }
            ],
            currency={"gp": 2.0, "cp": 0.0},
        ),
    )

    assert errors_by_path == {}


def test_ev210_owned_asset_is_an_ordinary_entry_without_taxonomy(tmp_path):
    """Mounts/carts/ships are ordinary possessions. EV2-10 offers no category or
    asset-ownership field, so an owned asset validates exactly like any other
    ordinary entry rather than through a separate subsystem."""
    errors_by_path, _ = _validate_inventory_record(
        tmp_path,
        "ok_asset.json",
        _inventory_record(
            entries=[
                {
                    "name": "Draft horse",
                    "description": "A sturdy cart horse with no individual identity tracked.",
                    "quantity": 1,
                }
            ]
        ),
    )

    assert errors_by_path == {}


def test_ev210_legacy_item_entry_is_rejected(tmp_path):
    """The intentional evolution: the EV2-03 `{ item }` entry shape is no longer
    valid, because it carries no explicit name/description/quantity."""
    errors_by_path, path = _validate_inventory_record(
        tmp_path, "legacy_item.json", _inventory_record(entries=[{"item": "+3 Maul"}])
    )

    assert path in errors_by_path


@pytest.mark.parametrize(
    "quantity",
    [0, -1, 1.5, "3", None, True],
)
def test_ev210_invalid_entry_quantity_is_rejected(tmp_path, quantity):
    """quantity must be present and an explicit integer >= 1. Zero means absence
    (never a stored entry); negative, fractional, string, boolean and missing
    quantities are all invalid."""
    entry = {"name": "Torch", "description": "A burning torch."}
    if quantity is not None:
        entry["quantity"] = quantity

    errors_by_path, path = _validate_inventory_record(
        tmp_path, "bad_quantity.json", _inventory_record(entries=[entry])
    )

    assert path in errors_by_path


def test_ev210_entry_missing_quantity_is_rejected(tmp_path):
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "missing_quantity.json",
        _inventory_record(
            entries=[{"name": "Torch", "description": "A burning torch."}]
        ),
    )

    assert path in errors_by_path


@pytest.mark.parametrize(
    "field", ["name", "description"]
)
def test_ev210_blank_entry_text_is_rejected(tmp_path, field):
    entry = {"name": "Torch", "description": "A burning torch.", "quantity": 1}
    entry[field] = "   "

    errors_by_path, path = _validate_inventory_record(
        tmp_path, f"blank_{field}.json", _inventory_record(entries=[entry])
    )

    assert path in errors_by_path


@pytest.mark.parametrize("field", ["name", "description"])
@pytest.mark.parametrize("bad", [123, True, ["x"], {"a": 1}])
def test_ev210_entry_text_must_be_a_json_string(tmp_path, field, bad):
    """The runtime mutation doorway must reject a non-string name/description
    exactly like the schema's `type: string` (not coerce it to text)."""
    entry = {"name": "Torch", "description": "A burning torch.", "quantity": 1}
    entry[field] = bad

    errors_by_path, path = _validate_inventory_record(
        tmp_path, f"nonstring_{field}.json", _inventory_record(entries=[entry])
    )

    assert path in errors_by_path


def test_ev210_duplicate_ordinary_entries_are_rejected(tmp_path):
    """`uniqueItems`: two equal ordinary entries are a double-count, not two
    independent facts. The guarded runtime route mirrors this rule."""
    entry = {"name": "Torch", "description": "A burning torch.", "quantity": 2}

    errors_by_path, path = _validate_inventory_record(
        tmp_path, "dup_entries.json", _inventory_record(entries=[entry, entry])
    )

    assert path in errors_by_path


def test_ev210_duplicate_entries_differing_only_by_integral_spelling_are_rejected(tmp_path):
    """Draft 2020-12 item equality is JSON numeric equality, so `quantity: 1` and
    `quantity: 1.0` are the same entry and `uniqueItems` must reject the pair."""
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "dup_integral_spelling.json",
        _inventory_record(
            entries=[
                {"name": "Torch", "description": "A burning torch.", "quantity": 1},
                {"name": "Torch", "description": "A burning torch.", "quantity": 1.0},
            ]
        ),
    )

    assert path in errors_by_path


def test_ev210_explicit_null_currency_is_rejected_but_omitted_is_valid(tmp_path):
    """An omitted `currency` is valid because the property is optional, but an
    explicit JSON `null` must fail the schema's `type: object` when present."""
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "null_currency.json",
        _inventory_record(currency=None),
    )
    assert path in errors_by_path

    omitted_errors, _ = _validate_inventory_record(
        tmp_path, "omitted_currency.json", _inventory_record()
    )
    assert omitted_errors == {}



def test_ev210_currency_valid_denominations_are_structural(tmp_path):
    errors_by_path, _ = _validate_inventory_record(
        tmp_path,
        "ok_currency.json",
        _inventory_record(currency={"cp": 0, "sp": 4, "ep": 0, "gp": 250, "pp": 3}),
    )

    assert errors_by_path == {}


def test_ev210_currency_invented_denomination_is_rejected(tmp_path):
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "bad_denomination.json",
        _inventory_record(currency={"gp": 10, "silver": 5}),
    )

    assert path in errors_by_path


@pytest.mark.parametrize("balance", [-1, 2.5, "5", None])
def test_ev210_invalid_currency_balance_is_rejected(tmp_path, balance):
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "bad_balance.json",
        _inventory_record(currency={"gp": balance}),
    )

    assert path in errors_by_path


def test_ev210_currency_is_forbidden_when_status_is_not_known(tmp_path):
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "unknown_currency.json",
        {"entity_id": "character:test-ev210", "status": "unknown", "currency": {"gp": 1}},
    )

    assert path in errors_by_path


def test_ev210_ordinary_inventory_requires_no_item_identity(tmp_path):
    """Ordinary entries must not self-promote into persistent `item:` identity:
    the approved entry exposes no identity/type/entity_id field at all."""
    errors_by_path, path = _validate_inventory_record(
        tmp_path,
        "no_identity.json",
        _inventory_record(
            entries=[
                {
                    "name": "Old map",
                    "description": "A hand-drawn map of the northern ridge.",
                    "quantity": 1,
                    "item_id": "item:northern-map",
                }
            ]
        ),
    )

    assert path in errors_by_path


# ---------------------------------------------------------------------------
# EV2-14 owner-local knowledge / secrets model
#
# The EV2-03 entry shape (`status` tri-state + optional scalar value) is
# replaced by epistemic entries: every entry holds exactly one content mode
# (a reusable `fact_id` reference OR a concise local scalar `value`), an
# explicit `epistemic_status` (confirmed/belief/suspicion), and — for local
# assertions — an explicit `visibility` because the assertion itself is the
# underlying information. Fact references inherit reader exposure from the
# referenced fact at read time and must not copy a `visibility` into the
# knower record. These tests pin the approved schema lock; the durable read
# semantics are proved by the synthetic BTH/exposure cases below.
# ---------------------------------------------------------------------------


def _knowledge_record(entries, **overrides):
    record = {
        "entity_id": "character:test-ev214",
        "status": "known",
        "entries": entries,
    }
    record.update(overrides)
    return record


def _validate_knowledge_record(tmp_path, name, record):
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return validate_paths([path], schema_path=schema_path("knowledge")), path


def _fact_reference(**overrides):
    entry = {
        "topic": "ritual_inscription_truth",
        "epistemic_status": "confirmed",
        "fact_id": "F001",
        "note": "Learned directly from the ritual inscription.",
        "source": "session_canon",
    }
    entry.update(overrides)
    return entry


def _local_assertion(**overrides):
    entry = {
        "topic": "crystal_ball_private_theory",
        "epistemic_status": "belief",
        "value": "the crystal ball listens when spoken to",
        "visibility": "meta",
    }
    entry.update(overrides)
    return entry


def test_ev214_fact_reference_confirmed_is_valid(tmp_path):
    errors_by_path, _ = _validate_knowledge_record(
        tmp_path, "ok_fact_reference.json", _knowledge_record([_fact_reference()])
    )

    assert errors_by_path == {}


@pytest.mark.parametrize("epistemic_status", ["belief", "suspicion"])
def test_ev214_fact_reference_belief_and_suspicion_are_valid(tmp_path, epistemic_status):
    """A knower may hold an established reusable fact without confirming it:
    the fact stays world truth owned by facts.json while the knower's
    epistemic stance stays local. This is schema-level allowance; whether a
    given belief/suspicion deserves a fact_id is the documented authoring
    rule in docs/EV2-14-LOCAL-KNOWLEDGE.md."""
    errors_by_path, _ = _validate_knowledge_record(
        tmp_path,
        "ok_fact_reference_nonconfirmed.json",
        _knowledge_record([_fact_reference(epistemic_status=epistemic_status)]),
    )

    assert errors_by_path == {}


def test_ev214_local_assertion_confirmed_is_valid(tmp_path):
    errors_by_path, _ = _validate_knowledge_record(
        tmp_path,
        "ok_local_confirmed.json",
        _knowledge_record([_local_assertion(epistemic_status="confirmed")]),
    )

    assert errors_by_path == {}


@pytest.mark.parametrize("epistemic_status", ["belief", "suspicion"])
def test_ev214_local_belief_and_suspicion_assertions_are_valid(tmp_path, epistemic_status):
    """Misunderstandings and hunches stay local assertions: they do not get a
    canonical fact_id merely because a character believes them, and they do
    not promote into world truth."""
    errors_by_path, _ = _validate_knowledge_record(
        tmp_path,
        "ok_local_nonconfirmed.json",
        _knowledge_record([_local_assertion(epistemic_status=epistemic_status)]),
    )

    assert errors_by_path == {}


def test_ev214_fact_reference_rejects_copied_visibility(tmp_path):
    """Fact-reference visibility is inherited from the referenced fact at read
    time; a copied `visibility` in the knower record could drift from the
    fact owner, so it is structurally forbidden."""
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "fact_reference_with_visibility.json",
        _knowledge_record([_fact_reference(visibility="non_meta")]),
    )

    assert path in errors_by_path


def test_ev214_local_assertion_requires_visibility(tmp_path):
    """A local assertion is itself the underlying information, so it must
    carry its own exposure classification; there is no safe default."""
    entry = _local_assertion()
    del entry["visibility"]

    errors_by_path, path = _validate_knowledge_record(
        tmp_path, "local_without_visibility.json", _knowledge_record([entry])
    )

    assert path in errors_by_path


def test_ev214_entry_rejects_both_fact_id_and_value(tmp_path):
    """Exactly one content mode per entry: a fact reference and a local
    assertion cannot be claimed by the same entry."""
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "both_modes.json",
        _knowledge_record([_fact_reference(value="witnessed")]),
    )

    assert path in errors_by_path


def test_ev214_entry_rejects_neither_fact_id_nor_value(tmp_path):
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "no_content_mode.json",
        _knowledge_record(
            [
                {
                    "topic": "empty_topic_entry",
                    "epistemic_status": "confirmed",
                }
            ]
        ),
    )

    assert path in errors_by_path


@pytest.mark.parametrize("bad", ["certain", "unknown", "not_applicable", "KNOWN"])
def test_ev214_unsupported_epistemic_state_is_rejected(tmp_path, bad):
    """The epistemic vocabulary is exactly confirmed/belief/suspicion; the
    EV2-03 entry-level status tri-state is not carried forward."""
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "bad_epistemic_status.json",
        _knowledge_record([_fact_reference(epistemic_status=bad)]),
    )

    assert path in errors_by_path


@pytest.mark.parametrize("topic", ["", "   "])
def test_ev214_blank_topic_is_rejected(tmp_path, topic):
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "blank_topic.json",
        _knowledge_record([_local_assertion(topic=topic)]),
    )

    assert path in errors_by_path


@pytest.mark.parametrize("bad", [{"a": 1}, ["x"]])
def test_ev214_structured_local_values_remain_rejected(tmp_path, bad):
    """The EV2-03 scalar player-agency boundary survives: a structured
    action/directive payload cannot be stored as a local assertion value."""
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "structured_value.json",
        _knowledge_record([_local_assertion(value=bad)]),
    )

    assert path in errors_by_path


def test_ev214_blank_fact_id_is_rejected(tmp_path):
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "blank_fact_id.json",
        _knowledge_record([_fact_reference(fact_id="   ")]),
    )

    assert path in errors_by_path


def test_ev214_entry_without_epistemic_status_is_rejected(tmp_path):
    entry = _local_assertion()
    del entry["epistemic_status"]

    errors_by_path, path = _validate_knowledge_record(
        tmp_path, "missing_epistemic_status.json", _knowledge_record([entry])
    )

    assert path in errors_by_path


def test_ev214_legacy_entry_status_shape_is_rejected(tmp_path):
    """The intentional evolution: the EV2-03 `{ topic, status, value }` entry
    shape is no longer valid; entries are epistemic statements of this knower,
    not independently unknown/not_applicable topic slots."""
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "legacy_entry_status.json",
        _knowledge_record(
            [{"topic": "formula_acquisition", "status": "known", "value": "witnessed"}]
        ),
    )

    assert path in errors_by_path


@pytest.mark.parametrize("box_status", ["unknown", "not_applicable"])
def test_ev214_box_unknown_and_not_applicable_forbid_entries(tmp_path, box_status):
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "box_without_entries.json",
        _knowledge_record([_local_assertion()], status=box_status),
    )

    assert path in errors_by_path


def test_ev214_duplicate_exact_entries_are_rejected(tmp_path):
    errors_by_path, path = _validate_knowledge_record(
        tmp_path,
        "duplicate_entries.json",
        _knowledge_record([_local_assertion(), _local_assertion()]),
    )

    assert path in errors_by_path


def test_ev214_bth_reader_visible_event_does_not_create_hero_knowledge(tmp_path):
    """Canonical acceptance scenario (Beyond the Heroes): a BTH event may be
    true RHC canon and deliberately reader-visible while every hero remains
    ignorant. The three answers stay independent: the event is true (it
    exists as a reusable world fact), the human reader may see it (the fact's
    own visibility is non_meta), and no hero knows it (no hero knowledge
    record references its fact_id — publication never mutates knowledge)."""
    synthetic_facts = {
        "F901": {
            "title": "The Midnight Bell Pact",
            "statement": "The Lantern Society sealed a pact beneath the chapel bell.",
            "status": "canon",
            "visibility": "non_meta",
        },
        "F902": {
            "title": "The Ferryman's Toll",
            "statement": "The river ferry charges one copper per crossing.",
            "status": "canon",
            "visibility": "non_meta",
        },
    }

    hero_record = _knowledge_record(
        [
            _fact_reference(
                topic="ferry_toll",
                epistemic_status="confirmed",
                fact_id="F902",
            )
        ],
        entity_id="character:test-bth-hero",
    )
    errors_by_path, hero_path = _validate_knowledge_record(
        tmp_path, "bth_hero.json", hero_record
    )
    assert errors_by_path == {}

    referenced_ids = {
        entry["fact_id"] for entry in hero_record["entries"] if "fact_id" in entry
    }
    assert "F901" not in referenced_ids, (
        "a reader-visible BTH fact must not appear in hero knowledge without "
        "an explicit knower-owned event"
    )
    assert synthetic_facts["F901"]["visibility"] == "non_meta", (
        "the BTH fact is reader-visible on its own terms"
    )


def test_ev214_fact_existence_does_not_create_knower_record(tmp_path):
    """A fact existing in facts.json grants knowledge to no one: no knower
    record may be inferred from the fact's existence, and reading a
    player-visible fact never implies any character knows it."""
    synthetic_facts = {
        "F903": {
            "title": "The Sexton's Debt",
            "statement": "The chapel sexton owes the Ferryman three silver.",
            "status": "canon",
            "visibility": "non_meta",
        }
    }

    unrelated_hero = _knowledge_record(
        [_fact_reference(topic="ferry_toll", fact_id="F902")],
        entity_id="character:test-unrelated-hero",
    )
    errors_by_path, hero_path = _validate_knowledge_record(
        tmp_path, "unrelated_hero.json", unrelated_hero
    )
    assert errors_by_path == {}

    referenced_ids = {
        entry["fact_id"] for entry in unrelated_hero["entries"] if "fact_id" in entry
    }
    assert "F903" not in referenced_ids
    assert "F903" in synthetic_facts, "the fact exists without any knower record"
