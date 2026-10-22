"""RT01-B — real-PostgreSQL concurrency and stale-lock recovery proof.

Uses multiple genuinely separate connections (separate advisory-lock holders and
transactions) to prove the lock/concurrency guarantees that only exist in a real
transactional engine: WIN 1 (single locked begin), WIN 2 (no burned generations),
WIN 5 (wrong/missing context fails closed).
"""

import psycopg2
import pytest

from gateway_util import begin_save, break_glass, exec_, locator, rows, scalar


# ---------------------------------------------------------------------------
# WIN 1 — a healthy active save blocks a second BEGIN
# ---------------------------------------------------------------------------
def test_second_begin_while_healthy_save_active_fails(db, new_connection):
    ctx = begin_save(db)  # active, non-expired save on the shared session
    other = new_connection()
    with pytest.raises(psycopg2.errors.RaiseException, match="already in progress"):
        with other.cursor() as cur:
            cur.execute("select * from public.begin_campaign_save(30)")
    # The original save is untouched; no second candidate generation was created.
    loc = locator(db)
    assert loc["save_in_progress"] is True and loc["lock_token"] == ctx["token"]
    assert scalar(db, "select count(*) from public.campaign_state_generations where generation = 2") == 0


# ---------------------------------------------------------------------------
# WIN 1 — the advisory/row lock actually serializes concurrent BEGINs
# ---------------------------------------------------------------------------
def test_advisory_lock_serializes_concurrent_begin(db, new_connection):
    # Holder opens a manual transaction and BEGINs, holding the advisory xact lock
    # and the singleton row lock without committing.
    holder = new_connection(autocommit=False)
    with holder.cursor() as hcur:
        hcur.execute("select * from public.begin_campaign_save(30)")

        # A concurrent session with a short statement timeout must BLOCK on the
        # lock and be cancelled, proving real serialization (not a state check).
        contender = new_connection()
        with pytest.raises(psycopg2.errors.QueryCanceled):
            with contender.cursor() as ccur:
                ccur.execute("set statement_timeout = '750ms'")
                ccur.execute("select * from public.begin_campaign_save(30)")

        holder.rollback()  # release the locks; the uncommitted candidate is gone

    # After rollback, no save state leaked and a fresh begin still starts at gen 1.
    assert scalar(db, "select save_in_progress from public.campaign_runtime") is False
    ctx = begin_save(db)
    assert ctx["staging"] == 1


# ---------------------------------------------------------------------------
# WIN 5 — wrong / missing save context fails closed on every mutation
# ---------------------------------------------------------------------------
def test_wrong_lock_token_fails_stage_abort_publish(db):
    begin_save(db)  # a real save is active, but with a different (real) token
    bogus = "00000000-0000-0000-0000-000000000000"
    for call in (
        "select public.stage_campaign_state(%s, 'k', '1'::jsonb)",
        "select public.delete_staged_campaign_state(%s, 'k')",
        "select public.abort_campaign_save(%s)",
        "select public.publish_campaign_save(%s)",
    ):
        with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
            exec_(db, call, (bogus,))


def test_mutations_fail_closed_when_no_save_active(db):
    # No begin has been called: every gated mutation must reject.
    for call in (
        "select public.stage_campaign_state(%s, 'k', '1'::jsonb)",
        "select public.publish_campaign_save(%s)",
        "select public.abort_campaign_save(%s)",
    ):
        with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
            exec_(db, call, ("any-token",))


# ---------------------------------------------------------------------------
# WIN 2 — an expired/abandoned save is recoverable without burning a generation
# ---------------------------------------------------------------------------
def test_expired_save_recovers_without_burning_a_generation(db):
    stale = begin_save(db)  # staging generation 1
    assert stale["staging"] == 1
    # A crashed caller left staged residue at the candidate generation.
    exec_(db, "select public.stage_campaign_state(%s, 'ghost', '\"stale\"'::jsonb)", (stale["token"],))

    # Simulate the TTL elapsing (break-glass stands in for the passage of time).
    break_glass(
        db,
        "update public.campaign_runtime set lock_expires_at = now() - interval '1 hour' where id = 1",
    )

    # A fresh BEGIN recovers the abandoned save: still the SAME candidate
    # generation (published + 1 == 1), not a burned generation 2.
    recovered = begin_save(db)
    assert recovered["staging"] == 1, "recovery must not consume an extra generation"
    assert recovered["token"] != stale["token"], "recovery issues a fresh lock context"

    # Stale candidate residue was cleared and re-derived from the (empty) published
    # snapshot; the ghost row never survives into the recovered candidate.
    assert (
        scalar(
            db,
            "select count(*) from public.campaign_state_generations"
            " where generation = 1 and key = 'ghost'",
        )
        == 0
    )
    # The old lock context is now dead and cannot publish.
    with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
        exec_(db, "select public.publish_campaign_save(%s)", (stale["token"],))


def test_expired_stale_candidate_never_becomes_published(db):
    stale = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'ghost', '\"stale\"'::jsonb)", (stale["token"],))
    break_glass(
        db,
        "update public.campaign_runtime set lock_expires_at = now() - interval '1 hour' where id = 1",
    )
    recovered = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'real', '\"clean\"'::jsonb)", (recovered["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (recovered["token"],))
    # Published generation 1 shows only the clean candidate, never the stale ghost.
    published = dict(
        rows(db, "select key, value from public.campaign_state_runtime order by key")
    )
    assert published == {"real": "clean"}
