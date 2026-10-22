"""RT01-B — real-PostgreSQL proof of the guarded save lifecycle.

BEGIN -> STAGE/DELETE -> ABORT | PUBLISH against a real PostgreSQL 15 engine.
Each test maps to one or more RT01-B WIN conditions (Issue #29).

Run:
    python -m pytest tests/rt01b -v
"""

import psycopg2
import pytest

from gateway_util import begin_save, exec_, locator, rows, scalar


# ---------------------------------------------------------------------------
# WIN 1 & 2 — BEGIN derives from authoritative current state; one candidate
# ---------------------------------------------------------------------------
def test_begin_stages_next_generation_from_published(db):
    # Published generation 0 with one published row.
    ctx = begin_save(db)
    assert ctx["published"] == 0
    assert ctx["staging"] == 1, "candidate must be exactly published + 1"
    assert ctx["token"], "database must return a generated lock token"

    loc = locator(db)
    assert loc["save_in_progress"] is True
    assert loc["staging_generation"] == 1
    assert loc["lock_token"] == ctx["token"]
    assert loc["save_started_at"] is not None
    assert loc["lock_expires_at"] is not None


def test_begin_copies_published_snapshot_into_candidate(db):
    # Seed a published row by publishing one generation first.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"clear\"'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1

    # A new save must copy the published snapshot forward as the candidate base.
    ctx2 = begin_save(db)
    assert ctx2["published"] == 1 and ctx2["staging"] == 2
    staged = rows(
        db,
        "select key, value from public.campaign_state_generations"
        " where generation = 2 order by key",
    )
    assert staged == [("weather", "clear")]


# ---------------------------------------------------------------------------
# WIN 3 — published truth is isolated from staged candidate state
# ---------------------------------------------------------------------------
def test_staged_changes_do_not_leak_into_published_view(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"storm\"'::jsonb)", (ctx["token"],))
    # Published view (generation 0) is still empty; the candidate is at gen 1.
    assert scalar(db, "select count(*) from public.campaign_state_runtime") == 0
    assert (
        scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 1 and key = 'weather'",
        )
        == "storm"
    )


def test_publish_advances_view_without_rewriting_history(db):
    # Publish gen 1 with a row, then a second save mutating it to gen 2.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"clear\"'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))

    ctx2 = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"storm\"'::jsonb)", (ctx2["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx2["token"],))

    assert rows(
        db, "select runtime_generation, value from public.campaign_state_runtime"
    ) == [(2, "storm")]
    # Generation 1 history is intact (not rewritten in place).
    assert (
        scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 1 and key = 'weather'",
        )
        == "clear"
    )


# ---------------------------------------------------------------------------
# WIN 5 — guarded staging: stage, upsert, delete only the candidate
# ---------------------------------------------------------------------------
def test_stage_is_upsert_on_candidate(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.stage_campaign_state(%s, 'k', '2'::jsonb)", (ctx["token"],))
    assert (
        scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 1 and key = 'k'",
        )
        == 2
    )


def test_delete_staged_removes_only_from_candidate(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    assert scalar(db, "select public.delete_staged_campaign_state(%s, 'k')", (ctx["token"],)) is True
    # A second delete of the now-absent key reports no rows removed.
    assert scalar(db, "select public.delete_staged_campaign_state(%s, 'k')", (ctx["token"],)) is False


# ---------------------------------------------------------------------------
# WIN 6 — ABORT restores a clean candidate boundary
# ---------------------------------------------------------------------------
def test_abort_removes_candidate_and_leaves_published_unchanged(db):
    # Establish a published generation 1 with a value.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"clear\"'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))

    # Begin a second save, stage a change, then ABORT.
    ctx2 = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"storm\"'::jsonb)", (ctx2["token"],))
    exec_(db, "select public.abort_campaign_save(%s)", (ctx2["token"],))

    loc = locator(db)
    assert loc["published_generation"] == 1
    assert loc["save_in_progress"] is False
    assert loc["staging_generation"] is None
    assert loc["lock_token"] is None
    # Candidate residue removed; published value unchanged.
    assert scalar(db, "select count(*) from public.campaign_state_generations where generation = 2") == 0
    assert rows(
        db, "select key, value from public.campaign_state_runtime"
    ) == [("weather", "clear")]


# ---------------------------------------------------------------------------
# WIN 7 & 8 — PUBLISH is atomic and advances exactly N -> N+1
# ---------------------------------------------------------------------------
def test_publish_advances_exactly_once_and_clears_lock(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    loc = locator(db)
    assert loc["published_generation"] == 1
    assert loc["save_in_progress"] is False
    assert loc["staging_generation"] is None
    assert loc["lock_token"] is None
    assert loc["save_started_at"] is None
    assert loc["lock_expires_at"] is None


def test_repeated_publish_with_old_context_cannot_advance_again(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    # Old token now names no active save: a replayed publish must fail closed.
    with pytest.raises(psycopg2.errors.RaiseException, match="lock mismatch"):
        exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1


# ---------------------------------------------------------------------------
# WIN 10 — Unknown remains Unknown: no invented campaign facts
# ---------------------------------------------------------------------------
def test_publish_does_not_invent_day_and_preserves_unknown(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    loc = locator(db)
    assert loc["published_day"] is None, "RT01-B must not invent a campaign day"


def test_gateway_has_no_day_or_git_parameter(db):
    # None of the gateway BEGIN/PUBLISH signatures may accept a day or git ref:
    # the caller cannot inject campaign-clock or checkpoint identity.
    sigs = dict(
        rows(
            db,
            """
            select p.proname, pg_get_function_arguments(p.oid)
            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public'
              and p.proname in ('begin_campaign_save', 'publish_campaign_save')
            """,
        )
    )
    assert "git" not in sigs["publish_campaign_save"].lower()
    assert "day" not in sigs["publish_campaign_save"].lower()
    assert "git" not in sigs["begin_campaign_save"].lower()
    assert "day" not in sigs["begin_campaign_save"].lower()
