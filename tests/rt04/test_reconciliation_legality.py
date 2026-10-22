"""RT04 Proof Matrix 2, 3, 4, 8: stale source authority, overlapping/newer
mutable owner, malformed/wrong lineage, and ownership legality all fail closed."""

from copy import deepcopy

import psycopg2
import pytest

from rt04_util import (
    RUN_ANCHOR,
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
)


def _seed_runs(db, runs):
    return publish_confirmed_runs(db, runs)


def _expect(db, token, req, message):
    with pytest.raises(psycopg2.errors.RaiseException, match=message):
        reconcile(db, token, req)


def _nothing_staged(db):
    """REPAIR Finding B proof 6: a failed candidate staged nothing anywhere."""
    with db.cursor() as cur:
        cur.execute(
            "select count(*) from public.campaign_state_generations where key = 'run_reconciliations'"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("select published_generation from public.campaign_runtime where id = 1")
        assert cur.fetchone()[0] == 1


def _proposal(**overrides):
    record = resolution("RP01", run_id="R01")
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# Stale source Run authority
# ---------------------------------------------------------------------------

def test_stale_source_run_removed_from_published_reality_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _seed_runs(db, [])  # R01 no longer exists in published reality

    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(_proposal()), "does not exist in published reality")


def test_unknown_run_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(_proposal(run_id="R99")), "does not exist in published reality")


def test_run_no_longer_owns_target_entity_fails_closed(db):
    """Proof 3/8: the Run still exists but no longer holds mutable control of the
    entity its accepted consequence targets -> stale authority fails closed."""
    released_run = run(
        "R01",
        participant_entity_ids=["character:test-hero"],
        mutable_owner_entity_ids=[],
        control_state="parked",
    )
    _seed_runs(db, [released_run])

    proposal = resolution(
        "RP01",
        run_id="R01",
        consequences=[
            {
                "consequence_id": "PC01",
                "scope": "participant",
                "kind": "injury",
                "summary": "The hero is hurt.",
                "related_entity_ids": ["character:test-hero"],
                "location_ids": [],
            }
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "no longer controls")


def test_overlapping_newer_mutable_owner_fails_closed(db):
    """Proof 3: another Run now claims one of this Run's mutable owners; the
    authoritative RT03 read refuses either claimant, so reconciliation fails
    closed before any write."""
    _seed_runs(
        db,
        [
            run("R01", outcome_summary="R01 currently owns the hero"),
            run("R02", participant_entity_ids=["character:test-hero"],
                mutable_owner_entity_ids=["character:test-hero"]),
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(_proposal()), "claimed by both R01 and R02")


def test_releasing_owner_the_run_does_not_own_fails_closed(db):
    _seed_runs(
        db,
        [
            run(
                "R01",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            )
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(
        db, token,
        request(_proposal(), released=["character:test-hero"]),
        "does not own released mutable entity",
    )


def test_released_owner_with_duplicate_entries_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(
        db, token,
        request(_proposal(), released=["character:test-hero", "character:test-hero"]),
        "must not contain duplicate entries",
    )


# ---------------------------------------------------------------------------
# REPAIR Finding B: candidate-wide Run ownership validation
# ---------------------------------------------------------------------------

def test_staged_run_claiming_source_owned_entity_fails_closed(db):
    """REPAIR Finding B proof 1: published R01 owns the hero; the active save's
    staged candidate also contains R02 claiming the hero. Reconciling R01 must
    fail closed on the contradictory candidate instead of publishing two Runs
    that own the same mutable entity."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-hero"],
                mutable_owner_entity_ids=["character:test-hero"],
            ),
        ],
    )
    _expect(db, token, request(_proposal()), "candidate Run ownership is contradictory")
    _nothing_staged(db)


def test_released_owner_cannot_become_staged_transfer(db):
    """REPAIR Finding B proof 2: releasing the hero while a staged sibling
    already claims the hero must fail closed — released_mutable_owners is
    subtractive-only and a pre-staged claim is never honored as an
    R01 -> R02 ownership transfer."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-hero"],
                mutable_owner_entity_ids=["character:test-hero"],
            ),
        ],
    )
    _expect(
        db,
        token,
        request(_proposal(), released=["character:test-hero"]),
        "released_mutable_owners cannot transfer ownership",
    )
    _nothing_staged(db)


