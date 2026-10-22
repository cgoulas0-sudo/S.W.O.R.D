"""EV2-12 first real RHC item canary proof.

Covers three things:
  * the first real Entity V2 item identity (`item:vampire`) validates against
    `schemas/entity.schema.json` and is graded separately from the synthetic
    fixtures;
  * the Vampire mechanics are normalized to D&D 2024 / 5.5e wording and the
    duplicated `villain/gork.md` wording stays consistent;
  * the one-item admission script is narrow, inert, and — against real
    PostgreSQL on the full RT01/RT02/RT03/RT04/HWB-02/EV2-10/EV2-11 spine —
    admits exactly `item:vampire` with unknown ownership, refuses a second
    admission or execution without explicit approval, and leaves the EV2-11
    non-minting gameplay route intact.

The runtime tests skip (never mock) when no real PostgreSQL server is reachable.
"""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "rt04"))

from validate_entities import validate_paths  # noqa: E402
import rt04_util as u  # noqa: E402

ENTITY_SCHEMA = ROOT / "schemas" / "entity.schema.json"
ENTITIES_DIR = ROOT / "entities"
ITEMS_DIR = ENTITIES_DIR / "items"
VAMPIRE_ENTITY = ITEMS_DIR / "vampire.json"
VAMPIRE_MD = ROOT / "inventory" / "weapons" / "vampire.md"
GORK_MD = ROOT / "villain" / "gork.md"
ADMISSION_SQL = ROOT / "supabase" / "canaries" / "ev212_vampire_admission.sql"
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
WORKFLOW = ROOT / ".github" / "workflows" / "entity-v2-identity.yml"

VAMPIRE = "item:vampire"
GORK = "character:gork"
HERO = "character:test-hero"
FANIS = "character:test-fanis"
SHIELD = "item:test-shield"


# ---------------------------------------------------------------------------
# Real identity validation
# ---------------------------------------------------------------------------

def test_real_item_identity_validates_against_entity_schema():
    assert validate_paths([VAMPIRE_ENTITY], schema_path=ENTITY_SCHEMA) == {}

    record = json.loads(VAMPIRE_ENTITY.read_text(encoding="utf-8"))
    assert record == {
        "entity_id": VAMPIRE,
        "entity_type": "item",
        "display_name": "Vampire",
    }


def test_real_item_directory_holds_exactly_one_identity():
    assert sorted(p.name for p in ITEMS_DIR.glob("*.json")) == ["vampire.json"]
    assert (ENTITIES_DIR / "README.md").is_file()


def test_real_identity_rejects_a_duplicate_in_the_same_batch(tmp_path):
    duplicate = tmp_path / "vampire-duplicate.json"
    duplicate.write_text(
        json.dumps({"entity_id": VAMPIRE, "entity_type": "item", "display_name": "Vampire Again"}),
        encoding="utf-8",
    )

    errors_by_path = validate_paths([VAMPIRE_ENTITY, duplicate], schema_path=ENTITY_SCHEMA)

    assert duplicate in errors_by_path
    assert any("duplicates" in error for error in errors_by_path[duplicate])


@pytest.mark.parametrize(
    "record",
    [
        {"entity_id": "item:Vampire", "entity_type": "item", "display_name": "Vampire"},
        {"entity_id": VAMPIRE, "entity_type": "creature", "display_name": "Vampire"},
        {"entity_id": VAMPIRE, "entity_type": "item"},
        {"entity_id": VAMPIRE, "entity_type": "item", "display_name": "   "},
        {"entity_id": VAMPIRE, "entity_type": "item", "display_name": "Vampire", "owner": HERO},
    ],
)
def test_real_identity_rejects_malformed_item_data(tmp_path, record):
    malformed = tmp_path / "vampire-malformed.json"
    malformed.write_text(json.dumps(record), encoding="utf-8")

    assert validate_paths([malformed], schema_path=ENTITY_SCHEMA)


def test_ci_validates_the_real_canary_separately_from_synthetic_fixtures():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python scripts/validate_entities.py entities/items" in workflow
    assert "python scripts/validate_entities.py tests/fixtures/entities/valid" in workflow
    assert "pytest tests/ev212/test_first_real_item_canary.py" in workflow


# ---------------------------------------------------------------------------
# Mechanics normalization
# ---------------------------------------------------------------------------

LEGACY_VAMPIRE_WORDING = (
    "Versatile",
    "Compatible",
    "19–20",
    "19-20",
    "×2",
    "15 seconds",
    "Fighters",
    "Paladins",
    "Barbarians",
    "Warlocks",
)


