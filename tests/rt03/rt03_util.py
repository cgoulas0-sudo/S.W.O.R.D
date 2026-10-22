"""Small SQL helpers shared by the RT03 canonical Run read proof modules."""

import json


BOOTSTRAP_BASE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONFIRMED_RUNTIME = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def clock_value(
    day=None,
    phase="unknown",
    elapsed_campaign_minutes=0,
    long_rests_completed=0,
):
    return {
        "schema_version": 1,
        "day": day,
        "phase": phase,
        "elapsed_campaign_minutes": elapsed_campaign_minutes,
        "long_rests_completed": long_rests_completed,
    }


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
    base_commit="cccccccccccccccccccccccccccccccccccccccc",
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


def read_run(db, run_id, as_service_role=False):
    """Supported RT03 read; optionally executed as service_role."""
    sql = "select public.dm_runtime_read_run(%s)"
    with db.cursor() as cur:
        if as_service_role:
            cur.execute("set role service_role")
        try:
            cur.execute(sql, (run_id,))
            value = cur.fetchone()[0]
        finally:
            if as_service_role:
                cur.execute("reset role")
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


def stage_clock(db, token, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(value)),
        )


def stage_runs(db, token, runs):
    return stage(db, token, "runs", runs)


def abort_save(db, token):
    return scalar(db, "select public.abort_campaign_save(%s)", (token,))


def publish(db, token):
    return scalar(db, "select public.publish_campaign_save(%s)", (token,))


def pending(db):
    return scalar(db, "select public.get_pending_runtime_mirror()")


def bind_base(db, candidate, sha=BOOTSTRAP_BASE):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(
                "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                (candidate["generation"], candidate["mirror_token"], sha),
            )
        finally:
            cur.execute("reset role")


def confirm(db, candidate, sha=CONFIRMED_RUNTIME):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(
                "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
                (candidate["generation"], candidate["mirror_token"], sha),
            )
        finally:
            cur.execute("reset role")


def establish_confirmed_runtime(db, state=None):
    _published, _staging, token, _expires = begin_save(db)
    for key, value in (state or {"baseline": {"status": "ready"}}).items():
        stage(db, token, key, value)
    publish(db, token)
    candidate = pending(db)
    bind_base(db, candidate)
    candidate = pending(db)
    confirm(db, candidate)
    return candidate


def establish_runs(db, runs, extra_state=None):
    """Publish + mirror-confirm one published generation carrying `runs`."""
    state = {"runs": runs}
    if extra_state:
        state.update(extra_state)
    return establish_confirmed_runtime(db, state)


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
    if bootstrap:
        bind_base(db, candidate)
        candidate = pending(db)
    confirm(db, candidate)
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


def break_glass(db, sql, params=None):
    previous = db.autocommit
    db.autocommit = False
    try:
        with db.cursor() as cur:
            cur.execute("select set_config('rhc.gated_write', 'active', true)")
            cur.execute(sql, params or ())
        db.commit()
    finally:
        db.autocommit = previous
