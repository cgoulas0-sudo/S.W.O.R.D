"""POST-EV2-2 proof suite — HOT Run registry + reservations (real PostgreSQL).

The Mission (JOHNNY #134) reuses the engine that already exists: the published
`runs` array remains the only authoritative Run/controller registry, and the
existing generic `dm_meta` runtime key gains one optional coordination field,
`run_claims`, keyed by Run ID and holding stable target IDs only. No new runtime
key, SQL migration, dedicated mutation route, ownership ledger or lock service is
introduced.

Proved against real PostgreSQL 15 and 17 with disposable schemas and synthetic
data only. No live Supabase is touched. The HOT picture is a read/interpretation
convention over the two already-published runtime values (`runs` and
`dm_meta.run_claims`), so the proof publishes both through the real Save Gateway
and derives HOT from the published generation.
"""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-2 HOT Run registry needs a real PostgreSQL server"
)

# --- real-PostgreSQL harness -------------------------------------------------
# Deliberately self-contained in this single File, matching the POST-EV2-1 proof
# convention: the Mission Surface Budget authorizes exactly this one test file,
# and there is no conftest.py/helper module in this directory (a second bare
# `conftest` module would shadow another test directory's `conftest`).

ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))

# The migration frontier POST-EV2-2 starts from. This Mission adds no migration;
# POST-EV2-3 later appends exactly one authorized migration, so the frontier is
# the original 18-file chain plus that forward migration.
MIGRATION_NAMES = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
    "20260908000004_rt01c_runtime_published_git_handshake.sql",
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    "20260908000006_rt01d_dm_read_engineering_release.sql",
    "20260911000001_rt02_campaign_clock.sql",
    "20260911000002_rt03_canonical_run_runtime_read.sql",
    "20260912000001_rt04_safe_run_reconciliation.sql",
    "20260914000001_hwb02_save_runtime_authority.sql",
    "20260915000001_ev210_inventory_ownership.sql",
    "20260917000001_ev211_item_custody.sql",
    "20260919000001_ev2121_item_identity_admission.sql",
    "20260919000002_ev213_mutable_entity_state.sql",
    "20260920000001_ev213420_temporal_core.sql",
    "20260920000002_ev2131_timed_status_continuity.sql",
    "20260923000001_post_ev2_1_save_domain_policy_registry.sql",
    "20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql",
    "20260924000001_post_ev2_3_knower_safe_run_impact.sql",
    "20260925000001_post_ev2_4a_temporal_timespace_continuity.sql",
    "20260926000001_post_ev2_5_current_search.sql",
    "20260928000001_post_ev2_9_character_vitals_resources.sql",
    "20260929000001_post_ev2_10_character_rest.sql",
    "20260929000002_post_ev2_11_begin_day.sql",
)

# Source pin: POST-EV2-2 must not alter the EV2-08 Run schema. The pin is read
# from the CURRENT repository HEAD Git object, never the working tree and never
# a fixed historical revision, so it proves the reviewed HEAD still carries the
# unchanged schema while Windows CRLF checkout conversion and Linux LF checkout
# produce the exact same repository bytes and the same proof.
RUN_SCHEMA_PATH = "schemas/run.schema.json"
RUN_SCHEMA_PIN_REV = "HEAD"
RUN_SCHEMA_SHA256 = "04d562bc2ee8278171c61f2b64dbd7fab653697b8238c7334fd5f590d6a8315a"

# Patch 1A's exact runtime-domain registry, unchanged by this Mission.
GENERIC_KEYS = (
    "daily_recap",
    "day_resolution",
    "live_status",
    "dm_meta",
    "narrative_hooks",
    "runs",
)
DEDICATED_KEYS = (
    "campaign_clock",
    "run_reconciliations",
    "inventory",
    "item_custody",
    "item_admissions",
    "entity_state",
    "applied_statuses",
    "entity_knowledge",
    "temporal_positions",
    "character_mechanics",
    "character_rests",
)

# Patch 1B's `stage_runs` ordered blocking facts. POST-EV2-3 appends exactly one
# authorized owner-local knowledge edge, POST-EV2-4A appends exactly one
# authorized temporal-position edge, POST-EV2-9 appends exactly one authorized
# character-mechanics edge and POST-EV2-10 appends exactly one authorized
# character-rest edge; the POST-EV2-2 facts are unchanged.
STAGE_RUNS_BLOCKERS = (
    "run_reconciliations",
    "inventory",
    "item_custody",
    "entity_state",
    "applied_statuses",
    "entity_knowledge",
    "temporal_positions",
    "character_mechanics",
    "character_rests",
)

