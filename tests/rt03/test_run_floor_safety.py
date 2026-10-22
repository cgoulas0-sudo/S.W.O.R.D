"""RT03 no-initialization + Clock/time non-expansion (Proof Matrix H, I)."""

from rt03_util import clock_value, read_run, runtime_row


def test_fresh_unknown_runtime_creates_no_run_record(db):
    result = read_run(db, "R01")
    assert result["run"] is None
    assert result["runtime"]["generation"] == 0
    assert result["runtime"]["day"] is None


def test_fresh_runtime_stays_empty_after_run_reads(db):
    read_run(db, "R01")
    read_run(db, "R99")

    row = runtime_row(db)
    assert row["published_day"] is None
    assert row["published_generation"] == 0
    with db.cursor() as cur:
        cur.execute("select count(*) from public.campaign_state_generations")
        assert cur.fetchone()[0] == 0


def test_read_does_not_seed_campaign_time(db):
    read_run(db, "R01")

    row = runtime_row(db)
    assert row["published_day"] is None
    with db.cursor() as cur:
        cur.execute(
            "select count(*) from public.campaign_state_generations where key = 'campaign_clock'"
        )
        assert cur.fetchone()[0] == 0


def test_anchor_campaign_time_is_returned_opaquely_without_clock_comparison(db):
    from rt03_util import begin_save, publish, stage_clock, stage_runs

    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock_value(day=7, phase="morning", elapsed_campaign_minutes=30))
    stage_runs(
        db,
        token,
        [
            {
                "run_id": "R01",
                "execution_mode": "played",
                "control_state": "parked",
                "scenario_id": "S01",
                "occurred_encounter_ids": [],
                "participant_entity_ids": ["character:test-hero"],
                "mutable_owner_entity_ids": [],
                "location_ids": [],
                "campaign_anchor": {
                    "base_commit": "cccccccccccccccccccccccccccccccccccccccc",
                    "campaign_time": "Day 3, late_night",
                },
            }
        ],
    )
    publish(db, token)

    result = read_run(db, "R01")
    assert result["run"]["campaign_anchor"]["campaign_time"] == "Day 3, late_night"
    # The RT02 Clock day is returned as runtime metadata only; RT03 performs no
    # arithmetic between the anchor label and the Clock.
    assert result["runtime"]["day"] == 7