def test_two_staged_runs_claiming_same_entity_fail_closed(db):
    """REPAIR Finding B proof 3: two non-source staged Runs claiming the same
    mutable entity cannot survive candidate validation while the source Run is
    reconciled."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["creature:test-goblin"],
                mutable_owner_entity_ids=["creature:test-goblin"],
            ),
            run(
                "R03",
                scenario_id="S02",
                participant_entity_ids=["creature:test-goblin"],
                mutable_owner_entity_ids=["creature:test-goblin"],
            ),
        ],
    )
    _expect(
        db,
        token,
        request(_proposal()),
        "mutable entity creature:test-goblin is claimed by more than one Run",
    )
    _nothing_staged(db)


def test_valid_distinct_ownership_across_staged_runs_remains_accepted(db):
    """REPAIR Finding B proof 4: globally disjoint ownership across the source
    Run and staged sibling Runs is valid and reconciles normally."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(
        db,
        token,
        [
            run("R01"),
            run(
                "R02",
                participant_entity_ids=["character:test-sidekick"],
                mutable_owner_entity_ids=["character:test-sidekick"],
            ),
            run(
                "R03",
                scenario_id="S02",
                participant_entity_ids=["creature:test-goblin"],
                mutable_owner_entity_ids=["creature:test-goblin"],
            ),
        ],
    )
    report = reconcile(db, token, request(_proposal()))
    assert report["resolution_id"] == "RP01"
    publish(db, token)
    confirm_mirror(db)
    assert read_run(db, "R01")["run"]["outcome_summary"].startswith("Resolution RP01 accepted")
    assert read_run(db, "R02")["run"]["mutable_owner_entity_ids"] == ["character:test-sidekick"]
    assert read_run(db, "R03")["run"]["mutable_owner_entity_ids"] == ["creature:test-goblin"]


def test_generic_runs_mutation_after_reconciliation_fails_closed(db):
    """REPAIR Finding B proof 5: the current call ordering DOES allow a generic
    same-save `runs` mutation after reconciliation (publish_campaign_save
    validates nothing), so RT04 closes the candidate: after a reconciliation is
    staged, stage/delete of the runs key fail closed, other keys stay generic,
    and the validated candidate still publishes coherently."""
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(_proposal()))

    with pytest.raises(
        psycopg2.errors.RaiseException, match="runs batch is engine-owned for the rest of this save"
    ):
        stage_runs(db, token, [run("R01", mutable_owner_entity_ids=["character:test-hero"])])
    with pytest.raises(
        psycopg2.errors.RaiseException, match="runs batch is engine-owned for the rest of this save"
    ):
        with db.cursor() as cur:
            cur.execute("select public.delete_staged_campaign_state(%s, 'runs')", (token,))
            cur.fetchone()

    # Other keys remain ordinary generic staging; nothing else is blocked.
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_state(%s, 'daily_recap', '\"ok\"'::jsonb)", (token,)
        )

    publish(db, token)
    confirm_mirror(db)
    with db.cursor() as cur:
        cur.execute(
            "select value from public.campaign_state_generations csg "
            "join public.campaign_runtime cr on cr.id = 1 "
            "and csg.generation = cr.published_generation and csg.key = 'runs'"
        )
        published_runs = cur.fetchone()[0]
    by_id = {r["run_id"]: r for r in published_runs}
    assert "Resolution RP01 accepted" in by_id["R01"]["outcome_summary"]


# ---------------------------------------------------------------------------
# Malformed / wrong lineage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update({"resolution_id": "RP1"}), "resolution_id must be RP"),
        (lambda p: p.update({"run_id": "R1"}), "run_id must be R"),
        (lambda p: p.update({"scenario_id": "S99"}), "does not match the source Run scenario"),
        (lambda p: p.update({"primary_hook_id": "x"}), "primary_hook_id must be H"),
        (lambda p: p.update({"campaign_anchor": {"base_commit": "f" * 40, "campaign_time": "Day 1"}}),
         "does not exactly match the source Run campaign_anchor"),
        (lambda p: p.update({"primary_roll": 2, "outcome_band": "normal"}), "outcome_band must be bad"),
        (lambda p: p.pop("proposed_consequences"), "missing a required EV2-09A field"),
        (lambda p: p.update({"severity_roll": 2, "severity_band": "minor"}),
         "severity is forbidden"),
        (lambda p: p.update({"invented": True}), "fields outside the EV2-09A contract"),
    ],
)
def test_malformed_or_wrong_lineage_fails_closed(db, mutate, message):
    _seed_runs(db, [run("R01")])
    proposal = _proposal()
    mutate(proposal)
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), message)


