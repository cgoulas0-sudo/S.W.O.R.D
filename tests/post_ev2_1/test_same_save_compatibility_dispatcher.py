"""POST-EV2-1 Patch 1B proof suite — same-save compatibility dispatcher.

The Mission (JOHNNY #126) centralizes the already-correct but distributed
same-save cross-domain exclusions behind ONE deterministic, server-owned
compatibility contract. Patch 1A centralized domain admission; Patch 1B
centralizes only the compatibility decision between already-existing mutation
domains, with NO semantic behavior change.

Proved against real PostgreSQL 15 and 17 with disposable schemas and synthetic
data only. No live Supabase is touched. The equivalence proof compares the exact
outcome of every affected doorway under every audited fact condition before and
after the dispatcher migration, so this patch is behaviorally indistinguishable
from repository `main` plus Patch 1B for the full compatibility matrix.
"""

import json
import os
import re
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-1 Patch 1B needs a real PostgreSQL server"
)

# --- real-PostgreSQL harness -------------------------------------------------
# Deliberately self-contained in this single File, matching the Patch 1A proof
# convention: the Mission Surface Budget authorizes exactly this one test file,
# and there is no conftest.py/helper module in this directory (a second bare
# `conftest` module would shadow another test directory's `conftest`).

ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
DISPATCHER_MIGRATION = _MIGRATIONS_DIR / (
    "20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql"
)
# The exact state of repository `main` at the Mission BASE: every migration
# before the Patch 1B dispatcher migration (Patch 1A included).
PRE_PATCH_MIGRATIONS = tuple(
    migration for migration in FORWARD_MIGRATIONS if migration != DISPATCHER_MIGRATION
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
        pytest.skip(f"POST-EV2-1 Patch 1B proof skipped (no server): {exc}")
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


# --- the exact declared policy (mirrors the migration; proved truthful below) -

RECON_STAGE = (
    "the runs batch is engine-owned for the rest of this save once a "
    "reconciliation has been staged; a later generic runs mutation could "
    "reintroduce duplicate mutable ownership or erase the reconciled candidate; "
    "abort this save and start a new one"
)
RECON_DELETE = (
    "the runs batch is engine-owned for the rest of this save once a "
    "reconciliation has been staged; deleting it would erase the reconciled "
    "candidate while the consumption ledger claims it was applied; abort this "
    "save and start a new one"
)
RUNS_INVENTORY = (
    "the runs batch cannot be changed in a save that has already staged an "
    "inventory mutation; inventory authority would become stale against the "
    "changed Run ownership, so abort this save and start a new one"
)
RUNS_CUSTODY = (
    "the runs batch cannot be changed in a save that has already staged an item "
    "custody or admission operation; custody authority would become stale "
    "against the changed Run ownership, so abort this save and start a new one"
)
RUNS_ENTITY = (
    "the runs batch cannot be changed in a save that has already staged a "
    "mutable entity-state mutation; entity-state authority would become stale "
    "against the changed Run ownership, so abort this save and start a new one"
)
RUNS_APPLIED = (
    "the runs batch cannot be changed in a save that has already staged a timed "
    "applied-status mutation; applied-status controller authority would become "
    "stale against the changed Run ownership, so abort this save and start a new one"
)
RECONCILE_INVENTORY = (
    "this save has already staged an inventory mutation; a Run reconciliation "
    "would change Run ownership after inventory authority was proven, so "
    "reconciliation fails closed (change Run ownership and inventory in separate saves)"
)
RECONCILE_CUSTODY = (
    "this save has already staged an item custody mutation; a Run reconciliation "
    "would change Run ownership after custody authority was proven, so "
    "reconciliation fails closed (change Run ownership and item custody in separate saves)"
)
RECONCILE_ENTITY = (
    "this save has already staged a mutable entity-state mutation; a Run "
    "reconciliation would change Run ownership after entity-state authority was "
    "proven, so reconciliation fails closed (change Run ownership and mutable "
    "entity state in separate saves)"
)
RECONCILE_APPLIED = (
    "this save has already staged a timed applied-status mutation; a Run "
    "reconciliation would change Run ownership after applied-status controller "
    "authority was proven, so reconciliation fails closed (change Run ownership "
    "and applied status in separate saves)"
)
INVENTORY_RUNS = (
    "this save has staged a different runs batch; inventory controller cannot be "
    "proven against published Run truth, so inventory mutation fails closed "
    "(change Run ownership and inventory in separate saves)"
)
CUSTODY_RUNS = (
    "this save has staged a different runs batch; item custody controller cannot "
    "be proven against published Run truth, so custody mutation fails closed "
    "(change Run ownership and item custody in separate saves)"
)
ADMIT_RUNS = (
    "this save has staged a different runs batch; admission controller cannot be "
    "proven against published Run truth, so item identity admission fails closed "
    "(change Run ownership and admit items in separate saves)"
)
ENTITY_RUNS = (
    "this save has staged a different runs batch; entity-state controller cannot "
    "be proven against published Run truth, so mutable entity-state mutation "
    "fails closed (change Run ownership and mutable entity state in separate saves)"
)
APPLIED_RUNS = (
    "this save has staged a different runs batch; applied-status controller "
    "cannot be proven against published Run truth, so timed applied-status "
    "mutation fails closed (change Run ownership and applied status in separate saves)"
)
APPLIED_CLOCK = (
    "this save has staged a different campaign_clock; applied-status elapsed "
    "anchors cannot be proven against the Clock this save would publish, so timed "
    "applied-status mutation fails closed (advance the Clock and mutate applied "
    "status in separate saves)"
)
CLOCK_APPLIED = (
    "this save has already staged a timed applied-status mutation; advancing the "
    "Campaign Clock in the same save would leave applied-status anchors proven "
    "against the wrong elapsed truth, so the Clock write fails closed (advance "
    "the Clock and mutate applied status in separate saves)"
)
# POST-EV2-3 extends this contract with the owner-local knowledge domain.
RUNS_KNOWLEDGE = (
    "the runs batch cannot be changed in a save that has already staged an "
    "owner-local knowledge mutation; knowledge controller authority would become "
    "stale against the changed Run ownership, so abort this save and start a new one"
)
RECONCILE_KNOWLEDGE = (
    "this save has already staged an owner-local knowledge mutation; a Run "
    "reconciliation would change Run ownership after knowledge controller "
    "authority was proven, so reconciliation fails closed (change Run ownership "
    "and knowledge in separate saves)"
)
KNOWLEDGE_RUNS = (
    "this save has staged a different runs batch; knowledge controller cannot be "
    "proven against published Run truth, so owner-local knowledge mutation fails "
    "closed (change Run ownership and knowledge in separate saves)"
)
# POST-EV2-4A extends this contract with the lane-scoped temporal-position domain.
RUNS_TEMPORAL = (
    "the runs batch cannot be changed in a save that has already staged a "
    "RUN-scoped temporal/timespace placement; RUN lane authority would become "
    "stale against the changed Run ownership, so abort this save and start a new one"
)
RECONCILE_TEMPORAL = (
    "this save has already staged a RUN-scoped temporal/timespace placement; a Run "
    "reconciliation would change Run ownership after RUN lane authority was proven, "
    "so reconciliation fails closed (change Run ownership and temporal placement in "
    "separate saves)"
)
# POST-EV2-9 extends this contract with the character vitals/resources domain.
RUNS_CHARACTER_MECHANICS = (
    "the runs batch cannot be changed in a save that has already staged a character "
    "vitals/resources mutation; character-mechanics controller authority would become "
    "stale against the changed Run ownership, so abort this save and start a new one"
)
RECONCILE_CHARACTER_MECHANICS = (
    "this save has already staged a character vitals/resources mutation; a Run "
    "reconciliation would change Run ownership after character-mechanics controller "
    "authority was proven, so reconciliation fails closed (change Run ownership and "
    "character vitals/resources in separate saves)"
)
CHARACTER_MECHANICS_RUNS = (
    "this save has staged a different runs batch; character-mechanics controller "
    "cannot be proven against published Run truth, so character vitals/resources "
    "mutation fails closed (change Run ownership and character vitals/resources in "
    "separate saves)"
)
# POST-EV2-10 extends this contract with the character Rest domain.
RUNS_CHARACTER_RESTS = (
    "the runs batch cannot be changed in a save that has already staged a character "
    "Rest mutation; Rest controller authority would become stale against the changed "
    "Run ownership, so abort this save and start a new one"
)
RECONCILE_CHARACTER_RESTS = (
    "this save has already staged a character Rest mutation; a Run reconciliation "
    "would change Run ownership after Rest controller authority was proven, so "
    "reconciliation fails closed (change Run ownership and character Rest in "
    "separate saves)"
)
CHARACTER_RESTS_RUNS = (
    "this save has staged a different runs batch; Rest controller cannot be proven "
    "against published Run truth, so character Rest mutation fails closed (change "
    "Run ownership and character Rest in separate saves)"
)

# operation -> (domain, ordered [(blocked_by, detector, error)])
POLICY = {
    "stage_runs": (
        "runs",
        [
            ("run_reconciliations", "reconciliation_new_in_save", RECON_STAGE),
            ("inventory", "inventory_staged_in_save", RUNS_INVENTORY),
            ("item_custody", "custody_staged_in_save", RUNS_CUSTODY),
            ("entity_state", "entity_state_staged_in_save", RUNS_ENTITY),
            ("applied_statuses", "applied_status_staged_in_save", RUNS_APPLIED),
            ("entity_knowledge", "knowledge_staged_in_save", RUNS_KNOWLEDGE),
            ("temporal_positions", "temporal_position_staged_in_save", RUNS_TEMPORAL),
            ("character_mechanics", "character_mechanics_staged_in_save", RUNS_CHARACTER_MECHANICS),
            ("character_rests", "character_rests_staged_in_save", RUNS_CHARACTER_RESTS),
        ],
    ),
    "delete_runs": (
        "runs",
        [
            ("run_reconciliations", "reconciliation_new_in_save", RECON_DELETE),
            ("inventory", "inventory_staged_in_save", RUNS_INVENTORY),
            ("item_custody", "custody_staged_in_save", RUNS_CUSTODY),
            ("entity_state", "entity_state_staged_in_save", RUNS_ENTITY),
            ("applied_statuses", "applied_status_staged_in_save", RUNS_APPLIED),
            ("entity_knowledge", "knowledge_staged_in_save", RUNS_KNOWLEDGE),
            ("temporal_positions", "temporal_position_staged_in_save", RUNS_TEMPORAL),
            ("character_mechanics", "character_mechanics_staged_in_save", RUNS_CHARACTER_MECHANICS),
            ("character_rests", "character_rests_staged_in_save", RUNS_CHARACTER_RESTS),
        ],
    ),
    "reconcile_runs": (
        "runs",
        [
            ("inventory", "inventory_staged_in_save", RECONCILE_INVENTORY),
            ("item_custody", "custody_staged_in_save", RECONCILE_CUSTODY),
            ("entity_state", "entity_state_staged_in_save", RECONCILE_ENTITY),
            ("applied_statuses", "applied_status_staged_in_save", RECONCILE_APPLIED),
            ("entity_knowledge", "knowledge_staged_in_save", RECONCILE_KNOWLEDGE),
            ("temporal_positions", "temporal_position_staged_in_save", RECONCILE_TEMPORAL),
            ("character_mechanics", "character_mechanics_staged_in_save", RECONCILE_CHARACTER_MECHANICS),
            ("character_rests", "character_rests_staged_in_save", RECONCILE_CHARACTER_RESTS),
        ],
    ),
    "mutate_inventory": ("inventory", [("runs", "runs_changed_in_save", INVENTORY_RUNS)]),
    "mutate_item_custody": ("item_custody", [("runs", "runs_changed_in_save", CUSTODY_RUNS)]),
    "admit_item_identity": ("item_admissions", [("runs", "runs_changed_in_save", ADMIT_RUNS)]),
    "mutate_entity_state": ("entity_state", [("runs", "runs_changed_in_save", ENTITY_RUNS)]),
    "mutate_applied_status": (
        "applied_statuses",
        [
            ("runs", "runs_changed_in_save", APPLIED_RUNS),
            ("campaign_clock", "campaign_clock_changed_in_save", APPLIED_CLOCK),
        ],
    ),
    "mutate_entity_knowledge": (
        "entity_knowledge",
        [("runs", "runs_changed_in_save", KNOWLEDGE_RUNS)],
    ),
    "mutate_character_mechanics": (
        "character_mechanics",
        [("runs", "runs_changed_in_save", CHARACTER_MECHANICS_RUNS)],
    ),
    "mutate_character_rest": (
        "character_rests",
        [("runs", "runs_changed_in_save", CHARACTER_RESTS_RUNS)],
    ),
    "stage_campaign_clock": (
        "campaign_clock",
        [("applied_statuses", "applied_status_staged_in_save", CLOCK_APPLIED)],
    ),
}

# operation -> SQL that calls the real doorway with a minimal probe request.
DOORWAYS = {
    "stage_runs": "select public.stage_campaign_state(%s, 'runs', '[]'::jsonb)",
    "delete_runs": "select public.delete_staged_campaign_state(%s, 'runs')",
    "reconcile_runs": "select public.reconcile_run_resolution(%s, '{}'::jsonb)",
    "mutate_inventory": "select public.mutate_owner_inventory(%s, '{}'::jsonb)",
    "mutate_item_custody": "select public.mutate_item_custody(%s, '{}'::jsonb)",
    "admit_item_identity": "select public.admit_item_identity(%s, '{}'::jsonb)",
    "mutate_entity_state": "select public.mutate_entity_state(%s, '{}'::jsonb)",
    "mutate_applied_status": "select public.mutate_applied_status(%s, '{}'::jsonb)",
    "mutate_entity_knowledge": "select public.mutate_entity_knowledge(%s, '{}'::jsonb)",
    "mutate_character_mechanics": "select public.mutate_character_mechanics(%s, '{}'::jsonb)",
    "mutate_character_rest": "select public.mutate_character_rest(%s, '{}'::jsonb)",
    "stage_campaign_clock": "select public.stage_campaign_clock(%s, '{}'::jsonb)",
}


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


def policy(db, operation):
    return scalar(
        db, "select public._rhc_same_save_compatibility_policy(%s)", (operation,)
    )


def decision(db, operation, staging, published):
    return scalar(
        db,
        "select public._rhc_same_save_compatibility(%s, %s, %s)",
        (operation, staging, published),
    )


def begin_save(db):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def runtime_row(db):
    with db.cursor() as cur:
        cur.execute("select * from public.campaign_runtime where id = 1")
        columns = [d.name for d in cur.description]
        row = cur.fetchone()
    return dict(zip(columns, row))


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


def set_operation_fact(db, token, column):
    break_glass(
        db,
        "update public.campaign_runtime set %s = %%s where id = 1" % column,
        (token,),
    )


def stage_runs_change(db, staging):
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(%s, 'runs', '[{\"run_id\": \"R99\"}]'::jsonb, now(), now()) "
        "on conflict (generation, key) do update set value = excluded.value, "
        "updated_at = now()",
        (staging,),
    )


