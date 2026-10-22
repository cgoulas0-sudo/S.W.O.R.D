"""POST-EV2-3 proof suite — Run impact wiring + knower-safe reconciliation.

Runs against real PostgreSQL 15 and 17 with the full forward migration chain
(RT01-A/B/C/D + RT02 + RT03 + RT04 + HWB-02 + EV2-10 + EV2-11 + EV2-12.1 +
EV2-13 + EV2-13.420 + EV2-13.1 + POST-EV2-1 Patch 1A/1B + POST-EV2-2 +
POST-EV2-3) with disposable schemas and synthetic data only. No live Supabase is
touched and no real RHC knowledge is imported.

The runtime proof proves that:

  * POST-EV2-1 Patch 1A classifies `entity_knowledge` as `dedicated` with exactly
    `mutate_entity_knowledge` as its initial legal writer, and the generic
    stage/delete routes fail closed for it;
  * `mutate_entity_knowledge` accepts an EV2-14-valid absolute record and
    publishes it through the normal RT01 lifecycle;
  * invalid EV2-14 shapes fail before staging (invalid epistemic status, invalid
    visibility, fact-reference visibility duplication, value+fact_id, missing
    content mode, blank topic, structured value, etc.), plus duplicate topics and
    duplicate/ambiguous knower records;
  * a Run controller may mutate knowledge only for a knower it currently controls
    per published `runs`, and MAINRUN only when no published Run controls it;
  * `dm_meta.run_claims` alone never authorizes knowledge mutation;
  * a different / stale / parked Run and malformed or ambiguous published Run
    truth fail closed;
  * same-save Run ownership change -> knowledge mutation fails closed, and
    knowledge staged -> later Run ownership / reconciliation fails closed;
  * knowledge stays attached to the knower across MAINRUN<->RUN handoff and is
    never copied to another entity or party member;
  * BTH/player visibility and fact existence alone grant no character knowledge;
  * RT04 continues to preserve unsupported Hook/location/world consequences and a
    free-form discovery consequence never synthesizes an EV2-14 record;
  * successful save proof includes generation advance, expected published state,
    mirror/confirmation and authoritative read-back; a failed mutation leaves the
    previous published generation intact;
  * the route is service-role-only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-3 needs real PostgreSQL servers"
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_KNOWLEDGE_MIGRATION = _MIGRATIONS_DIR / (
    "20260924000001_post_ev2_3_knower_safe_run_impact.sql"
)
_BASELINE_ROLES = (ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql").read_text(
    encoding="utf-8"
)
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)

_PG15_DSN_PRECEDENCE = (
    "RHC_POST_EV23_PG_DSN",
    "RHC_POST_EV22_PG_DSN",
    "RHC_POST_EV21_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV23_PG17_DSN",
    "RHC_POST_EV22_PG17_DSN",
    "RHC_POST_EV21_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

HERO = "character:test-hero"
SIDEKICK = "character:test-sidekick"
BEAST = "creature:test-wolf"
LOCATION = "location:tavern"
FACTION = "faction:test-guild"
PARTY = "party:test-stash"
ITEM = "item:test-blade"


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
        pytest.skip(f"POST-EV2-3 proof skipped (no server): {exc}")
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

def _run_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _error_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def _error_as_role(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def _mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_entity_knowledge(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_entity_knowledge(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _stage_error(db, token, key, value):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        ),
    )


def _delete_error(db, token, key):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)",
            (token, key),
        ),
    )


def _published_knowledge(db):
    return u.published_state(db).get("entity_knowledge") or []


def _staged_knowledge(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'entity_knowledge'",
    )
    return value or []


def _seed_published_knowledge(db, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, 'entity_knowledge', %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (json.dumps(value),),
    )


def _fact_entry(topic="courier_truth", fact_id="F012", epistemic_status="confirmed", **extra):
    entry = {"topic": topic, "epistemic_status": epistemic_status, "fact_id": fact_id}
    entry.update(extra)
    return entry


def _assertion_entry(topic="crystal_ball_theory", value="it listens", visibility="meta",
                     epistemic_status="belief", **extra):
    entry = {
        "topic": topic,
        "epistemic_status": epistemic_status,
        "value": value,
        "visibility": visibility,
    }
    entry.update(extra)
    return entry


def _known(entries):
    return {"status": "known", "entries": entries}


def _request(entity=HERO, controller=None, knowledge=None):
    return {
        "entity_id": entity,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "knowledge": _known([_assertion_entry()]) if knowledge is None else knowledge,
    }


def _policy(db, key):
    return u.scalar(db, "select public._rhc_save_domain_policy(%s)", (key,))


def _compat_policy(db, operation):
    return u.scalar(
        db, "select public._rhc_same_save_compatibility_policy(%s)", (operation,)
    )


# ---------------------------------------------------------------------------
# 1. Patch 1A registry classification + generic bypass closure
# ---------------------------------------------------------------------------

def test_patch_1a_classifies_entity_knowledge_as_dedicated(db):
    policy = _policy(db, "entity_knowledge")
    assert policy["admission"] == "dedicated"
    assert policy["dedicated_routes"] == ["mutate_entity_knowledge"]

    for key in ("daily_recap", "runs", "dm_meta", "narrative_hooks",
                "day_resolution", "live_status"):
        assert _policy(db, key)["admission"] == "generic"
    for key in ("campaign_clock", "run_reconciliations", "inventory",
                "item_custody", "item_admissions", "entity_state",
                "applied_statuses"):
        assert _policy(db, key)["admission"] == "dedicated"

    unknown = _policy(db, "__post_ev2_3_unknown_key__")
    assert unknown["admission"] == "forbidden"
    assert unknown["dedicated_routes"] == []


def test_generic_stage_and_delete_of_entity_knowledge_fail_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)

    err_stage = _stage_error(db, token, "entity_knowledge", [_known([_assertion_entry()])])
    assert "mutate_entity_knowledge" in err_stage

    err_delete = _delete_error(db, token, "entity_knowledge")
    assert "entity_knowledge" in err_delete

    # The generic routes still admit the ordinary allowlist unchanged.
    u.stage(db, token, "live_status", {"scene": "workshop"})
    u.publish(db, token)
    u.confirm_mirror(db)
    assert u.published_state(db).get("live_status") == {"scene": "workshop"}


# ---------------------------------------------------------------------------
# 2. Happy path + record shape
# ---------------------------------------------------------------------------

def test_mainrun_mutation_publishes_owner_local_knowledge(db):
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(
            knowledge=_known(
                [
                    _fact_entry(),
                    _assertion_entry(visibility="non_meta"),
                ]
            )
        ),
    )
    assert result["entity_id"] == HERO
    assert result["controller"] == {"kind": "mainrun"}
    assert result["knowledge_mutation_version"] == 1

    # Staging is invisible until the existing publication handshake completes.
    assert _published_knowledge(db) == []
    assert _staged_knowledge(db)[0]["entity_id"] == HERO

    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_knowledge(db)
    assert len(records) == 1
    assert records[0]["entity_id"] == HERO
    assert records[0]["status"] == "known"
    fact = records[0]["entries"][0]
    assert fact == {
        "topic": "courier_truth",
        "epistemic_status": "confirmed",
        "fact_id": "F012",
    }
    # A fact reference never copies a visibility into the knower record.
    assert "visibility" not in fact


def test_run_owned_mutation_publishes_through_existing_spine(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}),
    )
    assert result["controller"] == {"kind": "run", "run_id": "R01"}

    u.publish(db, token)
    u.confirm_mirror(db)
    records = _published_knowledge(db)
    assert len(records) == 1 and records[0]["entity_id"] == HERO


def test_unknown_and_not_applicable_records_are_coherent(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO, knowledge={"status": "unknown"}))
    _mutate(db, token, _request(entity=BEAST, knowledge={"status": "not_applicable"}))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = {r["entity_id"]: r for r in _published_knowledge(db)}
    assert records[HERO] == {"entity_id": HERO, "status": "unknown"}
    assert records[BEAST] == {"entity_id": BEAST, "status": "not_applicable"}


def test_multiple_knowers_keep_exactly_one_record_each(db):
    _published, _staging, token, _expires = u.begin_save(db)
    for entity in (HERO, SIDEKICK, LOCATION, FACTION, PARTY, ITEM):
        _mutate(db, token, _request(entity=entity))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_knowledge(db)
    assert sorted(r["entity_id"] for r in records) == sorted(
        [HERO, SIDEKICK, LOCATION, FACTION, PARTY, ITEM]
    )


def test_mutation_is_absolute_and_replay_safe(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request(knowledge=_known([_assertion_entry(value="Camp")]))
    _mutate(db, token, request)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_knowledge(db)
    assert len(records) == 1
    assert records[0]["entries"] == [
        {"topic": "crystal_ball_theory", "epistemic_status": "belief",
         "value": "Camp", "visibility": "meta"}
    ]


def test_abort_discards_unpublished_knowledge(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request())
    u.abort_save(db, token)
    assert _published_knowledge(db) == []


# ---------------------------------------------------------------------------
# 3. Bounded EV2-14 validation (fail closed before staging)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "knowledge",
    [
        None,
        "not-an-object",
        {"status": "sometimes"},
        {"status": 1},
        {"status": "known"},
        {"status": "known", "entries": []},
        {"status": "known", "entries": "nope"},
        {"status": "known", "entries": [_assertion_entry()], "extra": 1},
        {"status": "unknown", "entries": []},
        {"status": "not_applicable", "entries": [_assertion_entry()]},
        {"entries": [_assertion_entry()]},
    ],
)
def test_invalid_knowledge_body_fails_closed(db, knowledge):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": HERO, "controller": {"kind": "mainrun"}, "knowledge": knowledge}
    err = _mutate_error(db, token, request)
    assert "knowledge" in err.lower() or "status" in err or "entries" in err


@pytest.mark.parametrize(
    "entry",
    [
        {"epistemic_status": "confirmed", "fact_id": "F1"},  # missing topic
        {"topic": "t", "fact_id": "F1"},  # missing epistemic_status
        {"topic": "t", "epistemic_status": "maybe", "fact_id": "F1"},  # bad status
        {"topic": "", "epistemic_status": "confirmed", "fact_id": "F1"},  # blank topic
        {"topic": "t", "epistemic_status": "confirmed", "fact_id": "F1", "value": 1},
        {"topic": "t", "epistemic_status": "confirmed", "fact_id": "F1", "visibility": "meta"},
        {"topic": "t", "epistemic_status": "confirmed", "fact_id": ""},
        {"topic": "t", "epistemic_status": "confirmed"},  # neither mode
        {"topic": "t", "epistemic_status": "confirmed", "value": 1},  # missing visibility
        {"topic": "t", "epistemic_status": "confirmed", "value": 1, "visibility": "sometimes"},
        {"topic": "t", "epistemic_status": "confirmed", "value": None, "visibility": "meta"},
        {"topic": "t", "epistemic_status": "confirmed", "value": [1], "visibility": "meta"},
        {"topic": "t", "epistemic_status": "confirmed", "value": {"a": 1}, "visibility": "meta"},
        {"topic": "t", "epistemic_status": "confirmed", "value": True, "visibility": "meta", "extra": 1},
        {"topic": "t", "epistemic_status": "confirmed", "value": True, "visibility": "meta", "note": ""},
        {"topic": "t", "epistemic_status": "confirmed", "value": True, "visibility": "meta", "source": ""},
    ],
)
def test_invalid_knowledge_entry_fails_closed(db, entry):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(knowledge=_known([entry])))
    assert "entry" in err or "visibility" in err or "value" in err or "epistemic" in err


def test_duplicate_exact_entries_fail_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    duplicate = _assertion_entry()
    err = _mutate_error(db, token, _request(knowledge=_known([duplicate, duplicate])))
    assert "unique" in err.lower() or "topic" in err.lower()


def test_duplicate_topics_fail_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(
            knowledge=_known(
                [
                    _assertion_entry(topic="same", value="a", visibility="meta"),
                    _assertion_entry(topic="same", value="b", visibility="meta"),
                ]
            )
        ),
    )
    assert "topic" in err.lower()


@pytest.mark.parametrize(
    "entity",
    ["party", "character:", "character:Bad Slug", "npc:test", 123, None],
)
def test_entity_must_be_a_full_ev2_14_identity(db, entity):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": entity, "controller": {"kind": "mainrun"},
               "knowledge": _known([_assertion_entry()])}
    err = _mutate_error(db, token, request)
    assert "entity" in err.lower()


def test_request_rejects_fields_outside_the_contract(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request()
    request["narrative"] = "ignore this"
    err = _mutate_error(db, token, request)
    assert "outside the EV2-14 runtime contract" in err


@pytest.mark.parametrize(
    "controller",
    [
        None,
        "mainrun",
        {},
        {"kind": None},
        {"kind": 1},
        {"kind": "MAINRUN"},
        {"kind": "run"},
        {"kind": "run", "run_id": "R1"},
        {"kind": "run", "run_id": "R01", "extra": 1},
        {"kind": "mainrun", "extra": 1},
    ],
)
def test_controller_shape_is_bounded(db, controller):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": HERO, "controller": controller,
               "knowledge": _known([_assertion_entry()])}
    err = _mutate_error(db, token, request)
    assert "controller" in err.lower()


def test_mutation_requires_an_active_campaign_save(db):
    err = _mutate_error(db, "not-a-real-token", _request())
    assert "lock" in err.lower()


# ---------------------------------------------------------------------------
# 4. Malformed / duplicate existing truth
# ---------------------------------------------------------------------------

def test_malformed_existing_knowledge_fails_closed_even_for_unrelated_knower(db):
    _seed_published_knowledge(
        db,
        [{"entity_id": BEAST, "status": "unknown", "entries": [_assertion_entry()]}],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "knowledge" in err.lower() or "entries" in err


def test_duplicate_existing_knower_records_fail_closed(db):
    _seed_published_knowledge(
        db,
        [
            {"entity_id": HERO, "status": "unknown"},
            {"entity_id": HERO, "status": "not_applicable"},
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "duplicate" in err.lower() or "entity_knowledge" in err


# ---------------------------------------------------------------------------
# 5. Controller authority
# ---------------------------------------------------------------------------

def test_mainrun_allowed_only_when_no_published_run_controls_the_knower(db):
    # MAINRUN is the controller when no published Run claims HERO.
    _published, _staging, token, _expires = u.begin_save(db)
    assert _mutate(db, token, _request(entity=HERO))["entity_id"] == HERO
    u.abort_save(db, token)

    # Once a published Run claims HERO, MAINRUN fails closed.
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "MAINRUN may not mutate" in err


def test_run_controller_allowed_only_for_a_knower_it_controls(db):
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])]
    )
    _published, _staging, token, _expires = u.begin_save(db)
    # Correct controller.
    assert _mutate(
        db, token, _request(entity=HERO, controller={"kind": "run", "run_id": "R01"})
    )["entity_id"] == HERO
    # A Run cannot assert knowledge for a knower it does not own.
    err = _mutate_error(
        db, token, _request(entity=SIDEKICK, controller={"kind": "run", "run_id": "R01"})
    )
    assert "no published Run currently controls" in err


def test_non_mutable_knower_has_mainrun_controller(db):
    _published, _staging, token, _expires = u.begin_save(db)
    assert _mutate(db, token, _request(entity=LOCATION))["entity_id"] == LOCATION
    u.abort_save(db, token)

    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    # A Run can never control a location; MAINRUN remains its controller.
    assert _mutate(db, token, _request(entity=LOCATION))["entity_id"] == LOCATION
    err = _mutate_error(
        db, token, _request(entity=LOCATION, controller={"kind": "run", "run_id": "R01"})
    )
    assert "no published Run currently controls" in err


def test_run_claims_alone_never_authorize_knowledge_mutation(db):
    # R01 exists but owns no one; a dm_meta.run_claims reservation for HERO is
    # coordination metadata only.
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(db, token, "dm_meta", {"run_claims": {"R01": [HERO]}})
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    # The claim does not grant R01 authority over HERO...
    err = _mutate_error(
        db, token, _request(entity=HERO, controller={"kind": "run", "run_id": "R01"})
    )
    assert "no published Run currently controls" in err
    # ...and MAINRUN is still the truthful controller.
    assert _mutate(db, token, _request(entity=HERO))["entity_id"] == HERO


def test_wrong_stale_and_unknown_run_assertions_fail_closed(db):
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(
                run_id="R02",
                participant_entity_ids=[SIDEKICK],
                mutable_owner_entity_ids=[SIDEKICK],
            ),
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    # A different owning Run does not own HERO.
    err = _mutate_error(
        db, token, _request(entity=HERO, controller={"kind": "run", "run_id": "R02"})
    )
    assert "does not own it" in err
    # A Run that does not exist is not a controller.
    err = _mutate_error(
        db, token, _request(entity=HERO, controller={"kind": "run", "run_id": "R99"})
    )
    assert "does not own it" in err


def test_ambiguous_and_malformed_published_run_truth_fail_closed(db):
    # Two distinct Runs claiming one knower is ambiguous.
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", mutable_owner_entity_ids=[HERO]),
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "more than one published Run" in err
    u.abort_save(db, token)

    # A parked played Run that still claims the knower is not a controller.
    u.publish_confirmed_runs(
        db,
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[HERO])],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "parked" in err
    u.abort_save(db, token)

    # A duplicated authoritative Run identity is ambiguous.
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R01", mutable_owner_entity_ids=[]),
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "duplicate authoritative Run identity" in err
    u.abort_save(db, token)

    # A malformed published runs namespace fails closed.
    u.publish_confirmed_runs(db, "not-an-array")
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "runs" in err.lower()
    u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 6. Same-save compatibility (both orderings)
# ---------------------------------------------------------------------------

def test_same_save_run_ownership_change_closes_knowledge_mutation(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage_runs(db, token, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "runs batch" in err and "knowledge" in err.lower()


def test_knowledge_staged_closes_later_run_ownership_and_reconciliation(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db, token, _request(entity=HERO, controller={"kind": "run", "run_id": "R01"})
    )

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    assert "knowledge" in err_stage.lower()

    err_delete = _delete_error(db, token, "runs")
    assert "knowledge" in err_delete.lower()

    err_reconcile = _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(u.request(u.resolution(run_id="R01")))),
        ),
    )
    assert "knowledge" in err_reconcile.lower()


def test_compatibility_policy_declares_the_knowledge_edges(db):
    for operation in ("stage_runs", "delete_runs", "reconcile_runs"):
        policy = _compat_policy(db, operation)
        blocked_by = [edge["blocked_by"] for edge in policy["edges"]]
        assert "entity_knowledge" in blocked_by
        edge = next(e for e in policy["edges"] if e["blocked_by"] == "entity_knowledge")
        assert edge["detector"] == "knowledge_staged_in_save"

    knowledge_op = _compat_policy(db, "mutate_entity_knowledge")
    assert knowledge_op["known"] is True
    assert knowledge_op["domain"] == "entity_knowledge"
    assert [e["blocked_by"] for e in knowledge_op["edges"]] == ["runs"]
    assert knowledge_op["edges"][0]["detector"] == "runs_changed_in_save"

    # Unknown operations still fail closed.
    unknown = _compat_policy(db, "__post_ev2_3_unknown_operation__")
    assert unknown["known"] is False


# ---------------------------------------------------------------------------
# 7. Handoff + no propagation
# ---------------------------------------------------------------------------

def test_knowledge_stays_with_the_knower_across_handoffs(db):
    # MAINRUN writes HERO's knowledge.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO, knowledge=_known([_assertion_entry(value="Camp")])))
    u.publish(db, token)
    u.confirm_mirror(db)
    assert [r["entity_id"] for r in _published_knowledge(db)] == [HERO]

    # Ownership hands to RUN R01 in a later save; knowledge stays on HERO.
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    assert [r["entity_id"] for r in _published_knowledge(db)] == [HERO]

    # The Run controller may update HERO's own knowledge.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(entity=HERO, controller={"kind": "run", "run_id": "R01"},
                 knowledge=_known([_assertion_entry(value="Camp revisited")])),
    )
    u.publish(db, token)
    u.confirm_mirror(db)
    records = _published_knowledge(db)
    assert len(records) == 1 and records[0]["entity_id"] == HERO
    assert records[0]["entries"][0]["value"] == "Camp revisited"
    # No other entity (or party member) received a copy.
    assert SIDEKICK not in {r["entity_id"] for r in records}
    assert PARTY not in {r["entity_id"] for r in records}

    # Ownership hands back to MAINRUN via reconciliation; knowledge persists.
    _published, _staging, token, _expires = u.begin_save(db)
    u.reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))
    u.publish(db, token)
    u.confirm_mirror(db)
    records = _published_knowledge(db)
    assert len(records) == 1 and records[0]["entity_id"] == HERO
    assert SIDEKICK not in {r["entity_id"] for r in records}


def test_visibility_and_fact_existence_do_not_grant_character_knowledge(db):
    _published, _staging, token, _expires = u.begin_save(db)
    # A player-visible (non_meta) assertion and a fact reference are both just
    # one knower's own record; neither teaches anyone else.
    _mutate(
        db,
        token,
        _request(
            entity=HERO,
            knowledge=_known(
                [
                    _assertion_entry(visibility="non_meta", value="the door is open"),
                    _fact_entry(fact_id="F999"),
                ]
            ),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_knowledge(db)
    assert [r["entity_id"] for r in records] == [HERO]
    assert SIDEKICK not in {r["entity_id"] for r in records}


# ---------------------------------------------------------------------------
# 8. RT04 preserves unsupported consequences / no prose-to-knowledge promotion
# ---------------------------------------------------------------------------

def test_rt04_preserves_unsupported_consequences_without_minting_knowledge(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    report = u.reconcile(
        db,
        token,
        u.request(
            u.resolution(
                run_id="R01",
                consequences=[
                    {
                        "consequence_id": "PC01",
                        "scope": "run_objective",
                        "kind": "objective_result",
                        "summary": "Apply the objective result.",
                        "related_entity_ids": [],
                        "location_ids": [],
                    },
                    {
                        "consequence_id": "PC02",
                        "scope": "participant",
                        "kind": "discovery",
                        "summary": "The hero discovers a hidden sigil.",
                        "related_entity_ids": [HERO],
                        "location_ids": [],
                    },
                ],
            )
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    preserved = report["preserved_consequences"]
    assert len(preserved) == 1
    assert preserved[0]["consequence_id"] == "PC02"
    assert preserved[0]["kind"] == "discovery"
    assert preserved[0]["missing_downstream_owner"]
    # A free-form consequence is evidence only: no EV2-14 record was synthesized.
    assert u.published_state(db).get("entity_knowledge") in (None, [])


# ---------------------------------------------------------------------------
# 9. Publication integrity + failure isolation
# ---------------------------------------------------------------------------

def test_publication_keeps_generation_git_ref_mirror_and_confirmation_valid(db):
    before = u.runtime_row(db)
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO))
    u.publish(db, token)
    u.confirm_mirror(db)

    row = u.runtime_row(db)
    assert row["published_generation"] == before["published_generation"] + 1
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"]
    assert row["last_confirmed_generation"] == row["published_generation"]
    assert row["last_confirmed_git_ref"] == row["published_git_ref"]
    assert row["save_in_progress"] is False


def test_failed_mutation_leaves_previous_published_generation_intact(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO, knowledge=_known([_assertion_entry(value="v1")])))
    u.publish(db, token)
    u.confirm_mirror(db)
    published_before = u.runtime_row(db)
    knowledge_before = _published_knowledge(db)

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate_error(
        db,
        token,
        _request(entity=HERO, knowledge=_known([_assertion_entry(epistemic_status="maybe")])),
    )
    u.abort_save(db, token)

    published_after = u.runtime_row(db)
    assert published_after["published_generation"] == published_before["published_generation"]
    assert published_after["published_git_ref"] == published_before["published_git_ref"]
    assert _published_knowledge(db) == knowledge_before


# ---------------------------------------------------------------------------
# 10. Authority boundary
# ---------------------------------------------------------------------------

def test_route_is_not_executable_by_anon_or_authenticated(db):
    _published, _staging, token, _expires = u.begin_save(db)
    for role in ("anon", "authenticated"):
        err = _error_as_role(
            db,
            role,
            lambda cur: cur.execute(
                "select public.mutate_entity_knowledge(%s, %s::jsonb)",
                (token, json.dumps(_request())),
            ),
        )
        assert "permission denied" in err.lower()


def test_internal_helpers_are_not_executable_by_service_role(db):
    for function, args in (
        ("_rhc_normalize_knowledge_entry", "('{}'::jsonb)"),
        ("_rhc_normalize_knowledge_body", "('{}'::jsonb)"),
        ("_rhc_normalize_knowledge_record", "('{}'::jsonb)"),
        ("_rhc_validate_knowledge_collection", "('[]'::jsonb)"),
        ("_rhc_save_domain_policy", "('entity_knowledge')"),
    ):
        err = _error_as_service(
            db,
            lambda cur, f=function, a=args: cur.execute(f"select public.{f}{a}"),
        )
        assert "permission denied" in err.lower()


# ---------------------------------------------------------------------------
# 11. PostgreSQL 17 install + behavior
# ---------------------------------------------------------------------------

def test_migration_and_route_work_on_postgresql17(db_pg17):
    _published, _staging, token, _expires = u.begin_save(db_pg17)
    result = _mutate(
        db_pg17,
        token,
        _request(knowledge=_known([_fact_entry(), _assertion_entry(visibility="non_meta")])),
    )
    assert result["entity_id"] == HERO
    u.publish(db_pg17, token)
    u.confirm_mirror(db_pg17)
    records = _published_knowledge(db_pg17)
    assert len(records) == 1 and records[0]["entity_id"] == HERO


def test_knowledge_migration_is_the_authorized_surface_file(db):
    assert _KNOWLEDGE_MIGRATION in FORWARD_MIGRATIONS
    assert _KNOWLEDGE_MIGRATION.name == (
        "20260924000001_post_ev2_3_knower_safe_run_impact.sql"
    )