def test_primary_one_requires_severity_fails_closed(db):
    _seed_runs(db, [run("R01")])
    proposal = _proposal(primary_roll=1, outcome_band="critical_trigger")
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "primary_roll 1 requires severity_roll")


def test_severity_band_mismatch_fails_closed(db):
    _seed_runs(db, [run("R01")])
    proposal = _proposal(
        primary_roll=1,
        outcome_band="critical_trigger",
        severity_roll=6,
        severity_band="serious",
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "severity_band must be catastrophic")


def test_duplicate_consequence_ids_fail_closed(db):
    _seed_runs(db, [run("R01")])
    c = resolution("RP01", run_id="R01")["proposed_consequences"][0]
    proposal = resolution("RP01", run_id="R01", consequences=[c, deepcopy(c)])
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "duplicate consequence_id")


def test_death_consequence_kind_is_rejected(db):
    _seed_runs(db, [run("R01")])
    proposal = resolution(
        "RP01",
        run_id="R01",
        consequences=[
            {
                "consequence_id": "PC01",
                "scope": "participant",
                "kind": "death",
                "summary": "automatic death is not part of the vocabulary",
                "related_entity_ids": ["character:test-hero"],
                "location_ids": [],
            }
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "consequence kind is outside the EV2-09A vocabulary")


def test_consequence_outside_bounded_scope_references_fail_closed(db):
    _seed_runs(db, [run("R01")])
    proposal = resolution(
        "RP01",
        run_id="R01",
        consequences=[
            {
                "consequence_id": "PC01",
                "scope": "related_entity",
                "kind": "discovery",
                "summary": "malformed target identity",
                "related_entity_ids": ["item:Not-A-Slug"],
                "location_ids": [],
            }
        ],
    )
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "related_entity_ids contains an entry outside")


def test_empty_consequence_batch_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(
        db, token,
        request(resolution("RP01", run_id="R01", consequences=[])),
        "non-empty array",
    )


def test_request_with_extra_fields_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    req = request(_proposal())
    req["invented"] = True
    _expect(db, token, req, "fields outside the RT04 contract")


def test_request_missing_resolution_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, {"released_mutable_owners": []}, "requires a resolution proposal")


def test_null_request_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, None, "reconciliation request must be a JSON object")


def test_campaign_anchor_commit_must_be_exact_hex(db):
    _seed_runs(db, [run("R01")])
    proposal = _proposal()
    proposal["campaign_anchor"]["base_commit"] = "f" * 39
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "must be an exact 40-character lowercase hex commit")


def test_proposal_scenario_must_match_published_run_scenario(db):
    _seed_runs(db, [run("R01", scenario_id="S02")])
    proposal = _proposal()
    proposal["scenario_id"] = "S01"
    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(proposal), "does not match the source Run scenario")


def test_malformed_released_owner_identity_fails_closed(db):
    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    _expect(
        db, token,
        request(_proposal(), released=["character:UPPERCASE"]),
        "released_mutable_owners contains an entry outside",
    )


def test_published_ledger_is_engine_authoritative_and_rejects_corruption(db):
    """Proof 6: a malformed engine-owned ledger in published reality fails the
    reconciliation closed rather than trusting a broken consumption proof."""
    from rt04_util import break_glass, confirm_mirror

    _seed_runs(db, [run("R01")])
    _published, _staging, token, _expires = begin_save(db)
    reconcile(db, token, request(_proposal(resolution_id="RP00")))
    publish(db, token)
    confirm_mirror(db)

    break_glass(
        db,
        "update public.campaign_state_generations "
        "set value = '\"not-an-object\"'::jsonb "
        "where key = 'run_reconciliations' "
        "and generation = (select published_generation from public.campaign_runtime where id = 1)",
    )

    _published, _staging, token, _expires = begin_save(db)
    _expect(db, token, request(_proposal()), "published run_reconciliations ledger is unreadable")