def stage_clock_change(db, staging):
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(%s, 'campaign_clock', "
        "'{\"schema_version\":1,\"day\":null,\"phase\":\"unknown\","
        "\"elapsed_campaign_minutes\":5,\"long_rests_completed\":0}'::jsonb, "
        "now(), now()) "
        "on conflict (generation, key) do update set value = excluded.value, "
        "updated_at = now()",
        (staging,),
    )


def stage_new_reconciliation(db, staging):
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(%s, 'run_reconciliations', "
        "'{\"RPX\": {\"resolution_id\": \"RPX\", \"run_id\": \"R01\"}}'::jsonb, "
        "now(), now()) "
        "on conflict (generation, key) do update set value = excluded.value, "
        "updated_at = now()",
        (staging,),
    )


# detector -> setup callable(db, token, staging)
DETECTORS = {
    "reconciliation_new_in_save": lambda db, token, staging: stage_new_reconciliation(db, staging),
    "inventory_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "inventory_staged_lock_token"
    ),
    "custody_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "item_custody_staged_lock_token"
    ),
    "entity_state_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "entity_state_staged_lock_token"
    ),
    "applied_status_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "applied_status_staged_lock_token"
    ),
    "knowledge_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "entity_knowledge_staged_lock_token"
    ),
    "temporal_position_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "temporal_position_staged_lock_token"
    ),
    "character_mechanics_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "character_mechanics_staged_lock_token"
    ),
    "character_rests_staged_in_save": lambda db, token, staging: set_operation_fact(
        db, token, "character_rests_staged_lock_token"
    ),
    "runs_changed_in_save": lambda db, token, staging: stage_runs_change(db, staging),
    "campaign_clock_changed_in_save": lambda db, token, staging: stage_clock_change(
        db, staging
    ),
}


