"""EV2-13.1 timed applied-status instance proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 + EV2-10 + EV2-11 + EV2-12.1 + EV2-13 + EV2-13.420 spine plus the
forward-only EV2-13.1 migration. All durable mutation goes through the real
save/publication/mirror-confirmation spine; nothing is mocked. No real RHC
status is published: every application is synthetic.

Proof Matrix coverage:
  * a valid application anchors from authoritative published RT02 elapsed
    minutes, never caller-supplied time;
  * missing/Unknown Clock truth fails closed rather than assuming elapsed 0;
  * application identity is unique and replay/idempotency cannot duplicate;
  * status_effect definition and live application stay separate and no
    definition identity is minted or mutated;
  * the target is restricted to the existing mutable-actor identity space;
  * thresholds are normalized through EV2-13.420 and no duplicate time
    arithmetic is introduced;
  * acknowledgement and end anchors are engine-derived from published elapsed
    time, never caller input;
  * the timing definition is immutable after application;
  * generic SAVE stage/delete cannot bypass the validated route and legacy
    live_status stays separate;
  * the route/read are service_role-only;
  * abort leaves no staging residue and replay converges;
  * publication keeps generation/Git ref/mirror/confirmation valid;
  * the runtime workflow actually executes tests/ev2131;
  * the migration installs and behaves on PostgreSQL 15 and 17.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ev2131"))
import ev2131_util as s  # noqa: E402


# ---------------------------------------------------------------------------
# Happy path + anchoring
# ---------------------------------------------------------------------------

def test_application_anchors_from_published_clock_not_caller(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=1000))
    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(
        db, token,
        s.request(definition_obj=s.definition(thresholds=[s.threshold("T1", 10, "minute")])),
    )
    assert result["application_id"] == s.APPLICATION
    assert result["controller"] == {"kind": "mainrun"}
    record = result["application"]
    assert record["applied_at_elapsed_minutes"] == 1000
    assert record["thresholds"] == [
        {"threshold_id": "T1", "due_at_elapsed_minutes": 1010}
    ]

    s.publish(db, token)
    s.confirm_mirror(db)

    read = s.read_status(db)
    assert read["application"]["age_elapsed_minutes"] == 0
    assert read["due_thresholds"] == []
    assert read["pending_thresholds"] == [
        {
            "threshold_id": "T1",
            "due_at_elapsed_minutes": 1010,
            "remaining_elapsed_minutes": 10,
        }
    ]


def test_run_owned_target_mutation_publishes_through_spine(db):
    s.publish_confirmed_runs(
        db, [s.run(run_id="R01", mutable_owner_entity_ids=[s.HERO])]
    )
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=500))

    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(
        db, token,
        s.request(
            controller={"kind": "run", "run_id": "R01"},
            definition_obj=s.definition(thresholds=[s.threshold("T1", 1, "hour")]),
        ),
    )
    assert result["controller"] == {"kind": "run", "run_id": "R01"}
    assert result["application"]["applied_at_elapsed_minutes"] == 500
    assert result["application"]["thresholds"][0]["due_at_elapsed_minutes"] == 560

    s.publish(db, token)
    s.confirm_mirror(db)
    assert len(s.published_applied_statuses(db)) == 1


def test_missing_clock_fails_closed_not_zero(db):
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(
        db, token, s.request(definition_obj=s.definition())
    )
    assert "campaign_clock is unavailable" in err
    assert "defaults to zero" in err
    err_read = s.read_status_error(db)
    assert "campaign_clock" in err_read


def test_unknown_clock_is_still_a_known_elapsed_cursor(db):
    # A published Clock that is Unknown in presentation (day null/phase unknown)
    # still carries a known monotonic elapsed cursor; the anchor uses it and
    # never fabricates a day/date.
    _published, _staging, token, _expires = s.begin_save(db)
    s.publish_clock(db, token, s.clock(elapsed_campaign_minutes=42))
    s.confirm_mirror(db)

    _published, _staging, token, _expires = s.begin_save(db)
    result = s.mutate(db, token, s.request(definition_obj=s.definition()))
    assert result["application"]["applied_at_elapsed_minutes"] == 42
    assert result["application"]["source_entity_id"] is None


# ---------------------------------------------------------------------------
# Identity, replay, separation
# ---------------------------------------------------------------------------

def test_application_identity_unique_and_replay_safe(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    request = s.request(definition_obj=s.definition())

    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, request)
    s.mutate(db, token, request)
    s.publish(db, token)
    s.confirm_mirror(db)
    assert len(s.published_applied_statuses(db)) == 1

    # Replaying the same absolute create in a later save converges, no duplicate.
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, request)
    s.publish(db, token)
    s.confirm_mirror(db)
    assert len(s.published_applied_statuses(db)) == 1


def test_definition_and_live_application_remain_separate(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    s.publish(db, token)
    s.confirm_mirror(db)

    published = s.published_state(db)
    # The runtime references the definition identity; it never mints a
    # definition record/key for it.
    assert s.DEFINITION not in published
    record = published["applied_statuses"][0]
    assert record["definition_id"] == s.DEFINITION
    # No entity/state namespace was touched.
    assert "entity_state" not in published
    assert "status_effect" not in published


def test_multiple_applications_keep_exactly_one_record_each(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(application_id="AS01", definition_obj=s.definition()))
    s.mutate(db, token, s.request(application_id="AS02", definition_obj=s.definition()))
    s.publish(db, token)
    s.confirm_mirror(db)

    ids = sorted(r["application_id"] for r in s.published_applied_statuses(db))
    assert ids == ["AS01", "AS02"]


def test_abort_discards_unpublished_application(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    s.abort_save(db, token)
    assert s.published_applied_statuses(db) == []


# ---------------------------------------------------------------------------
# Bounded validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "target",
    ["party:test-stash", "item:test-blade", "location:test-town",
     "status_effect:test-chill", "character:", "character:Bad Slug", 123, None],
)
def test_target_must_be_a_mutable_actor(db, target):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(
        db, token, s.request(definition_obj=s.definition(target=target))
    )
    assert "target_entity_id" in err or "target" in err


@pytest.mark.parametrize(
    "definition_id",
    ["character:test-hero", "status-effect:test-chill", "status_effect:", "nope", 5],
)
def test_definition_must_be_a_status_effect_identity(db, definition_id):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(
        db, token, s.request(definition_obj=s.definition(definition_id=definition_id))
    )
    assert "definition_id" in err


def test_thresholds_must_be_present_and_unique(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)

    err_empty = s.mutate_error(
        db, token, s.request(definition_obj=s.definition(thresholds=[]))
    )
    assert "at least one" in err_empty

    duplicate = [s.threshold("T1", 5, "minute"), s.threshold("T1", 9, "minute")]
    err_dup = s.mutate_error(
        db, token, s.request(definition_obj=s.definition(thresholds=duplicate))
    )
    assert "unique" in err_dup


def test_threshold_durations_normalized_through_ev213420(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=1000))
    _published, _staging, token, _expires = s.begin_save(db)

    # 10 rounds == 1 minute exactly; 2 hours == 120 minutes.
    result = s.mutate(
        db, token,
        s.request(definition_obj=s.definition(thresholds=[
            s.threshold("T1", 10, "round"),
            s.threshold("T2", 2, "hour"),
        ])),
    )
    due = {t["threshold_id"]: t["due_at_elapsed_minutes"]
           for t in result["application"]["thresholds"]}
    assert due == {"T1": 1001, "T2": 1120}

    # A sub-minute duration (1 round = six seconds) fails closed; turn is never
    # an additive duration unit.
    for amount, unit, needle in ((1, "round", "whole number of minute"),
                                 (1, "turn", "elapsed-duration"),
                                 (1.5, "minute", "whole number")):
        err = s.mutate_error(
            db, token,
            s.request(definition_obj=s.definition(thresholds=[
                s.threshold("T1", amount, unit)
            ])),
        )
        assert needle in err


def test_threshold_anchor_beyond_rt02_range_fails_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=2000000000))
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(
        db, token,
        s.request(definition_obj=s.definition(thresholds=[
            s.threshold("T1", 200000000, "minute")
        ])),
    )
    assert "exceeds the RT02" in err


def test_applied_at_cannot_be_forged_by_caller(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    request = s.request(definition_obj=s.definition())
    request["applied_at_elapsed_minutes"] = 5
    err = s.mutate_error(db, token, request)
    assert "outside the EV2-13.1 contract" in err


def test_acknowledgement_anchor_cannot_be_forged_by_caller(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    request = s.request(acknowledge=["T1"])
    request["acknowledged_at_elapsed_minutes"] = 7
    err = s.mutate_error(db, token, request)
    assert "outside the EV2-13.1 contract" in err


def test_future_threshold_cannot_be_pre_acknowledged(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    err = s.mutate_error(db, token, s.request(acknowledge=["T1"]))
    assert "not yet due" in err


def test_unknown_acknowledge_threshold_fails_closed(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    err = s.mutate_error(db, token, s.request(acknowledge=["NOPE"]))
    assert "unknown threshold" in err


def test_definition_is_immutable_after_application(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))

    err = s.mutate_error(
        db, token,
        s.request(definition_obj=s.definition(thresholds=[s.threshold("T1", 99, "minute")])),
    )
    assert "immutable" in err


def test_source_optional_and_unknown_stays_unknown(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    omitted = s.mutate(db, token, s.request(definition_obj=s.definition()))
    assert omitted["application"]["source_entity_id"] is None

    supplied = s.mutate(
        db, token,
        s.request(application_id="AS02",
                  definition_obj=s.definition(source="ability:test-spark")),
    )
    assert supplied["application"]["source_entity_id"] == "ability:test-spark"

    err = s.mutate_error(
        db, token,
        s.request(application_id="AS03", definition_obj=s.definition(source="bad source")),
    )
    assert "source_entity_id" in err


@pytest.mark.parametrize(
    "controller",
    [None, "mainrun", {}, {"kind": None}, {"kind": 1}, {"kind": "MAINRUN"},
     {"kind": "run"}, {"kind": "run", "run_id": "R1"},
     {"kind": "run", "run_id": "R01", "extra": 1}, {"kind": "mainrun", "extra": 1}],
)
def test_controller_shape_is_bounded(db, controller):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    request = {"application_id": s.APPLICATION, "controller": controller,
               "definition": s.definition()}
    err = s.mutate_error(db, token, request)
    assert "controller" in err.lower()


def test_mutation_requires_an_active_campaign_save(db):
    err = s.mutate_error(db, "not-a-real-token", s.request(definition_obj=s.definition()))
    assert "lock" in err.lower()


def test_new_application_requires_definition(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    err = s.mutate_error(db, token, s.request())
    assert "requires a definition" in err


# ---------------------------------------------------------------------------
# Bypass closure + separation of legacy live_status
# ---------------------------------------------------------------------------

def test_generic_save_cannot_write_or_delete_applied_statuses(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)

    err_stage = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, "applied_statuses", json.dumps([s.definition()])),
        ),
    )
    assert "mutate_applied_status" in err_stage

    err_delete = s.error_as_role(
        db, "service_role",
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)",
            (token, "applied_statuses"),
        ),
    )
    assert "applied_statuses" in err_delete


def test_legacy_live_status_stays_separate(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    s.publish_confirmed_state(
        db,
        {"live_status": {"persistent_effects": [{"definition_id": s.DEFINITION}]}},
    )
    read = s.read_status(db)
    assert read["application"] is None
    assert s.published_applied_statuses(db) == []
    assert s.published_state(db)["live_status"] is not None


def test_route_and_read_are_service_role_only(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    for role in ("anon", "authenticated"):
        err_mutate = s.error_as_role(
            db, role,
            lambda cur: cur.execute(
                "select public.mutate_applied_status(%s, %s::jsonb)",
                (token, json.dumps(s.request(definition_obj=s.definition()))),
            ),
        )
        assert "permission denied" in err_mutate.lower()
        err_read = s.error_as_role(
            db, role,
            lambda cur: cur.execute(
                "select public.read_timed_applied_status(%s)", (s.APPLICATION,)
            ),
        )
        assert "permission denied" in err_read.lower()


# ---------------------------------------------------------------------------
# Publication integrity + workflow actually runs this suite
# ---------------------------------------------------------------------------

def test_publication_keeps_generation_git_ref_mirror_and_confirmation_valid(db):
    s.publish_confirmed_clock(db, s.clock(elapsed_campaign_minutes=100))
    _published, _staging, token, _expires = s.begin_save(db)
    s.mutate(db, token, s.request(definition_obj=s.definition()))
    s.publish(db, token)
    s.confirm_mirror(db)

    row = s.runtime_row(db)
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"]
    assert row["last_confirmed_generation"] == row["published_generation"]
    assert row["last_confirmed_git_ref"] == row["published_git_ref"]
    assert row["save_in_progress"] is False


def test_runtime_workflow_executes_ev2131(db):
    workflow = (ROOT / ".github" / "workflows" / "rt01-runtime.yml").read_text(
        encoding="utf-8"
    )
    assert "tests/ev2131" in workflow
    # It must be part of the pytest invocation, not merely a path filter.
    invocation = workflow.split("pytest", 1)[1]
    assert "tests/ev2131" in invocation


def test_migration_installs_and_behaves_on_postgres_17(db_pg17):
    assert s.scalar(
        db_pg17, "select current_setting('server_version_num')::int"
    ) >= 170000
    s.publish_confirmed_clock(db_pg17, s.clock(elapsed_campaign_minutes=777))
    _published, _staging, token, _expires = s.begin_save(db_pg17)
    result = s.mutate(db_pg17, token, s.request(definition_obj=s.definition()))
    assert result["application"]["applied_at_elapsed_minutes"] == 777
    s.publish(db_pg17, token)
    s.confirm_mirror(db_pg17)
    assert len(s.published_applied_statuses(db_pg17)) == 1