def test_vampire_mechanics_are_normalized_to_2024_wording():
    text = VAMPIRE_MD.read_text(encoding="utf-8")

    for legacy in LEGACY_VAMPIRE_WORDING:
        assert legacy not in text, f"legacy Vampire wording still present: {legacy!r}"

    for required in (
        "Two-Handed",
        "Heavy",
        "2d6 Slashing",
        "+3",
        "Attunement",
        "Legendary",
        "normal D&D critical-hit rules",
        "Blood Hunger",
        "Executioner",
        "Blood Parry",
        "Blood Memory",
        "second turn",
    ):
        assert required in text, f"normalized Vampire wording missing: {required!r}"

    # The three-stack escalation is preserved, not redesigned.
    assert "Maximum **3 Blood Stacks**" in text


def test_gork_duplicate_vampire_mechanics_are_consistent():
    text = GORK_MD.read_text(encoding="utf-8")

    for legacy in ("19–20", "19-20", "15 seconds", "×2"):
        assert legacy not in text, f"legacy Gork/Vampire wording still present: {legacy!r}"

    assert "normal D&D critical-hit rules" in text
    assert "second turn" in text
    # Gork keeps deferring all Vampire mechanics to the dedicated weapon file.
    assert "inventory/weapons/vampire.md" in text


# ---------------------------------------------------------------------------
# Admission script (repository content)
# ---------------------------------------------------------------------------

def test_admission_script_is_one_item_only_and_seeds_unknown_owner_and_known_gork_holder():
    sql = ADMISSION_SQL.read_text(encoding="utf-8")

    item_literals = set(re.findall(r"item:[a-z0-9]+(?:-[a-z0-9]+)*", sql))
    assert item_literals == {VAMPIRE}

    # Ownership is preserved as unknown; the known current holder is the
    # already-established campaign character Gork, referenced by ID only.
    assert "'owner_entity_id', null" in sql
    assert f"'holder_entity_id', {GORK!r}" in sql
    # No character:gork Entity V2 record is created or admitted by this script.
    assert "entities/" not in sql
    assert "character:gork.json" not in sql


def test_admission_script_cannot_execute_automatically():
    sql = ADMISSION_SQL.read_text(encoding="utf-8")

    assert ADMISSION_SQL.parent.name == "canaries"
    assert not (MIGRATIONS_DIR / ADMISSION_SQL.name).exists()
    for migration in MIGRATIONS_DIR.glob("*.sql"):
        assert "ev212_vampire_admission" not in migration.read_text(encoding="utf-8")
    assert "ev212_vampire_admission" not in WORKFLOW.read_text(encoding="utf-8")

    # Explicit human approval gate, no gameplay minting route, and the existing
    # RT01 candidate-generation lifecycle rather than an in-place published write.
    assert "rhc.ev212_vampire_admission_approved" in sql
    assert "raise exception" in sql
    assert "mutate_item_custody" not in sql
    assert "stage_campaign_state" not in sql
    assert "begin_campaign_save" in sql
    assert "publish_campaign_save" in sql
    # The EV2-11 validator is used to prove the existing and resulting collections.
    assert "_rhc_validate_item_custody_collection" in sql


# ---------------------------------------------------------------------------
# Admission script (runtime proof on real PostgreSQL)
# ---------------------------------------------------------------------------

def _approve_admission(db):
    with db.cursor() as cur:
        cur.execute("select set_config('rhc.ev212_vampire_admission_approved', 'on', false)")


def _clear_approval(db):
    with db.cursor() as cur:
        cur.execute("select set_config('rhc.ev212_vampire_admission_approved', '', false)")


def _execute_script(db):
    with db.cursor() as cur:
        cur.execute(ADMISSION_SQL.read_text(encoding="utf-8"))


def _rollback(db):
    """Clear an aborted explicit transaction.

    The admission script opens its own `begin; ... commit;` block, so a failed
    execution leaves the connection in an aborted transaction. `db.rollback()`
    is a no-op in autocommit mode, so issue an explicit ROLLBACK statement.
    """
    try:
        with db.cursor() as cur:
            cur.execute("rollback")
    except Exception:  # pragma: no cover - defensive cleanup
        pass


def _execute_script_error(db):
    try:
        _execute_script(db)
    except Exception as exc:  # noqa: BLE001 - fail-closed proof
        _rollback(db)
        return str(exc)
    _rollback(db)
    raise AssertionError("expected the admission script to fail closed")