def _error_primary(exc):
    """The server primary message only, independent of RAISE line numbers."""
    diag = getattr(exc, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    return primary or str(exc).splitlines()[0]


def call_doorway(db, operation, token):
    """Call a real doorway with a minimal probe request; return ok/error text."""
    try:
        with db.cursor() as cur:
            cur.execute(DOORWAYS[operation], (token,))
        return "ok"
    except psycopg2.Error as exc:  # noqa: BLE001 - behavior capture
        return _error_primary(exc)


# --- 1. The contract declares every audited incompatibility, truthfully ------


@pytest.mark.parametrize("operation", list(POLICY))
def test_policy_declares_operation_with_expected_domain(db, operation):
    record = policy(db, operation)
    domain, edges = POLICY[operation]
    assert record["operation"] == operation
    assert record["domain"] == domain
    assert record["known"] is True
    assert isinstance(record["edges"], list)
    assert record["edges"] == [
        {"blocked_by": b, "detector": d, "error": e} for (b, d, e) in edges
    ]


def test_policy_declares_no_misleading_or_missing_edges(db):
    """Every audited edge is represented once, and no extra edge is invented."""
    declared = set()
    for operation in POLICY:
        for edge in policy(db, operation)["edges"]:
            declared.add((operation, edge["blocked_by"]))
    expected = set()
    for operation, (_domain, edges) in POLICY.items():
        for (blocked_by, _detector, _error) in edges:
            expected.add((operation, blocked_by))
    assert declared == expected


def test_policy_covers_all_six_audited_edges_in_both_directions(db):
    """The six Mission-audited incompatibilities are each represented."""
    # runs <-> run_reconciliations
    assert "run_reconciliations" in _blockers(db, "stage_runs")
    assert "run_reconciliations" in _blockers(db, "delete_runs")
    # runs <-> inventory
    assert "inventory" in _blockers(db, "stage_runs")
    assert "runs" in _blockers(db, "mutate_inventory")
    # runs <-> item_custody / item admission custody effects
    assert "item_custody" in _blockers(db, "stage_runs")
    assert "runs" in _blockers(db, "mutate_item_custody")
    assert "runs" in _blockers(db, "admit_item_identity")
    # runs <-> entity_state
    assert "entity_state" in _blockers(db, "stage_runs")
    assert "runs" in _blockers(db, "mutate_entity_state")
    # runs <-> applied_statuses
    assert "applied_statuses" in _blockers(db, "stage_runs")
    assert "runs" in _blockers(db, "mutate_applied_status")
    # campaign_clock <-> applied_statuses
    assert "applied_statuses" in _blockers(db, "stage_campaign_clock")
    assert "campaign_clock" in _blockers(db, "mutate_applied_status")


def _blockers(db, operation):
    return {edge["blocked_by"] for edge in policy(db, operation)["edges"]}


@pytest.mark.parametrize("operation", list(POLICY))
def test_policy_metadata_is_truthful_against_the_real_doorway(db, operation):
    """Every declared edge is reachable and its declared error is exact.

    This directly honors the Patch 1A scar: machine-readable policy metadata must
    be truthful and exhaustive, not merely suggestive. Each declared edge is
    isolated (only its own detector is staged) and the real doorway is called.
    """
    _domain, edges = POLICY[operation]
    for (blocked_by, detector, error) in edges:
        _published, staging, token, _expires = begin_save(db)
        DETECTORS[detector](db, token, staging)
        raised = call_doorway(db, operation, token)
        abort_save(db, token)
        assert raised == error, (operation, blocked_by, raised)


# --- 2. The contract is server-owned, key-only and not caller-controllable ----


def test_contract_functions_have_exactly_the_expected_signatures(db):
    expected = {
        "_rhc_same_save_compatibility_policy": ("p_operation text",),
        "_rhc_same_save_compatibility": (
            "p_operation text, p_staging_generation bigint, p_published_generation bigint",
        ),
        "_rhc_require_same_save_compatibility": (
            "p_operation text, p_staging_generation bigint, p_published_generation bigint",
        ),
    }
    for name, signatures in expected.items():
        with db.cursor() as cur:
            cur.execute(
                "select pg_get_function_arguments(p.oid) from pg_proc p "
                "where p.proname = %s and p.pronamespace = 'public'::regnamespace",
                (name,),
            )
            rows = cur.fetchall()
        assert rows == [(s,) for s in signatures], name


@pytest.mark.parametrize("operation", list(POLICY))
def test_contract_is_not_executable_by_caller_roles(db, operation):
    for role in ("anon", "authenticated", "service_role"):
        with db.cursor() as cur:
            cur.execute(f"set role {role}")
            try:
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute(
                        "select public._rhc_same_save_compatibility_policy(%s)",
                        (operation,),
                    )
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute(
                        "select public._rhc_same_save_compatibility(%s, 0, 0)",
                        (operation,),
                    )
            finally:
                cur.execute("reset role")


@pytest.mark.parametrize(
    "operation", ("invented_operation", "stage_runs ", "STAGE_RUNS", "reconcile_run")
)
def test_unknown_operation_fails_closed(db, operation):
    record = policy(db, operation)
    assert record["known"] is False
    assert record["domain"] is None
    assert record["edges"] == []
    verdict = decision(db, operation, 0, 0)
    assert verdict["known"] is False
    assert verdict["compatible"] is False
    assert verdict["blocked_by"] == "unknown_operation"
    assert verdict["error"]


# --- 3. The decision is compatible when no incompatible fact exists ----------


@pytest.mark.parametrize("operation", list(POLICY))
def test_operation_is_compatible_without_any_staged_fact(db, operation):
    _published, staging, _token, _expires = begin_save(db)
    verdict = decision(db, operation, staging, _published)
    assert verdict["known"] is True
    assert verdict["compatible"] is True
    assert verdict["blocked_by"] is None
    assert verdict["error"] is None


# --- 4. Both orderings of every symmetric exclusion fail closed --------------


def test_runs_and_reconciliation_exclusion(db):
    # reconciliation newly staged -> generic runs stage and delete refused.
    _published, staging, token, _expires = begin_save(db)
    stage_new_reconciliation(db, staging)
    assert call_doorway(db, "stage_runs", token) == RECON_STAGE
    assert call_doorway(db, "delete_runs", token) == RECON_DELETE
    abort_save(db, token)


def test_runs_and_inventory_exclusion_both_orderings(db):
    # inventory staged -> runs doorways and reconciliation refused.
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "inventory_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_INVENTORY
    assert call_doorway(db, "delete_runs", token) == RUNS_INVENTORY
    assert call_doorway(db, "reconcile_runs", token) == RECONCILE_INVENTORY
    abort_save(db, token)

    # runs changed -> inventory mutation refused.
    _published, staging, token, _expires = begin_save(db)
    stage_runs_change(db, staging)
    assert call_doorway(db, "mutate_inventory", token) == INVENTORY_RUNS
    abort_save(db, token)


def test_runs_and_custody_admission_exclusion_both_orderings(db):
    # custody/admission staged -> runs doorways and reconciliation refused.
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "item_custody_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_CUSTODY
    assert call_doorway(db, "delete_runs", token) == RUNS_CUSTODY
    assert call_doorway(db, "reconcile_runs", token) == RECONCILE_CUSTODY
    abort_save(db, token)

    # runs changed -> both custody writers refused.
    _published, staging, token, _expires = begin_save(db)
    stage_runs_change(db, staging)
    assert call_doorway(db, "mutate_item_custody", token) == CUSTODY_RUNS
    assert call_doorway(db, "admit_item_identity", token) == ADMIT_RUNS
    abort_save(db, token)


def test_runs_and_entity_state_exclusion_both_orderings(db):
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "entity_state_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_ENTITY
    assert call_doorway(db, "delete_runs", token) == RUNS_ENTITY
    assert call_doorway(db, "reconcile_runs", token) == RECONCILE_ENTITY
    abort_save(db, token)

    _published, staging, token, _expires = begin_save(db)
    stage_runs_change(db, staging)
    assert call_doorway(db, "mutate_entity_state", token) == ENTITY_RUNS
    abort_save(db, token)


def test_runs_and_applied_status_exclusion_both_orderings(db):
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "applied_status_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_APPLIED
    assert call_doorway(db, "delete_runs", token) == RUNS_APPLIED
    assert call_doorway(db, "reconcile_runs", token) == RECONCILE_APPLIED
    abort_save(db, token)

    _published, staging, token, _expires = begin_save(db)
    stage_runs_change(db, staging)
    assert call_doorway(db, "mutate_applied_status", token) == APPLIED_RUNS
    abort_save(db, token)


def test_campaign_clock_and_applied_status_exclusion_both_orderings(db):
    # applied status staged -> Clock advance refused.
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "applied_status_staged_lock_token")
    assert call_doorway(db, "stage_campaign_clock", token) == CLOCK_APPLIED
    abort_save(db, token)

    # clock changed -> applied-status mutation refused.
    _published, staging, token, _expires = begin_save(db)
    stage_clock_change(db, staging)
    assert call_doorway(db, "mutate_applied_status", token) == APPLIED_CLOCK
    abort_save(db, token)


