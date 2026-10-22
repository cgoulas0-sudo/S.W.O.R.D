"""EV2-13 handoff + controller-safety runtime proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 + EV2-10 + EV2-11 + EV2-12.1 spine plus the forward-only EV2-13 migration.
All durable mutation goes through the real save/publication/mirror-confirmation
spine; nothing is mocked.

Controller authority is resolved ONLY from authoritative published Run truth. A
Run-ownership handoff is an atomic candidate transition staged through the real
spine; the former controller is historical/reference-only and cannot write.

Proof Matrix coverage:
  * MAINRUN -> RUN, RUN -> MAINRUN and RUN A -> RUN B handoffs each preserve
    exactly one current controller;
  * the former/stale controller write fails after a handoff;
  * two Runs claiming one entity fails closed;
  * a parked Run that still claims an entity fails closed for both the Run and
    MAINRUN assertions;
  * malformed and duplicated published Run truth fails closed;
  * same-save Run-ownership change plus mutable entity-state mutation is mutually
    exclusive in BOTH orderings;
  * a value-equal replay still closes every Run-ownership-writing doorway;
  * the entity-state staging marker never leaks into a later save;
  * generation, Git ref, mirror and confirmation remain valid after handoff.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402


HERO = "character:test-hero"
OTHER = "character:test-fanis"


# ---------------------------------------------------------------------------
# Harness helpers (same contract as test_mutable_entity_state.py)
# ---------------------------------------------------------------------------

def _run_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _error_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def _mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_entity_state(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_entity_state(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _stage_error(db, token, key, value):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        ),
    )


def _delete_error(db, token, key):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)", (token, key)
        ),
    )


def _reconcile(db, token, request):
    def call(cur):
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _reconcile_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _entry(attribute="location", status="known", value="Tavern"):
    entry = {"attribute": attribute, "status": status}
    if status == "known":
        entry["value"] = value
    return entry


def _request(entity=HERO, controller=None, entries=None):
    return {
        "entity_id": entity,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "state": {"status": "known", "entries": entries or [_entry()]},
    }


def _published_entity_state(db):
    return u.published_state(db).get("entity_state") or []


def _staged_entity_state(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'entity_state'",
    )
    return value or []


def _published_owners(db):
    owners = {}
    for run in u.published_state(db).get("runs") or []:
        for owner in run.get("mutable_owner_entity_ids", []):
            owners.setdefault(owner, []).append(run["run_id"])
    return owners


# ---------------------------------------------------------------------------
# Handoff preserves exactly one controller
# ---------------------------------------------------------------------------

def test_mainrun_to_run_handoff_preserves_one_controller(db):
    # MAINRUN owns the entity's state initially.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "mainrun"}))
    u.publish(db, token)
    u.confirm_mirror(db)
    assert _published_owners(db) == {}

    # Atomic handoff: the entity becomes owned by R01 in one published generation.
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    assert _published_owners(db) == {HERO: ["R01"]}

    # The new controller can author; the former MAINRUN cannot.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(
            controller={"kind": "run", "run_id": "R01"},
            entries=[_entry("location", "known", "Run camp")],
        ),
    )
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "MAINRUN" in err and "R01" in err
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert len(records) == 1
    assert records[0]["entries"][0]["value"] == "Run camp"
    assert _published_owners(db) == {HERO: ["R01"]}


def test_run_to_mainrun_handoff_preserves_one_controller(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    assert _published_owners(db) == {HERO: ["R01"]}

    # Handoff back to MAINRUN: R01 releases mutable ownership but keeps history.
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])]
    )
    assert _published_owners(db) == {}

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "mainrun"}))
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "no published Run" in err
    u.publish(db, token)
    u.confirm_mirror(db)

    assert len(_published_entity_state(db)) == 1


def test_run_a_to_run_b_handoff_preserves_one_controller(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    # R01 keeps historical participation but hands mutable authority to R02.
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[]),
            u.run(run_id="R02", mutable_owner_entity_ids=[HERO]),
        ],
    )
    assert _published_owners(db) == {HERO: ["R02"]}

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R02"}))
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "R02" in err
    u.publish(db, token)
    u.confirm_mirror(db)

    assert len(_published_entity_state(db)) == 1
    assert _published_owners(db) == {HERO: ["R02"]}


def test_handoff_keeps_exactly_one_state_record_and_advances_one_generation(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    before = u.runtime_row(db)["published_generation"]

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert len([r for r in records if r["entity_id"] == HERO]) == 1

    row = u.runtime_row(db)
    assert row["published_generation"] == before + 1
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"]
    assert row["last_confirmed_generation"] == row["published_generation"]


# ---------------------------------------------------------------------------
# Ambiguous / malformed controller truth fails closed
# ---------------------------------------------------------------------------

def test_two_runs_claiming_one_entity_fails_closed(db):
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", mutable_owner_entity_ids=[HERO]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "more than one published Run" in err_mainrun

    err_run = _mutate_error(
        db, token, _request(controller={"kind": "run", "run_id": "R01"})
    )
    assert "more than one published Run" in err_run


def test_parked_claiming_run_fails_closed_for_mainrun_and_run(db):
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[HERO])]
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err_run = _mutate_error(
        db, token, _request(controller={"kind": "run", "run_id": "R01"})
    )
    assert "parked" in err_run

    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "parked" in err_mainrun


def test_malformed_published_run_entry_fails_closed_not_mainrun(db):
    malformed = {
        "execution_mode": "played",
        "control_state": "active",
        "scenario_id": "S01",
        "occurred_encounter_ids": [],
        "participant_entity_ids": [HERO],
        "mutable_owner_entity_ids": [HERO],
        "location_ids": [],
        "campaign_anchor": {
            "base_commit": u.RUN_ANCHOR,
            "campaign_time": "Day 1, evening",
        },
    }
    u.publish_confirmed_runs(db, [malformed])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "run_id" in err or "unreadable" in err


def test_non_object_published_run_entry_fails_closed(db):
    u.publish_confirmed_runs(db, ["not-a-run-record"])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "non-object" in err


def test_duplicate_published_run_identity_fails_closed_before_authority(db):
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(
                run_id="R01",
                participant_entity_ids=[OTHER],
                mutable_owner_entity_ids=[OTHER],
            ),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "duplicate authoritative Run identity" in err


# ---------------------------------------------------------------------------
# Same-save ownership/mutation race (both orderings)
# ---------------------------------------------------------------------------

def test_same_save_runs_handoff_makes_entity_state_mutation_fail_closed(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    # Stage a same-save handoff releasing HERO from R01.
    u.stage(
        db,
        token,
        "runs",
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])],
    )

    err_run = _mutate_error(
        db, token, _request(controller={"kind": "run", "run_id": "R01"})
    )
    assert "runs" in err_run

    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "runs" in err_mainrun


def test_generic_runs_change_is_refused_once_entity_state_is_staged(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request())

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage

    err_delete = _delete_error(db, token, "runs")
    assert "runs" in err_delete

    # Unrelated ordinary-save keys remain stageable in the same save.
    u.stage(db, token, "live_status", {"scene": "workshop"})


def test_reconcile_is_refused_once_entity_state_is_staged_in_same_save(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))

    err = _reconcile_error(
        db, token, u.request(u.resolution(run_id="R01"), released=[HERO])
    )
    assert "entity-state" in err


def test_entity_state_mutation_is_refused_after_reconcile_in_same_save(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))

    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "runs" in err


def test_value_equal_replay_still_closes_every_runs_doorway(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    request = _request(controller={"kind": "run", "run_id": "R01"})
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    # New save: re-stage the identical absolute target so final entity state is
    # value-equal to published. Final-value equality alone would look unchanged.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    assert _staged_entity_state(db) == _published_entity_state(db)

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage

    err_delete = _delete_error(db, token, "runs")
    assert "runs" in err_delete

    err_reconcile = _reconcile_error(
        db, token, u.request(u.resolution(run_id="R01"), released=[HERO])
    )
    assert "entity-state" in err_reconcile


def test_entity_state_staging_marker_does_not_leak_into_a_later_save(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    u.publish(db, token)
    u.confirm_mirror(db)

    # A later save must be free to reconcile: the prior save's operation fact is
    # bound to its own database-minted lock token.
    _published, _staging, token, _expires = u.begin_save(db)
    result = _reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))
    assert result["run_id"] == "R01"
