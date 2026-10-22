"""RT04 Proof Matrix 5, 6, 7, 10: partial-candidate atomicity, replay
protection, gateway-bypass resistance and staged-data isolation."""

import json

import psycopg2
import pytest

from rt04_util import (
    abort_save,
    begin_save,
    confirm_mirror,
    dm_read,
    publish,
    publish_confirmed_runs,
    read_run,
    reconcile,
    request,
    resolution,
    run,
    runtime_row,
)


def _seed_runs(db, runs):
    return publish_confirmed_runs(db, runs)


def _txn_reconcile(txn, token, req):
    with txn.cursor() as cur:
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(req)),
        )
        return cur.fetchone()[0]


def _txn_begin(txn):
    with txn.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()[2]


# ---------------------------------------------------------------------------
# Idempotency / replay
# ---------------------------------------------------------------------------

def test_replay_across_saves_is_blocked(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)
    confirm_mirror(db)

    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(psycopg2.errors.RaiseException, match="already been reconciled"):
        reconcile(db, token, request(resolution("RP01", run_id="R01")))


def test_replay_within_same_save_is_blocked(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    with pytest.raises(psycopg2.errors.RaiseException, match="already been reconciled in this save"):
        reconcile(db, token, request(resolution("RP01", run_id="R01")))


def test_retry_after_abort_is_allowed(db):
    """A save that never published consumed nothing; the same resolution may be
    retried honestly in a fresh save."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    abort_save(db, token)

    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(db, token, request(resolution("RP01", run_id="R01")))
    assert report["resolution_id"] == "RP01"
    publish(db, token)
    confirm_mirror(db)
    assert read_run(db, "R01")["run"]["outcome_summary"] == (
        "Resolution RP01 accepted: above_average objective result. "
        "Scenario objective: Rescue the missing courier. "
        "Hook objective: Locate the courier before nightfall."
    )


def test_different_resolution_for_same_run_is_not_replay(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)
    confirm_mirror(db)

    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(
        db, token, request(resolution("RP02", run_id="R01", primary_roll=19, outcome_band="above_average"))
    )
    assert report["resolution_id"] == "RP02"


def test_second_same_run_reconciliation_in_one_save_fails_closed(db):
    """REPAIR Finding A: within one active save a source run_id may be
    reconciled at most once. A fresh resolution_id for the same Run must not
    bypass the guard."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    with pytest.raises(
        psycopg2.errors.RaiseException,
        match="second same-Run reconciliation would reuse stale published ownership",
    ):
        reconcile(db, token, request(resolution("RP02", run_id="R01")))