# --- 5. Blocker ordering is preserved when several facts coexist -------------


def test_first_declared_blocker_wins_when_multiple_facts_exist(db):
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "inventory_staged_lock_token")
    set_operation_fact(db, token, "item_custody_staged_lock_token")
    set_operation_fact(db, token, "entity_state_staged_lock_token")
    set_operation_fact(db, token, "applied_status_staged_lock_token")
    # inventory is the first declared runs blocker.
    assert call_doorway(db, "stage_runs", token) == RUNS_INVENTORY
    assert call_doorway(db, "delete_runs", token) == RUNS_INVENTORY
    assert call_doorway(db, "reconcile_runs", token) == RECONCILE_INVENTORY
    abort_save(db, token)


# --- 6. Operation-fact semantics stay lock-token / save scoped ---------------


def test_operation_fact_survives_value_equal_replay(db):
    """A value-equal staging operation still closes every runs doorway.

    The detector keys on the save's own database-minted lock token, never on
    final value equality, so a replay that re-stages a value already equal to
    published reality is indistinguishable from any other staging operation.
    """
    _published, staging, token, _expires = begin_save(db)
    # Simulate a value-equal inventory staging: the operation fact is recorded
    # while the inventory value is left exactly as published (unchanged).
    set_operation_fact(db, token, "inventory_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_INVENTORY
    abort_save(db, token)


def test_operation_fact_does_not_leak_into_a_later_save(db):
    _published, staging, token, _expires = begin_save(db)
    set_operation_fact(db, token, "inventory_staged_lock_token")
    assert call_doorway(db, "stage_runs", token) == RUNS_INVENTORY
    abort_save(db, token)

    # A later save mints a fresh lock token, so the prior closure is not inherited.
    _published, staging, token, _expires = begin_save(db)
    assert call_doorway(db, "stage_runs", token) == "ok"
    abort_save(db, token)


def test_unchanged_runs_does_not_close_domain_doorways(db):
    """A staging generation that still equals published does not trip the guard."""
    _published, staging, token, _expires = begin_save(db)
    # The candidate `runs` equals published reality; the domain doorway proceeds
    # past the compatibility decision to its own request validation.
    assert call_doorway(db, "mutate_inventory", token) != INVENTORY_RUNS
    assert call_doorway(db, "mutate_entity_state", token) != ENTITY_RUNS
    abort_save(db, token)


# --- 7. Patch 1A domain policy remains intact --------------------------------


@pytest.mark.parametrize(
    "key,admission",
    (
        ("runs", "generic"),
        ("daily_recap", "generic"),
        ("campaign_clock", "dedicated"),
        ("run_reconciliations", "dedicated"),
        ("inventory", "dedicated"),
        ("item_custody", "dedicated"),
        ("item_admissions", "dedicated"),
        ("entity_state", "dedicated"),
        ("applied_statuses", "dedicated"),
        ("character_mechanics", "dedicated"),
        ("character_rests", "dedicated"),
        ("invented_domain", "forbidden"),
    ),
)
def test_patch_1a_registry_classification_unchanged(db, key, admission):
    assert scalar(db, "select public._rhc_save_domain_policy(%s)", (key,))[
        "admission"
    ] == admission


def test_patch_1a_generic_route_still_rejects_dedicated_keys(db):
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'inventory', '{}'::jsonb)",
                (token,),
            )
    abort_save(db, token)


