"""POST-EV2-4A proof suite — temporal / timespace travel continuity.

Runs against real PostgreSQL 15 and 17 with the full forward migration chain
(RT01-A/B/C/D + RT02 + RT03 + RT04 + HWB-02 + EV2-10 + EV2-11 + EV2-12.1 +
EV2-13 + EV2-13.420 + EV2-13.1 + POST-EV2-1 Patch 1A/1B + POST-EV2-2 +
POST-EV2-3 + POST-EV2-4A) with disposable schemas and synthetic data only. No
live Supabase is touched and no real RHC chronology is imported.

The runtime proof proves that:

  * POST-EV2-1 Patch 1A classifies `temporal_positions` as `dedicated` with
    exactly `mutate_temporal_position` as its legal writer, and the generic
    stage/delete routes fail closed for it;
  * absence of a lane record is truthful Unknown, never an invented default date;
  * a MAINRUN lane can hold a known exact destination while Campaign Day and RT02
    elapsed time stay byte-for-byte unchanged;
  * a partial destination stays partial and an Unknown chronology/timespace stays
    Unknown — no finer precision is invented;
  * a backward or forward world-date placement changes no elapsed anchor, entity
    state, applied status or knowledge record, and never decrements Campaign Day,
    RT02 elapsed minutes or Long Rest count;
  * a supported relative whole-year displacement pins its exact source position,
    derives one stable absolute target, preserves already-known finer components
    and the current timespace, converges under same-save and post-publication
    retries, and fails closed on stale sources, unsupported day/month arithmetic
    or an Unknown source year;
  * a valid published active RUN # can hold a position different from MAINRUN at
    the same campaign moment, and the two lanes never overwrite one another;
  * missing / malformed / duplicate / parked / non-authoritative published Run
    truth fails closed for a RUN-scoped placement, and `dm_meta.run_claims` grants
    no temporal authority;
  * a same-save `runs` change closes a RUN-scoped placement, and a staged
    RUN-scoped placement closes the later Run-ownership/reconciliation doorways
    through Patch 1B — while a MAINRUN placement does neither;
  * replay is absolute/idempotent and successful publication advances the
    generation through the real mirror/confirmation handshake, leaving the prior
    generation intact on failure;
  * the route is service-role-only; the internal helpers are not caller reachable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-4A needs real PostgreSQL servers"
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_TEMPORAL_MIGRATION = _MIGRATIONS_DIR / (
    "20260925000001_post_ev2_4a_temporal_timespace_continuity.sql"
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
    "RHC_POST_EV24A_PG_DSN",
    "RHC_POST_EV23_PG_DSN",
    "RHC_POST_EV22_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV24A_PG17_DSN",
    "RHC_POST_EV23_PG17_DSN",
    "RHC_POST_EV22_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

HERO = "character:test-hero"
RUN_REF = "run:R01"


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
        pytest.skip(f"POST-EV2-4A proof skipped (no server): {exc}")
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
            "select public.mutate_temporal_position(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_temporal_position(%s, %s::jsonb)",
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


def _published_positions(db):
    return u.published_state(db).get("temporal_positions") or []


def _staged_positions(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'temporal_positions'",
    )
    return value or []


def _by_lane(db):
    return {r["lane"]: r for r in _published_positions(db)}


def _unknown():
    return {"status": "unknown"}


def _known(ref="material-plane"):
    return {"status": "known", "ref": ref}


def _exact_chronology(
    year=1490, month=7, day=12, hour=9, minute=30
):
    return {"year": year, "month": month, "day": day, "hour": hour, "minute": minute}


def _absolute(controller=None, chronology=None, timespace=None):
    return {
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "target": {
            "chronology": {} if chronology is None else chronology,
            "timespace": _unknown() if timespace is None else timespace,
        },
    }


def _relative(
    controller=None,
    displacement=-400,
    timespace=None,
    from_chronology=None,
    from_timespace=None,
):
    request = {
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "relative_year_displacement": displacement,
        "relative_from": {
            "chronology": (
                _exact_chronology()
                if from_chronology is None
                else from_chronology
            ),
            "timespace": (
                _known("material-plane")
                if from_timespace is None
                else from_timespace
            ),
        },
    }
    if timespace is not None:
        request["timespace"] = timespace
    return request


def _run_controller(run_id="R01"):
    return {"kind": "run", "run_id": run_id}


def _publish_clock(db, clock):
    _published, _staging, token, _expires = u.begin_save(db)
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(clock)),
        )
    u.publish(db, token)
    u.confirm_mirror(db)


def _seed_published_key(db, key, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def _without_positions(db):
    state = dict(u.published_state(db))
    state.pop("temporal_positions", None)
    return state


def _policy(db, key):
    return u.scalar(db, "select public._rhc_save_domain_policy(%s)", (key,))


def _compat_policy(db, operation):
    return u.scalar(
        db, "select public._rhc_same_save_compatibility_policy(%s)", (operation,)
    )


# ---------------------------------------------------------------------------
# 1. Patch 1A registry classification + generic bypass closure
# ---------------------------------------------------------------------------

def test_patch_1a_classifies_temporal_positions_as_dedicated(db):
    policy = _policy(db, "temporal_positions")
    assert policy["admission"] == "dedicated"
    assert policy["dedicated_routes"] == ["mutate_temporal_position"]

    for key in ("daily_recap", "runs", "dm_meta", "narrative_hooks",
                "day_resolution", "live_status"):
        assert _policy(db, key)["admission"] == "generic"
    for key in ("campaign_clock", "run_reconciliations", "inventory",
                "item_custody", "item_admissions", "entity_state",
                "applied_statuses", "entity_knowledge"):
        assert _policy(db, key)["admission"] == "dedicated"

    unknown = _policy(db, "__post_ev2_4a_unknown_key__")
    assert unknown["admission"] == "forbidden"
    assert unknown["dedicated_routes"] == []


def test_generic_stage_and_delete_of_temporal_positions_fail_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)

    err_stage = _stage_error(
        db, token, "temporal_positions", [{"lane": "mainrun"}]
    )
    assert "mutate_temporal_position" in err_stage

    err_delete = _delete_error(db, token, "temporal_positions")
    assert "temporal_positions" in err_delete

    # The generic routes still admit the ordinary allowlist unchanged.
    u.stage(db, token, "live_status", {"scene": "portal-chamber"})
    u.publish(db, token)
    u.confirm_mirror(db)
    assert u.published_state(db).get("live_status") == {"scene": "portal-chamber"}


# ---------------------------------------------------------------------------
# 2. Truthful Unknown: no record means no invented default position
# ---------------------------------------------------------------------------

def test_absence_of_a_position_is_truthful_unknown(db):
    assert _published_positions(db) == []
    read = u.dm_read(db, "temporal_positions")
    assert read["results"] == []

    # A relative displacement from a lane that has no position fails closed.
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _relative(displacement=-400))
    assert "no current temporal position" in err


# ---------------------------------------------------------------------------
# 3. Exact destination with byte-for-byte unchanged Campaign Day / RT02 time
# ---------------------------------------------------------------------------

def test_mainrun_exact_destination_leaves_clock_and_day_unchanged(db):
    clock = {
        "schema_version": 1,
        "day": 3,
        "phase": "evening",
        "elapsed_campaign_minutes": 120,
        "long_rests_completed": 1,
    }
    _publish_clock(db, clock)
    before = _without_positions(db)
    before_row = u.runtime_row(db)

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _absolute(chronology=_exact_chronology(), timespace=_known("material-plane")),
    )
    assert result["lane"] == "mainrun"
    assert result["temporal_position_mutation_version"] == 1
    assert _published_positions(db) == []  # invisible until confirmed

    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_positions(db)
    assert len(records) == 1
    assert records[0] == {
        "lane": "mainrun",
        "chronology": _exact_chronology(),
        "timespace": {"status": "known", "ref": "material-plane"},
    }
    # Campaign Day identity and RT02 experienced time are byte-for-byte unchanged.
    after = _without_positions(db)
    assert after == before
    assert u.published_state(db)["campaign_clock"] == clock
    assert u.runtime_row(db)["published_day"] == before_row["published_day"]


# ---------------------------------------------------------------------------
# 4. Partial / Unknown destinations never gain invented precision
# ---------------------------------------------------------------------------

def test_partial_destination_stays_partial(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"year": 1490, "month": 7}))
    u.publish(db, token)
    u.confirm_mirror(db)

    record = _published_positions(db)[0]
    assert record["chronology"] == {"year": 1490, "month": 7}
    assert "day" not in record["chronology"]
    assert "hour" not in record["chronology"]
    assert "minute" not in record["chronology"]


def test_unknown_chronology_and_timespace_stay_unknown(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={}, timespace=_unknown()))
    u.publish(db, token)
    u.confirm_mirror(db)

    record = _published_positions(db)[0]
    assert record == {
        "lane": "mainrun",
        "chronology": {},
        "timespace": {"status": "unknown"},
    }


# ---------------------------------------------------------------------------
# 5. World-calendar movement never touches elapsed time / other domains
# ---------------------------------------------------------------------------

def test_backward_and_forward_placement_leave_every_other_domain_untouched(db):
    clock = {
        "schema_version": 1,
        "day": 5,
        "phase": "night",
        "elapsed_campaign_minutes": 600,
        "long_rests_completed": 2,
    }
    _publish_clock(db, clock)
    # Seed unrelated owner-local state so the proof is not vacuous.
    _seed_published_key(
        db,
        "entity_knowledge",
        [{"entity_id": HERO, "status": "unknown"}],
    )
    _seed_published_key(
        db,
        "entity_state",
        [{"entity_id": HERO, "status": "unknown"}],
    )
    _seed_published_key(
        db,
        "applied_statuses",
        [{"application_id": "AS01", "target_entity_id": HERO}],
    )
    before = _without_positions(db)
    before_day = u.runtime_row(db)["published_day"]

    # Exact known position, then a backwards 400-year jump, then a forwards jump.
    for displacement in (None, -400, 700):
        _published, _staging, token, _expires = u.begin_save(db)
        if displacement is None:
            _mutate(
                db,
                token,
                _absolute(
                    chronology=_exact_chronology(),
                    timespace=_known("material-plane"),
                ),
            )
        else:
            source_year = 1490 if displacement == -400 else 1090
            _mutate(
                db,
                token,
                _relative(
                    displacement=displacement,
                    from_chronology=_exact_chronology(year=source_year),
                    from_timespace=_known("material-plane"),
                ),
            )
        u.publish(db, token)
        u.confirm_mirror(db)

        assert u.published_state(db)["campaign_clock"] == clock
        assert u.runtime_row(db)["published_day"] == before_day
        after = _without_positions(db)
        assert after == before

    # RT02 elapsed minutes never moved backward and a future jump added no
    # intervening calendar years to elapsed time.
    assert u.published_state(db)["campaign_clock"]["elapsed_campaign_minutes"] == 600
    assert u.published_state(db)["campaign_clock"]["long_rests_completed"] == 2


# ---------------------------------------------------------------------------
# 6. Relative whole-year displacement preserves known finer components
# ---------------------------------------------------------------------------

def test_relative_whole_year_displacement_preserves_finer_components(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _absolute(
            chronology=_exact_chronology(year=1490),
            timespace=_known("material-plane"),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    # Backwards displacement with no timespace override: year shifts, finer
    # components and the current timespace are preserved exactly.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _relative(displacement=-400))
    u.publish(db, token)
    u.confirm_mirror(db)
    record = _published_positions(db)[0]
    assert record["chronology"] == _exact_chronology(year=1090)
    assert record["timespace"] == {"status": "known", "ref": "material-plane"}

    # Forward displacement with a timespace override changes both deterministically.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _relative(
            displacement=50,
            timespace=_known("feywild"),
            from_chronology=_exact_chronology(year=1090),
            from_timespace=_known("material-plane"),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)
    record = _published_positions(db)[0]
    assert record["chronology"] == _exact_chronology(year=1140)
    assert record["timespace"] == {"status": "known", "ref": "feywild"}


@pytest.mark.parametrize(
    "payload",
    [
        # Unsupported relative calendar arithmetic: month/day offsets are not
        # part of the contract and must fail closed.
        {"controller": {"kind": "mainrun"}, "relative_year_displacement": -400,
         "relative_month_displacement": 3},
        {"controller": {"kind": "mainrun"}, "relative_year_displacement": -400,
         "relative_day_displacement": 10},
        # Non-integral displacement.
        {"controller": {"kind": "mainrun"}, "relative_year_displacement": -400.5},
        # Both an absolute target and a relative displacement at once.
        {"controller": {"kind": "mainrun"}, "relative_year_displacement": -400,
         "target": {"chronology": {}, "timespace": {"status": "unknown"}}},
    ],
)
def test_unsupported_relative_arithmetic_fails_closed(db, payload):
    _published, _staging, token, _expires = u.begin_save(db)
    # Establish a known current position so the failure is about the arithmetic.
    _mutate(db, token, _absolute(chronology=_exact_chronology()))
    err = _mutate_error(db, token, payload)
    assert "relative" in err.lower() or "contract" in err.lower()


def test_relative_displacement_from_unknown_year_fails_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"month": 7}))
    err = _mutate_error(
        db,
        token,
        _relative(
            displacement=-400,
            from_chronology={"month": 7},
            from_timespace=_unknown(),
        ),
    )
    assert "Unknown world-calendar year" in err


@pytest.mark.parametrize(
    "chronology",
    [
        {"year": "1490"},
        {"year": 1490.5},
        {"month": -1},
        {"day": "x"},
        {"era": "DR"},
    ],
)
def test_invalid_chronology_shape_fails_closed(db, chronology):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _absolute(chronology=chronology))
    assert "chronology" in err.lower()


@pytest.mark.parametrize(
    "timespace",
    [
        {"status": "sometimes"},
        {"status": "known"},
        {"status": "unknown", "ref": "material-plane"},
        {"status": "known", "ref": ""},
        {"status": "known", "ref": "Bad Ref"},
        {"ref": "material-plane"},
    ],
)
def test_invalid_timespace_shape_fails_closed(db, timespace):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _absolute(timespace=timespace))
    assert "timespace" in err.lower()


# ---------------------------------------------------------------------------
# 7. MAINRUN and RUN # lanes are independent placements in one reality
# ---------------------------------------------------------------------------

def test_run_lane_can_hold_a_different_position_than_mainrun(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _absolute(chronology=_exact_chronology(year=1000), timespace=_known("material-plane")),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _absolute(
            controller=_run_controller("R01"),
            chronology=_exact_chronology(year=2000),
            timespace=_known("shadowfell"),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    lanes = _by_lane(db)
    assert set(lanes) == {"mainrun", RUN_REF}
    assert lanes["mainrun"]["chronology"]["year"] == 1000
    assert lanes["mainrun"]["timespace"] == {"status": "known", "ref": "material-plane"}
    assert lanes[RUN_REF]["chronology"]["year"] == 2000
    assert lanes[RUN_REF]["timespace"] == {"status": "known", "ref": "shadowfell"}


def test_lane_positions_do_not_overwrite_one_another(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"year": 1000}))
    _mutate(db, token, _absolute(controller=_run_controller("R01"),
                                 chronology={"year": 2000}))
    u.publish(db, token)
    u.confirm_mirror(db)

    lanes = _by_lane(db)
    assert len(_published_positions(db)) == 2
    assert lanes["mainrun"]["chronology"] == {"year": 1000}
    assert lanes[RUN_REF]["chronology"] == {"year": 2000}

    # Updating one lane leaves the other untouched.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(controller=_run_controller("R01"),
                                 chronology={"year": 2500}))
    u.publish(db, token)
    u.confirm_mirror(db)

    lanes = _by_lane(db)
    assert lanes["mainrun"]["chronology"] == {"year": 1000}
    assert lanes[RUN_REF]["chronology"] == {"year": 2500}


# ---------------------------------------------------------------------------
# 8. RUN lane authority: published Run truth only
# ---------------------------------------------------------------------------

def test_run_lane_requires_an_authoritative_published_run(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R99"), chronology={"year": 1})
    )
    assert "no published Run R99 exists" in err


def test_parked_run_is_not_an_active_temporal_lane(db):
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])]
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1})
    )
    assert "parked" in err


def test_malformed_and_duplicate_published_run_truth_fail_closed(db):
    u.publish_confirmed_runs(db, "not-an-array")
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1})
    )
    assert "runs" in err.lower()
    u.abort_save(db, token)

    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[]),
            u.run(run_id="R01", mutable_owner_entity_ids=[]),
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1})
    )
    assert "duplicate authoritative Run identity" in err


def test_run_claims_alone_grant_no_temporal_authority(db):
    # R01 exists but owns no one; a dm_meta.run_claims note about R99 is
    # coordination metadata only and cannot mint a temporal lane.
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(db, token, "dm_meta", {"run_claims": {"R99": [HERO]}})
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R99"), chronology={"year": 1})
    )
    assert "no published Run R99 exists" in err
    # The real published R01 lane remains valid.
    assert _mutate(
        db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1})
    )["lane"] == RUN_REF


# ---------------------------------------------------------------------------
# 9. Same-save compatibility both orderings (RUN-scoped only)
# ---------------------------------------------------------------------------

def test_same_save_runs_change_closes_run_scoped_temporal_mutation(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage_runs(db, token, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    err = _mutate_error(
        db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1})
    )
    assert "runs batch" in err and "temporal" in err.lower()


def test_run_scoped_placement_closes_later_run_ownership_and_reconciliation(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(controller=_run_controller("R01"), chronology={"year": 1}))

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    assert "temporal" in err_stage.lower()

    err_delete = _delete_error(db, token, "runs")
    assert "temporal" in err_delete.lower()

    err_reconcile = _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(u.request(u.resolution(run_id="R01")))),
        ),
    )
    assert "temporal" in err_reconcile.lower()


def test_mainrun_placement_does_not_block_runs_or_the_clock(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"year": 1490}))

    # A MAINRUN placement is not a RUN-scoped placement: a later same-save `runs`
    # change and Campaign Clock advance both remain legal.
    u.stage_runs(db, token, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (
                token,
                json.dumps(
                    {
                        "schema_version": 1,
                        "day": 1,
                        "phase": "dawn",
                        "elapsed_campaign_minutes": 30,
                        "long_rests_completed": 0,
                    }
                ),
            ),
        )
    u.abort_save(db, token)


def test_compatibility_policy_declares_the_temporal_edges(db):
    for operation in ("stage_runs", "delete_runs", "reconcile_runs"):
        policy = _compat_policy(db, operation)
        blocked_by = [edge["blocked_by"] for edge in policy["edges"]]
        assert "temporal_positions" in blocked_by
        edge = next(e for e in policy["edges"] if e["blocked_by"] == "temporal_positions")
        assert edge["detector"] == "temporal_position_staged_in_save"

    temporal_op = _compat_policy(db, "mutate_temporal_position")
    assert temporal_op["known"] is True
    assert temporal_op["domain"] == "temporal_positions"
    assert [e["blocked_by"] for e in temporal_op["edges"]] == ["runs"]
    assert temporal_op["edges"][0]["detector"] == "runs_changed_in_save"

    unknown = _compat_policy(db, "__post_ev2_4a_unknown_operation__")
    assert unknown["known"] is False


# ---------------------------------------------------------------------------
# 10. Replay, publication integrity and failure isolation
# ---------------------------------------------------------------------------

def test_absolute_target_is_replay_safe(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _absolute(chronology=_exact_chronology(year=1490))
    _mutate(db, token, request)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_positions(db)
    assert len(records) == 1
    assert records[0]["chronology"] == _exact_chronology(year=1490)


def test_relative_retry_is_idempotent_in_same_save_and_after_publication(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _absolute(
            chronology=_exact_chronology(year=1490),
            timespace=_known("material-plane"),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    request = _relative(
        displacement=-400,
        from_chronology=_exact_chronology(year=1490),
        from_timespace=_known("material-plane"),
    )

    _published, _staging, token, _expires = u.begin_save(db)
    first = _mutate(db, token, request)
    second = _mutate(db, token, request)
    assert first["temporal_position"] == second["temporal_position"]
    assert _staged_positions(db)[0]["chronology"] == _exact_chronology(year=1090)
    u.publish(db, token)
    u.confirm_mirror(db)
    assert _published_positions(db)[0]["chronology"] == _exact_chronology(year=1090)

    _published, _staging, token, _expires = u.begin_save(db)
    replay = _mutate(db, token, request)
    assert replay["temporal_position"]["chronology"] == _exact_chronology(year=1090)
    assert _staged_positions(db)[0]["chronology"] == _exact_chronology(year=1090)
    u.publish(db, token)
    u.confirm_mirror(db)
    assert _published_positions(db)[0]["chronology"] == _exact_chronology(year=1090)


def test_relative_retry_with_stale_source_fails_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _absolute(
            chronology=_exact_chronology(year=1090),
            timespace=_known("material-plane"),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    stale = _relative(
        displacement=50,
        from_chronology=_exact_chronology(year=1490),
        from_timespace=_known("material-plane"),
    )
    err = _mutate_error(db, token, stale)
    assert "stale or ambiguous" in err
    u.abort_save(db, token)
    assert _published_positions(db)[0]["chronology"] == _exact_chronology(year=1090)


def test_abort_discards_unpublished_placement(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"year": 1490}))
    u.abort_save(db, token)
    assert _published_positions(db) == []


def test_publication_keeps_generation_git_ref_mirror_and_confirmation_valid(db):
    before = u.runtime_row(db)
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _absolute(chronology={"year": 1490}))
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
    _mutate(db, token, _absolute(chronology={"year": 1490}))
    u.publish(db, token)
    u.confirm_mirror(db)
    published_before = u.runtime_row(db)
    positions_before = _published_positions(db)

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate_error(db, token, _absolute(timespace={"status": "sometimes"}))
    u.abort_save(db, token)

    published_after = u.runtime_row(db)
    assert published_after["published_generation"] == published_before["published_generation"]
    assert published_after["published_git_ref"] == published_before["published_git_ref"]
    assert _published_positions(db) == positions_before


def test_malformed_existing_namespace_fails_closed_even_for_unrelated_lane(db):
    _seed_published_key(
        db,
        "temporal_positions",
        [
            {"lane": "run:R01", "chronology": {"year": 1}, "timespace": _unknown()},
            {"lane": "run:R01", "chronology": {"year": 2}, "timespace": _unknown()},
        ],
    )
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _absolute(chronology={"year": 5}))
    assert "duplicate" in err.lower() or "temporal_positions" in err


# ---------------------------------------------------------------------------
# 11. Authority boundary
# ---------------------------------------------------------------------------

def test_route_is_not_executable_by_anon_or_authenticated(db):
    _published, _staging, token, _expires = u.begin_save(db)
    for role in ("anon", "authenticated"):
        err = _error_as_role(
            db,
            role,
            lambda cur: cur.execute(
                "select public.mutate_temporal_position(%s, %s::jsonb)",
                (token, json.dumps(_absolute(chronology={"year": 1}))),
            ),
        )
        assert "permission denied" in err.lower()


def test_internal_helpers_are_not_executable_by_service_role(db):
    for function, args in (
        ("_rhc_normalize_temporal_chronology", "('{}'::jsonb)"),
        ("_rhc_normalize_temporal_timespace", "('{}'::jsonb)"),
        ("_rhc_normalize_temporal_position_record", "('{}'::jsonb)"),
        ("_rhc_validate_temporal_positions_collection", "('[]'::jsonb)"),
        ("_rhc_save_domain_policy", "('temporal_positions')"),
    ):
        err = _error_as_service(
            db,
            lambda cur, f=function, a=args: cur.execute(f"select public.{f}{a}"),
        )
        assert "permission denied" in err.lower()


# ---------------------------------------------------------------------------
# 12. PostgreSQL 17 install + behavior
# ---------------------------------------------------------------------------

def test_migration_and_route_work_on_postgresql17(db_pg17):
    _published, _staging, token, _expires = u.begin_save(db_pg17)
    result = _mutate(
        db_pg17,
        token,
        _absolute(chronology=_exact_chronology(year=1490), timespace=_known("elemental-fire")),
    )
    assert result["lane"] == "mainrun"
    u.publish(db_pg17, token)
    u.confirm_mirror(db_pg17)
    records = _published_positions(db_pg17)
    assert len(records) == 1
    assert records[0]["timespace"] == {"status": "known", "ref": "elemental-fire"}


def test_temporal_migration_is_the_authorized_surface_file(db):
    assert _TEMPORAL_MIGRATION in FORWARD_MIGRATIONS
    assert _TEMPORAL_MIGRATION.name == (
        "20260925000001_post_ev2_4a_temporal_timespace_continuity.sql"
    )
