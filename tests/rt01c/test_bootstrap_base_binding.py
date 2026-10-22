"""RT01-C durable bootstrap base anchor (fresh Codex P1).

The generation-1 bootstrap has no prior confirmed checkpoint to anchor on. These
tests prove the EXACT selected origin/main SHA is durably bound to the pending
generation/token under verifier authority, that binding is idempotent-for-the-same
anchor and fail-closed otherwise, that service_role cannot bind it, and that the
bound anchor is exposed to the worker and survives across retries.
"""

import uuid

import psycopg2
import pytest

# Distinct valid 40-hex commit SHAs.
BASE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
BASE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CONFIRM_SHA = "0123456789abcdef0123456789abcdef01234567"


def _scalar(db, sql, params=None):
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
    import json

    value = _scalar(db, "select public.get_pending_runtime_mirror()")
    if isinstance(value, str):
        value = json.loads(value)
    return value


def publish_one(db, value="1"):
    _published, staging, token, _expires = begin(db)
    stage(db, token, value=value)
    publish(db, token)
    return staging, pending(db)


def bind(db, generation, token, base):
    with db.cursor() as cur:
        cur.execute("set role rhc_mirror_verifier")
        try:
            cur.execute(
                "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                (generation, token, base),
            )
            return cur.fetchone()[0]
        finally:
            cur.execute("reset role")


def confirm(db, generation, token, sha=CONFIRM_SHA):
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


def test_pending_bootstrap_base_is_null_before_binding(db):
    _, candidate = publish_one(db)
    assert candidate["last_confirmed_git_ref"] is None
    assert candidate["mirror_base_git_ref"] is None


def test_verifier_binds_bootstrap_base_and_it_is_exposed_and_idempotent(db):
    _, candidate = publish_one(db)
    bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
    assert pending(db)["mirror_base_git_ref"] == BASE_A
    # Idempotent for the SAME anchor: a retry re-binds cleanly.
    bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
    assert pending(db)["mirror_base_git_ref"] == BASE_A


def test_rebinding_a_different_base_fails_closed(db):
    _, candidate = publish_one(db)
    bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
    with pytest.raises(
        psycopg2.errors.RaiseException, match="different anchor"
    ):
        bind(db, candidate["generation"], candidate["mirror_token"], BASE_B)
    # The originally selected anchor is untouched.
    assert (
        _scalar(db, "select runtime_mirror_base_git_ref from public.campaign_runtime")
        == BASE_A
    )


def test_service_role_cannot_bind_bootstrap_base(db):
    _, candidate = publish_one(db)
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                    (candidate["generation"], candidate["mirror_token"], BASE_A),
                )
        finally:
            cur.execute("reset role")


def test_bind_rejects_non_exact_sha_wrong_generation_and_wrong_token(db):
    _, candidate = publish_one(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="exact full commit SHA"):
        bind(db, candidate["generation"], candidate["mirror_token"], "main")
    with pytest.raises(psycopg2.errors.RaiseException, match="generation mismatch"):
        bind(db, 99, candidate["mirror_token"], BASE_A)
    with pytest.raises(psycopg2.errors.RaiseException, match="token mismatch"):
        bind(db, candidate["generation"], str(uuid.uuid4()), BASE_A)
    assert (
        _scalar(db, "select runtime_mirror_base_git_ref from public.campaign_runtime")
        is None
    )


def test_bound_base_survives_between_push_and_failed_confirmation_retry(db):
    """The durable anchor lives in the database, not in a re-fetch of origin/main:
    after binding base A the worker can (simulate a) crash before confirmation, and a
    fresh read of the still-pending candidate returns the same bound anchor A."""
    _, candidate = publish_one(db)
    bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
    # Simulate "Git push succeeded, DB confirmation failed": generation is still
    # pending, and the retry re-reads exactly the same bound anchor.
    retry_candidate = pending(db)
    assert retry_candidate["generation"] == candidate["generation"]
    assert retry_candidate["mirror_base_git_ref"] == BASE_A
    assert retry_candidate["mirror_token"] == candidate["mirror_token"]


def test_base_binding_only_applies_to_the_bootstrap_generation(db):
    # Confirm the bootstrap, then advance to a new pending generation.
    _, first = publish_one(db, "1")
    bind(db, first["generation"], first["mirror_token"], BASE_A)
    confirm(db, first["generation"], first["mirror_token"], CONFIRM_SHA)

    _published, _staging, token, _expires = begin(db)
    stage(db, token, value="2")
    publish(db, token)
    second = pending(db)
    assert second["generation"] == 2
    assert second["last_confirmed_git_ref"] == CONFIRM_SHA
    # Publishing a new generation cleared the bootstrap base anchor.
    assert second["mirror_base_git_ref"] is None

    # Generation 2 anchors on last_confirmed_git_ref; there is no bootstrap base to
    # bind, so a bind attempt fails closed.
    with pytest.raises(
        psycopg2.errors.RaiseException, match="only applies to the bootstrap generation"
    ):
        bind(db, second["generation"], second["mirror_token"], BASE_B)


def test_cannot_bind_base_after_mirror_confirmed(db):
    _, candidate = publish_one(db)
    bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
    confirm(db, candidate["generation"], candidate["mirror_token"], CONFIRM_SHA)
    with pytest.raises(
        psycopg2.errors.RaiseException, match="already confirmed"
    ):
        bind(db, candidate["generation"], candidate["mirror_token"], BASE_A)