def _run_admission(db):
    """Execute the admission script once; leaves the new generation mirror-pending."""
    _approve_admission(db)
    _execute_script(db)


def _complete_admission(db):
    """Admission plus the external mirror-confirmation step a worker would perform."""
    _run_admission(db)
    u.confirm_mirror(db)


def _admission_error(db):
    _approve_admission(db)
    return _execute_script_error(db)


def _published_custody(db):
    return u.published_state(db).get("item_custody") or []


def _published_generation(db):
    return u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )


def _seed_published_custody(db, records):
    """Test-only break-glass: seed published item_custody truth directly."""
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select cr.published_generation, 'item_custody', %s::jsonb, now(), now() "
        "from public.campaign_runtime cr where cr.id = 1 "
        "on conflict (generation, key) do update "
        "set value = excluded.value, updated_at = now()",
        (json.dumps(records),),
    )


def _request(item=VAMPIRE, owner=HERO, holder=HERO):
    return {
        "item_id": item,
        "controller": {"kind": "mainrun"},
        "owner_entity_id": owner,
        "holder_entity_id": holder,
    }


def _mutate(db, token, request):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.mutate_item_custody(%s, %s::jsonb)",
                (token, json.dumps(request)),
            )
            value = cur.fetchone()[0]
        finally:
            cur.execute("reset role")
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    try:
        _mutate(db, token, request)
    except Exception as exc:  # noqa: BLE001 - fail-closed proof
        return str(exc)
    raise AssertionError("expected mutate_item_custody to fail closed")


def test_admission_script_admits_unknown_owner_and_known_gork_holder(db):
    _complete_admission(db)

    assert _published_custody(db) == [
        {"item_id": VAMPIRE, "owner_entity_id": None, "holder_entity_id": GORK}
    ]


def test_admission_uses_candidate_generation_and_never_rewrites_published_in_place(db):
    before = _published_generation(db)

    _run_admission(db)

    after = _published_generation(db)
    assert after == before + 1

    # The pre-admission generation is untouched: no item_custody row was written
    # into it in place.
    assert (
        u.scalar(
            db,
            "select count(*) from public.campaign_state_generations "
            "where generation = %s and key = 'item_custody'",
            (before,),
        )
        == 0
    )

    # The new generation is published and mirror-pending for the existing
    # external runtime-published worker.
    assert u.pending(db)["generation"] == after
    assert _published_custody(db) == [
        {"item_id": VAMPIRE, "owner_entity_id": None, "holder_entity_id": GORK}
    ]


def test_admission_script_refuses_a_second_admission(db):
    _complete_admission(db)

    error = _admission_error(db)

    assert "already has an admitted custody record" in error
    assert len(_published_custody(db)) == 1


def test_admission_script_refuses_without_explicit_approval(db):
    _clear_approval(db)

    error = _execute_script_error(db)

    assert "inert until a human DM/SAVE operator" in error
    assert _published_custody(db) == []
    assert _published_generation(db) == 0


def test_admission_fails_closed_on_malformed_unrelated_custody(db):
    malformed = {"item_id": SHIELD, "owner_entity_id": HERO}
    _seed_published_custody(db, [malformed])

    error = _admission_error(db)

    assert (
        "holder_entity_id" in error
        or "EV2-11 contract" in error
        or "requires" in error
    )
    # Nothing was appended and no new generation was published.
    assert _published_custody(db) == [malformed]
    assert _published_generation(db) == 0


def test_admission_fails_closed_on_duplicate_unrelated_custody(db):
    duplicates = [
        {"item_id": SHIELD, "owner_entity_id": HERO, "holder_entity_id": HERO},
        {"item_id": SHIELD, "owner_entity_id": FANIS, "holder_entity_id": FANIS},
    ]
    _seed_published_custody(db, duplicates)

    error = _admission_error(db)

    assert "duplicate" in error
    assert _published_generation(db) == 0


def test_admitted_item_can_be_updated_by_non_minting_gameplay(db):
    _complete_admission(db)

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(owner=HERO, holder=HERO))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert result["custody"] == {
        "item_id": VAMPIRE,
        "owner_entity_id": HERO,
        "holder_entity_id": HERO,
    }
    assert _published_custody(db) == [result["custody"]]


def test_gameplay_cannot_mint_a_second_item_after_admission(db):
    _complete_admission(db)

    _published, _staging, token, _expires = u.begin_save(db)
    error = _mutate_error(db, token, _request(item="item:bell"))

    assert "no admitted custody record" in error
    assert [r["item_id"] for r in _published_custody(db)] == [VAMPIRE]
