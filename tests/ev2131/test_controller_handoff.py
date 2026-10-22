"""EV2-13.1 controller / handoff runtime proof.

Runs against real PostgreSQL 15 with the full forward migration chain and the
real save/publication/mirror-confirmation spine. Nothing is mocked.

Controller authority is resolved ONLY from authoritative published Run truth. A
Run-ownership handoff is an atomic candidate transition staged through the real
spine; the former controller is historical/reference-only and cannot mutate,
acknowledge or end an applied status.

Proof Matrix coverage:
  * MAINRUN -> RUN, RUN -> MAINRUN and RUN A -> RUN B handoffs each preserve
    exactly one current controller;
  * the former/stale controller write fails after a handoff;
  * one application remains exactly one record across those handoffs;
  * two Runs claiming one target, a parked Run that still claims it, malformed
    published Run truth and a duplicated authoritative Run identity all fail
    closed rather than falling through to MAINRUN;
  * status mutation and Run-ownership write are refused in BOTH same-save
    orderings;
  * status mutation and Campaign Clock write are refused in BOTH same-save
    orderings;
  * a value-equal replay still closes every Run-ownership and Clock doorway;
  * the applied-status staging marker never leaks into a later save;
  * generation, Git ref, mirror and confirmation remain valid after handoff.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ev2131"))
import ev2131_util as s  # noqa: E402


def _create(clock_elapsed, thresholds=None, controller=None, target=s.HERO,
            application_id=s.APPLICATION):
    s.publish_confirmed_clock(_db(), s.clock(elapsed_campaign_minutes=clock_elapsed))
    _published, _staging, token, _expires = s.begin_save(_db())
    s.mutate(_db(), token, s.request(
        application_id=application_id,
        controller=controller,
        definition_obj=s.definition(thresholds=thresholds, target=target),
    ))
    s.publish(_db(), token)
    s.confirm_mirror(_db())


_ACTIVE_DB = {"db": None}


def _db():
    return _ACTIVE_DB["db"]


@pytest.fixture(autouse=True)
def _bind(db):
    _ACTIVE_DB["db"] = db
    yield
    _ACTIVE_DB["db"] = None


def _advance(db, elapsed):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=elapsed))


# ---------------------------------------------------------------------------
# Handoffs preserve exactly one controller
# ---------------------------------------------------------------------------

def test_mainrun_to_run_handoff_transfers_mutation_authority(db):
    _create(100, thresholds=[s.threshold("T1", 10, "minute")])
    _advance(db, 200)
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )

    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(db, token, s.request(
        controller={"kind": "run", "run_id": "R01"}, acknowledge=["T1"]))
    assert result["controller"] == {"kind": "run", "run_id": "R01"}
    err = s.mutate_error(db, token, s.request(controller={"kind": "mainrun"}))
    assert "R01" in err
    s.publish(db, token)
    s.confirm_mirror(db)

    read = s.read_status(db)
    assert read["application"]["acknowledged_thresholds"] == [
        {"threshold_id": "T1", "acknowledged_at_elapsed_minutes": 200}
    ]
    assert len(s.published_applied_statuses(db)) == 1


def test_run_to_mainrun_handoff_transfers_mutation_authority(db):
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    _create(100, thresholds=[s.threshold("T1", 10, "minute")],
            controller={"kind": "run", "run_id": "R01"})
    _advance(db, 200)

    # R01 releases mutable ownership; MAINRUN becomes the controller.
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", control_state="parked",
                   mutable_owner_entity_ids=[])]
    )

    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(db, token, s.request(
        controller={"kind": "mainrun"}, acknowledge=["T1"]))
    assert result["controller"] == {"kind": "mainrun"}
    err = s.mutate_error(
        db, token, s.request(controller={"kind": "run", "run_id": "R01"}))
    assert "no published Run" in err
    s.publish(db, token)
    s.confirm_mirror(db)
    assert len(s.published_applied_statuses(db)) == 1


def test_run_a_to_run_b_handoff_transfers_mutation_authority(db):
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    _create(100, thresholds=[s.threshold("T1", 10, "minute")],
            controller={"kind": "run", "run_id": "R01"})
    _advance(db, 200)

    s.publish_confirmed_runs(
        db,
        [s.run(run_id="R01", mutable_owner_entity_ids=[]),
         s.run(run_id="R02", mutable_owner_entity_ids=[s.HERO])],
    )

    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(db, token, s.request(
        controller={"kind": "run", "run_id": "R02"}, acknowledge=["T1"]))
    assert result["controller"] == {"kind": "run", "run_id": "R02"}
    err = s.mutate_error(
        db, token, s.request(controller={"kind": "run", "run_id": "R01"}))
    assert "R02" in err
    s.publish(db, token)
    s.confirm_mirror(db)
    assert len(s.published_applied_statuses(db)) == 1


def test_one_application_remains_one_record_across_handoffs(db):
    _create(100, thresholds=[s.threshold("T1", 10, "minute")])
    assert len(s.published_applied_statuses(db)) == 1

    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    assert len(s.published_applied_statuses(db)) == 1

    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", control_state="parked",
                   mutable_owner_entity_ids=[])]
    )
    assert len(s.published_applied_statuses(db)) == 1
    assert s.published_applied_statuses(db)[0]["target_entity_id"] == s.HERO


def test_handoff_keeps_publication_integrity(db):
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    before = s.runtime_row(db)["published_generation"]

    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(
        controller={"kind": "run", "run_id": "R01"},
        definition_obj=s.definition()))
    s.publish(db, token)
    s.confirm_mirror(db)

    row = s.runtime_row(db)
    assert row["published_generation"] == before + 1
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"]
    assert row["last_confirmed_generation"] == row["published_generation"]


# ---------------------------------------------------------------------------
# Ambiguous / malformed controller truth fails closed
# ---------------------------------------------------------------------------

def test_two_runs_claiming_one_target_fail_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db,
        [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO]),
         s.run(run_id="R02", mutable_owner_entity_ids=[s.HERO])],
    )
    _published, _staging, token, _expires = s.begin_save(db)
    err_mainrun = s.mutate_error(
        db, token, s.request(controller={"kind": "mainrun"},
                             definition_obj=s.definition()))
    assert "more than one published Run" in err_mainrun
    err_run = s.mutate_error(
        db, token, s.request(controller={"kind": "run", "run_id": "R01"},
                             definition_obj=s.definition()))
    assert "more than one published Run" in err_run


def test_parked_claiming_run_fails_closed_for_run_and_mainrun(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", control_state="parked",
                   mutable_owner_entity_ids=[s.HERO])]
    )
    _published, _staging, token, _expires = s.begin_save(db)
    err_run = s.mutate_error(
        db, token, s.request(controller={"kind": "run", "run_id": "R01"},
                             definition_obj=s.definition()))
    assert "parked" in err_run
    err_mainrun = s.mutate_error(
        db, token, s.request(controller={"kind": "mainrun"},
                             definition_obj=s.definition()))
    assert "parked" in err_mainrun


def test_malformed_published_run_entry_fails_closed_not_mainrun(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    malformed = {
        "execution_mode": "played",
        "control_state": "active",
        "scenario_id": "S01",
        "occurred_encounter_ids": [],
        "participant_entity_ids": [s.HERO],
        "mutable_owner_entity_ids": [s.HERO],
        "location_ids": [],
        "campaign_anchor": {"base_commit": s.RUN_ANCHOR,
                            "campaign_time": "Day 1, evening"},
    }
    s.publish_confirmed_runs(db, [malformed])
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(db, token, s.request(controller={"kind": "mainrun"},
                                              definition_obj=s.definition()))
    assert "run_id" in err or "unreadable" in err


def test_non_object_published_run_entry_fails_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(db, ["not-a-run-record"])
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(db, token, s.request(controller={"kind": "mainrun"},
                                              definition_obj=s.definition()))
    assert "non-object" in err


def test_duplicate_published_run_identity_fails_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db,
        [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO]),
         s.run(run_id="R01", participant_entity_ids=[s.OTHER],
               mutable_owner_entity_ids=[s.OTHER])],
    )
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(db, token, s.request(controller={"kind": "mainrun"},
                                              definition_obj=s.definition()))
    assert "duplicate authoritative Run identity" in err


# ---------------------------------------------------------------------------
# Same-save Run-ownership exclusion (both orderings)
# ---------------------------------------------------------------------------

def test_staged_runs_change_makes_status_mutation_fail_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    _published, _staging, token, _expires = s.begin_save(db)
    s.stage(db, token, "runs",
            [s.run(run_id="R01", control_state="parked",
                   mutable_owner_entity_ids=[])])
    err = s.mutate_error(
        db, token, s.request(controller={"kind": "run", "run_id": "R01"},
                             definition_obj=s.definition()))
    assert "runs" in err


def test_status_staging_closes_every_runs_doorway(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(controller={"kind": "run", "run_id": "R01"},
                                  definition_obj=s.definition()))

    err_stage = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, "runs", json.dumps([s.run(run_id="R01",
                                              mutable_owner_entity_ids=[])])),
        ),
    )
    assert "runs" in err_stage

    err_delete = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)", (token, "runs")),
    )
    assert "runs" in err_delete

    err_reconcile = s.reconcile_error(
        db, token,
        s.reconcile_request(s.resolution(run_id="R01"), released=[s.HERO]),
    )
    assert "applied-status" in err_reconcile


def test_status_mutation_refused_after_reconcile_in_same_save(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    _published, _staging, token, _expires = s.begin_save(db)
    s.reconcile(db, token,
                s.reconcile_request(s.resolution(run_id="R01"), released=[s.HERO]))
    err = s.mutate_error(
        db, token, s.request(controller={"kind": "mainrun"},
                             definition_obj=s.definition()))
    assert "runs" in err


# ---------------------------------------------------------------------------
# Same-save Campaign-Clock exclusion (both orderings)
# ---------------------------------------------------------------------------

def test_staged_clock_change_makes_status_mutation_fail_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.stage_clock(db, token, s.clock(elapsed_campaign_minutes=200))
    err = s.mutate_error(db, token, s.request(definition_obj=s.definition()))
    assert "campaign_clock" in err


def test_clock_staging_refused_once_status_is_staged(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    err = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(s.clock(elapsed_campaign_minutes=200))),
        ),
    )
    assert "applied-status" in err


# ---------------------------------------------------------------------------
# Operation-fact closure and marker lifetime
# ---------------------------------------------------------------------------

def test_value_equal_replay_still_closes_runs_and_clock_doorways(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    request = s.request(definition_obj=s.definition())

    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, request)
    s.publish(db, token)
    s.confirm_mirror(db)

    # New save: re-stage the identical absolute target (value-equal to published).
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, request)
    assert s.staged_state_key(db, "applied_statuses") == s.published_applied_statuses(db)

    err_stage = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, "runs", json.dumps([s.run(run_id="R01")])),
        ),
    )
    assert "runs" in err_stage

    err_clock = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(s.clock(elapsed_campaign_minutes=200))),
        ),
    )
    assert "applied-status" in err_clock


def test_applied_status_marker_does_not_leak_into_a_later_save(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    s.publish(db, token)
    s.confirm_mirror(db)

    # A later save must be free to advance the Clock: the prior save's operation
    # fact is bound to its own database-minted lock token.
    _published, _staging, token, _expires = s.begin_save(db)
    s.publish_clock(db, token, s.clock(elapsed_campaign_minutes=500))
    assert s.published_clock(db)["elapsed_campaign_minutes"] == 500
