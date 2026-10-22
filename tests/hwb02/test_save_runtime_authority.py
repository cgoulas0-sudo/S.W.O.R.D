"""HWB-02 proof suite — ordinary SAVE runtime key authority (real PostgreSQL).

Behavior proofs around the real failure class (JOHNNY #69 Threat Model): an
ordinary `campaign_save` could name a new/undeclared runtime key through the
generic RT01-B staging routes, letting caller/model prose — not the database —
decide which runtime keys exist. The forward-only migration
`20260914000001_hwb02_save_runtime_authority.sql` adds the server-owned
ordinary-save allowlist (`daily_recap`, `day_resolution`, `live_status`,
`dm_meta`, `narrative_hooks`, `runs`); unknown keys fail closed; stage and delete
are symmetric; RT02/RT04 dedicated closures and the RT04 same-save `runs`
closure compose instead of being bypassed.

Proved against real PostgreSQL 15 and 17 with disposable schemas and synthetic
policy data only. No live Supabase is touched.
"""

import json

import psycopg2
import pytest

from conftest import CAMPAIGN_SAVE_ALLOWED_KEYS

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
    with pytest.raises(psycopg2.errors.RaiseException, match=match):
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
    """Stage + publish + mirror-confirm one generation carrying `key`."""
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, value)
    publish(db, token)
    return confirm_mirror(db)


def run_record(run_id="R01", control_state="active", owners=None):
    return {
        "run_id": run_id,
        "execution_mode": "played",
        "control_state": control_state,
        "scenario_id": "S01",
        "occurred_encounter_ids": ["E01"],
        "participant_entity_ids": ["character:test-hero"],
        "mutable_owner_entity_ids": (
            ["character:test-hero"] if owners is None else owners
        ),
        "location_ids": ["location:tavern"],
        "campaign_anchor": {"base_commit": RUN_ANCHOR, "campaign_time": "Day 1, evening"},
    }


def resolution_record():
    return {
        "resolution_id": "RP01",
        "run_id": "R01",
        "scenario_id": "S01",
        "primary_hook_id": "H01",
        "campaign_anchor": {"base_commit": RUN_ANCHOR, "campaign_time": "Day 1, evening"},
        "objective_context": {
            "scenario_objective": "Rescue the missing courier.",
            "hook_objective": "Locate the courier before nightfall.",
        },
        "primary_roll": 18,
        "outcome_band": "above_average",
        "proposed_consequences": [
            {
                "consequence_id": "PC01",
                "scope": "run_objective",
                "kind": "objective_result",
                "summary": "Apply the above average result to the Run objective.",
                "related_entity_ids": [],
                "location_ids": [],
            }
        ],
    }


def reconcile(db, token, request):
    with db.cursor() as cur:
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        value = cur.fetchone()[0]
    return json.loads(value) if isinstance(value, str) else value


def break_glass(db, sql, params=None):
    """Administrative direct row write (gated, one transaction).

    Mirrors the RT04 break-glass pattern: assert the documented
    transaction-local guard in ONE transaction so the mutation-boundary trigger
    is satisfied. This is break-glass administration, not normal save authority.
    """
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


# --- 1/2. Six allowed keys stage and delete symmetrically --------------------


@pytest.mark.parametrize("key", CAMPAIGN_SAVE_ALLOWED_KEYS)
def test_allowed_key_stages(db, key):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, {"policy": key})
    assert staged_candidate(db, key) == {"policy": key}


@pytest.mark.parametrize("key", CAMPAIGN_SAVE_ALLOWED_KEYS)
def test_allowed_key_deletes_symmetrically(db, key):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, key, {"policy": key})
    assert delete_staged(db, token, key) is True
    assert staged_candidate(db, key) is None
    # Deleting an absent (but declared) key is a clean no-op, not a policy error.
    assert delete_staged(db, token, key) is False


# --- 3/4. Unknown keys fail closed, stage and delete -------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_unknown_key_stage_fails_closed_without_mutation(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
        (token,),
        "not allowed for campaign_save; the server-owned allowlist",
    )
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'campaign_epoch', '1'::jsonb)",
        (token,),
        "not allowed for campaign_save",
    )
    assert staged_candidate(db, "invented_domain") is None
    assert staged_candidate(db, "campaign_epoch") is None


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_unknown_key_delete_fails_closed(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'invented_domain')",
        (token,),
        "not allowed for campaign_save",
    )


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_unknown_key_is_symmetric_with_other_adjacent_spelling(request, db_fixture):
    """Near-miss/adjacent keys are undeclared too; the allowlist is exact."""
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


# --- 5. RT02 dedicated Clock closure composes without being bypassed ---------


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_campaign_clock_stays_dedicated_and_route_still_works(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    clock = {
        "schema_version": 1,
        "day": None,
        "phase": "unknown",
        "elapsed_campaign_minutes": 0,
        "long_rests_completed": 0,
    }
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'campaign_clock', %s::jsonb)",
        (token, json.dumps(clock)),
        "campaign_clock must be staged through stage_campaign_clock",
    )
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'campaign_clock')",
        (token,),
        "campaign_clock is engine-owned and cannot be deleted",
    )

    # The RT02 dedicated route is undiminished by HWB-02: a valid absolute
    # target Clock still stages through its own validated function.
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


