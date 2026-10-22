"""POST-EV2-11.10 proof suite -- Begin Day consumer ``live_status`` state patch.

POST-EV2-11.10 extends the POST-EV2-11 daily-consumer return contract with one
optional ``state_patch`` beside the four existing audit arrays. A patch is a flat
object of top-level ``live_status`` keys to replace; Begin Day *transports* the
declared current-state change to the existing RT01 publication path and never
interprets the mechanic.

This suite proves, with pure orchestration doubles plus real PostgreSQL 15 and 17
on the full forward migration chain:

* an authorized ``live_status`` patch round-trips through the existing RT01/RT02
  spine with exact confirmed published read-back, while every unmentioned
  ``live_status`` key is preserved and the conductor's ``current_day`` and the
  owner ``schema_version`` are protected;
* an inactive/absent ``live_status``, an empty/oversized/malformed patch, a
  protected key, a conflicting cross-consumer key and an unknown result field all
  fail closed without partial publication;
* a refused patch leaves the published Day N truth and generation unchanged;
* rehydration reads the published patch back without rerunning the consumer;
* patch values are deep-copied so the consumer/published/staged data never alias;
* audit-only/zero-consumer behavior, deterministic ordering, the shared RNG seam
  and the existing effect bounds are unchanged.

No real campaign state is mutated and no real ``canon/days/day_XXX.md`` is
created or edited.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-11 needs real PostgreSQL servers"
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import begin_day as bd  # noqa: E402
import rt04_util as u  # noqa: E402
import test_begin_day as tb  # noqa: E402


# ---------------------------------------------------------------------------
# Real-PostgreSQL fixtures (mirrors the POST-EV2-11 Begin Day harness)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def database_server():
    connection = tb._connect(
        tb._first_dsn(tb._PG15_DSN_PRECEDENCE, tb._PG15_FALLBACK)
    )
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    tb.install_chain(database_server)
    return database_server


@pytest.fixture(scope="session")
def database_server_pg17():
    connection = tb._connect(
        tb._first_dsn(tb._PG17_DSN_PRECEDENCE, tb._PG17_FALLBACK)
    )
    yield connection
    connection.close()


@pytest.fixture()
def db_pg17(database_server_pg17):
    tb.install_chain(database_server_pg17)
    return database_server_pg17


# ---------------------------------------------------------------------------
# Synthetic consumers
# ---------------------------------------------------------------------------


class StatePatchConsumer:
    """A declared daily consumer that returns an optional ``state_patch``."""

    def __init__(self, consumer_id, patch, *, effect=None, error=None):
        self.consumer_id = consumer_id
        self.patch = patch
        self.effect = effect
        self.error = error
        self.calls = 0

    def resolve(self, context, dispatch):
        self.calls += 1
        if self.error is not None:
            raise self.error
        result = {"state_patch": copy.deepcopy(self.patch)}
        if self.effect is not None:
            result.update(copy.deepcopy(self.effect))
        return result


def _store():
    return tb.FakeDayStore({1: "# Day 001 -- Finalized Campaign Record\nbody"})


def _open(bundle, consumers):
    return bd.open_next_day(
        2,
        runtime=tb.FakeRuntime(bundle),
        finalized_store=_store(),
        consumers=consumers,
    )


# ---------------------------------------------------------------------------
# Pure conductor proof
# ---------------------------------------------------------------------------


def test_authorized_live_status_patch_is_transported_and_preserves_other_keys():
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    consumer = StatePatchConsumer(
        "daily-economy",
        {"campaign_resources": {"gold": 120}},
    )
    packet = bd.open_next_day(
        2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
    )
    staged_live = runtime.published_states[0]["live_status"]
    # The patch lands, the day-boundary/schema fields are conductor-protected,
    # and unrelated keys survive untouched.
    assert staged_live["campaign_resources"] == {"gold": 120}
    assert staged_live["current_day"] == 2
    assert staged_live["schema_version"] == 1
    assert staged_live["party_state"] == {
        "character:test-hero": {"status": "ready"}
    }
    assert staged_live["status"] == "uninitialized"
    # The derived boot packet reflects the published patch; it is never persisted.
    assert packet["current_context"]["live_status"]["campaign_resources"] == {
        "gold": 120
    }
    assert "boot_packet" not in runtime.published["current"]


def test_patch_leaves_only_an_effect_consumer_baseline_unchanged():
    # A consumer that returns only audit arrays (no state_patch) must leave
    # live_status with nothing but the conductor's day boundary.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    effect_consumer = tb.RecordingConsumer(
        "daily-notes", result=lambda context, dispatch: {"notes": [{"n": 1}]}
    )
    bd.open_next_day(
        2, runtime=runtime, finalized_store=_store(), consumers=[effect_consumer]
    )
    staged_live = runtime.published_states[0]["live_status"]
    assert set(staged_live) == set(tb.owners_for(1)["live_status"])
    assert staged_live["current_day"] == 2


def test_protected_live_status_keys_fail_closed():
    for protected in ("current_day", "schema_version"):
        runtime = tb.FakeRuntime(tb.published_bundle(1))
        consumer = StatePatchConsumer("daily-x", {protected: 99})
        with pytest.raises(bd.BeginDayError):
            bd.open_next_day(
                2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
            )
        # No partial publication: the candidate was aborted.
        assert runtime.aborted == [1]
        assert runtime.read_published()["current"]["published_day"] == 1


def test_state_patch_on_inactive_or_absent_live_status_fails_closed():
    bundle = tb.published_bundle(1)
    del bundle["current"]["live_status"]
    runtime = tb.FakeRuntime(bundle)
    consumer = StatePatchConsumer("daily-economy", {"campaign_resources": {"gold": 1}})
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
        )
    assert "live_status" in str(excinfo.value)
    assert runtime.aborted == [1]
    assert runtime.read_published()["current"]["published_day"] == 1


def test_empty_live_status_is_inactive_and_refused():
    bundle = tb.published_bundle(1)
    bundle["current"]["live_status"] = {}
    runtime = tb.FakeRuntime(bundle)
    consumer = StatePatchConsumer("daily-economy", {"campaign_resources": {"gold": 1}})
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
        )
    assert runtime.aborted == [1]


def test_explicitly_empty_state_patch_fails_closed_on_active_live_status():
    # An explicitly returned {"state_patch": {}} is a declared patch, not an
    # omitted one, so it must never silently bypass active-owner admission.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    consumer = StatePatchConsumer("daily-economy", {})
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
        )
    assert "empty state_patch" in str(excinfo.value)
    assert runtime.aborted == [1]
    assert runtime.read_published()["current"]["published_day"] == 1


def test_explicitly_empty_state_patch_fails_closed_on_absent_live_status():
    # The empty patch fails closed whether live_status is active or absent.
    bundle = tb.published_bundle(1)
    del bundle["current"]["live_status"]
    runtime = tb.FakeRuntime(bundle)
    consumer = StatePatchConsumer("daily-economy", {})
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
        )
    assert "empty state_patch" in str(excinfo.value)
    assert runtime.aborted == [1]
    assert runtime.read_published()["current"]["published_day"] == 1


def test_omitted_state_patch_remains_legal_and_publishes():
    # A consumer that does not declare state_patch at all is unchanged law.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    consumer = tb.RecordingConsumer(
        "daily-notes", result=lambda context, dispatch: {"notes": [{"n": 1}]}
    )
    packet = bd.open_next_day(
        2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
    )
    assert packet["mode"] == "fresh_day_boot"
    assert consumer.calls == 1
    assert runtime.aborted == []
    assert runtime.published_states[0]["live_status"]["current_day"] == 2


def test_zero_consumers_remain_unchanged_by_the_state_patch_contract():
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    packet = bd.open_next_day(
        2, runtime=runtime, finalized_store=_store(), consumers=()
    )
    assert packet["mode"] == "fresh_day_boot"
    assert runtime.aborted == []
    assert runtime.published_states[0]["live_status"]["current_day"] == 2


def test_conflicting_cross_consumer_live_status_keys_fail_closed():
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    first = StatePatchConsumer("daily-a", {"campaign_resources": {"gold": 1}})
    second = StatePatchConsumer("daily-b", {"campaign_resources": {"gold": 2}})
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2,
            runtime=runtime,
            finalized_store=_store(),
            consumers=[first, second],
        )
    assert "already written" in str(excinfo.value)
    assert runtime.aborted == [1]
    assert runtime.read_published()["current"]["published_day"] == 1


def test_malformed_and_oversized_patches_fail_closed():
    # state_patch must be an object.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    not_an_object = StatePatchConsumer("daily-x", ["nope"])
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[not_an_object]
        )
    assert runtime.aborted == [1]

    # A non-string / blank key fails closed.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    bad_key = StatePatchConsumer("daily-x", {1: "value"})
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[bad_key]
        )

    # Too many top-level keys fails closed.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    oversized = StatePatchConsumer(
        "daily-x",
        {"k%d" % i: i for i in range(bd._MAX_STATE_PATCH_KEYS + 1)},
    )
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[oversized]
        )
    assert "bound" in str(excinfo.value)


def test_unknown_result_field_is_still_refused():
    runtime = tb.FakeRuntime(tb.published_bundle(1))

    class BogusConsumer:
        consumer_id = "daily-bogus"

        def resolve(self, context, dispatch):
            return {"state_patch": {"campaign_resources": {}}, "surprise": 1}

    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(
            2, runtime=runtime, finalized_store=_store(), consumers=[BogusConsumer()]
        )
    assert "unknown field" in str(excinfo.value)


def test_state_patch_values_are_deep_copied_isolating_the_consumer_object():
    live_status = {"current_day": 2, "campaign_resources": {}}
    nested = {"nested": {"value": 1}}
    patch = {"campaign_resources": nested}
    seen = set()
    bd._merge_consumer_state_patch(live_status, "c", patch, seen)
    # A later mutation of the consumer's own object cannot reach staged truth.
    nested["nested"]["value"] = 999
    assert live_status["campaign_resources"] == {"nested": {"value": 1}}
    assert seen == {"campaign_resources"}


def test_state_patch_does_not_disturb_rng_or_effect_behavior():
    # A patch consumer can also carry audit arrays; the shared RNG seam and the
    # existing effect stamping are unchanged.
    runtime = tb.FakeRuntime(tb.published_bundle(1))
    consumer = StatePatchConsumer(
        "daily-audit",
        {"campaign_resources": {"gold": 7}},
        effect={"rng_rolls": [{"notation": "1d20", "total": 5}]},
    )
    packet = bd.open_next_day(
        2, runtime=runtime, finalized_store=_store(), consumers=[consumer]
    )
    rolls = packet["today_mechanics"]["rng_rolls"]
    assert rolls[0]["consumer_id"] == "daily-audit"
    assert packet["current_context"]["live_status"]["campaign_resources"] == {
        "gold": 7
    }


# ---------------------------------------------------------------------------
# Real PostgreSQL 15/17 round-trip and fail-closed proof
# ---------------------------------------------------------------------------


def _sql_runtime(db):
    return bd.SqlDayBoundaryRuntime(db, confirmation_worker=lambda: u.confirm_mirror(db))


def test_state_patch_round_trips_through_rt01_rt02(db, tmp_path):
    tb.establish(db, tb.clock(day=1), tb.owners_for(1))
    tb._write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    consumer = StatePatchConsumer(
        "daily-economy",
        {"campaign_resources": {"gold": 120}, "financial_obligations": {"party": []}},
    )
    packet = bd.open_next_day(
        2,
        runtime=_sql_runtime(db),
        finalized_store=store,
        consumers=[consumer],
    )
    assert packet["mode"] == "fresh_day_boot"
    assert packet["current_context"]["live_status"]["campaign_resources"] == {
        "gold": 120
    }

    published = u.published_state(db)
    live = published["live_status"]
    # The transported change is durably published; unrelated keys are intact and
    # the conductor owns the day boundary.
    assert live["campaign_resources"] == {"gold": 120}
    assert live["financial_obligations"] == {"party": []}
    assert live["current_day"] == 2
    assert live["schema_version"] == 1
    assert live["party_state"] == {"character:test-hero": {"status": "ready"}}
    assert live["status"] == "uninitialized"
    assert published["campaign_clock"]["day"] == 2

    # Retry is rehydration: the consumer is never rerun and the published patch
    # is read back unchanged.
    retry = bd.open_next_day(
        2,
        runtime=_sql_runtime(db),
        finalized_store=store,
        consumers=[consumer],
    )
    assert retry["mode"] == "rehydrated_day_boot"
    assert consumer.calls == 1
    assert u.published_state(db)["live_status"]["campaign_resources"] == {
        "gold": 120
    }


def test_state_patch_round_trips_pg17(db_pg17, tmp_path):
    tb.establish(db_pg17, tb.clock(day=1), tb.owners_for(1))
    tb._write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    consumer = StatePatchConsumer("daily-economy", {"campaign_resources": {"gold": 5}})
    bd.open_next_day(
        2,
        runtime=_sql_runtime(db_pg17),
        finalized_store=store,
        consumers=[consumer],
    )
    assert u.published_state(db_pg17)["live_status"]["campaign_resources"] == {
        "gold": 5
    }


def test_inactive_live_status_patch_fails_closed_without_partial_save(db, tmp_path):
    owners = tb.owners_for(1)
    del owners["live_status"]
    tb.establish(db, tb.clock(day=1), owners)
    tb._write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    before_generation = u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )
    before_state = u.published_state(db)
    consumer = StatePatchConsumer("daily-economy", {"campaign_resources": {"gold": 1}})
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2,
            runtime=_sql_runtime(db),
            finalized_store=store,
            consumers=[consumer],
        )
    # The refused patch partially published nothing.
    assert (
        u.scalar(
            db, "select published_generation from public.campaign_runtime where id = 1"
        )
        == before_generation
    )
    assert u.published_state(db) == before_state
    assert u.runtime_row(db)["save_in_progress"] is False


def test_protected_field_patch_fails_closed_without_partial_save(db, tmp_path):
    tb.establish(db, tb.clock(day=1), tb.owners_for(1))
    tb._write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    before_generation = u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )
    before_state = u.published_state(db)
    consumer = StatePatchConsumer("daily-x", {"current_day": 99})
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2,
            runtime=_sql_runtime(db),
            finalized_store=store,
            consumers=[consumer],
        )
    assert (
        u.scalar(
            db, "select published_generation from public.campaign_runtime where id = 1"
        )
        == before_generation
    )
    assert u.published_state(db) == before_state
    assert u.runtime_row(db)["save_in_progress"] is False


def test_explicitly_empty_state_patch_fails_closed_without_partial_save(db, tmp_path):
    # The previously-succeeding explicitly-empty-patch path must abort before
    # publication: no partial save, Day 1 published truth unchanged.
    tb.establish(db, tb.clock(day=1), tb.owners_for(1))
    tb._write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    before_generation = u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )
    before_state = u.published_state(db)
    consumer = StatePatchConsumer("daily-economy", {})
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2,
            runtime=_sql_runtime(db),
            finalized_store=store,
            consumers=[consumer],
        )
    assert (
        u.scalar(
            db, "select published_generation from public.campaign_runtime where id = 1"
        )
        == before_generation
    )
    assert u.published_state(db) == before_state
    assert u.runtime_row(db)["save_in_progress"] is False
