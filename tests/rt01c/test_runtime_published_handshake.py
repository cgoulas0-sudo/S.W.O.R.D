import json
import uuid

import psycopg2
import pytest

FULL_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "89abcdef0123456789abcdef0123456789abcdef"
BOOTSTRAP_BASE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def scalar(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def begin(db):
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()


def stage(db, token, key="k", value="1"):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, value),
        )


def publish(db, token):
    with db.cursor() as cur:
        cur.execute("select public.publish_campaign_save(%s)", (token,))
        return cur.fetchone()[0]


def pending(db):
    value = scalar(db, "select public.get_pending_runtime_mirror()")
    if isinstance(value, str):
        value = json.loads(value)
    return value


def bind_base(db, generation, token, sha=BOOTSTRAP_BASE_SHA):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(
                "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                (generation, token, sha),
            )
            return cur.fetchone()[0]
        finally:
            cur.execute("reset role")


def confirm(db, generation, token, sha=FULL_SHA):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(
                "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
                (generation, token, sha),
            )
            return cur.fetchone()[0]
        finally:
            cur.execute("reset role")


def publish_one(db, value="1"):
    _published, staging, token, _expires = begin(db)
    stage(db, token, value=value)
    publish(db, token)
    candidate = pending(db)
    if candidate["last_confirmed_git_ref"] is None:
        bind_base(db, candidate["generation"], candidate["mirror_token"])
        candidate = pending(db)
    return staging, candidate


def test_sql_publish_enters_durable_pending_state_and_blocks_next_generation(db):
    generation, candidate = publish_one(db)
    assert generation == 1
    assert candidate["generation"] == 1
    assert candidate["mirror_token"]
    assert candidate["mirror_base_git_ref"] == BOOTSTRAP_BASE_SHA
    assert scalar(db, "select published_git_ref from public.campaign_runtime") is None
    assert scalar(db, "select runtime_published_confirmed from public.campaign_runtime") is False
    with pytest.raises(psycopg2.errors.RaiseException, match="pending runtime-published mirror"):
        begin(db)
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1
    assert scalar(db, "select count(*) from public.campaign_state_generations where generation = 2") == 0


def test_pending_candidate_is_exact_current_published_state(db):
    _pub, _staging, token, _expires = begin(db)
    stage(db, token, "weather", '"storm"')
    stage(db, token, "npc", '{"status":"awake"}')
    publish(db, token)
    candidate = pending(db)
    assert candidate["schema_version"] == 1
    assert candidate["generation"] == 1
    assert candidate["published_day"] is None
    assert candidate["last_confirmed_git_ref"] is None
    assert candidate["mirror_base_git_ref"] is None
    assert candidate["state"] == {
        "npc": {"status": "awake"},
        "weather": "storm",
    }
    assert uuid.UUID(candidate["mirror_token"])


def test_service_role_cannot_self_certify_git_proof(db):
    _, candidate = publish_one(db)
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "select public.confirm_runtime_published_mirror(%s, %s::uuid, %s)",
                    (candidate["generation"], candidate["mirror_token"], FULL_SHA),
                )
        finally:
            cur.execute("reset role")


def test_verifier_confirmation_binds_exact_sha_and_unlocks_next_save(db):
    _, candidate = publish_one(db)
    confirm(db, candidate["generation"], candidate["mirror_token"], FULL_SHA)
    assert scalar(db, "select published_git_ref from public.campaign_runtime") == FULL_SHA
    assert scalar(db, "select runtime_published_confirmed from public.campaign_runtime") is True
    assert scalar(db, "select runtime_published_confirmed_at is not null from public.campaign_runtime") is True
    assert scalar(db, "select last_confirmed_generation from public.campaign_runtime") == 1
    assert scalar(db, "select last_confirmed_git_ref from public.campaign_runtime") == FULL_SHA
    published, staging, _token, _expires = begin(db)
    assert (published, staging) == (1, 2)


def test_confirmation_rejects_wrong_generation_token_and_non_exact_ref(db):
    _, candidate = publish_one(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="generation mismatch"):
        confirm(db, 99, candidate["mirror_token"], FULL_SHA)
    with pytest.raises(psycopg2.errors.RaiseException, match="token mismatch"):
        confirm(db, 1, str(uuid.uuid4()), FULL_SHA)
    with pytest.raises(psycopg2.errors.RaiseException, match="exact full commit SHA"):
        confirm(db, 1, candidate["mirror_token"], "main")
    assert scalar(db, "select runtime_published_confirmed from public.campaign_runtime") is False


def test_confirmation_is_idempotent_only_for_same_exact_sha(db):
    _, candidate = publish_one(db)
    confirm(db, 1, candidate["mirror_token"], FULL_SHA)
    confirm(db, 1, candidate["mirror_token"], FULL_SHA)
    with pytest.raises(psycopg2.errors.RaiseException, match="different Git ref"):
        confirm(db, 1, candidate["mirror_token"], OTHER_SHA)
    assert scalar(db, "select published_git_ref from public.campaign_runtime") == FULL_SHA


def test_last_healthy_git_anchor_survives_new_pending_publication(db):
    _, first = publish_one(db, "1")
    confirm(db, 1, first["mirror_token"], FULL_SHA)
    _published, _staging, token, _expires = begin(db)
    stage(db, token, value="2")
    publish(db, token)
    second = pending(db)
    assert second["generation"] == 2
    assert second["last_confirmed_git_ref"] == FULL_SHA
    assert second["mirror_base_git_ref"] is None
    assert scalar(db, "select published_git_ref from public.campaign_runtime") is None
    assert scalar(db, "select last_confirmed_git_ref from public.campaign_runtime") == FULL_SHA
    assert scalar(db, "select last_confirmed_generation from public.campaign_runtime") == 1


def test_rt01c_does_not_add_rt01d_read_or_engineering_release_surface(db):
    for name in (
        "dm_quick_context",
        "dm_runtime_lookup",
        "dm_runtime_read",
        "engineering_release",
    ):
        assert scalar(
            db,
            "select exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname=%s)",
            (name,),
        ) is False
