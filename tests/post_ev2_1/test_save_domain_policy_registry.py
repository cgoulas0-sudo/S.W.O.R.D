"""POST-EV2-1 Patch 1A proof suite — Save domain policy registry (real PostgreSQL).

The Mission (JOHNNY #124) confirms, not hypothesizes, that the central generic
stage/delete guards accrete a hard-coded branch per new runtime domain. Patch 1A
adds ONE server-owned, machine-readable policy registry
(`public._rhc_save_domain_policy`) and routes the generic
`stage_campaign_state` / `delete_staged_campaign_state` generic-vs-dedicated
admission and the HWB-02 ordinary-save allowlist through it, with NO semantic
behavior change.

Proved against real PostgreSQL 15 and 17 with disposable schemas and synthetic
policy data only. No live Supabase is touched. The equivalence proof compares the
exact stage/delete outcome for a key matrix before and after the registry
migration so this patch is behaviorally indistinguishable from repository `main`
plus Patch 1A.
"""

import json
import os
import re
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-1 Patch 1A needs a real PostgreSQL server"
)

# --- real-PostgreSQL harness -------------------------------------------------
# Deliberately self-contained in this single File. The Mission Surface Budget
# authorizes exactly this one test file, and there is no conftest.py/helper
# module in this directory (a second bare `conftest` module would shadow another
# test directory's `conftest` and break its `from conftest import`).

ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
REGISTRY_MIGRATION = _MIGRATIONS_DIR / (
    "20260923000001_post_ev2_1_save_domain_policy_registry.sql"
)
# The exact state of repository `main` at the Mission BASE: every migration
# before the Patch 1A registry migration.
PRE_PATCH_MIGRATIONS = tuple(
    migration for migration in FORWARD_MIGRATIONS if migration != REGISTRY_MIGRATION
)

_BASELINE_ROLES = (
    ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
).read_text(encoding="utf-8")
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)

_DSN_PRECEDENCE = (
    "RHC_POST_EV21_PG_DSN",
    "RHC_EV2131_PG_DSN",
    "RHC_EV213420_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV21_PG17_DSN",
    "RHC_EV2131_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55433/rhc"


def _first_dsn(variables, fallback):
    for variable in variables:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return fallback


def install_chain(connection, migrations=FORWARD_MIGRATIONS):
    """Install the baseline roles plus the given forward migration chain."""
    with connection.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES)
        for statement in _SCHEMA_RESET:
            cursor.execute(statement)
        for migration in migrations:
            cursor.execute(migration.read_text(encoding="utf-8"))


def _connect(connection_factory, dsn):
    try:
        connection = connection_factory(dsn)
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"POST-EV2-1 Patch 1A proof skipped (no server): {exc}")
    connection.autocommit = True
    return connection


@pytest.fixture(scope="session")
def database_server():
    connection = _connect(psycopg2.connect, _first_dsn(_DSN_PRECEDENCE, _FALLBACK_DSN))
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    install_chain(database_server)
    return database_server


@pytest.fixture()
def db_pre_patch(database_server):
    install_chain(database_server, PRE_PATCH_MIGRATIONS)
    return database_server


@pytest.fixture(scope="session")
def database_server_pg17():
    connection = _connect(
        psycopg2.connect, _first_dsn(_PG17_DSN_PRECEDENCE, _PG17_FALLBACK_DSN)
    )
    yield connection
    connection.close()


@pytest.fixture()
def db_pg17(database_server_pg17):
    install_chain(database_server_pg17)
    return database_server_pg17

GENERIC_KEYS = (
    "daily_recap",
    "day_resolution",
    "live_status",
    "dm_meta",
    "narrative_hooks",
    "runs",
)