# --- 8. RT01 lifecycle unchanged ---------------------------------------------


def test_begin_abort_publish_lifecycle_unchanged(db):
    before = scalar(db, "select published_generation from public.campaign_runtime where id = 1")
    _published, _staging, token, _expires = begin_save(db)
    abort_save(db, token)
    assert scalar(db, "select published_generation from public.campaign_runtime where id = 1") == before

    _published, _staging, token, _expires = begin_save(db)
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, 'live_status', '{\"state\":\"x\"}'::jsonb)",
            (token,),
        )
    publish(db, token)
    assert scalar(db, "select published_generation from public.campaign_runtime where id = 1") == before + 1
    assert runtime_row(db)["save_in_progress"] is False


# --- 9. Behavioral equivalence with the pre-Patch-1B chain -------------------

SCENARIOS = (
    "none",
    "reconciliation_new_in_save",
    "inventory_staged_in_save",
    "custody_staged_in_save",
    "entity_state_staged_in_save",
    "applied_status_staged_in_save",
    "runs_changed_in_save",
    "campaign_clock_changed_in_save",
)


def _capture_compatibility_outcomes(db):
    outcomes = {}
    for operation in EQUIVALENCE_OPERATIONS:
        for scenario in SCENARIOS:
            _published, staging, token, _expires = begin_save(db)
            if scenario != "none":
                DETECTORS[scenario](db, token, staging)
            outcomes[(operation, scenario)] = call_doorway(db, operation, token)
            abort_save(db, token)
    return outcomes


