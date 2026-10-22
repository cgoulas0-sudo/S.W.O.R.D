"""RT01-B — real-PostgreSQL proof that the save lease clock starts AFTER locks.

P1 follow-up (Codex thread on `begin_campaign_save`): the lease wall-clock instant
must be captured only after the authoritative locks are held
(`pg_advisory_xact_lock` + the singleton `FOR UPDATE`), never at function entry. If
BEGIN blocks waiting on those locks, a timestamp taken before the wait is stale and
can (a) treat an actually-expired prior save as still active, or (b) mint a new lease
that is already partially/fully expired by the time the lock is acquired.

These tests use a genuinely separate holder connection that grabs the SAME advisory
lock the gateway serializes on, forcing a contender's BEGIN to block. Because the
holder only releases at a known instant, a correctly-ordered gateway must produce a
`save_started_at` strictly AFTER that instant; the pre-wait bug would produce one
before it. This behaviour only exists in a real transactional engine, so — like the
rest of the RT01-B proof — it is skipped, never downgraded, without real Postgres.
"""

import threading
import time

import psycopg2  # noqa: F401 - imported for parity with the rest of the proof suite
import pytest

from gateway_util import begin_save, break_glass, locator, scalar

# The advisory-lock key the gateway serializes on (begin_campaign_save /
# _rhc_require_active_save both take pg_advisory_xact_lock(hashtext('rhc_campaign_save'))).
ADVISORY_LOCK_SQL = "select pg_advisory_xact_lock(hashtext('rhc_campaign_save'))"


def _spawn_begin(conn, ttl_minutes=30):
    """Run begin_campaign_save on ``conn`` in a background thread.

    Returns (thread, result). ``result`` gets 'row' on success or 'error' on failure
    once the thread finishes. The connection blocks inside BEGIN until whoever holds
    the advisory lock releases it.
    """
    result = {}

    def _run():
        try:
            with conn.cursor() as cur:
                cur.execute("select * from public.begin_campaign_save(%s)", (ttl_minutes,))
                result["row"] = cur.fetchone()
        except Exception as exc:  # pragma: no cover - surfaced via result["error"]
            result["error"] = exc

    t = threading.Thread(target=_run)
    t.start()
    return t, result


# ---------------------------------------------------------------------------
# 1 & 3 — a contender that waits on the lock uses POST-lock time, and the new
#         lease it mints is never born already expired from lock-wait time
# ---------------------------------------------------------------------------
def test_waiting_begin_captures_post_lock_time_for_a_fresh_lease(db, new_connection):
    # A holder grabs the gateway's advisory lock WITHOUT starting a save. The
    # singleton stays "no save active"; only the lock is held.
    holder = new_connection(autocommit=False)
    with holder.cursor() as hcur:
        hcur.execute(ADVISORY_LOCK_SQL)

        # The contender's BEGIN sets its gated context, then BLOCKS on the advisory
        # lock the holder is holding.
        contender = new_connection()
        t, result = _spawn_begin(contender)

        time.sleep(2)  # let the contender reach BEGIN and block on the lock
        assert t.is_alive(), "contender should be blocked on the advisory lock"

        # Latest instant BEFORE the contender can acquire the lock. It only proceeds
        # after the holder releases below, so any post-lock timestamp it captures MUST
        # be strictly after this marker; a pre-wait timestamp (the bug) precedes it.
        marker = scalar(db, "select clock_timestamp()")

        holder.rollback()  # release the advisory lock; the contender proceeds
        t.join(timeout=10)

    assert not t.is_alive(), "contender BEGIN never completed after lock release"
    assert "error" not in result, f"contender BEGIN failed: {result.get('error')}"

    loc = locator(db)
    assert loc["save_in_progress"] is True
    # The fix: the lease clock started AFTER lock acquisition, not at pre-wait entry.
    assert loc["save_started_at"] > marker, (
        "save_started_at must be captured AFTER the advisory lock is acquired, "
        "not before the lock wait"
    )
    # And the fresh lease is not born expired: it still lies in the future.
    assert loc["lock_expires_at"] > loc["save_started_at"]
    assert loc["lock_expires_at"] > scalar(db, "select clock_timestamp()"), (
        "a fresh lease must never be born already expired because of lock-wait time"
    )


# ---------------------------------------------------------------------------
# 2 — an actually-expired prior save is judged against fresh POST-lock time, so a
#     contender recovers it instead of treating a stale lease as still active
# ---------------------------------------------------------------------------
def test_waiting_begin_evaluates_expiry_against_post_lock_time(db, new_connection):
    # A committed active save whose lease elapses 2 seconds in the future.
    ctx = begin_save(db)
    break_glass(
        db,
        "update public.campaign_runtime"
        " set lock_expires_at = clock_timestamp() + interval '2 seconds' where id = 1",
    )

    # A holder grabs the gateway's advisory lock (no save of its own) so the
    # contender's BEGIN must wait.
    holder = new_connection(autocommit=False)
    with holder.cursor() as hcur:
        hcur.execute(ADVISORY_LOCK_SQL)

        contender = new_connection()
        t, result = _spawn_begin(contender)

        time.sleep(1)  # let the contender reach BEGIN and block
        assert t.is_alive(), "contender should be blocked on the advisory lock"

        # Burn real wall-clock time past the prior save's 2s lease WHILE the contender
        # is blocked. A pre-wait timestamp would still read that lease as live and make
        # the contender raise "already in progress"; post-lock time sees it expired.
        time.sleep(3)
        holder.rollback()  # contender proceeds and must judge expiry on fresh time
        t.join(timeout=10)

    assert not t.is_alive(), "contender BEGIN never completed after lock release"
    assert "error" not in result, (
        "an expired prior save must be recovered, not treated as active: "
        f"{result.get('error')}"
    )

    # begin returns (published_generation, staging_generation, lock_token, expires).
    published, staging, token, _expires = result["row"]
    assert published == 0
    assert staging == 1, "recovery reuses published + 1; no burned generation"
    assert token != ctx["token"], "recovery issues a fresh lock context"

    loc = locator(db)
    assert loc["lock_token"] == token
    # The recovered lease speaks fresh post-lock time and is not born expired.
    assert loc["lock_expires_at"] > scalar(db, "select clock_timestamp()")

    # The dead prior context can no longer publish.
    with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
        with db.cursor() as cur:
            cur.execute("select public.publish_campaign_save(%s)", (ctx["token"],))
