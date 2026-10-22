"""Small SQL helpers shared by the RT02 Campaign Clock proof modules."""

import json


BOOTSTRAP_BASE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONFIRMED_RUNTIME = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
ENGINEERING_TARGET = "cccccccccccccccccccccccccccccccccccccccc"


def clock(
    day=None,
    phase="unknown",
    elapsed_campaign_minutes=0,
    long_rests_completed=0,
    schema_version=1,
):
    return {
        "schema_version": schema_version,
        "day": day,
        "phase": phase,
        "elapsed_campaign_minutes": elapsed_campaign_minutes,
        "long_rests_completed": long_rests_completed,
    }


UNKNOWN_CLOCK = clock()


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


def published_clock(db):
    return scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.published_generation "
        "where csg.key = 'campaign_clock'",
    )


def published_day(db):
    return scalar(db, "select published_day from public.campaign_runtime where id = 1")


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


def establish_clock(db, value):
    """Publish + mirror-confirm one Clock value, returning the pending candidate."""
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, value)
    publish(db, token)
    candidate = pending(db)
    bind_base(db, candidate)
    candidate = pending(db)
    confirm(db, candidate)
    return candidate


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


def publish_clock(db, token, value):
    """Stage a Clock and publish it, returning the published campaign_runtime row."""
    stage_clock(db, token, value)
    return publish(db, token)