# The immutable registry contract: dedicated keys, the EXHAUSTIVE set of legal
# writers for each, and the exact historical fail-closed messages the generic
# routes must still raise. `routes` is exhaustive, never a single writer.
DEDICATED_KEYS = {
    "campaign_clock": {
        "routes": ("stage_campaign_clock",),
        "stage": "campaign_clock must be staged through stage_campaign_clock",
        "delete": "campaign_clock is engine-owned and cannot be deleted",
    },
    "run_reconciliations": {
        "routes": ("reconcile_run_resolution",),
        "stage": (
            "run_reconciliations is engine-owned and can only be staged through "
            "reconcile_run_resolution"
        ),
        "delete": "run_reconciliations is engine-owned and cannot be deleted",
    },
    "inventory": {
        "routes": ("mutate_owner_inventory",),
        "stage": (
            "inventory is engine-owned and can only be staged through "
            "mutate_owner_inventory"
        ),
        "delete": (
            "inventory is engine-owned and cannot be deleted through the generic "
            "route"
        ),
    },
    "item_custody": {
        "routes": ("mutate_item_custody", "admit_item_identity"),
        "stage": (
            "item_custody is engine-owned and can only be staged through "
            "mutate_item_custody or admit_item_identity"
        ),
        "delete": (
            "item_custody is engine-owned and cannot be deleted through the generic "
            "route"
        ),
    },
    "item_admissions": {
        "routes": ("admit_item_identity",),
        "stage": (
            "item_admissions is engine-owned and can only be staged through "
            "admit_item_identity"
        ),
        "delete": (
            "item_admissions is engine-owned and cannot be deleted through the "
            "generic route"
        ),
    },
    "entity_state": {
        "routes": ("mutate_entity_state",),
        "stage": (
            "entity_state is engine-owned and can only be staged through "
            "mutate_entity_state"
        ),
        "delete": (
            "entity_state is engine-owned and cannot be deleted through the generic "
            "route"
        ),
    },
    "applied_statuses": {
        "routes": ("mutate_applied_status",),
        "stage": (
            "applied_statuses is engine-owned and can only be staged through "
            "mutate_applied_status"
        ),
        "delete": (
            "applied_statuses is engine-owned and cannot be deleted through the "
            "generic route"
        ),
    },
}

ALLOWLIST_PHRASE = (
    "not allowed for campaign_save; the server-owned allowlist is daily_recap, "
    "day_resolution, live_status, dm_meta, narrative_hooks, runs; unknown or "
    "undeclared runtime keys fail closed (HWB-02 save runtime authority)"
)

BOOTSTRAP_BASE = "a" * 40
CONFIRMED_RUNTIME = "b" * 40
RUN_ANCHOR = "c" * 40


# --- helpers -----------------------------------------------------------------


def scalar(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
    value = row[0] if row else None
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def policy(db, key):
    return scalar(
        db, "select public._rhc_save_domain_policy(%s)", (key,)
    )


def begin_save(db):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()


def stage(db, token, key, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        )


def delete_staged(db, token, key):
    with db.cursor() as cur:
        cur.execute("select public.delete_staged_campaign_state(%s, %s)", (token, key))
        return cur.fetchone()[0]


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def expect_policy_error(db, sql, params, match):
    with pytest.raises(psycopg2.errors.RaiseException, match=re.escape(match)):
        with db.cursor() as cur:
            cur.execute(sql, params)


def staged_candidate(db, key):
    return scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation where csg.key = %s",
        (key,),
    )


def published_generation(db):
    return scalar(db, "select published_generation from public.campaign_runtime where id = 1")


def runtime_row(db):
    with db.cursor() as cur:
        cur.execute("select * from public.campaign_runtime where id = 1")
        columns = [d.name for d in cur.description]
        row = cur.fetchone()
    return dict(zip(columns, row))


def pending(db):
    return scalar(db, "select public.get_pending_runtime_mirror()")


def confirm_mirror(db):
    bootstrap = runtime_row(db)["last_confirmed_generation"] is None
    candidate = pending(db)
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            if bootstrap:
                cur.execute(
                    "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                    (candidate["generation"], candidate["mirror_token"], BOOTSTRAP_BASE),
                )
                candidate = pending(db)
            cur.execute(
                "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
                (candidate["generation"], candidate["mirror_token"], CONFIRMED_RUNTIME),
            )
        finally:
            cur.execute("reset role")
    return candidate