# --- 6/7. RT04 dedicated reconciliation composes; runs closure still fires ----


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_run_reconciliations_stays_engine_owned_generically(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'run_reconciliations', '{}'::jsonb)",
        (token,),
        "run_reconciliations is engine-owned",
    )
    expect_policy_error(
        db,
        "select public.delete_staged_campaign_state(%s, 'run_reconciliations')",
        (token,),
        "run_reconciliations is engine-owned",
    )


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_runs_generic_stage_allowed_before_reconciliation(request, db_fixture):
    """`runs` remains allowed where RT04 currently allows it (no reconciliation yet)."""
    db = request.getfixturevalue(db_fixture)
    _published, _staging, token, _expires = begin_save(db)
    runs = [run_record()]
    stage(db, token, "runs", runs)
    assert staged_candidate(db, "runs") == runs
    assert delete_staged(db, token, "runs") is True


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_rt04_dedicated_route_authoritative_and_runs_closure_composes(request, db_fixture):
    """RT04's real reconciliation still works, and afterwards the generic routes
    refuse same-save `runs` staging/deletion (JOHNNY #69 proof 6/7)."""
    db = request.getfixturevalue(db_fixture)
    publish_confirmed_state(db, "runs", [run_record()])

    _published, staging, token, _expires = begin_save(db)
    result = reconcile(
        db,
        token,
        {"resolution": resolution_record()},
    )
    assert result["resolution_id"] == "RP01"
    assert result["applied"]["run_state_after"]["control_state"] == "active"

    # The engine-owned ledger was staged by the dedicated route only.
    ledger = staged_candidate(db, "run_reconciliations")
    assert ledger is not None and "RP01" in ledger
    # The generic route still cannot touch the engine-owned ledger.
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'run_reconciliations', '{}'::jsonb)",
        (token,),
        "run_reconciliations is engine-owned",
    )

    # RT04 same-save closure fires after a NEW reconciliation marker exists.
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


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_runs_closure_composes_with_policy_via_break_glass_marker(request, db_fixture):
    """ISO proof of the closure independent of reconciliation data validation.

    A reconciliation marker NEWLY staged in this save makes the generic `runs`
    routes refuse for the rest of the save, exactly as RT04 proved on its own
    chain. Historical markers copied forward from published reality must not
    trigger the closure.
    """
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


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_historical_reconciliation_receipt_does_not_close_runs(request, db_fixture):
    """A receipt copied forward from published reality is not a same-save marker."""
    db = request.getfixturevalue(db_fixture)
    # Seed the published-generation reconciliation ledger with a prior-save
    # receipt through break-glass (the dedicated route is the only normal writer,
    # and HWB-02 does not change that). The next save copy-forwards it.
    break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) values "
        "(0, 'run_reconciliations', '{\"RP_OLD\": {\"resolution_id\": \"RP_OLD\"}}'::jsonb, now(), now())",
    )
    _published, _staging, token, _expires = begin_save(db)
    runs = [run_record()]
    stage(db, token, "runs", runs)
    assert staged_candidate(db, "runs") == runs


# --- 8. engineering_release still forbids campaign-state mutation -------------


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_engineering_release_cannot_stage_or_delete_campaign_state(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
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


# --- 9. Lifecycle + raw-DML guards/privileges are not weakened ---------------


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


def test_allowed_save_publishes_and_confirms_like_rt01(db):
    publish_confirmed_state(db, "daily_recap", {"handoff": "verified"})
    row = runtime_row(db)
    assert row["runtime_published_confirmed"] is True
    assert row["last_confirmed_generation"] == row["published_generation"]


def test_ungated_raw_dml_still_blocked(db):
    """Layer-2 mutation guard is untouched: ungated owner/superuser DML fails."""
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with db.cursor() as cur:
            cur.execute(
                "insert into public.campaign_state_generations "
                "(generation, key, value) values (999, 'daily_recap', '\"x\"'::jsonb)"
            )


def test_service_role_still_routed_through_gateway(db):
    """Layer-1 privilege layer is untouched: service_role keeps no direct DML."""
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
    # The supported path still works end-to-end for an allowed key.
    stage(db, token, "daily_recap", {"via": "gateway"})


# --- Atomicity ---------------------------------------------------------------


@pytest.mark.parametrize("db_fixture", ("db", "db17"))
def test_policy_failure_is_all_or_nothing_and_abort_is_clean(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    before = published_generation(db)
    _published, _staging, token, _expires = begin_save(db)
    expect_policy_error(
        db,
        "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
        (token,),
        "not allowed for campaign_save",
    )
    assert staged_candidate(db, "invented_domain") is None
    abort_save(db, token)
    assert published_generation(db) == before
