"""RT04 Proof Matrix 1, 8, 9, 10: happy path through the normal save spine,
continuing Run stays controller, zero-owner collapse, published-only visibility."""

import json

import pytest

from rt04_util import (
    CONFIRMED_RUNTIME,
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


def _expected_summary():
    return (
        "Resolution RP01 accepted: above_average objective result. "
        "Scenario objective: Rescue the missing courier. "
        "Hook objective: Locate the courier before nightfall."
    )


def _txn_reconcile(txn, token, req):
    with txn.cursor() as cur:
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(req)),
        )
        return cur.fetchone()[0]


def test_happy_path_reconciles_through_normal_save_gateway(db):
    _seed_runs(
        db,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    before = runtime_row(db)
    _published, _staging, token, _expires = begin_save(db)

    report = reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)
    confirm_mirror(db)

    assert report["resolution_id"] == "RP01"
    assert report["run_id"] == "R01"
    assert report["applied"]["outcome_summary"] == _expected_summary()
    assert report["applied"]["released_mutable_owners"] == []
    assert report["applied"]["run_state_after"]["control_state"] == "active"
    assert report["applied"]["run_state_after"]["mutable_owner_entity_ids"] == ["character:test-hero"]
    assert report["preserved_consequences"] == []

    assert runtime_row(db)["published_generation"] == before["published_generation"] + 1

    result = read_run(db, "R01")
    assert result["run"]["outcome_summary"] == _expected_summary()
    assert result["run"]["mutable_owner_entity_ids"] == ["character:test-hero"]
    assert result["run"]["control_state"] == "active"

    other = read_run(db, "R02")
    assert other["run"]["run_id"] == "R02"
    assert other["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]


def test_happy_path_becomes_visible_only_as_published_reality(db, txn):
    """Proof 1 + 10: staged-but-unpublished reconciliation is invisible to the
    supported reads; it becomes visible only after the gateway publish."""
    _seed_runs(db, [run("R01")])

    with txn.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        row = cur.fetchone()
        token = row[2]
    _txn_reconcile(txn, token, request(resolution("RP01", run_id="R01")))

    pre = read_run(db, "R01")
    assert pre["run"].get("outcome_summary") is None
    assert pre["run"]["control_state"] == "active"
    lookup = dm_read(db, "run_reconciliations")
    assert lookup["results"] == []
    assert runtime_row(db)["published_generation"] == 1

    with txn.cursor() as cur:
        cur.execute("select public.publish_campaign_save(%s)", (token,))
        cur.fetchone()
    txn.commit()

    post = read_run(db, "R01")
    assert post["run"]["outcome_summary"] == _expected_summary()
    assert runtime_row(db)["published_generation"] == 2
    ledger = dm_read(db, "run_reconciliations")
    assert ledger["results"] and ledger["results"][0]["key"] == "run_reconciliations"


def test_reconcile_uses_existing_mirror_publication_law(db):
    """Proof 1 + 7: publication runs through the normal RT01-C spine, including
    the mirror-pending window and confirmation."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)

    with db.cursor() as cur:
        cur.execute("select public.get_pending_runtime_mirror()")
        candidate = cur.fetchone()[0]
    if isinstance(candidate, str):
        candidate = json.loads(candidate)
    assert candidate["generation"] == 2
    assert candidate["state"]["runs"]
    assert candidate["state"]["run_reconciliations"]["RP01"]

    confirm_mirror(db)
    row = runtime_row(db)
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"] == CONFIRMED_RUNTIME


def test_continuing_run_remains_current_controller_after_sync(db):
    """Proof 8: releasing one owner does not end the Run; it continues as the
    current continuation lane for its remaining owner."""
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
    report = reconcile(
        db,
        token,
        request(resolution("RP01", run_id="R01"), released=["character:test-hero"]),
    )
    publish(db, token)
    confirm_mirror(db)

    assert report["applied"]["run_state_after"]["control_state"] == "active"
    assert report["applied"]["run_state_after"]["mutable_owner_entity_ids"] == [
        "character:test-sidekick"
    ]
    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "active"
    assert result["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]
    assert result["run"]["outcome_summary"] == _expected_summary()


def test_zero_owner_run_collapses_to_parked_without_stale_authority(db):
    """Proof 9: releasing the last mutable owner removes the Run's mutable
    authority (played -> parked) while preserving historical participation."""
    _seed_runs(
        db,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(
        db, token, request(resolution("RP01", run_id="R01"), released=["character:test-hero"])
    )
    publish(db, token)
    confirm_mirror(db)

    assert report["applied"]["run_state_after"]["control_state"] == "parked"
    assert report["applied"]["run_state_after"]["mutable_owner_entity_ids"] == []

    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "parked"
    assert result["run"]["mutable_owner_entity_ids"] == []
    assert result["run"]["participant_entity_ids"] == ["character:test-hero"]

    other = read_run(db, "R02")
    assert other["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]


def test_reconciliation_never_auto_terminates_a_continuing_run(db):
    """Proof 8: synchronization alone never changes a Run's control state when
    owners remain; only the explicit bounded release disposition does."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)
    confirm_mirror(db)

    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "active"
    assert result["run"]["mutable_owner_entity_ids"] == ["character:test-hero"]


def test_off_screen_run_keeps_not_applicable_control_state(db):
    _seed_runs(
        db,
        [
            run(
                "R01",
                execution_mode="off_screen",
                control_state="not_applicable",
                participant_entity_ids=["character:test-hero", "character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-hero", "character:test-sidekick"],
            )
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(
        db,
        token,
        request(
            resolution("RP01", run_id="R01"),
            released=["character:test-hero", "character:test-sidekick"],
        ),
    )
    publish(db, token)
    confirm_mirror(db)

    assert report["applied"]["run_state_after"]["control_state"] == "not_applicable"
    assert report["applied"]["run_state_after"]["mutable_owner_entity_ids"] == []
    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "not_applicable"
    assert result["run"]["mutable_owner_entity_ids"] == []


def test_preserved_consequences_are_reported_and_durable(db):
    """Proof 1: consequences without a legal durable surface are preserved in the
    consumption ledger and reported, never dropped and never invented into a new
    subsystem."""
    proposal = resolution(
        "RP01",
        run_id="R01",
        consequences=[
            {
                "consequence_id": "PC01",
                "scope": "run_objective",
                "kind": "objective_result",
                "summary": "Apply the above average result.",
                "related_entity_ids": [],
                "location_ids": [],
            },
            {
                "consequence_id": "PC02",
                "scope": "participant",
                "kind": "injury",
                "summary": "The hero is hurt.",
                "related_entity_ids": ["character:test-hero"],
                "location_ids": [],
            },
            {
                "consequence_id": "PC03",
                "scope": "location",
                "kind": "world_change",
                "summary": "The tavern changes.",
                "related_entity_ids": [],
                "location_ids": ["location:tavern"],
            },
        ],
    )
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(db, token, request(proposal))
    publish(db, token)
    confirm_mirror(db)

    preserved = report["preserved_consequences"]
    by_id = {p["consequence_id"]: p for p in preserved}
    assert set(by_id) == {"PC02", "PC03"}
    # REPAIR Finding C: the validated human-readable summary is preserved with
    # each unsupported consequence, so consuming the resolution can never lose
    # the meaning of what happened.
    assert by_id["PC02"]["summary"] == "The hero is hurt."
    assert by_id["PC03"]["summary"] == "The tavern changes."
    assert by_id["PC02"]["missing_downstream_owner"] == (
        "no legal durable entity-state mutation surface exists yet"
    )
    assert by_id["PC03"]["missing_downstream_owner"] == (
        "no legal durable location-state mutation surface exists yet"
    )

    with db.cursor() as cur:
        cur.execute(
            "select value from public.campaign_state_generations csg "
            "join public.campaign_runtime cr on cr.id = 1 "
            "and csg.generation = cr.published_generation "
            "and csg.key = 'run_reconciliations'"
        )
        ledger = cur.fetchone()[0]
    marker = ledger["RP01"]
    assert {p["consequence_id"] for p in marker["preserved_consequences"]} == {"PC02", "PC03"}
    # The durable receipt preserves the exact validated summaries too.
    assert {p["summary"] for p in marker["preserved_consequences"]} == {
        "The hero is hurt.",
        "The tavern changes.",
    }
    assert marker["run_id"] == "R01"


def test_service_role_can_reconcile(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(db, token, request(resolution("RP01", run_id="R01")), as_service_role=True)
    assert report["resolution_id"] == "RP01"
    publish(db, token)
    confirm_mirror(db)
    assert read_run(db, "R01")["run"]["outcome_summary"] == _expected_summary()


def test_outcome_summary_is_deterministic_and_does_not_invent_facts(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    report = reconcile(db, token, request(resolution("RP01", run_id="R01")))
    assert report["applied"]["outcome_summary"] == _expected_summary()
    assert "Resolution RP01 accepted" in report["applied"]["outcome_summary"]
    assert "Rescue the missing courier." in report["applied"]["outcome_summary"]


def test_other_staged_run_work_is_preserved_by_reconciliation(db):
    """The bounded translation only rewrites the source Run record; unrelated
    staged edits to the runs batch survive the reconcile."""
    _seed_runs(
        db,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    r02 = run(
        "R02",
        participant_entity_ids=["character:test-sidekick"],
        mutable_owner_entity_ids=["character:test-sidekick"],
        outcome_summary="DM note about R02.",
    )
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, 'runs', %s::jsonb)",
            (token, json.dumps([run("R01"), r02])),
        )
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    with db.cursor() as cur:
        cur.execute(
            "select value from public.campaign_state_generations "
            "where generation = (select staging_generation from public.campaign_runtime where id = 1) "
            "and key = 'runs'"
        )
        staged_runs = cur.fetchone()[0]
    by_id = {r["run_id"]: r for r in staged_runs}
    assert by_id["R01"]["outcome_summary"] == _expected_summary()
    assert by_id["R02"]["outcome_summary"] == "DM note about R02."


def test_reconcile_keeps_mirror_confirmation_required(db):
    """The reconciliation reuse of the normal spine keeps the RT01-C mirror
    handshake mandatory: a freshly published generation is mirror-pending and
    blocks the next save until confirmed."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(resolution("RP01", run_id="R01")))
    publish(db, token)
    assert runtime_row(db)["runtime_published_confirmed"] is False
    with pytest.raises(Exception, match="pending runtime-published mirror"):
        begin_save(db)
    confirm_mirror(db)
    assert runtime_row(db)["runtime_published_confirmed"] is True