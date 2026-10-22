import psycopg2
import pytest

BASE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONFIRM_SHA = "0123456789abcdef0123456789abcdef01234567"


def _pending(db):
    import json

    with db.cursor() as cur:
        cur.execute("select public.get_pending_runtime_mirror()")
        value = cur.fetchone()[0]
    if isinstance(value, str):
        value = json.loads(value)
    return value


def _publish_first(db):
    with db.cursor() as cur:
        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
        cur.execute("select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (token,))
        cur.execute("select public.publish_campaign_save(%s)", (token,))
    return _pending(db)


def _as_verifier(db, sql, params):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(sql, params)
            return cur.fetchone()[0]
        finally:
            cur.execute("reset role")


def test_bootstrap_confirmation_requires_durable_base_binding(db):
    candidate = _publish_first(db)
    assert candidate["last_confirmed_git_ref"] is None
    assert candidate["mirror_base_git_ref"] is None

    with pytest.raises(psycopg2.errors.RaiseException, match="requires a bound base Git ref"):
        _as_verifier(
            db,
            "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
            (candidate["generation"], candidate["mirror_token"], CONFIRM_SHA),
        )

    _as_verifier(
        db,
        "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
        (candidate["generation"], candidate["mirror_token"], BASE_SHA),
    )
    _as_verifier(
        db,
        "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
        (candidate["generation"], candidate["mirror_token"], CONFIRM_SHA),
    )

    with db.cursor() as cur:
        cur.execute("select runtime_published_confirmed from public.campaign_runtime")
        assert cur.fetchone()[0] is True