def test_second_same_run_reconciliation_cannot_resurrect_released_ownership(db):
    """REPAIR Finding A core proof: published R01 owns [hero, sidekick]; RP01
    releases hero and stages R01=[sidekick]; before publication RP02 releases
    sidekick. The second call must be refused instead of restarting from the
    published [hero, sidekick] record, so the first release can never be
    undone by stale input."""
    _seed_runs(
        db,
        [
            run(
                "R01",
                participant_entity_ids=["character:test-hero", "character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-hero", "character:test-sidekick"],
            )
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    first = reconcile(
        db,
        token,
        request(resolution("RP01", run_id="R01"), released=["character:test-hero"]),
    )
    assert first["applied"]["run_state_after"]["mutable_owner_entity_ids"] == [
        "character:test-sidekick"
    ]

    with pytest.raises(
        psycopg2.errors.RaiseException,
        match="second same-Run reconciliation would reuse stale published ownership",
    ):
        reconcile(
            db,
            token,
            request(
                resolution("RP02", run_id="R01", primary_roll=11, outcome_band="normal"),
                released=["character:test-sidekick"],
            ),
        )

    # The refused second call left the first staged candidate coherent: only
    # RP01 is consumed and the staged Run state is still the first result.
    with db.cursor() as cur:
        cur.execute(
            "select value from public.campaign_state_generations "
            "where generation = (select staging_generation from public.campaign_runtime where id = 1) "
            "and key = 'run_reconciliations'"
        )
        ledger = cur.fetchone()[0]
    assert set(ledger) == {"RP01"}
    assert ledger["RP01"]["run_state_after"]["mutable_owner_entity_ids"] == [
        "character:test-sidekick"
    ]

    publish(db, token)
    confirm_mirror(db)
    result = read_run(db, "R01")
    assert result["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]
    assert "character:test-hero" not in result["run"]["mutable_owner_entity_ids"]


# ---------------------------------------------------------------------------
# Atomicity / all-or-nothing
# ---------------------------------------------------------------------------

def test_partial_candidate_failure_publishes_nothing(db, txn):
    """Proof 5: one accepted candidate staged, then a second candidate fails in
    the same save -> the whole transaction rolls back; nothing publishes."""
    _seed_runs(db, [run("R01")])
    token = _txn_begin(txn)
    _txn_reconcile(txn, token, request(resolution("RP01", run_id="R01")))

    with pytest.raises(psycopg2.errors.RaiseException, match="does not exist in published reality"):
        _txn_reconcile(txn, token, request(resolution("RP02", run_id="R99")))
    txn.rollback()

    assert runtime_row(db)["published_generation"] == 1
    assert dm_read(db, "run_reconciliations")["results"] == []
    assert read_run(db, "R01")["run"].get("outcome_summary") is None
    assert read_run(db, "R01")["run"]["mutable_owner_entity_ids"] == ["character:test-hero"]


def test_failed_reconciliation_leaves_published_reality_unchanged(db, txn):
    _seed_runs(db, [run("R01")])
    token = _txn_begin(txn)
    with pytest.raises(psycopg2.errors.RaiseException, match="does not exist in published reality"):
        _txn_reconcile(txn, token, request(resolution("RP01", run_id="R99")))
    txn.rollback()

    assert runtime_row(db)["published_generation"] == 1
    assert dm_read(db, "run_reconciliations")["results"] == []
    assert read_run(db, "R01")["run"].get("outcome_summary") is None


def test_staged_reconciliation_is_invisible_to_supported_reads(db, txn):
    """Proof 10: while a reconciliation is staged but unpublished, the supported
    reads (dm_runtime_read_run / dm_runtime_read) still serve published truth."""
    _seed_runs(db, [run("R01")])
    token = _txn_begin(txn)
    _txn_reconcile(txn, token, request(resolution("RP01", run_id="R01")))

    assert read_run(db, "R01")["run"].get("outcome_summary") is None
    assert read_run(db, "R01")["run"]["control_state"] == "active"
    assert dm_read(db, "run_reconciliations")["results"] == []
    assert runtime_row(db)["published_generation"] == 1
    txn.rollback()


def test_abort_after_reconcile_discards_the_candidate(db, txn):
    _seed_runs(db, [run("R01")])
    token = _txn_begin(txn)
    _txn_reconcile(txn, token, request(resolution("RP01", run_id="R01")))
    with txn.cursor() as cur:
        cur.execute("select public.abort_campaign_save(%s)", (token,))
        cur.fetchone()
    txn.commit()

    assert runtime_row(db)["published_generation"] == 1
    assert dm_read(db, "run_reconciliations")["results"] == []
    assert read_run(db, "R01")["run"].get("outcome_summary") is None


# ---------------------------------------------------------------------------
# Gateway bypass resistance
# ---------------------------------------------------------------------------

def test_reconcile_requires_active_save(db):
    _seed_runs(db, [run("R01")])
    with pytest.raises(psycopg2.errors.RaiseException, match="campaign save lock mismatch"):
        reconcile(db, "bogus-token", request(resolution("RP01", run_id="R01")))


def test_reconcile_rejects_engineering_release(db):
    _seed_runs(db, [run("R01")])
    with db.cursor() as cur:
        cur.execute("select * from public.begin_engineering_release(%s, 30)", ("e" * 40,))
        row = cur.fetchone()
    token = row[4]
    with pytest.raises(
        psycopg2.errors.RaiseException, match="engineering_release forbids campaign state mutation"
    ):
        reconcile(db, token, request(resolution("RP01", run_id="R01")))


def test_engine_owned_ledger_rejects_generic_stage(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(
        psycopg2.errors.RaiseException, match="run_reconciliations is engine-owned"
    ):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'run_reconciliations', %s::jsonb)",
                (token, json.dumps({"RP99": {}})),
            )


def test_engine_owned_ledger_rejects_generic_delete(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(
        psycopg2.errors.RaiseException, match="run_reconciliations is engine-owned"
    ):
        with db.cursor() as cur:
            cur.execute(
                "select public.delete_staged_campaign_state(%s, 'run_reconciliations')",
                (token,),
            )


def test_engine_owned_clock_closure_remains_intact(db):
    """The RT02 campaign_clock closure is preserved by the RT04 re-creation of
    the generic stage/delete routes."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    with pytest.raises(
        psycopg2.errors.RaiseException, match="campaign_clock must be staged through stage_campaign_clock"
    ):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'campaign_clock', %s::jsonb)",
                (token, json.dumps({"schema_version": 1})),
            )
    with pytest.raises(
        psycopg2.errors.RaiseException, match="campaign_clock is engine-owned"
    ):
        with db.cursor() as cur:
            cur.execute(
                "select public.delete_staged_campaign_state(%s, 'campaign_clock')",
                (token,),
            )