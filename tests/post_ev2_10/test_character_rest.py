"""POST-EV2-10 proof suite -- Character Rest / Long Rest Lifecycle.

Runs against real PostgreSQL 15 and 17 with the full forward migration chain
(RT01-A/B/C/D + RT02 + RT03 + RT04 + HWB-02 + EV2-10 + EV2-11 + EV2-12.1 +
EV2-13 + EV2-13.420 + EV2-13.1 + POST-EV2-1 Patch 1A/1B + POST-EV2-2 +
POST-EV2-3 + POST-EV2-4A + POST-EV2-5 + POST-EV2-9 + POST-EV2-10) using
disposable schemas and synthetic characters only. No live Supabase is touched and
no real RHC state is imported.

The Mission adds one engine-owned `character_rests` runtime namespace holding
exactly one bounded per-character Rest lifecycle record, one validated
controller-safe absolute mutation route (`public.mutate_character_rest`) and one
supported service-only published read (`public.dm_runtime_read_character_rest`).
Controller authority is resolved only from authoritative published Run truth;
time is derived only from authoritative published RT02 elapsed minutes.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-10 needs real PostgreSQL servers"
)
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
sys.path.insert(0, str(ROOT / "scripts"))
import rt04_util as u  # noqa: E402
import character_rest as cr  # noqa: E402
import dice_resolver  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_CURRENT_MIGRATION = _MIGRATIONS_DIR / "20260929000001_post_ev2_10_character_rest.sql"
_SCHEMA_PATH = ROOT / "schemas" / "character_rests.schema.json"
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
    "RHC_POST_EV210_PG_DSN",
    "RHC_POST_EV29_PG_DSN",
    "RHC_POST_EV25_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV210_PG17_DSN",
    "RHC_POST_EV29_PG17_DSN",
    "RHC_POST_EV25_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

HERO = "character:test-hero"
SIDEKICK = "character:test-sidekick"
R01 = "R01"
R02 = "R02"


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
        pytest.skip(f"POST-EV2-10 proof skipped (no server): {exc}")
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


def clock(elapsed=1000, day=None, phase="unknown", rests=0):
    return {
        "schema_version": 1,
        "day": day,
        "phase": phase,
        "elapsed_campaign_minutes": elapsed,
        "long_rests_completed": rests,
    }


def establish(db, seed=None, runs=None, elapsed=1000):
    _published, _staging, token, _expires = u.begin_save(db)
    if runs is not None:
        u.stage_runs(db, token, runs)
    u.publish(db, token)
    u.confirm_mirror(db)
    base = {"campaign_clock": clock(elapsed)}
    base.update(seed or {})
    for key, value in base.items():
        publish_namespace(db, key, value)
    return published_generation(db)


def advance_clock(db, elapsed, day=None, phase="unknown", rests=0):
    _published, _staging, token, _expires = u.begin_save(db)
    stage_clock(db, token, clock(elapsed, day, phase, rests))
    u.publish(db, token)
    u.confirm_mirror(db)


def stage_clock(db, token, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(value)),
        )


def rest_mutate(db, token, request, as_role="service_role"):
    def call(cur):
        cur.execute(
            "select public.mutate_character_rest(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as(db, as_role, call)
    return json.loads(value) if isinstance(value, str) else value


def rest_error(db, token, request, as_role="service_role"):
    return _error_as(
        db,
        as_role,
        lambda cur: cur.execute(
            "select public.mutate_character_rest(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def apply_rest(db, request):
    _published, _staging, token, _expires = u.begin_save(db)
    result = rest_mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)
    return result


def read_rest(db, character_id):
    def call(cur):
        cur.execute(
            "select public.dm_runtime_read_character_rest(%s)", (character_id,)
        )
        return cur.fetchone()[0]

    value = _run_as(db, "service_role", call)
    return json.loads(value) if isinstance(value, str) else value


def read_rest_error(db, character_id):
    return _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.dm_runtime_read_character_rest(%s)", (character_id,)
        ),
    )


def read_mechanics(db, character_id):
    def call(cur):
        cur.execute(
            "select public.dm_runtime_read_character_mechanics(%s)", (character_id,)
        )
        return cur.fetchone()[0]

    value = _run_as(db, "service_role", call)
    return json.loads(value) if isinstance(value, str) else value


def read_clock(db):
    return u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation "
        "where csg.key = 'campaign_clock'",
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


def stored_rests(db):
    return u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation "
        "where csg.key = 'character_rests'",
    )


# --- mechanics builders ------------------------------------------------------


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


def mech(hp_section=None, hit_dice=None, spell_slots=None, resources=None):
    return {
        "hp": hp_section if hp_section is not None else unknown(),
        "hit_dice": hit_dice if hit_dice is not None else unknown(),
        "spell_slots": spell_slots if spell_slots is not None else unknown(),
        "resources": resources if resources is not None else unknown(),
    }


def mechanics_record(character_id, body):
    return {"character_id": character_id, **body}


def ready_mechanics(hp_current=10, hp_max=28):
    return mech(
        hp_section=hp(hp_current, hp_max, temporary=0),
        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 3, 3)]},
        spell_slots={
            "status": "known",
            "pools": [
                slot_pool("pact", 1, 0, 1, ["short_rest"]),
                slot_pool("wizard", 1, 0, 2, ["long_rest"]),
            ],
        },
        resources={
            "status": "known",
            "items": [
                resource("action-surge", "Action Surge", 0, 1, ["short_rest"]),
                resource("second-wind", "Second Wind", 0, 2, ["long_rest"]),
                resource("luck", "Luck", 1, 1, []),
            ],
        },
    )


# --- rest builders -----------------------------------------------------------


def idle(character):
    return {
        "character_id": character,
        "schema_version": 1,
        "status": "idle",
        "rest_kind": None,
        "started_at_elapsed_minutes": None,
        "required_minutes": None,
        "completed_at_elapsed_minutes": None,
        "last_long_rest_completed_at_elapsed_minutes": None,
        "interruptions": [],
        "short_benefit_granted": False,
    }


def _required(kind, ints):
    return 60 if kind == "short" else 480 + 60 * len(ints)


def active(character, kind, started, ints=None, granted=False, last=None):
    ints = ints or []
    return {
        "character_id": character,
        "schema_version": 1,
        "status": "active",
        "rest_kind": kind,
        "started_at_elapsed_minutes": started,
        "required_minutes": _required(kind, ints),
        "completed_at_elapsed_minutes": None,
        "last_long_rest_completed_at_elapsed_minutes": last,
        "interruptions": ints,
        "short_benefit_granted": granted,
    }


def completed(character, kind, started, comp, ints=None, granted=False, last=None):
    ints = ints or []
    return {
        "character_id": character,
        "schema_version": 1,
        "status": "completed",
        "rest_kind": kind,
        "started_at_elapsed_minutes": started,
        "required_minutes": _required(kind, ints),
        "completed_at_elapsed_minutes": comp,
        "last_long_rest_completed_at_elapsed_minutes": last,
        "interruptions": ints,
        "short_benefit_granted": granted,
    }


def interrupted(character, started, ints, last=None):
    return {
        "character_id": character,
        "schema_version": 1,
        "status": "interrupted",
        "rest_kind": "short",
        "started_at_elapsed_minutes": started,
        "required_minutes": 60,
        "completed_at_elapsed_minutes": None,
        "last_long_rest_completed_at_elapsed_minutes": last,
        "interruptions": ints,
        "short_benefit_granted": False,
    }


def cause(name, at):
    return {"cause": name, "at_elapsed_minutes": at}


def req(character_id, rest, controller=None, **extra):
    request = {
        "character_id": character_id,
        "controller": controller if controller is not None else {"kind": "mainrun"},
        "rest": rest,
    }
    request.update(extra)
    return request


# ---------------------------------------------------------------------------
# 0. Schema accepts coherent records (structural proof)
# ---------------------------------------------------------------------------


def test_schema_accepts_coherent_records():
    for record in (
        idle(HERO),
        active(HERO, "short", 100),
        active(HERO, "long", 100, ints=[cause("damage", 200)], granted=True, last=50),
        completed(HERO, "short", 100, 160),
        completed(HERO, "long", 100, 580, last=580),
        interrupted(HERO, 100, [cause("initiative", 130)]),
    ):
        _VALIDATOR.validate(record)


def test_schema_rejects_bad_shapes():
    bad = active(HERO, "short", 100)
    bad["completed_at_elapsed_minutes"] = 200
    assert list(_VALIDATOR.iter_errors(bad))
    bad2 = idle(HERO)
    bad2["rest_kind"] = "short"
    assert list(_VALIDATOR.iter_errors(bad2))
    bad3 = interrupted(HERO, 100, [cause("initiative", 130)])
    bad3["short_benefit_granted"] = True
    assert list(_VALIDATOR.iter_errors(bad3))


def test_schema_rejects_non_character_id():
    assert list(_VALIDATOR.iter_errors(idle("creature:test-wolf")))


# ---------------------------------------------------------------------------
# 1. Shared-resolver Hit Point Die spending (no raw RNG) -- proof 4
# ---------------------------------------------------------------------------


def test_hit_die_spending_uses_shared_dice_resolver():
    entries = [{"pool_id": "fighter", "die_faces": 10, "count": 3}]
    got = cr.roll_hit_die_spending(entries, rng=random.Random(12345))
    expected = dice_resolver.resolve({"notation": "3d10"}, rng=random.Random(12345))
    assert got == [{"pool_id": "fighter", "rolls": expected["kept_rolls"]}]
    assert len(got[0]["rolls"]) == 3


def test_spending_helper_has_no_raw_rng_root():
    source = (ROOT / "scripts" / "character_rest.py").read_text(encoding="utf-8")
    assert "import random" not in source
    assert "randint" not in source
    assert "dice_resolver.resolve" in source


def test_hit_die_spending_rejects_bad_input():
    with pytest.raises(ValueError):
        cr.roll_hit_die_spending([{"pool_id": "x", "die_faces": 7, "count": 1}])
    with pytest.raises(ValueError):
        cr.roll_hit_die_spending([{"pool_id": "x", "die_faces": 8, "count": 0}])
    with pytest.raises(ValueError):
        cr.roll_hit_die_spending(
            [
                {"pool_id": "x", "die_faces": 8, "count": 1},
                {"pool_id": "x", "die_faces": 8, "count": 1},
            ]
        )


# ---------------------------------------------------------------------------
# 2. Mainrun happy paths + published read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_short_rest_start_publish_and_read(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    establish(db, seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]}, elapsed=1000)
    result = apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    assert result["character_rest_mutation_version"] == 1
    assert result["record"]["status"] == "active"
    read = read_rest(db, HERO)
    assert read["mode"] == "character_rest"
    assert read["record"] == active(HERO, "short", 1000)
    assert read["runtime"]["generation"] == published_generation(db)


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_long_rest_completes_and_restores_hp_and_hit_dice(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics(hp_current=5, hp_max=28))]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1600)
    apply_rest(db, req(HERO, completed(HERO, "long", 1000, 1600, last=1600)))

    body = read_mechanics(db, HERO)["record"]
    assert body["hp"]["current"] == 28
    assert body["hit_dice"]["pools"][0]["current"] == 3
    # Long-Rest recharge applied; non-Rest and short-Rest counters untouched.
    by_id = {i["resource_id"]: i for i in body["resources"]["items"]}
    assert by_id["second-wind"]["current"] == 2
    assert by_id["action-surge"]["current"] == 0
    assert by_id["luck"]["current"] == 1
    # The global campaign metric is RT02-owned and never fabricated by Rest.
    assert read_clock(db)["long_rests_completed"] == 0


def test_read_returns_truthful_absence(db):
    establish(db)
    read = read_rest(db, HERO)
    assert read["record"] is None
    assert read["character_id"] == HERO


def test_read_rejects_non_character_identity(db):
    establish(db)
    assert "character" in read_rest_error(db, "creature:test-wolf")


# ---------------------------------------------------------------------------
# 3. Independent per-character state (proof 1, 2, 3)
# ---------------------------------------------------------------------------


def test_two_characters_in_one_scene_hold_independent_rest_records(db):
    establish(
        db,
        seed={
            "character_mechanics": [
                mechanics_record(HERO, ready_mechanics()),
                mechanics_record(SIDEKICK, ready_mechanics(hp_current=8, hp_max=12)),
            ]
        },
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    apply_rest(db, req(SIDEKICK, active(SIDEKICK, "long", 1000)))
    advance_clock(db, 1100)
    # Interrupt HERO's Short Rest; SIDEKICK's Long Rest is untouched.
    apply_rest(db, req(HERO, interrupted(HERO, 1000, [cause("initiative", 1100)]))) 

    assert read_rest(db, HERO)["record"]["status"] == "interrupted"
    sidekick = read_rest(db, SIDEKICK)["record"]
    assert sidekick["status"] == "active"
    assert sidekick["rest_kind"] == "long"


def test_short_rest_cannot_start_below_1_hp(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics(hp_current=0))]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, active(HERO, "short", 1000)))
    u.abort_save(db, token)
    assert "at least 1 current hit point" in err


def test_long_rest_cannot_start_below_1_hp(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics(hp_current=0))]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, active(HERO, "long", 1000)))
    u.abort_save(db, token)
    assert "at least 1 current hit point" in err


def test_short_rest_cannot_complete_before_60_elapsed_minutes(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, completed(HERO, "short", 1000, 1000)))
    u.abort_save(db, token)
    assert "official minimum duration" in err


def test_interrupted_short_rest_grants_no_benefit(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1030)
    apply_rest(db, req(HERO, interrupted(HERO, 1000, [cause("damage", 1030)])))
    body = read_mechanics(db, HERO)["record"]
    by_id = {i["resource_id"]: i for i in body["resources"]["items"]}
    assert by_id["action-surge"]["current"] == 0  # no Short-Rest recharge
    assert body["hp"]["current"] == 10


# ---------------------------------------------------------------------------
# 4. Hit Point Die spending (proof 4, 5)
# ---------------------------------------------------------------------------


def test_short_rest_spending_adds_die_plus_sourced_con_and_min_one(db):
    establish(
        db,
        seed={
            "character_mechanics": [
                mechanics_record(
                    HERO,
                    mech(
                        hp_section=hp(10, 28),
                        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 3, 3)]},
                        spell_slots=not_applicable(),
                        resources=not_applicable(),
                    ),
                )
            ]
        },
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    # Roll 1 + CON 3 -> max(1, 4) = 4 recovered; roll 1 + CON -5 -> max(1, -4) = 1.
    request = req(
        HERO,
        completed(HERO, "short", 1000, 1060),
        hit_die_spending=[{"pool_id": "fighter", "rolls": [1, 1]}],
        con_modifier={"value": 3, "source": "character:test-hero sheet CON modifier"},
    )
    result = apply_rest(db, request)
    assert result["mechanics_applied"] is True
    body = read_mechanics(db, HERO)["record"]
    assert body["hp"]["current"] == 18  # 10 + (1+3) + (1+3)
    assert body["hit_dice"]["pools"][0]["current"] == 1


def test_hit_die_spending_cannot_exceed_remaining_or_max_hp(db):
    establish(
        db,
        seed={
            "character_mechanics": [
                mechanics_record(
                    HERO,
                    mech(
                        hp_section=hp(27, 28),
                        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 1, 3)]},
                        spell_slots=not_applicable(),
                        resources=not_applicable(),
                    ),
                )
            ]
        },
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    # Spend more dice than remain -> fail closed.
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db,
        token,
        req(
            HERO,
            completed(HERO, "short", 1000, 1060),
            hit_die_spending=[{"pool_id": "fighter", "rolls": [5, 5]}],
            con_modifier={"value": 0, "source": "sheet"},
        ),
    )
    u.abort_save(db, token)
    assert "only 1 remain" in err

    # A legal single die cannot push HP above its maximum.
    apply_rest(
        db,
        req(
            HERO,
            completed(HERO, "short", 1000, 1060),
            hit_die_spending=[{"pool_id": "fighter", "rolls": [10]}],
            con_modifier={"value": 5, "source": "sheet"},
        ),
    )
    body = read_mechanics(db, HERO)["record"]
    assert body["hp"]["current"] == 28
    assert body["hit_dice"]["pools"][0]["current"] == 0


def test_hit_die_spending_requires_sourced_con_modifier(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db,
        token,
        req(
            HERO,
            completed(HERO, "short", 1000, 1060),
            hit_die_spending=[{"pool_id": "fighter", "rolls": [4]}],
        ),
    )
    u.abort_save(db, token)
    assert "con_modifier" in err


def test_hit_die_spending_rejects_out_of_range_roll(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db,
        token,
        req(
            HERO,
            completed(HERO, "short", 1000, 1060),
            hit_die_spending=[{"pool_id": "fighter", "rolls": [11]}],
            con_modifier={"value": 0, "source": "sheet"},
        ),
    )
    u.abort_save(db, token)
    assert "outside the valid 1..10 range" in err


# ---------------------------------------------------------------------------
# 5. Long Rest lifecycle (proof 6, 7, 8, 9, 10, 11)
# ---------------------------------------------------------------------------


def test_long_rest_requires_personal_16_hour_wait(db):
    establish(
        db,
        seed={
            "character_mechanics": [mechanics_record(HERO, ready_mechanics())],
            "character_rests": [
                completed(HERO, "long", 520, 1000, last=1000)
            ],
        },
        elapsed=1050,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, active(HERO, "long", 1050, last=1000)))
    u.abort_save(db, token)
    assert "at least 16 hours" in err


def test_long_rest_may_start_after_16_hours(db):
    establish(
        db,
        seed={
            "character_mechanics": [mechanics_record(HERO, ready_mechanics())],
            "character_rests": [completed(HERO, "long", 520, 1000, last=1000)],
        },
        elapsed=1960,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1960, last=1000)))
    assert read_rest(db, HERO)["record"]["started_at_elapsed_minutes"] == 1960


def test_long_rest_cannot_complete_before_480_minutes(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1479)
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, completed(HERO, "long", 1000, 1479, last=1479)))
    u.abort_save(db, token)
    assert "official minimum duration" in err


def test_every_interruption_cause_is_representable(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    for offset, name in enumerate(("initiative", "spell", "damage", "exertion"), start=1):
        now = 1000 + offset * 60
        advance_clock(db, now)
        current = read_rest(db, HERO)["record"]
        apply_rest(
            db,
            req(
                HERO,
                active(
                    HERO,
                    "long",
                    1000,
                    ints=current["interruptions"] + [cause(name, now)],
                    granted=True,
                    last=None,
                ),
            ),
        )
    record = read_rest(db, HERO)["record"]
    assert [i["cause"] for i in record["interruptions"]] == [
        "initiative",
        "spell",
        "damage",
        "exertion",
    ]
    assert record["required_minutes"] == 480 + 60 * 4
    assert record["short_benefit_granted"] is True


def test_long_interruption_after_hour_grants_short_benefit_then_resumes(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1120)  # > 1 hour elapsed
    apply_rest(
        db,
        req(HERO, active(HERO, "long", 1000, ints=[cause("damage", 1120)], granted=True)),
    )
    record = read_rest(db, HERO)["record"]
    assert record["status"] == "active"
    assert record["required_minutes"] == 540
    assert record["short_benefit_granted"] is True
    body = read_mechanics(db, HERO)["record"]
    by_id = {i["resource_id"]: i for i in body["resources"]["items"]}
    assert by_id["action-surge"]["current"] == 1  # Short-Rest recharge granted

    # Resume to completion at the longer required duration.
    advance_clock(db, 1540)
    apply_rest(db, req(HERO, completed(HERO, "long", 1000, 1540, ints=[cause("damage", 1120)], granted=True, last=1540)))
    assert read_rest(db, HERO)["record"]["status"] == "completed"


def test_short_benefit_not_due_before_one_hour(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1030)  # < 1 hour
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db,
        token,
        req(HERO, active(HERO, "long", 1000, ints=[cause("damage", 1030)], granted=True)),
    )
    u.abort_save(db, token)
    assert "not yet due" in err


def test_short_rest_interruption_is_terminal_and_grants_nothing(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1010)
    apply_rest(db, req(HERO, interrupted(HERO, 1000, [cause("spell", 1010)])))
    assert read_rest(db, HERO)["record"]["status"] == "interrupted"


def test_long_rest_spending_is_rejected(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1500)
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db,
        token,
        req(
            HERO,
            completed(HERO, "long", 1000, 1500, last=1500),
            hit_die_spending=[{"pool_id": "fighter", "rolls": [4]}],
            con_modifier={"value": 1, "source": "sheet"},
        ),
    )
    u.abort_save(db, token)
    assert "Short Rest benefit" in err


# ---------------------------------------------------------------------------
# 6. Metadata-driven recharge only (proof 12)
# ---------------------------------------------------------------------------


def test_only_short_rest_recharge_restored_on_short_rest(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    apply_rest(db, req(HERO, completed(HERO, "short", 1000, 1060)))
    body = read_mechanics(db, HERO)["record"]
    by_id = {i["resource_id"]: i for i in body["resources"]["items"]}
    slots = {p["pool_id"]: p for p in body["spell_slots"]["pools"]}
    assert by_id["action-surge"]["current"] == 1
    assert by_id["second-wind"]["current"] == 0
    assert by_id["luck"]["current"] == 1
    assert slots["pact"]["current"] == 1
    assert slots["wizard"]["current"] == 0


# ---------------------------------------------------------------------------
# 7. Unsupported rest-sensitive state fails explicitly (proof 13)
# ---------------------------------------------------------------------------


def test_unknown_rest_sensitive_section_fails_closed(db):
    establish(
        db,
        seed={
            "character_mechanics": [
                mechanics_record(HERO, mech(hp_section=hp(10, 28)))
            ]
        },
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, completed(HERO, "short", 1000, 1060)))
    u.abort_save(db, token)
    assert "unknown character-mechanics section" in err


# ---------------------------------------------------------------------------
# 8. Controller authority from published Run truth (proof 16)
# ---------------------------------------------------------------------------


def test_run_controller_happy_path(db):
    establish(
        db,
        runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])],
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(
        db,
        req(HERO, active(HERO, "short", 1000), controller={"kind": "run", "run_id": R01}),
    )
    assert read_rest(db, HERO)["record"]["status"] == "active"


def test_mainrun_cannot_mutate_run_owned_character(db):
    establish(
        db,
        runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])],
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(db, token, req(HERO, active(HERO, "short", 1000)))
    u.abort_save(db, token)
    assert "MAINRUN may not mutate" in err


def test_wrong_run_controller_fails_closed(db):
    establish(
        db,
        runs=[u.run(run_id=R01, mutable_owner_entity_ids=[HERO])],
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = rest_error(
        db, token, req(HERO, active(HERO, "short", 1000), controller={"kind": "run", "run_id": R02})
    )
    u.abort_save(db, token)
    assert "crosses controllers" in err


def test_malformed_controller_assertions_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    for bad in (None, "mainrun", {"kind": None}, {"kind": "run"}, {"kind": "mainrun", "run_id": R01}):
        err = rest_error(db, token, req(HERO, active(HERO, "short", 1000), controller=bad))
        assert err
    u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 9. Patch 1A / 1B wiring (proof 15, 16, 17)
# ---------------------------------------------------------------------------


def test_patch_1a_registers_character_rests_dedicated(db):
    record = u.scalar(db, "select public._rhc_save_domain_policy('character_rests')")
    assert record["admission"] == "dedicated"
    assert record["dedicated_routes"] == ["mutate_character_rest"]
    assert record["stage_error"] == (
        "character_rests is engine-owned and can only be staged through "
        "mutate_character_rest"
    )
    assert record["delete_error"] == (
        "character_rests is engine-owned and cannot be deleted through the generic route"
    )


def test_generic_stage_and_delete_bypass_fail_closed(db):
    establish(db)
    _published, _staging, token, _expires = u.begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'character_rests', '[]'::jsonb)",
                (token,),
            )
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.delete_staged_campaign_state(%s, 'character_rests')",
                (token,),
            )
    u.abort_save(db, token)


def test_character_rest_declares_only_the_runs_edge(db):
    record = u.scalar(
        db, "select public._rhc_same_save_compatibility_policy('mutate_character_rest')"
    )
    assert record["known"] is True
    assert record["domain"] == "character_rests"
    assert [e["blocked_by"] for e in record["edges"]] == ["runs"]


def test_stage_runs_gains_trailing_character_rests_edge(db):
    stage_runs = u.scalar(
        db, "select public._rhc_same_save_compatibility_policy('stage_runs')"
    )
    assert [e["blocked_by"] for e in stage_runs["edges"]][-1] == "character_rests"


def test_runs_change_then_rest_is_blocked(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage_runs(db, token, [u.run(run_id=R01, mutable_owner_entity_ids=[HERO])])
    err = rest_error(db, token, req(HERO, active(HERO, "short", 1000)))
    u.abort_save(db, token)
    assert "staged a different runs batch" in err


def test_rest_then_runs_is_blocked(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    rest_mutate(db, token, req(HERO, active(HERO, "short", 1000)))
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)", (token,)
        ),
    )
    assert "already staged a character Rest mutation" in err
    u.abort_save(db, token)


def test_value_equal_rest_replay_still_closes_runs_doorway(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    target = active(HERO, "short", 1000)
    apply_rest(db, req(HERO, target))
    _published, _staging, token, _expires = u.begin_save(db)
    rest_mutate(db, token, req(HERO, target))
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)", (token,)
        ),
    )
    assert "already staged a character Rest mutation" in err
    u.abort_save(db, token)


def test_rest_and_clock_and_mechanics_coexist_in_one_save(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    stage_clock(db, token, clock(1060))
    rest_mutate(db, token, req(HERO, active(HERO, "short", 1000)))
    u.publish(db, token)
    u.confirm_mirror(db)
    assert read_rest(db, HERO)["record"]["status"] == "active"
    assert read_clock(db)["elapsed_campaign_minutes"] == 1060


# ---------------------------------------------------------------------------
# 10. Absolute replay idempotency (proof 18)
# ---------------------------------------------------------------------------


def test_absolute_rest_replay_does_not_double_spend_or_recover(db):
    establish(
        db,
        seed={
            "character_mechanics": [
                mechanics_record(
                    HERO,
                    mech(
                        hp_section=hp(10, 28),
                        hit_dice={"status": "known", "pools": [hd_pool("fighter", 10, 3, 3)]},
                        spell_slots=not_applicable(),
                        resources=not_applicable(),
                    ),
                )
            ]
        },
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    target = completed(HERO, "short", 1000, 1060)
    request = req(
        HERO,
        target,
        hit_die_spending=[{"pool_id": "fighter", "rolls": [4]}],
        con_modifier={"value": 2, "source": "sheet"},
    )
    apply_rest(db, request)
    first = read_mechanics(db, HERO)["record"]

    # Replay the identical absolute target: idempotent no-op.
    replay = apply_rest(db, request)
    assert replay["replay"] is True
    second = read_mechanics(db, HERO)["record"]
    assert first == second
    assert second["hit_dice"]["pools"][0]["current"] == 2


def test_replayed_interruption_does_not_add_duplicate_hour(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1120)
    target = active(HERO, "long", 1000, ints=[cause("damage", 1120)], granted=True)
    apply_rest(db, req(HERO, target))
    replay = apply_rest(db, req(HERO, target))
    assert replay["replay"] is True
    record = read_rest(db, HERO)["record"]
    assert record["required_minutes"] == 540
    assert len(record["interruptions"]) == 1


# ---------------------------------------------------------------------------
# 11. Abort / residue (proof 19)
# ---------------------------------------------------------------------------


def test_abort_leaves_no_residue(db):
    generation = establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    rest_mutate(db, token, req(HERO, active(HERO, "short", 1000)))
    u.abort_save(db, token)
    assert published_generation(db) == generation
    assert stored_rests(db) is None
    assert read_rest(db, HERO)["record"] is None


def test_rest_abort_action_returns_to_idle_without_benefit(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1070)
    apply_rest(db, req(HERO, idle(HERO)))
    record = read_rest(db, HERO)["record"]
    assert record["status"] == "idle"
    assert read_mechanics(db, HERO)["record"]["hp"]["current"] == 10


# ---------------------------------------------------------------------------
# 12. Published-only, service-only read (proof 20)
# ---------------------------------------------------------------------------


def test_read_consumes_only_published_generation(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    published_now = published_generation(db)

    _published, _staging, token, _expires = u.begin_save(db)
    stage_namespace(db, "character_rests", [idle(HERO)])
    try:
        read = read_rest(db, HERO)
        assert read["record"] == active(HERO, "short", 1000)
        assert published_generation(db) == published_now
    finally:
        u.abort_save(db, token)


def test_read_is_service_role_only(db):
    establish(db)
    for role in ("anon", "authenticated"):
        err = _error_as(
            db,
            role,
            lambda cur: cur.execute(
                "select public.dm_runtime_read_character_rest(%s)", (HERO,)
            ),
        )
        assert "permission denied" in err.lower()


def test_mutation_is_service_role_only(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    for role in ("anon", "authenticated"):
        err = rest_error(db, token, req(HERO, active(HERO, "short", 1000)), as_role=role)
        assert "permission denied" in err.lower()
    u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 12b. REPAIR invariants
# ---------------------------------------------------------------------------


def test_rest_applies_mechanics_only_through_post_ev2_9_owner(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    _published, _staging, token, _expires = u.begin_save(db)
    result = rest_mutate(db, token, req(HERO, completed(HERO, "short", 1000, 1060)))
    assert result["mechanics_applied"] is True
    # POST-EV2-9's dedicated owner staged the mechanics change, so its operation
    # marker is set and its exclusive-writer contract remains true.
    assert u.scalar(db, "select public._rhc_character_mechanics_staged_in_save()") is True
    assert u.scalar(db, "select public._rhc_character_rests_staged_in_save()") is True
    err = _error_as(
        db,
        "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, 'character_mechanics', '[]'::jsonb)",
            (token,),
        ),
    )
    assert "engine-owned" in err
    u.abort_save(db, token)


def test_rest_migration_never_writes_character_mechanics_directly():
    migration = _CURRENT_MIGRATION.read_text(encoding="utf-8")
    # No direct insert into the character_mechanics runtime key exists anywhere.
    assert "values (r.staging_generation, 'character_mechanics'" not in migration
    assert "perform public.mutate_character_mechanics(" in migration


def _mechanics_with_temporary(temporary):
    body = ready_mechanics(hp_current=5, hp_max=28)
    body["hp"]["temporary"] = temporary
    return body


def test_long_rest_completion_clears_temporary_hit_points(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, _mechanics_with_temporary(7))]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    advance_clock(db, 1600)
    apply_rest(db, req(HERO, completed(HERO, "long", 1000, 1600, last=1600)))

    body = read_mechanics(db, HERO)["record"]
    assert body["hp"]["current"] == 28
    assert body["hp"]["temporary"] == 0


def test_short_rest_preserves_temporary_hit_points(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, _mechanics_with_temporary(7))]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "short", 1000)))
    advance_clock(db, 1060)
    apply_rest(db, req(HERO, completed(HERO, "short", 1000, 1060)))

    body = read_mechanics(db, HERO)["record"]
    assert body["hp"]["temporary"] == 7


def test_incomplete_or_interrupted_long_rest_preserves_temporary_hit_points(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, _mechanics_with_temporary(7))]},
        elapsed=1000,
    )
    apply_rest(db, req(HERO, active(HERO, "long", 1000)))
    # Incomplete Long Rest: still active, no consequence applied.
    assert read_mechanics(db, HERO)["record"]["hp"]["temporary"] == 7

    # Interrupted before 1 hour: no Short-Rest benefit, Temporary HP preserved.
    advance_clock(db, 1030)
    apply_rest(
        db,
        req(HERO, active(HERO, "long", 1000, ints=[cause("damage", 1030)])),
    )
    assert read_mechanics(db, HERO)["record"]["hp"]["temporary"] == 7

    # Interrupted after 1 hour: Short-Rest benefit granted, Temporary HP preserved.
    advance_clock(db, 1120)
    apply_rest(
        db,
        req(
            HERO,
            active(
                HERO,
                "long",
                1000,
                ints=[cause("damage", 1030), cause("damage", 1120)],
                granted=True,
            ),
        ),
    )
    assert read_mechanics(db, HERO)["record"]["hp"]["temporary"] == 7


def _long_record_with_interruptions(n):
    return active(HERO, "long", 0, ints=[cause("damage", i) for i in range(n)], granted=True)


def test_schema_caps_interruptions_at_1000():
    _VALIDATOR.validate(_long_record_with_interruptions(1000))
    assert list(_VALIDATOR.iter_errors(_long_record_with_interruptions(1001)))


def test_sql_normalizer_enforces_same_interruption_bound(db):
    with db.cursor() as cur:
        cur.execute(
            "select public._rhc_normalize_character_rest_record(%s::jsonb)",
            (json.dumps(_long_record_with_interruptions(1000)),),
        )
        assert cur.fetchone()[0] is not None
    with pytest.raises(psycopg2.errors.RaiseException, match="at most 1000"):
        with db.cursor() as cur:
            cur.execute(
                "select public._rhc_normalize_character_rest_record(%s::jsonb)",
                (json.dumps(_long_record_with_interruptions(1001)),),
            )


def test_rest_route_rejects_over_bound_interruptions(db):
    establish(
        db,
        seed={"character_mechanics": [mechanics_record(HERO, ready_mechanics())]},
        elapsed=1000,
    )
    _published, _staging, token, _expires = u.begin_save(db)
    target = _long_record_with_interruptions(1001)
    target["started_at_elapsed_minutes"] = 1000
    err = rest_error(db, token, req(HERO, target))
    u.abort_save(db, token)
    assert "at most 1000" in err


# ---------------------------------------------------------------------------
# 13. Migration frontier + no real seed (proof 21, 22)
# ---------------------------------------------------------------------------


def test_forward_migration_frontier_includes_post_ev2_10():
    # POST-EV2-10 must remain in the frozen forward migration chain. A later
    # Mission necessarily advances the repository migration frontier beyond
    # POST-EV2-10, so this suite only asserts presence, not finality.
    assert _CURRENT_MIGRATION in FORWARD_MIGRATIONS
    assert FORWARD_MIGRATIONS[-1].name == (
        "20260929000002_post_ev2_11_begin_day.sql"
    )


def test_no_real_character_rest_seed_exists():
    migration = _CURRENT_MIGRATION.read_text(encoding="utf-8")
    assert "character:mugen" not in migration
    assert not (ROOT / "state" / "character_rests.json").exists()


def test_existing_owner_contracts_remain_unchanged(db):
    assert u.scalar(db, "select public._rhc_save_domain_policy('character_mechanics')")["admission"] == "dedicated"
    assert u.scalar(db, "select public._rhc_save_domain_policy('campaign_clock')")["admission"] == "dedicated"
    mechanics = u.scalar(
        db, "select public._rhc_same_save_compatibility_policy('mutate_character_mechanics')"
    )
    assert [e["blocked_by"] for e in mechanics["edges"]] == ["runs"]
    blockers = [
        e["blocked_by"]
        for e in u.scalar(db, "select public._rhc_same_save_compatibility_policy('stage_runs')")["edges"]
    ]
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
