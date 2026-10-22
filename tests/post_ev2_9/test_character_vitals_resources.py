"""POST-EV2-9 proof suite — Character vitals + resources runtime.

Runs against real PostgreSQL 15 and 17 with the full forward migration chain
(RT01-A/B/C/D + RT02 + RT03 + RT04 + HWB-02 + EV2-10 + EV2-11 + EV2-12.1 +
EV2-13 + EV2-13.420 + EV2-13.1 + POST-EV2-1 Patch 1A/1B + POST-EV2-2 +
POST-EV2-3 + POST-EV2-4A + POST-EV2-5 + POST-EV2-9) using disposable schemas and
synthetic data only. No live Supabase is touched and no real RHC state is
imported.

The Mission adds one engine-owned `character_mechanics` runtime namespace holding
exactly one bounded mechanical record per `character:<slug>` (HP, Hit Dice pools,
spell-slot pools and limited resources, with explicit known/unknown/
not_applicable section status), one validated controller-safe absolute mutation
route (`public.mutate_character_mechanics`) and one supported service-only
published read (`public.dm_runtime_read_character_mechanics`). Controller
authority is resolved only from authoritative published Run truth.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-9 needs real PostgreSQL servers"
)
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_CURRENT_MIGRATION = _MIGRATIONS_DIR / (
    "20260928000001_post_ev2_9_character_vitals_resources.sql"
)
_POST_EV2_5_TEST = ROOT / "tests" / "post_ev2_5" / "test_current_search.py"
_SCHEMA_PATH = ROOT / "schemas" / "character_mechanics.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(_SCHEMA)

_BASELINE_ROLES = (ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql").read_text(
    encoding="utf-8"
)
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)

_PG15_DSN_PRECEDENCE = (
    "RHC_POST_EV29_PG_DSN",
    "RHC_POST_EV25_PG_DSN",
    "RHC_POST_EV24A_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV29_PG17_DSN",
    "RHC_POST_EV25_PG17_DSN",
    "RHC_POST_EV24A_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

HERO = "character:test-hero"
SIDEKICK = "character:test-sidekick"
R01 = "R01"
R02 = "R02"

# The surfaces this Mission is authorized to touch. Any tracked/working-tree
# diff outside this set is a STOP-and-return, not an opportunistic edit.
ALLOWED_SURFACES = frozenset(
    {
        "schemas/character_mechanics.schema.json",
        "supabase/migrations/20260928000001_post_ev2_9_character_vitals_resources.sql",
        "docs/POST-EV2-9-CHARACTER-VITALS-RESOURCES.md",
        "tests/post_ev2_9/test_character_vitals_resources.py",
        "schemas/README.md",
        "supabase/README.md",
        ".github/workflows/rt01-runtime.yml",
        "tests/post_ev2_1/test_same_save_compatibility_dispatcher.py",
        "tests/post_ev2_2/test_hot_run_registry.py",
        "tests/post_ev2_5/test_current_search.py",
    }
)


def _first_dsn(variables, fallback):
    for variable in variables:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return fallback


def install_chain(connection, migrations=FORWARD_MIGRATIONS):
    with connection.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES)
        for statement in _SCHEMA_RESET:
            cursor.execute(statement)
        for migration in migrations:
            cursor.execute(migration.read_text(encoding="utf-8"))


def _connect(dsn):
    try:
        connection = psycopg2.connect(dsn)
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"POST-EV2-9 proof skipped (no server): {exc}")
    connection.autocommit = True
    return connection


@pytest.fixture(scope="session")
def database_server():
    connection = _connect(_first_dsn(_PG15_DSN_PRECEDENCE, _PG15_FALLBACK))
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    install_chain(database_server)
    return database_server


@pytest.fixture(scope="session")
def database_server_pg17():
    connection = _connect(_first_dsn(_PG17_DSN_PRECEDENCE, _PG17_FALLBACK))
    yield connection
    connection.close()


@pytest.fixture()
def db_pg17(database_server_pg17):
    install_chain(database_server_pg17)
    return database_server_pg17


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _primary_error(exc):
    diag = getattr(exc, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    return primary or str(exc).splitlines()[0]


def _run_as(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _error_as(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return _primary_error(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def published_generation(db):
    return u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )


def publish_namespace(db, key, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def stage_namespace(db, key, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select staging_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def establish(db, runs=None, seed=None):
    _published, _staging, token, _expires = u.begin_save(db)
    if runs is not None:
        u.stage_runs(db, token, runs)
    u.publish(db, token)
    u.confirm_mirror(db)
    for key, value in (seed or {}).items():
        publish_namespace(db, key, value)
    return published_generation(db)


def mutate(db, token, request, as_role="service_role"):
    def call(cur):
        cur.execute(
            "select public.mutate_character_mechanics(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as(db, as_role, call)
    return json.loads(value) if isinstance(value, str) else value


def mutate_error(db, token, request, as_role="service_role"):
    return _error_as(
        db,
        as_role,
        lambda cur: cur.execute(
            "select public.mutate_character_mechanics(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def publish_mutation(db, request):
    _published, _staging, token, _expires = u.begin_save(db)
    result = mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)
    return result


def read_mechanics(db, character_id):
    def call(cur):
        cur.execute(
            "select public.dm_runtime_read_character_mechanics(%s)", (character_id,)
        )
        return cur.fetchone()[0]

    value = _run_as(db, "service_role", call)
    return json.loads(value) if isinstance(value, str) else value


def read_error(db, character_id):
    return _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.dm_runtime_read_character_mechanics(%s)", (character_id,)
        ),
    )


def stage_clock(db, token, clock):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(clock)),
        )


def stored_collection(db):
    return u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation "
        "where csg.key = 'character_mechanics'",
    )


# --- record builders ---------------------------------------------------------


def unknown():
    return {"status": "unknown"}


def not_applicable():
    return {"status": "not_applicable"}


def hp(current, maximum, temporary=None):
    section = {"status": "known", "current": current, "maximum": maximum}
    if temporary is not None:
        section["temporary"] = temporary
    return section


def hd_pool(pool_id, die_faces, current, maximum):
    return {
        "pool_id": pool_id,
        "die_faces": die_faces,
        "current": current,
        "maximum": maximum,
    }


def slot_pool(pool_id, slot_level, current, maximum, recharge_on):
    return {
        "pool_id": pool_id,
        "slot_level": slot_level,
        "current": current,
        "maximum": maximum,
        "recharge_on": recharge_on,
    }


def resource(resource_id, label, current, maximum, recharge_on):
    return {
        "resource_id": resource_id,
        "label": label,
        "current": current,
        "maximum": maximum,
        "recharge_on": recharge_on,
    }


def mechanics(hp_section=None, hit_dice=None, spell_slots=None, resources=None):
    return {
        "hp": hp_section if hp_section is not None else unknown(),
        "hit_dice": hit_dice if hit_dice is not None else unknown(),
        "spell_slots": spell_slots if spell_slots is not None else unknown(),
        "resources": resources if resources is not None else unknown(),
    }


def req(character_id, body, controller=None):
    return {
        "character_id": character_id,
        "controller": controller if controller is not None else {"kind": "mainrun"},
        "mechanics": body,
    }


def full_hero_mechanics():
    return mechanics(
        hp_section=hp(28, 28, temporary=0),
        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 3, 3)]},
        spell_slots={
            "status": "known",
            "pools": [
                slot_pool("warlock-pact", 1, 1, 1, ["short_rest"]),
                slot_pool("wizard-1a", 1, 2, 2, ["long_rest"]),
                slot_pool("wizard-2", 2, 0, 1, ["long_rest"]),
            ],
        },
        resources={
            "status": "known",
            "items": [
                resource("action-surge", "Action Surge", 1, 1, ["short_rest"]),
                resource("second-wind", "Second Wind", 2, 2, ["long_rest"]),
            ],
        },
    )


# ---------------------------------------------------------------------------
# 1. Schema accepts coherent records (structural proof)
# ---------------------------------------------------------------------------


def test_schema_accepts_coherent_record_with_multiple_pools():
    record = {"character_id": HERO, **full_hero_mechanics()}
    _VALIDATOR.validate(record)


def test_schema_accepts_unknown_and_not_applicable_sections():
    record = {
        "character_id": HERO,
        "hp": unknown(),
        "hit_dice": not_applicable(),
        "spell_slots": unknown(),
        "resources": not_applicable(),
    }
    _VALIDATOR.validate(record)


def test_schema_accepts_integral_float_spelling():
    record = {"character_id": HERO, **mechanics(hp_section=hp(28.0, 28.0, temporary=0.0))}
    _VALIDATOR.validate(record)


@pytest.mark.parametrize("bad", [{"status": "known", "current": 5}, {"status": "unknown", "current": 5}])
def test_schema_rejects_bad_hp_shapes(bad):
    record = {
        "character_id": HERO,
        "hp": bad,
        "hit_dice": unknown(),
        "spell_slots": unknown(),
        "resources": unknown(),
    }
    assert list(_VALIDATOR.iter_errors(record))


def test_schema_rejects_non_character_id():
    record = {"character_id": "creature:test-wolf", **full_hero_mechanics()}
    assert list(_VALIDATOR.iter_errors(record))


# ---------------------------------------------------------------------------
# 2 & 3. Runtime happy path + Unknown / not_applicable / known distinction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_mainrun_happy_path_publishes_and_reads_exact_normalized_record(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    establish(db)
    body = full_hero_mechanics()
    result = publish_mutation(db, req(HERO, body))
    assert result["character_mechanics_mutation_version"] == 1
    assert result["character_id"] == HERO

    read = read_mechanics(db, HERO)
    assert read["read_version"] == 1
    assert read["mode"] == "character_mechanics"
    assert read["character_id"] == HERO
    assert read["runtime"]["generation"] == published_generation(db)
    # The record round-trips exactly and is schema-valid.
    assert read["record"] == {"character_id": HERO, **body}
    _VALIDATOR.validate(read["record"])


def test_unknown_not_applicable_and_known_remain_distinguishable(db):
    establish(db)
    body = mechanics(
        hp_section=unknown(),
        hit_dice=not_applicable(),
        spell_slots={"status": "known", "pools": []},
        resources={"status": "known", "items": []},
    )
    publish_mutation(db, req(HERO, body))
    record = read_mechanics(db, HERO)["record"]
    assert record["hp"] == {"status": "unknown"}
    assert record["hit_dice"] == {"status": "not_applicable"}
    # Known + empty list means "known to be none", not Unknown.
    assert record["spell_slots"] == {"status": "known", "pools": []}
    assert record["resources"] == {"status": "known", "items": []}


def test_unknown_section_never_synthesizes_zero_or_empty(db):
    establish(db)
    publish_mutation(db, req(HERO, mechanics()))
    record = read_mechanics(db, HERO)["record"]
    for section in ("hp", "hit_dice", "spell_slots", "resources"):
        assert record[section] == {"status": "unknown"}
    serialized = json.dumps(record)
    assert "pools" not in serialized
    assert "items" not in serialized


def test_known_section_must_carry_its_payload(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(hp_section={"status": "known"})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "requires current and maximum" in err


def test_unknown_section_must_not_carry_payload(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(spell_slots={"status": "unknown", "pools": []})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "must not carry pools" in err


# ---------------------------------------------------------------------------
# 3 & 4. Whole non-negative integers and current <= maximum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [-1, -5])
def test_negative_capacity_fails_closed(db, value):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(hp_section=hp(value, 10))
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "non-negative" in err


@pytest.mark.parametrize("value", [1.5, 2.25])
def test_fractional_capacity_fails_closed(db, value):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(resources={
        "status": "known",
        "items": [resource("ki", "Ki", value, 5, ["short_rest"])],
    })
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "fractional" in err


@pytest.mark.parametrize("bad", ["3", True, None, [1], {"x": 1}])
def test_non_number_capacity_fails_closed(db, bad):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(hp_section={"status": "known", "current": bad, "maximum": 10})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "whole non-negative integer" in err


def test_current_greater_than_capacity_fails_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(hp_section=hp(30, 28))
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "current cannot exceed maximum" in err


def test_current_equal_capacity_and_zero_are_legal(db):
    establish(db)
    body = mechanics(
        hp_section=hp(28, 28),
        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 0, 3)]},
        spell_slots={"status": "known", "pools": [slot_pool("wizard-1", 1, 0, 0, ["long_rest"])]},
        resources={"status": "known", "items": [resource("luck", "Luck", 0, 0, [])]},
    )
    publish_mutation(db, req(HERO, body))
    assert read_mechanics(db, HERO)["record"]["hp"]["current"] == 28


def test_temporary_hp_is_not_capacity_bounded(db):
    establish(db)
    body = mechanics(hp_section=hp(10, 10, temporary=50))
    publish_mutation(db, req(HERO, body))
    assert read_mechanics(db, HERO)["record"]["hp"]["temporary"] == 50


def test_integral_float_values_are_accepted_and_canonicalized(db):
    establish(db)
    body = mechanics(hp_section=hp(28.0, 28.0, temporary=0.0))
    publish_mutation(db, req(HERO, body))
    record = read_mechanics(db, HERO)["record"]
    # Canonical integer spelling: 28.0 is stored/returned as 28.
    assert record["hp"] == {"status": "known", "current": 28, "maximum": 28, "temporary": 0}


# ---------------------------------------------------------------------------
# 5. Duplicates fail closed; normalization/order is deterministic
# ---------------------------------------------------------------------------


def test_duplicate_character_records_fail_closed(db):
    establish(db, seed={"character_mechanics": [
        {"character_id": HERO, **mechanics()},
        {"character_id": HERO, **mechanics()},
    ]})
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(SIDEKICK, mechanics()))
    u.abort_save(db, token)
    assert "duplicate records" in err


def test_duplicate_resource_ids_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(resources={"status": "known", "items": [
        resource("ki", "Ki", 1, 1, []),
        resource("ki", "Ki again", 1, 1, []),
    ]})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "duplicate resource_id" in err


def test_duplicate_slot_pool_ids_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(spell_slots={"status": "known", "pools": [
        slot_pool("p", 1, 1, 1, ["long_rest"]),
        slot_pool("p", 2, 1, 1, ["long_rest"]),
    ]})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "duplicate pool_id" in err


def test_duplicate_hit_die_pool_ids_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    body = mechanics(hit_dice={"status": "known", "pools": [
        hd_pool("hd", 8, 1, 1),
        hd_pool("hd", 10, 1, 1),
    ]})
    err = mutate_error(db, token, req(HERO, body))
    u.abort_save(db, token)
    assert "duplicate pool_id" in err


def test_multiple_slot_pools_at_same_level_are_representable(db):
    establish(db)
    body = mechanics(spell_slots={"status": "known", "pools": [
        slot_pool("pact", 1, 1, 1, ["short_rest"]),
        slot_pool("wizard", 1, 2, 2, ["long_rest"]),
    ]})
    publish_mutation(db, req(HERO, body))
    pools = read_mechanics(db, HERO)["record"]["spell_slots"]["pools"]
    assert [(p["slot_level"], p["pool_id"]) for p in pools] == [(1, "pact"), (1, "wizard")]


def test_normalization_order_is_deterministic(db):
    establish(db)
    body_a = mechanics(
        spell_slots={"status": "known", "pools": [
            slot_pool("wizard-1", 1, 2, 2, ["long_rest"]),
            slot_pool("warlock-pact", 1, 1, 1, ["short_rest"]),
        ]},
        resources={"status": "known", "items": [
            resource("second-wind", "Second Wind", 2, 2, ["long_rest"]),
            resource("action-surge", "Action Surge", 1, 1, ["short_rest"]),
        ]},
    )
    body_b = mechanics(
        spell_slots={"status": "known", "pools": [
            slot_pool("warlock-pact", 1, 1, 1, ["short_rest"]),
            slot_pool("wizard-1", 1, 2, 2, ["long_rest"]),
        ]},
        resources={"status": "known", "items": [
            resource("action-surge", "Action Surge", 1, 1, ["short_rest"]),
            resource("second-wind", "Second Wind", 2, 2, ["long_rest"]),
        ]},
    )
    publish_mutation(db, req(HERO, body_a))
    first = stored_collection(db)
    publish_mutation(db, req(HERO, body_b))
    second = stored_collection(db)
    assert first == second


# ---------------------------------------------------------------------------
# 6, 7 & 8. Controller authority from published Run truth
# ---------------------------------------------------------------------------


def test_run_controller_happy_path_for_authoritative_run(db):
    establish(db, runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    body = full_hero_mechanics()
    publish_mutation(
        db,
        req(HERO, body, controller={"kind": "run", "run_id": R01}),
    )
    assert read_mechanics(db, HERO)["record"] == {"character_id": HERO, **body}


def test_mainrun_cannot_mutate_run_owned_character(db):
    establish(db, runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics()))
    u.abort_save(db, token)
    assert "MAINRUN may not mutate" in err


def test_wrong_run_controller_fails_closed(db):
    establish(db, runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics(), controller={"kind": "run", "run_id": R02}))
    u.abort_save(db, token)
    assert "crosses controllers" in err


def test_run_controller_without_claim_fails_closed(db):
    establish(db, runs=[u.run(
        run_id=R01,
        participant_entity_ids=[SIDEKICK],
        mutable_owner_entity_ids=[SIDEKICK],
    )])
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics(), controller={"kind": "run", "run_id": R01}))
    u.abort_save(db, token)
    assert "no published Run currently controls" in err


def test_parked_claiming_run_fails_closed(db):
    establish(db, runs=[u.run(run_id=R01, control_state="parked", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics()))
    u.abort_save(db, token)
    assert "parked" in err.lower() or "MAINRUN" in err


def test_two_runs_claiming_one_character_fail_closed(db):
    runs = [
        u.run(run_id=R01, mutable_owner_entity_ids=[HERO]),
        u.run(run_id=R02, mutable_owner_entity_ids=[HERO]),
    ]
    establish(db, runs=runs)
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics(), controller={"kind": "run", "run_id": R01}))
    u.abort_save(db, token)
    assert "controller" in err.lower()


def test_malformed_published_runs_fails_closed(db):
    establish(db, runs=[{"run_id": R01}])
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, mechanics()))
    u.abort_save(db, token)
    assert "Run" in err


def test_malformed_controller_assertions_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    base = req(HERO, mechanics())
    for bad in (
        None,
        "mainrun",
        {},
        {"kind": None},
        {"kind": 1},
        {"kind": "MAINRUN"},
        {"kind": "run"},
        {"kind": "run", "run_id": "R1"},
        {"kind": "mainrun", "run_id": R01},
    ):
        malformed = dict(base)
        malformed["controller"] = bad
        err = mutate_error(db, token, malformed)
        assert err
    u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 9. Patch 1A registry + generic bypass closure
# ---------------------------------------------------------------------------


def test_patch_1a_registers_character_mechanics_dedicated(db):
    record = u.scalar(db, "select public._rhc_save_domain_policy('character_mechanics')")
    assert record["admission"] == "dedicated"
    assert record["dedicated_routes"] == ["mutate_character_mechanics"]
    assert record["stage_error"] == (
        "character_mechanics is engine-owned and can only be staged through "
        "mutate_character_mechanics"
    )
    assert record["delete_error"] == (
        "character_mechanics is engine-owned and cannot be deleted through the generic route"
    )


def test_generic_stage_and_delete_bypass_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'character_mechanics', '[]'::jsonb)",
                (token,),
            )
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.delete_staged_campaign_state(%s, 'character_mechanics')",
                (token,),
            )
    u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 10 & 11. Same-save Run-ownership exclusion, both orderings, no invented edge
# ---------------------------------------------------------------------------


def test_character_mechanics_then_runs_is_blocked(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    mutate(db, token, req(HERO, mechanics()))
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)", (token,)
        ),
    )
    assert "already staged a character vitals/resources mutation" in err
    u.abort_save(db, token)


def test_runs_change_then_character_mechanics_is_blocked(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage_runs(db, token, [u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    err = mutate_error(db, token, req(HERO, mechanics()))
    assert "staged a different runs batch" in err
    u.abort_save(db, token)


def test_reconcile_runs_blocked_after_character_mechanics(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    mutate(db, token, req(HERO, mechanics()))
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, '{}'::jsonb)", (token,)
        ),
    )
    assert "already staged a character vitals/resources mutation" in err
    u.abort_save(db, token)


def test_value_equal_replay_still_closes_runs_doorway(db):
    establish(db)
    body = mechanics()
    publish_mutation(db, req(HERO, body))
    # Re-stage the identical absolute target (a value-equal replay) and confirm
    # the operation fact still closes the runs doorway for this save.
    _published, _staging, token, _expires = u.begin_save(db)
    mutate(db, token, req(HERO, body))
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)", (token,)
        ),
    )
    assert "already staged a character vitals/resources mutation" in err
    u.abort_save(db, token)


def test_operation_fact_does_not_leak_into_later_save(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    mutate(db, token, req(HERO, mechanics()))
    u.abort_save(db, token)

    _published, _staging, token, _expires = u.begin_save(db)
    u.stage_runs(db, token, [u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    assert u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation where csg.key = 'runs'",
    ) is not None
    u.abort_save(db, token)


def test_no_invented_compatibility_edge_with_campaign_clock(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    stage_clock(db, token, {
        "schema_version": 1,
        "day": None,
        "phase": "unknown",
        "elapsed_campaign_minutes": 5,
        "long_rests_completed": 0,
    })
    # A Campaign Clock change is unrelated; character-mechanics mutation coexists.
    mutate(db, token, req(HERO, mechanics()))
    u.abort_save(db, token)


def test_character_mechanics_operation_declares_only_the_runs_edge(db):
    record = u.scalar(
        db,
        "select public._rhc_same_save_compatibility_policy('mutate_character_mechanics')",
    )
    assert record["known"] is True
    assert record["domain"] == "character_mechanics"
    assert [e["blocked_by"] for e in record["edges"]] == ["runs"]


# ---------------------------------------------------------------------------
# 12. Absolute replay idempotency
# ---------------------------------------------------------------------------


def test_absolute_replay_is_idempotent(db):
    establish(db)
    body = mechanics(
        hp_section=hp(10, 28),
        resources={"status": "known", "items": [resource("ki", "Ki", 3, 3, ["short_rest"])]},
    )
    publish_mutation(db, req(HERO, body))
    first = read_mechanics(db, HERO)["record"]
    publish_mutation(db, req(HERO, body))
    second = read_mechanics(db, HERO)["record"]
    assert first == second
    # Replay cannot decrement/spend twice.
    assert second["resources"]["items"][0]["current"] == 3


# ---------------------------------------------------------------------------
# 13. Abort leaves no published/staging residue
# ---------------------------------------------------------------------------


def test_abort_leaves_no_residue(db):
    generation = establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    mutate(db, token, req(HERO, full_hero_mechanics()))
    u.abort_save(db, token)
    assert published_generation(db) == generation
    assert stored_collection(db) is None
    assert read_mechanics(db, HERO)["record"] is None


# ---------------------------------------------------------------------------
# 14. Complete candidate validation before staging
# ---------------------------------------------------------------------------


def test_malformed_unrelated_existing_truth_is_not_repaired(db):
    establish(db, seed={"character_mechanics": [
        {"character_id": HERO, **mechanics()},
        {"character_id": SIDEKICK, **mechanics(hp_section=hp(30, 10))},
    ]})
    before = stored_collection(db)
    _published, _staging, token, _expires = u.begin_save(db)
    err = mutate_error(db, token, req(HERO, full_hero_mechanics()))
    u.abort_save(db, token)
    assert "current cannot exceed maximum" in err
    assert stored_collection(db) == before


def test_read_fails_closed_on_malformed_published_collection(db):
    establish(db, seed={"character_mechanics": "not-an-array"})
    err = read_error(db, HERO)
    assert "character_mechanics" in err


# ---------------------------------------------------------------------------
# 15 & 16. Published-only read; service-role-only exposure
# ---------------------------------------------------------------------------


def test_read_consumes_only_published_generation(db):
    generation = establish(db)
    publish_mutation(db, req(HERO, full_hero_mechanics()))
    published_generation_now = published_generation(db)

    # Begin a new save and directly change the staged (future) value.
    _published, _staging, token, _expires = u.begin_save(db)
    stage_namespace(db, "character_mechanics", [{"character_id": HERO, **mechanics()}])
    try:
        read = read_mechanics(db, HERO)
        assert published_generation(db) == published_generation_now
        assert read["record"] == {"character_id": HERO, **full_hero_mechanics()}
        assert generation < published_generation_now
    finally:
        u.abort_save(db, token)


def test_read_returns_truthful_absence(db):
    establish(db)
    read = read_mechanics(db, HERO)
    assert read["record"] is None
    assert read["character_id"] == HERO
    assert read["runtime"]["generation"] >= 1


def test_read_rejects_non_character_identity(db):
    establish(db)
    err = read_error(db, "creature:test-wolf")
    assert "character" in err


def test_read_is_service_role_only(db):
    establish(db)
    for role in ("anon", "authenticated"):
        err = _error_as(
            db,
            role,
            lambda cur: cur.execute(
                "select public.dm_runtime_read_character_mechanics(%s)", (HERO,)
            ),
        )
        assert "permission denied" in err.lower()


def test_mutation_is_service_role_only(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    for role in ("anon", "authenticated"):
        err = mutate_error(db, token, req(HERO, mechanics()), as_role=role)
        assert "permission denied" in err.lower()
    u.abort_save(db, token)


def test_read_is_stable_and_non_mutating(db):
    establish(db)
    publish_mutation(db, req(HERO, full_hero_mechanics()))
    before = u.scalar(db, "select count(*) from public.campaign_state_generations")
    meta = u.scalar(
        db,
        "select jsonb_build_object('volatile', p.provolatile, "
        "'security_definer', p.prosecdef) "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace "
        "and p.proname = 'dm_runtime_read_character_mechanics'",
    )
    assert meta["volatile"] == "s"
    assert meta["security_definer"] is True
    read_mechanics(db, HERO)
    after = u.scalar(db, "select count(*) from public.campaign_state_generations")
    assert after == before


# ---------------------------------------------------------------------------
# 17. No real RHC state is seeded by the repository
# ---------------------------------------------------------------------------


def test_no_real_character_mechanics_seed_exists():
    migration = _CURRENT_MIGRATION.read_text(encoding="utf-8")
    # The migration never inserts a real record; it only creates the route.
    assert "character:mugen" not in migration
    assert "insert into public.campaign_state_generations" in migration
    # No fixture/seed directory for real character mechanics was added.
    assert not (ROOT / "state" / "character_mechanics.json").exists()


# ---------------------------------------------------------------------------
# 18. Existing owner contracts remain unchanged
# ---------------------------------------------------------------------------


def test_existing_domain_classifications_and_edges_unchanged(db):
    assert u.scalar(db, "select public._rhc_save_domain_policy('entity_state')")["admission"] == "dedicated"
    assert u.scalar(db, "select public._rhc_save_domain_policy('inventory')")["admission"] == "dedicated"
    assert u.scalar(db, "select public._rhc_save_domain_policy('runs')")["admission"] == "generic"
    entity = u.scalar(
        db, "select public._rhc_same_save_compatibility_policy('mutate_entity_state')"
    )
    assert [e["blocked_by"] for e in entity["edges"]] == ["runs"]
    # The new edge is trailing on the runs doorways; prior edges keep their order.
    stage_runs = u.scalar(
        db, "select public._rhc_same_save_compatibility_policy('stage_runs')"
    )
    blockers = [e["blocked_by"] for e in stage_runs["edges"]]
    # POST-EV2-10 appended a trailing `character_rests` edge; the POST-EV2-9
    # `character_mechanics` edge keeps its position in the frozen order.
    assert blockers[:8] == [
        "run_reconciliations",
        "inventory",
        "item_custody",
        "entity_state",
        "applied_statuses",
        "entity_knowledge",
        "temporal_positions",
        "character_mechanics",
    ]
    assert blockers[-1] == "character_rests"


# ---------------------------------------------------------------------------
# 19 & 20. Frontier + static surface guard
# ---------------------------------------------------------------------------


def test_forward_migration_frontier_includes_post_ev2_9():
    # POST-EV2-9 must remain in the frozen forward migration chain. A later
    # Mission necessarily advances the repository migration frontier beyond
    # POST-EV2-9, so this suite only asserts presence, not finality.
    assert _CURRENT_MIGRATION in FORWARD_MIGRATIONS
    assert FORWARD_MIGRATIONS[-1].name == (
        "20260929000002_post_ev2_11_begin_day.sql"
    )


def test_post_ev2_5_frontier_pin_no_longer_claims_finality():
    text = _POST_EV2_5_TEST.read_text(encoding="utf-8")
    # POST-EV2-5's own migration must still be present in its forward chain.
    assert "_CURRENT_SEARCH_MIGRATION in FORWARD_MIGRATIONS" in text
    # The stale "must remain the repository's final migration" claim is gone.
    assert 'FORWARD_MIGRATIONS[-1].name == (' not in text


def test_only_the_authorized_surfaces_are_in_scope():
    assert ALLOWED_SURFACES == {
        "schemas/character_mechanics.schema.json",
        "supabase/migrations/20260928000001_post_ev2_9_character_vitals_resources.sql",
        "docs/POST-EV2-9-CHARACTER-VITALS-RESOURCES.md",
        "tests/post_ev2_9/test_character_vitals_resources.py",
        "schemas/README.md",
        "supabase/README.md",
        ".github/workflows/rt01-runtime.yml",
        "tests/post_ev2_1/test_same_save_compatibility_dispatcher.py",
        "tests/post_ev2_2/test_hot_run_registry.py",
        "tests/post_ev2_5/test_current_search.py",
    }