def publish_confirmed_state(db, key, value):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, value)
    publish(db, token)
    return confirm_mirror(db)


def break_glass(db, sql, params=None):
    previous = db.autocommit
    db.autocommit = False
    try:
        with db.cursor() as cur:
            cur.execute("select set_config('rhc.gated_write', 'active', true)")
            cur.execute(sql, params or ())
        db.commit()
    finally:
        try:
            db.rollback()
        except Exception:
            pass
        db.autocommit = previous


# --- 1. Registry classification is machine-readable and exact ---------------


@pytest.mark.parametrize("key", GENERIC_KEYS)
def test_registry_classifies_generic_keys(db, key):
    record = policy(db, key)
    assert record["key"] == key
    assert record["admission"] == "generic"
    assert record["dedicated_routes"] == []
    # No misleading singular field that could imply a complete single writer.
    assert "dedicated_route" not in record
    assert record["stage_error"] is None
    assert record["delete_error"] is None


@pytest.mark.parametrize("key", list(DEDICATED_KEYS))
def test_registry_classifies_dedicated_keys(db, key):
    record = policy(db, key)
    assert record["admission"] == "dedicated"
    assert record["dedicated_routes"] == list(DEDICATED_KEYS[key]["routes"])
    assert "dedicated_route" not in record
    assert record["stage_error"] == DEDICATED_KEYS[key]["stage"]
    assert record["delete_error"] == DEDICATED_KEYS[key]["delete"]


@pytest.mark.parametrize(
    "key", ("invented_domain", "campaign_epoch", "daily_recaps", "LIVE_STATUS", "runs_meta")
)
def test_registry_unknown_key_is_forbidden(db, key):
    record = policy(db, key)
    assert record["admission"] == "forbidden"
    assert record["dedicated_routes"] == []
    assert "dedicated_route" not in record
    assert record["stage_error"].startswith(f"campaign state key {key} is ")
    assert ALLOWLIST_PHRASE in record["stage_error"]
    assert record["delete_error"] == record["stage_error"]


# --- 1b. Dedicated-writer metadata is exhaustive (Codex P2 repair) ----------


def test_item_custody_lists_both_legal_writers(db):
    """`item_custody` has two legal writers; neither may be omitted."""
    record = policy(db, "item_custody")
    assert record["dedicated_routes"] == [
        "mutate_item_custody",
        "admit_item_identity",
    ]


def test_dedicated_writer_metadata_is_exhaustive_for_all_dedicated_domains(db):
    """Every current dedicated domain exposes an explicit, non-empty array.

    The contract is intentionally plural: a singular writer field could imply a
    complete writer set when it is not (e.g. item_custody), so it must not exist.
    """
    for key, contract in DEDICATED_KEYS.items():
        record = policy(db, key)
        assert record["admission"] == "dedicated", key
        assert isinstance(record["dedicated_routes"], list), key
        assert record["dedicated_routes"], key
        assert all(isinstance(route, str) and route for route in record["dedicated_routes"]), key
        assert record["dedicated_routes"] == list(contract["routes"]), key
        assert "dedicated_route" not in record, key

    for key in GENERIC_KEYS:
        record = policy(db, key)
        assert record["dedicated_routes"] == [], key
        assert "dedicated_route" not in record, key


def test_every_writer_name_is_a_real_function(db):
    """Each advertised dedicated writer is a callable public function."""
    for contract in DEDICATED_KEYS.values():
        for route in contract["routes"]:
            with db.cursor() as cur:
                cur.execute(
                    "select count(*) from pg_proc "
                    "where proname = %s and pronamespace = 'public'::regnamespace",
                    (route,),
                )
                assert cur.fetchone()[0] == 1, route


# --- 2. The registry source is server-owned and key-only ---------------------


