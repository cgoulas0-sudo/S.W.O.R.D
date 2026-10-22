"""RT03 published-only boundary + one-generation coherence (Proof Matrix D, E)."""

from rt03_util import (
    abort_save,
    begin_save,
    confirm_mirror,
    publish,
    read_run,
    run,
    stage_runs,
)


def test_staged_only_run_is_invisible(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01")])

    result = read_run(db, "R01")
    assert result["run"] is None
    assert result["runtime"]["generation"] == 0


def test_published_run_a_stays_visible_while_staged_run_b_waits_with_same_id(db):
    published_record = run("R01", outcome_summary="published branch")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [published_record])
    publish(db, token)
    confirm_mirror(db)

    _published, _staging, next_token, _expires = begin_save(db)
    stage_runs(db, next_token, [run("R01", outcome_summary="future branch")])

    result = read_run(db, "R01")
    assert result["run"] == published_record
    assert result["runtime"]["generation"] == 1


def test_aborted_candidate_changes_do_not_affect_output(db):
    published_record = run("R01")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [published_record])
    publish(db, token)
    confirm_mirror(db)

    _published, _staging, next_token, _expires = begin_save(db)
    stage_runs(db, next_token, [run("R01", outcome_summary="temporary edit")])
    abort_save(db, next_token)

    result = read_run(db, "R01")
    assert result["run"] == published_record
    assert result["runtime"]["generation"] == 1


def test_run_and_metadata_come_from_one_published_snapshot(db):
    record = run("R01")
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [record])
    publish(db, token)

    result = read_run(db, "R01")
    assert result["runtime"]["generation"] == 1
    assert result["run"] == record


def test_next_publication_reflects_new_run_and_metadata_together(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01", outcome_summary="version 1")])
    publish(db, token)
    confirm_mirror(db)

    before = read_run(db, "R01")
    assert before["runtime"]["generation"] == 1
    assert before["run"]["outcome_summary"] == "version 1"

    _published, _staging, next_token, _expires = begin_save(db)
    stage_runs(db, next_token, [run("R01", outcome_summary="version 2")])
    publish(db, next_token)

    after = read_run(db, "R01")
    assert after["runtime"]["generation"] == 2
    assert after["run"]["outcome_summary"] == "version 2"


def test_confirmed_git_metadata_never_proves_a_newer_mirror_pending_generation(db):
    from rt03_util import CONFIRMED_RUNTIME

    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01", outcome_summary="version 1")])
    publish(db, token)
    confirm_mirror(db)

    confirmed = read_run(db, "R01")
    assert confirmed["runtime"]["fallback_freshness"] == "current"
    assert confirmed["runtime"]["git_ref"] == CONFIRMED_RUNTIME

    _published, _staging, next_token, _expires = begin_save(db)
    stage_runs(db, next_token, [run("R01", outcome_summary="version 2")])
    publish(db, next_token)

    pending_read = read_run(db, "R01")
    assert pending_read["runtime"]["generation"] == 2
    assert pending_read["run"]["outcome_summary"] == "version 2"
    assert pending_read["runtime"]["git_ref"] is None
    assert pending_read["runtime"]["last_confirmed_git_ref"] == CONFIRMED_RUNTIME
    assert pending_read["runtime"]["fallback_freshness"] == "stale"


def test_staging_run_never_leaks_through_any_identity(db):
    _published, _staging, token, _expires = begin_save(db)
    stage_runs(db, token, [run("R01")])
    publish(db, token)
    confirm_mirror(db)

    _published, _staging, next_token, _expires = begin_save(db)
    stage_runs(db, next_token, [run("R01"), run("R02")])

    assert read_run(db, "R01")["run"] == run("R01")
    assert read_run(db, "R02")["run"] is None
    assert read_run(db, "R02")["runtime"]["generation"] == 1
