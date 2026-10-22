"""RT01-B — real-PostgreSQL proof that an EXPIRED save context fails closed.

P1 repair (Codex thread on migration L130): `_rhc_require_active_save` must reject
a save whose lease has elapsed BEFORE any other caller runs BEGIN recovery, so a
stale/abandoned caller can no longer stage, delete, abort, or publish — and in
particular can never make its stale candidate authoritative. Expiry is judged on
wall-clock time (clock_timestamp), not the transaction-start-frozen now(), so a
long-running transaction cannot outlive its own lease. Candidate cleanup stays in
BEGIN's recovery path; this module proves the fail-closed half of that contract.
"""

import psycopg2
import pytest

from gateway_util import begin_save, break_glass, exec_, scalar


def _expire_active_lease(db):
    # Age the active lease into the past. break-glass stands in for elapsed time so
    # the test does not have to sleep out a real TTL; the gateway itself is unchanged.
    break_glass(
        db,
        "update public.campaign_runtime"
        " set lock_expires_at = clock_timestamp() - interval '1 hour' where id = 1",
    )


# ---------------------------------------------------------------------------
# 1-4: an expired context cannot mutate, even holding the CORRECT token
# ---------------------------------------------------------------------------
def test_expired_token_cannot_stage(db):
    ctx = begin_save(db)
    _expire_active_lease(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
        exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))


def test_expired_token_cannot_delete(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    _expire_active_lease(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
        exec_(db, "select public.delete_staged_campaign_state(%s, 'k')", (ctx["token"],))


def test_expired_token_cannot_abort(db):
    ctx = begin_save(db)
    _expire_active_lease(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
        exec_(db, "select public.abort_campaign_save(%s)", (ctx["token"],))


def test_expired_token_cannot_publish_stale_candidate(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    _expire_active_lease(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
        exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    # The expired candidate never became authoritative.
    assert scalar(db, "select published_generation from public.campaign_runtime") == 0
    assert scalar(db, "select count(*) from public.campaign_state_runtime") == 0


# ---------------------------------------------------------------------------
# 5-6: a fresh BEGIN after expiry recovers the SAME candidate generation
#      without burning another, and the stale token stays dead afterward
# ---------------------------------------------------------------------------
def test_fresh_begin_after_expiry_recovers_same_generation_and_kills_stale(db):
    stale = begin_save(db)
    assert stale["staging"] == 1
    exec_(db, "select public.stage_campaign_state(%s, 'ghost', '\"stale\"'::jsonb)", (stale["token"],))
    _expire_active_lease(db)

    recovered = begin_save(db)
    # Same candidate generation (published + 1 == 1), not a burned generation 2.
    assert recovered["staging"] == 1, "recovery must not consume an extra generation"
    assert recovered["token"] != stale["token"], "recovery issues a fresh lock context"

    # The stale token is dead after recovery: it now mismatches the fresh token and
    # fails closed at the token check before the expiry check even applies.
    with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
        exec_(db, "select public.publish_campaign_save(%s)", (stale["token"],))

    # The recovered context publishes exactly one clean generation; the stale ghost
    # residue was cleared by recovery and never surfaces as published truth.
    exec_(db, "select public.stage_campaign_state(%s, 'real', '\"clean\"'::jsonb)", (recovered["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (recovered["token"],))
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1
    assert (
        scalar(db, "select value from public.campaign_state_runtime where key = 'real'") == "clean"
    )
    assert scalar(db, "select count(*) from public.campaign_state_runtime where key = 'ghost'") == 0


# ---------------------------------------------------------------------------
# 7: expiry uses REAL wall-clock time, not transaction-start-frozen time
# ---------------------------------------------------------------------------
def test_expiry_uses_wall_clock_not_transaction_start_time(db, new_connection):
    """Definitive proof the gate uses clock_timestamp(), not now().

    now()/transaction_timestamp() is frozen at transaction start; clock_timestamp()
    advances during the transaction. We open a transaction BEFORE the lease elapses,
    then burn real time past it. If the gate compared now() the mutation would still
    look valid (frozen before expiry); because it compares clock_timestamp() it
    fails closed.
    """
    ctx = begin_save(db)
    # Lease expires 2 seconds into the future (real wall clock).
    break_glass(
        db,
        "update public.campaign_runtime"
        " set lock_expires_at = clock_timestamp() + interval '2 seconds' where id = 1",
    )

    conn = new_connection(autocommit=False)
    try:
        with conn.cursor() as cur:
            # Anchor this transaction's now() to BEFORE the lease expires.
            cur.execute("select now(), lock_expires_at from public.campaign_runtime where id = 1")
            txn_now, expires = cur.fetchone()
            assert txn_now < expires, "transaction must start before the lease expires"

            # Burn real wall-clock time past the lease while now() stays frozen.
            cur.execute("select pg_sleep(3)")

            # now() still reads not-expired, but clock_timestamp() has passed the
            # lease: the gate must reject on wall-clock semantics.
            with pytest.raises(psycopg2.errors.RaiseException, match="lock expired"):
                cur.execute(
                    "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],)
                )
    finally:
        conn.rollback()

    # Nothing leaked through the aborted transaction.
    assert scalar(db, "select count(*) from public.campaign_state_generations where key = 'k'") == 0