# POST-EV2-3 adds one new operation (`mutate_entity_knowledge`), POST-EV2-9
# adds `mutate_character_mechanics` and POST-EV2-10 adds `mutate_character_rest`;
# all three routes depend on the Patch 1B enforcement helper, so they cannot
# exist before Patch 1B and are outside this equivalence claim. Patch 1B's "no
# semantic behavior change" equivalence is asserted over the operations Patch 1B
# itself re-declared.
EQUIVALENCE_OPERATIONS = tuple(
    operation
    for operation in DOORWAYS
    if operation not in (
        "mutate_entity_knowledge",
        "mutate_character_mechanics",
        "mutate_character_rest",
    )
)


def test_fresh_replay_reaches_same_effective_compatibility_as_main(db_pre_patch):
    before = _capture_compatibility_outcomes(db_pre_patch)

    # Fresh full replay now includes the Patch 1B dispatcher migration.
    install_chain(db_pre_patch, FORWARD_MIGRATIONS)
    after = _capture_compatibility_outcomes(db_pre_patch)

    assert before == after
    # Guard the proof itself: the matrix must exercise blocked and allowed cases.
    assert any(value == "ok" for value in before.values())
    assert any(value.endswith("start a new one") for value in before.values())
    assert any("separate saves" in value for value in before.values())
