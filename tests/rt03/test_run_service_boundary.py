"""RT03 service read boundary + parked truth / read-only guarantee (Proof Matrix F, G)."""

import psycopg2
import pytest

from rt03_util import (
    begin_save,
    clock_value,
    published_state,
    publish,
    read_run,
    run,
    runtime_row,
    stage_clock,
    stage_runs,
)


def establish_runs_with_clock(db, runs):
    _published, _staging, token, _expires = begin_save(db)
    stage_clock(db, token, clock_value(day=4, phase="night", elapsed_campaign_minutes=90))
    stage_runs(db, token, runs)
    publish(db, token)


def test_service_role_can_perform_the_supported_run_read(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01")])
    publish(db, token)

    result = read_run(db, "R01", as_service_role=True)
    assert result["run"]["run_id"] == "R01"
    assert result["runtime"]["generation"] == 1


def test_service_role_can_read_truthful_absence_with_metadata(db):
    result = read_run(db, "R01", as_service_role=True)
    assert result["run"] is None
    assert result["runtime"]["generation"] == 0


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_client_roles_cannot_execute_the_run_read(db, role):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select public.dm_runtime_read_run('R01')")
        finally:
            cur.execute("reset role")


def test_service_role_does_not_regain_raw_generation_select(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select * from public.campaign_state_generations")
        finally:
            cur.execute("reset role")


def test_internal_run_validator_is_not_service_executable(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select public._rhc_validate_run_record('{\"run_id\": \"R01\"}'::jsonb)")
        finally:
            cur.execute("reset role")


def test_parked_run_is_returned_truthfully_without_promotion(db):
    parked = run("R01", control_state="parked", mutable_owner_entity_ids=[])
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [parked])
    publish(db, token)

    result = read_run(db, "R01")
    assert result["run"]["control_state"] == "parked"
    assert result["run"]["mutable_owner_entity_ids"] == []


def test_run_read_is_read_only_over_the_entire_runtime(db):
    establish_runs_with_clock(
        db, [run("R01", control_state="parked", mutable_owner_entity_ids=[])]
    )
    before_state = published_state(db)
    before_runtime = runtime_row(db)

    for _ in range(3):
        read_run(db, "R01")
    read_run(db, "R99")

    assert published_state(db) == before_state
    assert runtime_row(db) == before_runtime


def test_run_read_performs_no_clock_mutation(db):
    establish_runs_with_clock(db, [run("R01")])
    before = published_state(db)["campaign_clock"]

    read_run(db, "R01")

    assert published_state(db)["campaign_clock"] == before


def test_run_read_does_not_advance_the_published_generation(db):
    establish_runs_with_clock(db, [run("R01")])
    before = runtime_row(db)

    read_run(db, "R01")

    after = runtime_row(db)
    assert after["published_generation"] == before["published_generation"]
    assert after["runtime_published_confirmed"] == before["runtime_published_confirmed"]