# The five files this Mission is authorized to change. Any tracked/working-tree
# diff outside this set is a STOP-and-return, not an opportunistic edit.
ALLOWED_SURFACES = frozenset(
    {
        "docs/POST-EV2-2-HOT-RUN-REGISTRY.md",
        "tests/post_ev2_2/test_hot_run_registry.py",
        "state/dm_meta.json",
        "state/README.md",
        ".github/workflows/rt01-runtime.yml",
    }
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
    "RHC_POST_EV22_PG_DSN",
    "RHC_POST_EV21_PG_DSN",
    "RHC_EV2131_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV22_PG17_DSN",
    "RHC_POST_EV21_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55433/rhc"

BOOTSTRAP_BASE = "a" * 40
CONFIRMED_RUNTIME = "b" * 40
RUN_ANCHOR = "c" * 40


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
        pytest.skip(f"POST-EV2-2 proof skipped (no server): {exc}")
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


# --- shared helpers ----------------------------------------------------------


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
    return scalar(db, "select public._rhc_save_domain_policy(%s)", (key,))


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
    return scalar(db, "select public.delete_staged_campaign_state(%s, %s)", (token, key))


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def staged_candidate(db, key):
    return scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation where csg.key = %s",
        (key,),
    )


def published_state(db):
    return scalar(
        db,
        "select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb) "
        "from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation",
    )


def published_generation(db):
    return scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )


def runtime_row(db):
    with db.cursor() as cur:
        cur.execute("select * from public.campaign_runtime where id = 1")
        columns = [description.name for description in cur.description]
        row = cur.fetchone()
    return dict(zip(columns, row))


def pending(db):
    return scalar(db, "select public.get_pending_runtime_mirror()")


def confirm_mirror(db):
    """Confirm the current pending mirror so the next save may begin."""
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


def publish_confirmed(db, state):
    """Stage + publish + mirror-confirm one generation carrying `state`."""
    _published, _staging, token, _expires = begin_save(db)
    for key, value in state.items():
        stage(db, token, key, value)
    publish(db, token)
    return confirm_mirror(db)


def read_run(db, run_id):
    return scalar(db, "select public.dm_runtime_read_run(%s)", (run_id,))


def run(
    run_id="R01",
    execution_mode="played",
    control_state="active",
    scenario_id="S01",
    occurred_encounter_ids=None,
    participant_entity_ids=None,
    mutable_owner_entity_ids=None,
    location_ids=None,
):
    return {
        "run_id": run_id,
        "execution_mode": execution_mode,
        "control_state": control_state,
        "scenario_id": scenario_id,
        "occurred_encounter_ids": (
            ["E01"] if occurred_encounter_ids is None else occurred_encounter_ids
        ),
        "participant_entity_ids": (
            ["character:test-hero"]
            if participant_entity_ids is None
            else participant_entity_ids
        ),
        "mutable_owner_entity_ids": (
            ["character:test-hero"]
            if mutable_owner_entity_ids is None
            else mutable_owner_entity_ids
        ),
        "location_ids": ["location:tavern"] if location_ids is None else location_ids,
        "campaign_anchor": {
            "base_commit": RUN_ANCHOR,
            "campaign_time": "Day 1, evening",
        },
    }


def dm_meta(run_claims):
    """A committed DM-only dm_meta value carrying only the coordination field."""
    return {
        "schema_version": 1,
        "system": "Rolling High Club DM Meta",
        "visibility": "meta",
        "status": "active",
        "current_day": None,
        "committed_hidden_truths": [],
        "durable_dm_plans": [],
        "ghost_seeds": [],
        "unresolved_reveal_conditions": [],
        "run_claims": run_claims,
        "last_update_source": None,
    }


def derive_hot(published):
    """The documented read/interpretation convention over published runtime state.

    A Run is HOT when it is a played Run with `control_state = active`, or it
    currently owns one or more mutable owners, or it has a current
    `dm_meta.run_claims[run_id]` entry. Nothing is persisted by deriving this.
    """
    runs = published.get("runs") or []
    meta = published.get("dm_meta") or {}
    claims = meta.get("run_claims") or {}
    hot = set()
    for entry in runs:
        if not isinstance(entry, dict):
            continue
        run_id = entry.get("run_id")
        if not isinstance(run_id, str):
            continue
        owners = entry.get("mutable_owner_entity_ids") or []
        if entry.get("control_state") == "active" or owners or run_id in claims:
            hot.add(run_id)
    return hot


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


# --- 1. Repository document is Unknown-safe and adds run_claims only ---------


def test_dm_meta_document_is_unknown_safe_and_run_claims_is_the_only_addition():
    document = json.loads((ROOT / "state" / "dm_meta.json").read_text(encoding="utf-8"))
    assert document["status"] == "uninitialized"
    assert document["visibility"] == "meta"
    assert document["current_day"] is None
    assert document["committed_hidden_truths"] == []
    assert document["durable_dm_plans"] == []
    assert document["ghost_seeds"] == []
    assert document["unresolved_reveal_conditions"] == []
    assert document["last_update_source"] is None
    # The one new field is empty coordination state, not campaign data.
    assert document["run_claims"] == {}
    assert set(document) == {
        "schema_version",
        "system",
        "purpose",
        "visibility",
        "status",
        "current_day",
        "committed_hidden_truths",
        "durable_dm_plans",
        "ghost_seeds",
        "unresolved_reveal_conditions",
        "run_claims",
        "last_update_source",
    }