def test_registry_helper_has_exactly_one_key_only_signature(db):
    with db.cursor() as cur:
        cur.execute(
            "select pg_get_function_arguments(p.oid) "
            "from pg_proc p "
            "where p.proname = '_rhc_save_domain_policy' "
            "and p.pronamespace = 'public'::regnamespace"
        )
        rows = cur.fetchall()
    assert rows == [("p_key text",)]


def test_registry_helper_is_not_executable_by_caller_roles(db):
    for role in ("anon", "authenticated", "service_role"):
        with db.cursor() as cur:
            cur.execute(f"set role {role}")
            try:
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute("select public._rhc_save_domain_policy('runs')")
            finally:
                cur.execute("reset role")


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_caller_cannot_supply_or_override_policy(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    # A caller-declared "policy" payload cannot whitelist an unknown key.
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'invented_domain', %s::jsonb)",
        (token, json.dumps({"admission": "generic", "allow": True})),
        "not allowed for campaign_save",
    )
    assert staged_candidate(db, "invented_domain") is None


# --- 3. Generic admission equivalence: allowed keys stage/delete ------------


@pytest.mark.parametrize("key", GENERIC_KEYS)
def test_allowed_key_stages(db, key):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, {"policy": key})
    assert staged_candidate(db, key) == {"policy": key}


@pytest.mark.parametrize("key", GENERIC_KEYS)
def test_allowed_key_deletes_symmetrically(db, key):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, {"policy": key})
    assert delete_staged(db, token, key) is True
    assert staged_candidate(db, key) is None
    assert delete_staged(db, token, key) is False


# --- 4. Dedicated keys remain generic-route forbidden with exact messages ---


@pytest.mark.parametrize("key", list(DEDICATED_KEYS))
def test_dedicated_key_stage_rejected_exactly(db, key):
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, %s, '{}'::jsonb)",
        (token, key),
        DEDICATED_KEYS[key]["stage"],
    )
    assert staged_candidate(db, key) is None


@pytest.mark.parametrize("key", list(DEDICATED_KEYS))
def test_dedicated_key_delete_rejected_exactly(db, key):
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, %s)",
        (token, key),
        DEDICATED_KEYS[key]["delete"],
    )


# --- 5. Unknown keys fail closed, stage and delete ---------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_unknown_key_stage_fails_closed_without_mutation(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
        (token,),
        "not allowed for campaign_save",
    )
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'campaign_epoch', '1'::jsonb)",
        (token,),
        "not allowed for campaign_save",
    )
    assert staged_candidate(db, "invented_domain") is None
    assert staged_candidate(db, "campaign_epoch") is None


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_unknown_key_delete_fails_closed(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'invented_domain')",
        (token,),
        "not allowed for campaign_save",
    )


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_unknown_key_is_symmetric_with_adjacent_spelling(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    for near_miss in ("daily_recaps", "runs_meta", "live_status ", "LIVE_STATUS"):
        expect_policy_error(
            db,
            "select public.stage_campaign_state(%s, %s, '{}'::jsonb)",
            (token, near_miss),
            "not allowed for campaign_save",
        )
        expect_policy_error(
            db,
            "select public.delete_staged_campaign_state(%s, %s)",
            (token, near_miss),
            "not allowed for campaign_save",
        )


# --- 6. Dedicated semantic routes are unchanged ------------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_campaign_clock_dedicated_route_still_works(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    target = {
        "schema_version": 1,
        "day": 3,
        "phase": "morning",
        "elapsed_campaign_minutes": 200,
        "long_rests_completed": 0,
    }
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(target)),
        )
    assert staged_candidate(db, "campaign_clock") == target


# --- 7. `runs` same-save coupling guards remain inline and identical ---------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_runs_closure_still_fires_on_new_same_save_marker(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, staging, token, _expires = begin_save(db)
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(%s, 'run_reconciliations', '{\"RP_POLICY\": {\"resolution_id\": \"RP_POLICY\"}}'::jsonb, now(), now())",
        (staging,),
    )
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)",
        (token,),
        "the runs batch is engine-owned for the rest of this save",
    )
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'runs')",
        (token,),
        "the runs batch is engine-owned for the rest of this save",
    )


