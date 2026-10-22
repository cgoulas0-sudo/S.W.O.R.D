"""Shared helpers for the EV2-13.1 timed applied-status proof modules.

The runtime proof drives the real RT01 save/publication/mirror-confirmation
spine; nothing is mocked. Controller authority is resolved from published Run
truth and timing from published Campaign Clock truth, exactly as production
does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="EV2-13.1 timed applied status needs a real PostgreSQL server"
)

ROOT = Path(__file__).resolve().parents[2]
FORWARD_MIGRATIONS = tuple(sorted((ROOT / "supabase" / "migrations").glob("*.sql")))
EV2131_MIGRATION = ROOT / "supabase" / "migrations" / (
    "20260920000002_ev2131_timed_status_continuity.sql"
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
    "RHC_EV2131_PG_DSN",
    "RHC_EV213420_PG_DSN",
    "RHC_EV213_PG_DSN",
    "RHC_EV2121_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG17_DSN_PRECEDENCE = (
    "RHC_EV2131_PG17_DSN",
    "RHC_EV213420_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_FALLBACK_DSN = "postgresql://postgres:rhc@localhost:55433/rhc"


def _first_dsn(variables, fallback):
    for variable in variables:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return fallback


def install_chain(connection, migrations=FORWARD_MIGRATIONS) -> None:
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
        pytest.skip(f"EV2-13.1 timed applied status proof skipped (no server): {exc}")
    connection.autocommit = True
    return connection


@pytest.fixture(scope="session")
def database_server():
    connection = _connect(
        psycopg2.connect, _first_dsn(_DSN_PRECEDENCE, _FALLBACK_DSN)
    )
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


BOOTSTRAP_BASE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONFIRMED_RUNTIME = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
RUN_ANCHOR = "cccccccccccccccccccccccccccccccccccccccc"

HERO = "character:test-hero"
BEAST = "creature:test-wolf"
OTHER = "character:test-fanis"
DEFINITION = "status_effect:test-chill"
APPLICATION = "AS01"


def clock(day=None, phase="unknown", elapsed_campaign_minutes=0,
          long_rests_completed=0, schema_version=1):
    return {
        "schema_version": schema_version,
        "day": day,
        "phase": phase,
        "elapsed_campaign_minutes": elapsed_campaign_minutes,
        "long_rests_completed": long_rests_completed,
    }


def threshold(threshold_id="T1", amount=10, unit="minute"):
    return {"threshold_id": threshold_id, "amount": amount, "unit": unit}


def definition(thresholds=None, target=HERO, definition_id=DEFINITION, source=None):
    value = {
        "definition_id": definition_id,
        "target_entity_id": target,
        "thresholds": (
            [threshold()] if thresholds is None else thresholds
        ),
    }
    if source is not None:
        value["source_entity_id"] = source
    return value


def request(application_id=APPLICATION, controller=None, definition_obj=None,
            acknowledge=None, end=None):
    value = {
        "application_id": application_id,
        "controller": {"kind": "mainrun"} if controller is None else controller,
    }
    if definition_obj is not None:
        value["definition"] = definition_obj
    if acknowledge is not None:
        value["acknowledge"] = acknowledge
    if end is not None:
        value["end"] = end
    return value


def run(run_id="R01", execution_mode="played", control_state="active",
        scenario_id="S01", occurred_encounter_ids=None, party_id=None,
        participant_entity_ids=None, mutable_owner_entity_ids=None,
        location_ids=None, base_commit=RUN_ANCHOR, campaign_time="Day 1, evening",
        outcome_summary=None):
    value = {
        "run_id": run_id,
        "execution_mode": execution_mode,
        "control_state": control_state,
        "scenario_id": scenario_id,
        "occurred_encounter_ids": (
            ["E01"] if occurred_encounter_ids is None else occurred_encounter_ids
        ),
        "participant_entity_ids": (
            [HERO] if participant_entity_ids is None else participant_entity_ids
        ),
        "mutable_owner_entity_ids": (
            [HERO] if mutable_owner_entity_ids is None else mutable_owner_entity_ids
        ),
        "location_ids": ["location:tavern"] if location_ids is None else location_ids,
        "campaign_anchor": {
            "base_commit": base_commit,
            "campaign_time": campaign_time,
        },
    }
    if party_id is not None:
        value["party_id"] = party_id
    if outcome_summary is not None:
        value["outcome_summary"] = outcome_summary
    return value


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


def begin_save(db):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()


def stage_clock(db, token, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(value)),
        )


def stage(db, token, key, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        )


def delete_staged(db, token, key):
    return scalar(
        db, "select public.delete_staged_campaign_state(%s, %s)", (token, key)
    )


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def pending(db):
    return scalar(db, "select public.get_pending_runtime_mirror()")


def confirm_mirror(db):
    """Confirm the current pending mirror so the next save may begin."""
    bootstrap = (
        scalar(
            db,
            "select last_confirmed_generation from public.campaign_runtime where id = 1",
        )
        is None
    )
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


def publish_confirmed_state(db, state):
    """Stage + publish + mirror-confirm one ordinary-state generation."""
    _published, _staging, token, _expires = begin_save(db)
    for key, value in state.items():
        stage(db, token, key, value)
    publish(db, token)
    return confirm_mirror(db)


def publish_confirmed_runs(db, runs):
    return publish_confirmed_state(db, {"runs": runs})


def publish_confirmed_clock(db, value):
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, value)
    publish(db, token)
    return confirm_mirror(db)


def publish_clock(db, token, value):
    stage_clock(db, token, value)
    return publish(db, token)


def published_state(db):
    return scalar(
        db,
        "select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb) "
        "from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation",
    )


def published_clock(db):
    return published_state(db).get("campaign_clock")


def staged_state_key(db, key):
    return scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = %s",
        (key,),
    )


def published_applied_statuses(db):
    return published_state(db).get("applied_statuses") or []


def runtime_row(db):
    with db.cursor() as cur:
        cur.execute("select * from public.campaign_runtime where id = 1")
        columns = [description.name for description in cur.description]
        row = cur.fetchone()
    return dict(zip(columns, row))


def mutate(db, token, req):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.mutate_applied_status(%s, %s::jsonb)",
                (token, json.dumps(req)),
            )
            value = cur.fetchone()[0]
        finally:
            cur.execute("reset role")
    return json.loads(value) if isinstance(value, str) else value


def mutate_error(db, token, req):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.mutate_applied_status(%s, %s::jsonb)",
                (token, json.dumps(req)),
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the applied-status mutation to fail closed")


def read_status(db, application_id=APPLICATION):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.read_timed_applied_status(%s)", (application_id,)
            )
            value = cur.fetchone()[0]
        finally:
            cur.execute("reset role")
    return json.loads(value) if isinstance(value, str) else value


def read_status_error(db, application_id=APPLICATION):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.read_timed_applied_status(%s)", (application_id,)
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the applied-status read to fail closed")


def error_as_role(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def resolution(resolution_id="RP01", run_id="R01", scenario_id="S01",
               primary_hook_id="H01", base_commit=RUN_ANCHOR,
               campaign_time="Day 1, evening",
               scenario_objective="Rescue the missing courier.",
               hook_objective="Locate the courier before nightfall.",
               primary_roll=18, outcome_band="above_average",
               severity_roll=None, severity_band=None, consequences=None):
    value = {
        "resolution_id": resolution_id,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "primary_hook_id": primary_hook_id,
        "campaign_anchor": {
            "base_commit": base_commit,
            "campaign_time": campaign_time,
        },
        "objective_context": {
            "scenario_objective": scenario_objective,
            "hook_objective": hook_objective,
        },
        "primary_roll": primary_roll,
        "outcome_band": outcome_band,
        "proposed_consequences": (
            consequences if consequences is not None
            else [{
                "consequence_id": "PC01",
                "scope": "run_objective",
                "kind": "objective_result",
                "summary": "Apply the above average result to the Run objective.",
                "related_entity_ids": [],
                "location_ids": [],
            }]
        ),
    }
    if severity_roll is not None:
        value["severity_roll"] = severity_roll
        value["severity_band"] = severity_band
    return value


def reconcile_request(resolution_record, released=None):
    value = {"resolution": resolution_record}
    if released is not None:
        value["released_mutable_owners"] = released
    return value


def reconcile(db, token, req):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.reconcile_run_resolution(%s, %s::jsonb)",
                (token, json.dumps(req)),
            )
            value = cur.fetchone()[0]
        finally:
            cur.execute("reset role")
    return json.loads(value) if isinstance(value, str) else value


def reconcile_error(db, token, req):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.reconcile_run_resolution(%s, %s::jsonb)",
                (token, json.dumps(req)),
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected reconciliation to fail closed")


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