# --- 2 & 12. No schema/migration/function/ledger/lock was introduced ---------


def test_forward_migration_set_is_unchanged():
    assert tuple(path.name for path in FORWARD_MIGRATIONS) == MIGRATION_NAMES


def git_object_bytes(rev, path):
    """Raw bytes of a tracked path as stored in the Git object at `rev`.

    Reads `rev:path` instead of the working tree so the proof is independent of
    platform line-ending conversion (Windows CRLF vs Linux LF).
    """
    return subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def test_run_schema_is_source_unchanged():
    schema_bytes = git_object_bytes(RUN_SCHEMA_PIN_REV, RUN_SCHEMA_PATH)
    assert hashlib.sha256(schema_bytes).hexdigest() == RUN_SCHEMA_SHA256
    schema = json.loads(schema_bytes)
    assert schema["additionalProperties"] is False
    assert "mutable_owner_entity_ids" in schema["required"]


def test_no_claim_runtime_key_function_ledger_or_lock_exists(db):
    # `run_claims` is not a runtime key: it is forbidden by Patch 1A.
    record = policy(db, "run_claims")
    assert record["admission"] == "forbidden"
    assert record["dedicated_routes"] == []
    assert "daily_recap" in record["stage_error"] and "runs" in record["stage_error"]

    # No dedicated claim mutation function was invented.
    with db.cursor() as cur:
        cur.execute(
            "select proname from pg_proc "
            "where pronamespace = 'public'::regnamespace "
            "and (proname ilike '%run_claim%' or proname ilike '%claim_run%' "
            "     or proname ilike '%reserve_run%' or proname ilike '%run_reservation%')"
        )
        names = [row[0] for row in cur.fetchall()]
    assert names == []


# --- 3 & 4. Patch 1A / Patch 1B runtime policy is unchanged ------------------


def test_patch_1a_still_classifies_runs_and_dm_meta_generic(db):
    for key in GENERIC_KEYS:
        record = policy(db, key)
        assert record["admission"] == "generic", key
        assert record["dedicated_routes"] == [], key
    for key in DEDICATED_KEYS:
        record = policy(db, key)
        assert record["admission"] == "dedicated", key


def test_patch_1b_stage_runs_blockers_are_unchanged(db):
    decision = scalar(
        db, "select public._rhc_same_save_compatibility_policy('stage_runs')"
    )
    assert decision["known"] is True
    assert decision["domain"] == "runs"
    assert tuple(edge["blocked_by"] for edge in decision["edges"]) == STAGE_RUNS_BLOCKERS


# --- 5. run_claims travels through the real gateway as ordinary dm_meta ------


def test_run_claims_stages_and_publishes_as_ordinary_dm_meta(db):
    claims = {"R01": ["H04", "location:aethel-guard"]}
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "dm_meta", dm_meta(claims))
    assert staged_candidate(db, "dm_meta")["run_claims"] == claims
    publish(db, token)

    published = published_state(db)
    assert published["dm_meta"]["run_claims"] == claims


# --- 6. One generation may carry runs + run_claims without a second store ----


def test_same_generation_carries_runs_and_claims_without_second_owner_store(db):
    runs = [run(run_id="R01")]
    claims = {"R01": ["H04"]}
    publish_confirmed(db, {"runs": runs, "dm_meta": dm_meta(claims)})

    published = published_state(db)
    assert published["runs"] == runs
    assert published["dm_meta"]["run_claims"] == claims
    # The claim is coordination metadata, never duplicated controller truth.
    assert "mutable_owner_entity_ids" not in json.dumps(published["dm_meta"])


# --- 7. RT03 reads Run authority from published `runs` alone -----------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_rt03_authority_is_independent_of_run_claims(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    runs = [run(run_id="R01", mutable_owner_entity_ids=["character:test-hero"])]
    publish_confirmed(db, {"runs": runs, "dm_meta": dm_meta({})})

    before = read_run(db, "R01")["run"]
    assert before["mutable_owner_entity_ids"] == ["character:test-hero"]

    # A later claim change publishes a new generation but cannot alter authority.
    publish_confirmed(
        db,
        {"dm_meta": dm_meta({"R01": ["H04", "S03"], "R02": ["character:other-hero"]})},
    )

    after = read_run(db, "R01")["run"]
    assert after == before
    published = published_state(db)
    assert published["runs"] == runs
    assert published["dm_meta"]["run_claims"]["R01"] == ["H04", "S03"]