def test_historical_reconciliation_receipt_does_not_close_runs(db):
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(0, 'run_reconciliations', '{\"RP_OLD\": {\"resolution_id\": \"RP_OLD\"}}'::jsonb, now(), now())",
    )
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "runs", [{"run_id": "R01"}])
    assert staged_candidate(db, "runs") == [{"run_id": "R01"}]


# --- 8. Lifecycle, raw-DML guards and privileges unchanged -------------------


def test_begin_abort_publish_lifecycle_unchanged(db):
    before = published_generation(db)
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "live_status", {"state": "scouting"})
    abort_save(db, token)
    assert published_generation(db) == before

    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "live_status", {"state": "scouting"})
    publish(db, token)
    assert published_generation(db) == before + 1
    assert runtime_row(db)["save_in_progress"] is False


def test_ungated_raw_dml_still_blocked(db):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with db.cursor() as cur:
            cur.execute(
                "insert into public.campaign_state_generations "
                "(generation, key, value) values (999, 'daily_recap', '\"x\"'::jsonb)"
            )


def test_service_role_still_routed_through_gateway(db):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        token = cur.fetchone()[2]
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "insert into public.campaign_state_generations "
                    "(generation, key, value) values (999, 'daily_recap', '\"x\"'::jsonb)"
                )
        finally:
            cur.execute("reset role")
    stage(db, token, "daily_recap", {"via": "gateway"})
    assert staged_candidate(db, "daily_recap") == {"via": "gateway"}


def test_engineering_release_cannot_stage_or_delete_campaign_state(db):
    publish_confirmed_state(db, "daily_recap", {"confirmed": True})
    with db.cursor() as cur:
        cur.execute("select * from public.begin_engineering_release(%s, 30)", ("e" * 40,))
        eng_token = cur.fetchone()[4]
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'daily_recap', '\"nope\"'::jsonb)",
        (eng_token,),
        "engineering_release forbids campaign state mutation",
    )
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'daily_recap')",
        (eng_token,),
        "engineering_release forbids campaign state mutation",
    )


# --- 9. Behavioral equivalence with the pre-Patch-1A chain -------------------


def _error_primary(exc):
    """The server primary message only, independent of RAISE line numbers."""
    diag = getattr(exc, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    return primary or str(exc).splitlines()[0]


def _capture_outcomes(db, keys):
    outcomes = {}
    for key in keys:
        _published, _staging, token, _expires = begin_save(db)
        try:
            stage(db, token, key, {"probe": key})
            outcomes[("stage", key)] = "ok"
        except psycopg2.Error as exc:  # noqa: BLE001 - equivalence capture
            outcomes[("stage", key)] = _error_primary(exc)
        abort_save(db, token)

        _published, _staging, token, _expires = begin_save(db)
        try:
            outcomes[("delete", key)] = f"ok:{delete_staged(db, token, key)}"
        except psycopg2.Error as exc:  # noqa: BLE001 - equivalence capture
            outcomes[("delete", key)] = _error_primary(exc)
        abort_save(db, token)
    return outcomes


def test_fresh_replay_reaches_same_effective_policy_as_main_plus_patch_1a(db_pre_patch):
    matrix = (
        GENERIC_KEYS
        + tuple(DEDICATED_KEYS)
        + ("invented_domain", "campaign_epoch", "daily_recaps", "LIVE_STATUS", "runs_meta")
    )
    before = _capture_outcomes(db_pre_patch, matrix)

    # Fresh full replay now includes the Patch 1A registry migration.
    install_chain(db_pre_patch, FORWARD_MIGRATIONS)
    after = _capture_outcomes(db_pre_patch, matrix)

    assert before == after
    # Guard the proof itself: the matrix must exercise both outcomes.
    assert any(value == "ok" for value in before.values())
    assert any(value.startswith("campaign state key") for value in before.values())
