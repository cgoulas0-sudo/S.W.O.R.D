"""Small SQL helpers shared by the RT04 Safe Run Reconciliation proof modules."""

import json


BOOTSTRAP_BASE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONFIRMED_RUNTIME = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
RUN_ANCHOR = "cccccccccccccccccccccccccccccccccccccccc"


def run(
    run_id="R01",
    execution_mode="played",
    control_state="active",
    scenario_id="S01",
    occurred_encounter_ids=None,
    party_id=None,
    participant_entity_ids=None,
    mutable_owner_entity_ids=None,
    location_ids=None,
    base_commit=RUN_ANCHOR,
    campaign_time="Day 1, evening",
    outcome_summary=None,
):
    value = {
        "run_id": run_id,
        "execution_mode": execution_mode,
        "control_state": control_state,
        "scenario_id": scenario_id,
        "occurred_encounter_ids": (
            ["E01"] if occurred_encounter_ids is None else occurred_encounter_ids
        ),
        "participant_entity_ids": (
            ["character:test-hero"] if participant_entity_ids is None else participant_entity_ids
        ),
        "mutable_owner_entity_ids": (
            ["character:test-hero"] if mutable_owner_entity_ids is None else mutable_owner_entity_ids
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


def resolution(
    resolution_id="RP01",
    run_id="R01",
    scenario_id="S01",
    primary_hook_id="H01",
    base_commit=RUN_ANCHOR,
    campaign_time="Day 1, evening",
    scenario_objective="Rescue the missing courier.",
    hook_objective="Locate the courier before nightfall.",
    primary_roll=18,
    outcome_band="above_average",
    severity_roll=None,
    severity_band=None,
    consequences=None,
):
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
            consequences
            if consequences is not None
            else [
                {
                    "consequence_id": "PC01",
                    "scope": "run_objective",
                    "kind": "objective_result",
                    "summary": "Apply the above average result to the Run objective.",
                    "related_entity_ids": [],
                    "location_ids": [],
                }
            ]
        ),
    }
    if severity_roll is not None:
        value["severity_roll"] = severity_roll
        value["severity_band"] = severity_band
    return value


def request(resolution_record, released=None):
    value = {"resolution": resolution_record}
    if released is not None:
        value["released_mutable_owners"] = released
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


def reconcile(db, token, req, as_service_role=False):
    sql = "select public.reconcile_run_resolution(%s, %s::jsonb)"
    with db.cursor() as cur:
        if as_service_role:
            cur.execute("set role service_role")
        try:
            cur.execute(sql, (token, json.dumps(req)))
            value = cur.fetchone()[0]
        finally:
            if as_service_role:
                cur.execute("reset role")
    if isinstance(value, str):
        return json.loads(value)
    return value


def read_run(db, run_id):
    with db.cursor() as cur:
        cur.execute("select public.dm_runtime_read_run(%s)", (run_id,))
        value = cur.fetchone()[0]
    if isinstance(value, str):
        return json.loads(value)
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


def stage_runs(db, token, runs):
    return stage(db, token, "runs", runs)


def delete_staged(db, token, key):
    with db.cursor() as cur:
        cur.execute("select public.delete_staged_campaign_state(%s, %s)", (token, key))
        return cur.fetchone()[0]


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def pending(db):
    return scalar(db, "select public.get_pending_runtime_mirror()")


def confirm_mirror(db):
    """Confirm the current pending mirror so the next save may begin.

    The bootstrap-base binding is only legal/required for the first ever
    confirmation; later generations confirm against the previous ref directly.
    """
    bootstrap = (
        scalar(db, "select last_confirmed_generation from public.campaign_runtime where id = 1")
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


def publish_confirmed_runs(db, runs):
    """Stage + publish + mirror-confirm one generation carrying `runs`."""
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, runs)
    publish(db, token)
    return confirm_mirror(db)


def published_state(db):
    return scalar(
        db,
        "select coalesce(jsonb_object_agg(csg.key, csg.value order by csg.key), '{}'::jsonb) "
        "from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation",
    )


def runtime_row(db):
    with db.cursor() as cur:
        cur.execute("select * from public.campaign_runtime where id = 1")
        columns = [description.name for description in cur.description]
        row = cur.fetchone()
    return dict(zip(columns, row))


def dm_read(db, query=None, limit=20):
    with db.cursor() as cur:
        if query is None:
            cur.execute("select public.dm_runtime_read()")
        else:
            cur.execute("select public.dm_runtime_read(%s, %s)", (query, limit))
        value = cur.fetchone()[0]
    if isinstance(value, str):
        return json.loads(value)
    return value


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