# --- 8. Claims are added, changed and removed by absolute dm_meta staging ----


def test_claim_can_be_added_changed_and_removed_via_ordinary_staging(db):
    publish_confirmed(db, {"dm_meta": dm_meta({"R01": ["H04"]})})
    assert published_state(db)["dm_meta"]["run_claims"] == {"R01": ["H04"]}

    # Absolute replacement: changing R01's note and moving the note to R02.
    publish_confirmed(db, {"dm_meta": dm_meta({"R01": ["H04", "S03"], "R02": ["E02"]})})
    claims = published_state(db)["dm_meta"]["run_claims"]
    assert claims == {"R01": ["H04", "S03"], "R02": ["E02"]}

    # Clearing the reservation note removes it without touching Run history.
    publish_confirmed(db, {"dm_meta": dm_meta({})})
    assert published_state(db)["dm_meta"]["run_claims"] == {}


# --- 9. Clearing run_claims never deletes or alters a historical Run --------


def test_clearing_run_claims_preserves_historical_run_record(db):
    historical = [
        run(
            run_id="R01",
            control_state="parked",
            mutable_owner_entity_ids=[],
        )
    ]
    publish_confirmed(
        db, {"runs": historical, "dm_meta": dm_meta({"R01": ["H04"]})}
    )
    assert published_state(db)["dm_meta"]["run_claims"] == {"R01": ["H04"]}

    publish_confirmed(db, {"dm_meta": dm_meta({})})
    published = published_state(db)
    assert published["runs"] == historical
    assert published["dm_meta"]["run_claims"] == {}


# --- 10. The HOT interpretation over published runs + claims ----------------


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_hot_interpretation_over_published_state(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    runs = [
        run(run_id="R01", control_state="active"),
        run(
            run_id="R02",
            control_state="parked",
            mutable_owner_entity_ids=[],
        ),
        run(
            run_id="R03",
            control_state="parked",
            mutable_owner_entity_ids=[],
        ),
        run(
            run_id="R04",
            execution_mode="off_screen",
            control_state="not_applicable",
            mutable_owner_entity_ids=[],
        ),
    ]
    claims = {
        "R01": ["H04"],  # active + owned + claimed
        "R02": ["H05"],  # parked zero-owner but claimed
    }
    publish_confirmed(db, {"runs": runs, "dm_meta": dm_meta(claims)})

    published = published_state(db)
    # R01 active/owned and R02 claimed are HOT; parked/off-screen zero-owner
    # Runs without a claim remain historical truth but are not HOT.
    assert derive_hot(published) == {"R01", "R02"}
    # Historical Runs are still present in authoritative published state.
    assert {entry["run_id"] for entry in published["runs"]} == {
        "R01",
        "R02",
        "R03",
        "R04",
    }


# --- 11. Stable-ID families only; no path/write-permission fields -----------


def test_claim_values_are_stable_ids_across_all_documented_families(db):
    stable_ids = [
        "H04",
        "S03",
        "E02",
        "character:test-hero",
        "creature:test-wolf",
        "location:aethel-guard",
        "faction:iron-pact",
        "party:rolling-high",
        "item:vampire",
    ]
    claims = {"R01": stable_ids, "R02": ["S03"]}
    publish_confirmed(db, {"dm_meta": dm_meta(claims)})

    published = published_state(db)
    assert published["dm_meta"]["run_claims"] == claims
    # Convention guard: no repository path, filename or write-permission field.
    serialized = json.dumps(published["dm_meta"])
    assert "/" not in serialized
    for forbidden in ("permission", "write_scope", "lock", "impact_mode"):
        assert forbidden not in serialized


# --- 13. Lifecycle and raw-DML boundaries remain intact ---------------------


def test_lifecycle_and_raw_dml_boundary_unchanged(db):
    before = published_generation(db)
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "dm_meta", dm_meta({"R01": ["H04"]}))
    abort_save(db, token)
    assert published_generation(db) == before

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with db.cursor() as cur:
            cur.execute(
                "insert into public.campaign_state_generations "
                "(generation, key, value) values (999, 'dm_meta', '\"x\"'::jsonb)"
            )


def test_only_the_authorized_surfaces_are_in_scope():
    # Static guard mirroring the Mission Surface Budget (HWB enforces the real
    # fence at commit/PR time; this keeps the intended budget legible in-test).
    assert ALLOWED_SURFACES == {
        "docs/POST-EV2-2-HOT-RUN-REGISTRY.md",
        "tests/post_ev2_2/test_hot_run_registry.py",
        "state/dm_meta.json",
        "state/README.md",
        ".github/workflows/rt01-runtime.yml",
    }
    assert not re.search(r"supabase/migrations", "".join(sorted(ALLOWED_SURFACES)))
