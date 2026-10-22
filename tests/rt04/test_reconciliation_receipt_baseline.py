"""RT04 REPAIR 2 proof matrix: historical reconciliation receipts copied into a
new save must not be mistaken for reconciliation activity created inside that
save. The generic-`runs` closure fires only when a reconciliation marker is
newly staged in the current active save."""

import psycopg2
import pytest

from rt04_util import (
    begin_save,
    confirm_mirror,
    publish,
    publish_confirmed_runs,
    read_run,
    reconcile,
    request,
    resolution,
    run,
    stage_runs,
    delete_staged,
)


def _helper(db):
    with db.cursor() as cur:
        cur.execute(
            "select public._rhc_reconciliation_new_in_save(cr.staging_generation, cr.published_generation) "
            "from public.campaign_runtime cr where cr.id = 1"
        )
        return cur.fetchone()[0]


def _staged_receipt_ids(db):
    with db.cursor() as cur:
        cur.execute(
            "select csg.value from public.campaign_state_generations csg "
            "join public.campaign_runtime cr on cr.id = 1 "
            "and csg.generation = cr.staging_generation and csg.key = 'run_reconciliations'"
        )
        row = cur.fetchone()
    return sorted((row[0] or {}).keys()) if row else []


def _published_receipt_ids(db):
    with db.cursor() as cur:
        cur.execute(
            "select csg.value from public.campaign_state_generations csg "
            "join public.campaign_runtime cr on cr.id = 1 "
            "and csg.generation = cr.published_generation and csg.key = 'run_reconciliations'"
        )
        row = cur.fetchone()
    return sorted((row[0] or {}).keys()) if row else []


def _publish_first_reconciliation(db):
    """Save N: reconcile RP01 for R01 and publish it."""
    publish_confirmed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(db, token, request(resolution("RP01", run_id="R01")))
    assert report["resolution_id"] == "RP01"
    publish(db, token)
    confirm_mirror(db)
    assert _published_receipt_ids(db) == ["RP01"]


# ---------------------------------------------------------------------------
# Case A / D: historical receipt only, new save, no current reconciliation yet
# ---------------------------------------------------------------------------

def test_copied_historical_receipt_does_not_block_future_save(db):
    """Save N published RP01. Save N+1 inherits it as baseline; legal generic
    `runs` staging/deletion before any N+1 reconciliation must succeed."""
    _publish_first_reconciliation(db)

    _published, _staging, token, _expires = begin_save(db)
    assert _staged_receipt_ids(db) == ["RP01"]
    assert _helper(db) is False

    legal_disjoint_runs = [
        run("R01"),
        run(
            "R02",
            scenario_id="S02",
            participant_entity_ids=["character:test-sidekick"],
            mutable_owner_entity_ids=["character:test-sidekick"],
        ),
    ]
    stage_runs(db, token, legal_disjoint_runs)
    delete_staged(db, token, "runs")
    stage_runs(db, token, legal_disjoint_runs)

    publish(db, token)
    confirm_mirror(db)
    # Old receipt remains preserved as durable historical evidence.
    assert _published_receipt_ids(db) == ["RP01"]
    assert read_run(db, "R02")["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]


def test_presence_alone_is_not_a_current_save_marker(db):
    """Copied-baseline receipt present in staging must not count as a
    same-save reconciliation marker."""
    _publish_first_reconciliation(db)

    begin_save(db)
    assert _staged_receipt_ids(db) == ["RP01"]
    assert _helper(db) is False


# ---------------------------------------------------------------------------
# Case B: current-save reconciliation does trigger closure
# ---------------------------------------------------------------------------

def test_new_current_save_reconciliation_blocks_generic_runs_mutation(db):
    _publish_first_reconciliation(db)

    _published, _staging, token, _expires = begin_save(db)
    assert _helper(db) is False

    reconcile(db, token, request(resolution("RP02", run_id="R01")))
    assert _helper(db) is True

    with pytest.raises(
        psycopg2.errors.RaiseException, match="runs batch is engine-owned for the rest of this save"
    ):
        stage_runs(db, token, [run("R01", mutable_owner_entity_ids=[])])
    with pytest.raises(
        psycopg2.errors.RaiseException, match="runs batch is engine-owned for the rest of this save"
    ):
        delete_staged(db, token, "runs")


# ---------------------------------------------------------------------------
# Case C: same-RUN double reconciliation in one save stays rejected
# ---------------------------------------------------------------------------

def test_same_run_double_reconciliation_in_one_save_still_rejected(db):
    _publish_first_reconciliation(db)

    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP02", run_id="R01")))

    with pytest.raises(
        psycopg2.errors.RaiseException, match="already been reconciled in this save as RP02"
    ):
        reconcile(db, token, request(resolution("RP03", run_id="R01")))

