"""POST-EV2-11 proof suite -- Begin Day + Fresh-DM Boot.

Pure orchestration proof (injected RT01/RT02 gateway seam) plus real PostgreSQL
15 and 17 proof of the POST-EV2-11 published read and one end-to-end Begin Day
publication through the existing RT01 Save Gateway + RT02 Campaign Clock. Only
synthetic data is used and no real ``canon/days/day_XXX.md`` is created or
edited; finalized-day fixtures live in a pytest temporary directory.

The repair proofs additionally cover the exact-head Codex P1 findings: the
durable transaction boundary under default DB-API transaction behavior (P1-01),
retry rehydration that restores the exact finalized previous-day memory (P1-02),
the generation-pinned Fresh-Day boot packet (P1-03), and the fail-closed
coherence verdict for an active day-boundary owner with a missing/malformed/
unparseable ``current_day`` (P1-04). The finalized-day reader resolves by numeric
day identity across every legal filename width (leading zeroes legal, no
digit-count ceiling) and fails closed when more than one legal file resolves to
the same numeric day (P1-06 / P1-07).

The Mission adds NO runtime key, mutation domain, same-save compatibility edge,
Save Gateway, controller ledger, RNG root or mirror path. It adds:

* ``scripts/begin_day.py`` -- the conductor;
* ``public.dm_begin_day_read()`` -- one service-only read-only published read;
* ``docs/POST-EV2-11-BEGIN-DAY.md``; and
* this proof.
"""

from __future__ import annotations

import copy
import json
import os
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
import begin_day as bd  # noqa: E402
import rt04_util as u  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_CURRENT_MIGRATION = (
    _MIGRATIONS_DIR / "20260929000002_post_ev2_11_begin_day.sql"
)

_BASELINE_ROLES = (ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql").read_text(
    encoding="utf-8"
)
_SCHEMA_RESET = (
    "drop schema if exists public cascade;",
    "create schema public;",
    "grant usage on schema public to anon, authenticated, service_role;",
)

_PG15_DSN_PRECEDENCE = (
    "RHC_POST_EV211_PG_DSN",
    "RHC_POST_EV210_PG_DSN",
    "RHC_POST_EV29_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV211_PG17_DSN",
    "RHC_POST_EV210_PG17_DSN",
    "RHC_POST_EV29_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"


def _first_dsn(variables, fallback):
    for variable in variables:
        candidate = os.environ.get(variable)
        if candidate:
            return candidate
    return fallback


def install_chain(connection, migrations=FORWARD_MIGRATIONS):
    with connection.cursor() as cursor:
        cursor.execute(_BASELINE_ROLES)
        for statement in _SCHEMA_RESET:
            cursor.execute(statement)
        for migration in migrations:
            cursor.execute(migration.read_text(encoding="utf-8"))


def _connect(dsn):
    try:
        connection = psycopg2.connect(dsn)
    except psycopg2.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"POST-EV2-11 proof skipped (no server): {exc}")
    connection.autocommit = True
    return connection


@pytest.fixture(scope="session")
def database_server():
    connection = _connect(_first_dsn(_PG15_DSN_PRECEDENCE, _PG15_FALLBACK))
    yield connection
    connection.close()


@pytest.fixture()
def db(database_server):
    install_chain(database_server)
    return database_server


@pytest.fixture(scope="session")
def database_server_pg17():
    connection = _connect(_first_dsn(_PG17_DSN_PRECEDENCE, _PG17_FALLBACK))
    yield connection
    connection.close()


@pytest.fixture()
def db_pg17(database_server_pg17):
    install_chain(database_server_pg17)
    return database_server_pg17


# ---------------------------------------------------------------------------
# Synthetic doubles
# ---------------------------------------------------------------------------


def clock(day=None, phase="evening", elapsed=100, rests=0):
    return {
        "schema_version": 1,
        "day": day,
        "phase": phase,
        "elapsed_campaign_minutes": elapsed,
        "long_rests_completed": rests,
    }


def owners_for(day):
    return {
        "daily_recap": {
            "schema_version": 1,
            "system": "Rolling High Club Daily Recap Live State",
            "status": "closed",
            "current_day": day,
            "current_summary": {
                "rng_highlights": ["stale"],
                "mechanical_handoff": [],
                "next_scene_handoff": ["stale"],
                "general_development": [],
            },
            "previous_day_record": "canon/days/day_%03d.md" % (day - 1) if day > 1 else None,
            "carryover_active_hooks_at_start": [],
        },
        "day_resolution": {
            "schema_version": 1,
            "system": "Rolling High Club Day Resolution",
            "status": "closed",
            "current_day": day,
            "rng_rolls": [{"notation": "1d20", "total": 3}],
            "mechanical_resolutions": [{"summary": "stale"}],
            "persistent_effects_applied": [],
            "notes": ["stale"],
        },
        "live_status": {
            "schema_version": 1,
            "system": "Rolling High Club Live Status",
            "status": "uninitialized",
            "current_day": day,
            "party_state": {"character:test-hero": {"status": "ready"}},
            "campaign_resources": {},
            "organizations": {},
            "assets": {},
            "persistent_effects": [],
            "financial_obligations": {},
            "last_update_source": None,
        },
        "dm_meta": {
            "schema_version": 1,
            "system": "Rolling High Club DM Meta",
            "visibility": "meta",
            "status": "uninitialized",
            "current_day": day,
            "committed_hidden_truths": [],
            "durable_dm_plans": [],
            "ghost_seeds": [],
            "unreveal_conditions": [],
            "run_claims": {},
            "last_update_source": None,
        },
        "narrative_hooks": {
            "schema_version": 1,
            "system": "Rolling High Club Narrative Hook Ledger",
            "day_status": "closed",
            "current_day": day,
            "next_hook_id": "H03",
            "active_hooks": [{"id": "H01"}, {"id": "H02"}],
            "dormant_hooks": [],
            "closed_hooks_today": [{"id": "H99"}],
        },
    }


def published_bundle(day, *, generation=7, mirror_confirmed=True, owners=None):
    current = {
        "published_day": day,
        "campaign_clock": clock(day=day),
    }
    current.update(owners if owners is not None else owners_for(day))
    return {
        "read_version": 1,
        "mode": "begin_day",
        "runtime": {
            "generation": generation,
            "day": day,
            "mirror_confirmed": mirror_confirmed,
            "last_confirmed_generation": generation if mirror_confirmed else None,
        },
        "current": current,
        "coherence": {
            "coherent": True,
            "unknown_day": day is None,
            "clock_day": day,
            "owner_current_days": {},
            "issues": [],
        },
    }


class FakeDayStore:
    def __init__(self, finalized=None, paths=None):
        self._finalized = dict(finalized or {})
        self._paths = dict(paths or {})

    def read_finalized_record(self, day):
        text = self._finalized.get(day)
        if text is None:
            return (None, None)
        return (self._paths.get(day, "canon/days/day_%03d.md" % day), text)


class FakeRuntime:
    """In-memory RT01/RT02 gateway seam."""

    def __init__(self, bundle, *, confirmed=True, fail_publish=False):
        self.published = copy.deepcopy(bundle)
        self.confirmed = confirmed
        self.fail_publish = fail_publish
        self.staged = {}
        self.aborted = []
        self.published_states = []
        self.begin_calls = 0
        self._token = 0
        self._generation = bundle["runtime"]["generation"]

    def read_published(self):
        return copy.deepcopy(self.published)

    def begin_save(self, ttl_seconds=30):
        self.begin_calls += 1
        self._token += 1
        self.staged[self._token] = {}
        return self._token

    def stage_state(self, token, key, value):
        self.staged[token][key] = copy.deepcopy(value)

    def stage_clock(self, token, value):
        self.staged[token]["campaign_clock"] = copy.deepcopy(value)

    def publish(self, token):
        if self.fail_publish:
            raise RuntimeError("synthetic publish failure")
        staged = self.staged[token]
        self.published_states.append(copy.deepcopy(staged))
        current = self.published["current"]
        for key, value in staged.items():
            current[key] = copy.deepcopy(value)
        day = staged["campaign_clock"]["day"]
        current["published_day"] = day
        self.published["coherence"]["clock_day"] = day
        self.published["coherence"]["unknown_day"] = False
        self._generation += 1
        self.published["runtime"]["generation"] = self._generation
        self.published["runtime"]["day"] = day
        if self.confirmed:
            self.published["runtime"]["last_confirmed_generation"] = self._generation
            self.published["runtime"]["mirror_confirmed"] = True
        else:
            self.published["runtime"]["last_confirmed_generation"] = None
            self.published["runtime"]["mirror_confirmed"] = False
        return self._generation

    def abort_save(self, token):
        self.aborted.append(token)
        self.staged.pop(token, None)

    def ensure_confirmed(self):
        return self.confirmed


class RecordingConsumer:
    def __init__(self, consumer_id, result=None, error=None):
        self.consumer_id = consumer_id
        self.calls = 0
        self._result = result
        self._error = error

    def resolve(self, context, dispatch):
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._result is not None:
            return self._result(context, dispatch)
        return None


class WeatherConsumer:
    consumer_id = "daily-weather"

    def __init__(self):
        self.calls = 0

    def resolve(self, context, dispatch):
        self.calls += 1
        rolled = dispatch.roll(
            {"notation": "1d20", "modifiers": [{"value": 2, "source": "season"}]},
            source=self.consumer_id,
        )
        return {
            "rng_rolls": [
                {"notation": "1d20", "total": rolled["total"], "source": self.consumer_id}
            ]
        }


def _open_day(bundle, store, **kwargs):
    return bd.open_next_day(
        2, runtime=FakeRuntime(bundle), finalized_store=store, **kwargs
    )


# ---------------------------------------------------------------------------
# Stage 4 proof matrix -- pure conductor
# ---------------------------------------------------------------------------


def test_healthy_finalized_day_opens_only_next_day():
    store = FakeDayStore({1: "# Day 001 -- Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert packet["mode"] == "fresh_day_boot"
    assert packet["day"] == 2
    assert packet["previous_day"]["day"] == 1
    assert packet["previous_day"]["finalized_record_path"] == "canon/days/day_001.md"


# ---------------------------------------------------------------------------
# P1-06 proof -- exact finalized-day path provenance
# ---------------------------------------------------------------------------


def test_finalized_record_reader_reports_the_exact_padded_path(tmp_path):
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_001.md").write_text(
        "# Day 001 -- Finalized Campaign Record\nbody", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    path, text = store.read_finalized_record(1)
    assert path == "canon/days/day_001.md"
    assert "body" in text

    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert packet["previous_day"]["finalized_record_path"] == "canon/days/day_001.md"
    assert (
        runtime.published_states[0]["daily_recap"]["previous_day_record"]
        == "canon/days/day_001.md"
    )


def test_finalized_record_reader_reports_the_exact_unpadded_path(tmp_path):
    # A legal unpadded archive (day_1.md) exists; the reader must report the exact
    # path it opened and must not fabricate a canonical-looking padded pointer.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_1.md").write_text(
        "# Day 1 -- Finalized Campaign Record\nunpadded body", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    path, text = store.read_finalized_record(1)
    assert path == "canon/days/day_1.md"
    assert "unpadded body" in text

    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert packet["previous_day"]["finalized_record_path"] == "canon/days/day_1.md"
    assert packet["previous_day"]["finalized_record"] == text
    assert (
        runtime.published_states[0]["daily_recap"]["previous_day_record"]
        == "canon/days/day_1.md"
    )
    # No fabricated padded sibling was created or persisted.
    assert not (days / "day_001.md").exists()


def test_retry_restores_the_exact_unpadded_finalized_path(tmp_path):
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_1.md").write_text(
        "# Day 1 -- Finalized Campaign Record\nunpadded body", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    runtime = FakeRuntime(published_bundle(1))
    first = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    second = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert second["mode"] == "rehydrated_day_boot"
    assert second["previous_day"] == first["previous_day"]
    assert second["previous_day"]["finalized_record_path"] == "canon/days/day_1.md"
    assert "unpadded body" in second["previous_day"]["finalized_record"]


# ---------------------------------------------------------------------------
# P1-07 proof -- numeric finalized-day identity across legal widths + ambiguity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,day",
    [
        ("day_1.md", 1),
        ("day_01.md", 1),
        ("day_001.md", 1),
        ("day_0001.md", 1),
        ("day_007.md", 7),
        ("day_12547.md", 12547),
    ],
)
def test_finalized_record_reader_resolves_any_legal_width_by_day_identity(
    tmp_path, name, day
):
    # The SAVE boundary admits `canon/days/day_<positive int>.md` with leading
    # zeroes legal and no digit-count ceiling, so the reader must resolve the
    # record by numeric day identity rather than one fixed filename width.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / name).write_text(
        "# Day -- Finalized Campaign Record\nbody", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    path, text = store.read_finalized_record(day)
    assert path == "canon/days/%s" % name
    assert "body" in text


def test_finalized_record_reader_is_not_confused_by_a_different_day_width(tmp_path):
    # A different numeric day at any width is neither a match nor an ambiguity.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_02.md").write_text(
        "# Day 2 -- Finalized Campaign Record\nother day", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    assert store.read_finalized_record(1) == (None, None)
    path, _text = store.read_finalized_record(2)
    assert path == "canon/days/day_02.md"


def test_finalized_record_reader_fails_closed_on_ambiguous_day_identity(tmp_path):
    # Two legal files resolve to the same numeric day: refuse to choose silently.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_001.md").write_text(
        "# Day 001 -- Finalized Campaign Record\npadded", encoding="utf-8"
    )
    (days / "day_1.md").write_text(
        "# Day 1 -- Finalized Campaign Record\nunpadded", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    with pytest.raises(bd.BeginDayError) as excinfo:
        store.read_finalized_record(1)
    assert "ambiguous" in str(excinfo.value)

    runtime = FakeRuntime(published_bundle(1))
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=runtime, finalized_store=store)


def test_conductor_persists_exact_arbitrary_width_finalized_path(tmp_path):
    # The exact legal path opened (here a 2-digit width) is what gets persisted
    # in the handoff and returned in the boot packet -- and restored on retry.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_01.md").write_text(
        "# Day 1 -- Finalized Campaign Record\nbody", encoding="utf-8"
    )
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert packet["previous_day"]["finalized_record_path"] == "canon/days/day_01.md"
    assert (
        runtime.published_states[0]["daily_recap"]["previous_day_record"]
        == "canon/days/day_01.md"
    )

    retry = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert retry["mode"] == "rehydrated_day_boot"
    assert retry["previous_day"]["finalized_record_path"] == "canon/days/day_01.md"
    assert "body" in retry["previous_day"]["finalized_record"]


def test_day_skip_fails_closed():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    # Requesting Day 3 while Day 1 is published is a skip, not the next day.
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(3, runtime=FakeRuntime(published_bundle(1)), finalized_store=store)
    # Jumping far ahead is refused too.
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(5, runtime=FakeRuntime(published_bundle(1)), finalized_store=store)


def test_missing_or_unfinalized_previous_day_fails_closed(tmp_path):
    # Missing record.
    with pytest.raises(bd.BeginDayError):
        _open_day(published_bundle(1), FakeDayStore())
    # File present at the exact path but not a finalized record.
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True)
    (days / "day_001.md").write_text("# Day 001 -- draft\n", encoding="utf-8")
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    assert store.read_finalized_record(1) == (None, None)
    with pytest.raises(bd.BeginDayError):
        _open_day(published_bundle(1), store)


def test_unknown_current_day_fails_closed():
    bundle = published_bundle(1)
    bundle["coherence"]["clock_day"] = None
    bundle["coherence"]["unknown_day"] = True
    bundle["current"]["published_day"] = None
    with pytest.raises(bd.BeginDayError):
        _open_day(bundle, FakeDayStore({1: "Finalized Campaign Record"}))


def test_incoherent_current_day_fails_closed():
    bundle = published_bundle(1)
    bundle["coherence"]["coherent"] = False
    bundle["coherence"]["issues"] = ["daily_recap.current_day disagrees with campaign_clock.day"]
    with pytest.raises(bd.BeginDayError):
        _open_day(bundle, FakeDayStore({1: "Finalized Campaign Record"}))


def test_day_changes_only_through_rt02_no_invented_time_phase_or_rest():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    bd.open_next_day(2, runtime=runtime, finalized_store=store)
    staged_clock = runtime.published_states[0]["campaign_clock"]
    assert staged_clock["day"] == 2
    assert staged_clock["elapsed_campaign_minutes"] == 100
    assert staged_clock["long_rests_completed"] == 0
    # The published broad phase is carried forward, not invented as dawn.
    assert staged_clock["phase"] == "evening"


def test_only_day_boundary_owners_are_initialized_without_rewriting_entities():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    bd.open_next_day(2, runtime=runtime, finalized_store=store)
    staged = runtime.published_states[0]
    assert set(staged) == {
        "campaign_clock",
        "daily_recap",
        "day_resolution",
        "narrative_hooks",
        "live_status",
        "dm_meta",
    }
    # Unrelated entity-ish content is carried forward untouched.
    assert staged["live_status"]["party_state"] == {
        "character:test-hero": {"status": "ready"}
    }


def test_carryover_hook_snapshot_derives_from_hook_owner():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    bd.open_next_day(2, runtime=runtime, finalized_store=store)
    staged = runtime.published_states[0]
    assert staged["daily_recap"]["carryover_active_hooks_at_start"] == ["H01", "H02"]
    # The Hook owner remains the only lifecycle owner: active hooks survive and
    # only the day-boundary fields change.
    assert staged["narrative_hooks"]["active_hooks"] == [{"id": "H01"}, {"id": "H02"}]


def test_previous_day_closed_bucket_does_not_leak_into_new_day():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    bd.open_next_day(2, runtime=runtime, finalized_store=store)
    staged = runtime.published_states[0]
    assert staged["narrative_hooks"]["closed_hooks_today"] == []
    assert staged["daily_recap"]["current_summary"] == {
        "rng_highlights": [],
        "mechanical_handoff": [],
        "next_scene_handoff": [],
        "general_development": [],
    }
    assert staged["day_resolution"]["rng_rolls"] == []
    assert staged["day_resolution"]["mechanical_resolutions"] == []


def test_zero_configured_daily_mechanics_means_zero_rng():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store, consumers=())
    staged = runtime.published_states[0]
    assert staged["day_resolution"]["rng_rolls"] == []
    assert packet["today_mechanics"]["rng_rolls"] == []


def test_synthetic_consumer_uses_the_declared_dispatch_seam():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    weather = WeatherConsumer()
    packet = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[weather],
        dispatch_rng=random.Random(1234),
    )
    rolls = packet["today_mechanics"]["rng_rolls"]
    assert weather.calls == 1
    assert len(rolls) == 1
    assert rolls[0]["notation"] == "1d20"
    assert rolls[0]["consumer_id"] == "daily-weather"
    assert rolls[0]["source"] == "daily-weather"


def test_daily_consumer_order_is_deterministic_and_bounded():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))

    def make(consumer_id):
        return RecordingConsumer(
            consumer_id,
            result=lambda context, dispatch: {
                "notes": [{"note": consumer_id}]
            },
        )

    bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[make("zeta"), make("alpha"), make("mid")],
    )
    notes = runtime.published_states[0]["day_resolution"]["notes"]
    assert [entry["consumer_id"] for entry in notes] == ["alpha", "mid", "zeta"]

    # A duplicate consumer id is ambiguous authority and fails closed.
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(
            2,
            runtime=FakeRuntime(published_bundle(1)),
            finalized_store=store,
            consumers=[make("dup"), make("dup")],
        )


def test_retry_after_publication_never_rerolls():
    store = FakeDayStore({1: "# Day 001 -- Finalized Campaign Record\nbody"})
    runtime = FakeRuntime(published_bundle(1))
    weather = WeatherConsumer()
    first = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[weather],
        dispatch_rng=random.Random(1234),
    )
    assert weather.calls == 1
    rolls_first = first["today_mechanics"]["rng_rolls"]

    second = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[weather],
        dispatch_rng=random.Random(9999),
    )
    assert second["mode"] == "rehydrated_day_boot"
    assert weather.calls == 1
    assert second["today_mechanics"]["rng_rolls"] == rolls_first
    assert second["today_mechanics"] == first["today_mechanics"]
    # P1-02: rehydration restores the exact finalized Day N memory instead of
    # null placeholders.
    assert second["previous_day"] == first["previous_day"]
    assert second["previous_day"]["day"] == 1
    assert (
        second["previous_day"]["finalized_record_path"] == "canon/days/day_001.md"
    )
    assert "body" in second["previous_day"]["finalized_record"]


class _MidRetryRaceRuntime(FakeRuntime):
    """A runtime whose published world moves between the two retry reads."""

    def __init__(self, bundle, race_bundle):
        super().__init__(bundle)
        self._race_bundle = race_bundle
        self._reads = 0

    def read_published(self):
        self._reads += 1
        if self._reads >= 2:
            return copy.deepcopy(self._race_bundle)
        return super().read_published()


class _PostConfirmRaceRuntime(FakeRuntime):
    """A runtime whose published world moves after Begin Day confirmation."""

    def __init__(self, bundle, race_bundle):
        super().__init__(bundle)
        self._race_bundle = race_bundle
        self._race_armed = False

    def ensure_confirmed(self):
        result = super().ensure_confirmed()
        if result:
            self._race_armed = True
        return result

    def read_published(self):
        if self._race_armed:
            return copy.deepcopy(self._race_bundle)
        return super().read_published()


class _OpaquePublishRuntime(FakeRuntime):
    """A runtime that publishes but refuses to report the exact generation."""

    def publish(self, token):
        super().publish(token)
        return None


def test_retry_without_the_exact_finalized_previous_day_fails_closed():
    # Day 2 is already published, but the finalized Day 1 record is gone: the
    # rehydrated packet would lose yesterday's memory, so it fails closed.
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(2, runtime=FakeRuntime(published_bundle(2)), finalized_store=FakeDayStore())
    assert "finalized Day 1" in str(excinfo.value)


def test_retry_fails_closed_when_published_handoff_pointer_disagrees():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    bundle = published_bundle(2)
    bundle["current"]["daily_recap"]["previous_day_record"] = "canon/days/day_099.md"
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=FakeRuntime(bundle), finalized_store=store)


def test_retry_fails_closed_when_the_confirmed_world_moves_mid_rehydration():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    bd.open_next_day(2, runtime=runtime, finalized_store=store)
    # A concurrent/later save publishes generation 9 after the retry's first
    # read; the rehydrated packet must never mix it in.
    racer = _MidRetryRaceRuntime(runtime.published, published_bundle(2, generation=9))
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(2, runtime=racer, finalized_store=store)
    assert "mixed-generation" in str(excinfo.value)


def test_fresh_boot_packet_is_pinned_to_the_exact_confirmed_generation():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    packet = bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert packet["current_context"]["published_generation"] == 8
    assert (
        packet["current_context"]["published_generation"]
        == runtime.read_published()["runtime"]["generation"]
    )


def test_later_publication_cannot_mix_into_the_fresh_boot_packet():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    # A concurrent day-neutral save advances the generation after confirmation;
    # the packet must fail closed rather than mix generations.
    racer = _PostConfirmRaceRuntime(
        published_bundle(1), published_bundle(2, generation=9)
    )
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(2, runtime=racer, finalized_store=store)
    assert "mixed-generation" in str(excinfo.value)


def test_boot_packet_fails_closed_on_same_generation_day_drift():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    drifted = published_bundle(2, generation=8)
    drifted["coherence"]["clock_day"] = 3
    racer = _PostConfirmRaceRuntime(published_bundle(1), drifted)
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=racer, finalized_store=store)


def test_publication_without_an_exact_generation_fails_closed():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = _OpaquePublishRuntime(published_bundle(1))
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert "unpinned" in str(excinfo.value)
    # The publication itself stands (no abort); only the packet is refused and
    # the caller must repair/rehydrate the same generation.
    assert runtime.read_published()["current"]["published_day"] == 2
    assert runtime.aborted == []


def test_abort_leaves_published_truth_unchanged():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1))
    before = runtime.read_published()
    boom = RecordingConsumer("daily-boom", error=ValueError("synthetic mechanic failure"))
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=runtime, finalized_store=store, consumers=[boom])
    assert runtime.read_published() == before
    assert runtime.aborted == [1]


def test_mirror_confirmation_failure_is_not_success():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    runtime = FakeRuntime(published_bundle(1), confirmed=False)
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=runtime, finalized_store=store)


def test_boot_packet_is_derived_and_complete():
    store = FakeDayStore({1: "# Day 001 -- Finalized Campaign Record\nbody"})
    runtime = FakeRuntime(published_bundle(1))
    weather = WeatherConsumer()
    packet = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[weather],
        dispatch_rng=random.Random(5),
    )
    assert packet["packet_version"] == 1
    assert "body" in packet["previous_day"]["finalized_record"]
    assert packet["current_context"]["campaign_clock"]["day"] == 2
    assert packet["current_context"]["published_day"] == 2
    assert packet["today_mechanics"]["rng_rolls"]
    # The packet is not persisted: the runtime only ever saw the owner candidates.
    assert "boot_packet" not in runtime.published["current"]


def test_invalid_requested_day_fails_closed():
    store = FakeDayStore({1: "Finalized Campaign Record"})
    for bad in (0, -1, "2", True, 2.0):
        with pytest.raises(bd.BeginDayError):
            bd.open_next_day(
                bad, runtime=FakeRuntime(published_bundle(1)), finalized_store=store
            )


def test_begin_day_does_not_own_rest_runs_or_history_search():
    source = (ROOT / "scripts" / "begin_day.py").read_text(encoding="utf-8")
    assert "character_rests" not in source
    assert "mutate_character_rest" not in source
    assert "character_mechanics" not in source
    assert "run_reconciliations" not in source
    assert "dm_runtime_read_run" not in source
    assert "story_retrieval" not in source
    # The one RNG root is the shared resolver, never raw random in the conductor.
    assert "import random" not in source


# ---------------------------------------------------------------------------
# Stage 4 proof matrix -- real PostgreSQL read + end-to-end publication
# ---------------------------------------------------------------------------


def _primary_error(exc):
    diag = getattr(exc, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    return primary or str(exc).splitlines()[0]


def _run_as(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _error_as(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return _primary_error(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def _stage_clock(db, token, value):
    with db.cursor() as cur:
        cur.execute(
            "select public.stage_campaign_clock(%s, %s::jsonb)",
            (token, json.dumps(value)),
        )


def establish(db, clock_value, owners):
    _published, _staging, token, _expires = u.begin_save(db)
    _stage_clock(db, token, clock_value)
    for key, value in owners.items():
        u.stage(db, token, key, value)
    u.publish(db, token)
    u.confirm_mirror(db)


def begin_read(db):
    return u.scalar(db, "select public.dm_begin_day_read()")


def _write_finalized(tmp_path, day, body="# Day -- Finalized Campaign Record"):
    days = tmp_path / "canon" / "days"
    days.mkdir(parents=True, exist_ok=True)
    (days / ("day_%03d.md" % day)).write_text(body, encoding="utf-8")


def test_begin_day_read_is_published_only_and_coherent(db):
    establish(db, clock(day=1), owners_for(1))
    payload = begin_read(db)
    assert payload["read_version"] == 1
    assert payload["mode"] == "begin_day"
    assert payload["coherence"]["coherent"] is True
    assert payload["coherence"]["clock_day"] == 1
    assert payload["current"]["published_day"] == 1
    assert payload["current"]["campaign_clock"]["day"] == 1
    for key in ("daily_recap", "day_resolution", "live_status", "dm_meta", "narrative_hooks"):
        assert payload["current"][key]["current_day"] == 1
    assert "generation" in payload["runtime"]


def test_begin_day_read_reports_unknown_day(db):
    establish(db, clock(day=None), owners_for(1))
    payload = begin_read(db)
    assert payload["coherence"]["unknown_day"] is True
    assert payload["coherence"]["clock_day"] is None


def test_begin_day_read_reports_owner_disagreement(db):
    # A published Clock day that disagrees with the day-boundary owners is not
    # coerced; the read reports the incoherence for the conductor to refuse.
    _published, _staging, token, _expires = u.begin_save(db)
    _stage_clock(db, token, clock(day=2))
    u.stage(db, token, "daily_recap", owners_for(1)["daily_recap"])
    u.stage(db, token, "narrative_hooks", owners_for(1)["narrative_hooks"])
    u.publish(db, token)
    u.confirm_mirror(db)
    payload = begin_read(db)
    assert payload["coherence"]["coherent"] is False
    assert any("daily_recap.current_day" in issue for issue in payload["coherence"]["issues"])


def test_begin_day_read_is_service_role_only(db):
    def call(cur):
        cur.execute("select public.dm_begin_day_read()")

    assert _error_as(db, "anon", call)
    assert _error_as(db, "authenticated", call)
    _run_as(db, "service_role", call)


def test_begin_day_migration_adds_no_runtime_key_or_policy(db):
    source = _CURRENT_MIGRATION.read_text(encoding="utf-8")
    assert "create table" not in source.lower()
    assert "insert into public.campaign_state_generations" not in source.lower()
    assert "_rhc_save_domain_policy" not in source
    assert "_rhc_same_save_compatibility" not in source
    # The migration is present on the frozen forward chain.
    assert _CURRENT_MIGRATION in FORWARD_MIGRATIONS


def test_begin_day_read_pg17(db_pg17):
    establish(db_pg17, clock(day=1), owners_for(1))
    payload = begin_read(db_pg17)
    assert payload["coherence"]["coherent"] is True
    assert payload["current"]["campaign_clock"]["day"] == 1


def test_begin_day_end_to_end_publishes_through_rt01_rt02(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    consumer = WeatherConsumer()
    runtime = bd.SqlDayBoundaryRuntime(
        db, confirmation_worker=lambda: u.confirm_mirror(db)
    )
    packet = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[consumer],
        dispatch_rng=random.Random(7),
    )
    assert packet["mode"] == "fresh_day_boot"
    assert packet["day"] == 2
    assert packet["previous_day"]["day"] == 1
    assert "Finalized Campaign Record" in packet["previous_day"]["finalized_record"]

    published = u.published_state(db)
    assert published["campaign_clock"]["day"] == 2
    assert published["campaign_clock"]["elapsed_campaign_minutes"] == 100
    assert published["campaign_clock"]["long_rests_completed"] == 0
    assert published["daily_recap"]["current_day"] == 2
    assert published["daily_recap"]["previous_day_record"] == "canon/days/day_001.md"
    assert published["daily_recap"]["carryover_active_hooks_at_start"] == ["H01", "H02"]
    assert published["narrative_hooks"]["closed_hooks_today"] == []
    assert published["day_resolution"]["current_day"] == 2
    assert len(published["day_resolution"]["rng_rolls"]) == 1
    assert published["day_resolution"]["rng_rolls"][0]["consumer_id"] == "daily-weather"
    # Begin Day never touches Rest or character resources.
    assert "character_rests" not in published
    assert "character_mechanics" not in published
    assert u.scalar(db, "select published_day from public.campaign_runtime where id = 1") == 2

    # Retry is rehydration, never a second set of rolls.
    rolls_before = published["day_resolution"]["rng_rolls"]
    retry = bd.open_next_day(
        2,
        runtime=runtime,
        finalized_store=store,
        consumers=[consumer],
        dispatch_rng=random.Random(999),
    )
    assert retry["mode"] == "rehydrated_day_boot"
    assert consumer.calls == 1
    assert u.published_state(db)["day_resolution"]["rng_rolls"] == rolls_before


def test_begin_day_abort_leaves_published_truth_unchanged(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    before_generation = u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )
    before_state = u.published_state(db)
    boom = RecordingConsumer("daily-boom", error=ValueError("synthetic mechanic failure"))
    runtime = bd.SqlDayBoundaryRuntime(
        db, confirmation_worker=lambda: u.confirm_mirror(db)
    )
    with pytest.raises(bd.BeginDayError):
        bd.open_next_day(2, runtime=runtime, finalized_store=store, consumers=[boom])
    assert (
        u.scalar(db, "select published_generation from public.campaign_runtime where id = 1")
        == before_generation
    )
    assert u.published_state(db) == before_state


# ---------------------------------------------------------------------------
# P1-04 proof -- active day-boundary owner with an unverifiable current_day
# ---------------------------------------------------------------------------


def _publish_namespace(db, key, value):
    """Overwrite one published namespace directly (synthetic corruption probe)."""
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def test_begin_day_read_fails_closed_on_unparseable_active_owner_day(db):
    establish(db, clock(day=1), owners_for(1))
    recap = owners_for(1)["daily_recap"]
    recap["current_day"] = "1"
    _publish_namespace(db, "daily_recap", recap)
    payload = begin_read(db)
    assert payload["coherence"]["coherent"] is False
    assert any(
        "daily_recap" in issue and "current_day" in issue
        for issue in payload["coherence"]["issues"]
    )
    assert payload["coherence"]["owner_current_days"]["daily_recap"] is None


@pytest.mark.parametrize("corruption", ["string", "missing", "null", "float"])
def test_begin_day_read_fails_closed_on_unverifiable_owner_days(db, corruption):
    establish(db, clock(day=1), owners_for(1))
    hooks = owners_for(1)["narrative_hooks"]
    if corruption == "string":
        hooks["current_day"] = "1"
    elif corruption == "missing":
        hooks.pop("current_day")
    elif corruption == "null":
        hooks["current_day"] = None
    else:
        hooks["current_day"] = 1.5
    _publish_namespace(db, "narrative_hooks", hooks)
    payload = begin_read(db)
    assert payload["coherence"]["coherent"] is False
    assert any(
        "narrative_hooks" in issue for issue in payload["coherence"]["issues"]
    )
    assert payload["coherence"]["owner_current_days"]["narrative_hooks"] is None


def test_begin_day_read_does_not_treat_empty_or_absent_owners_as_active(db):
    # An empty published owner carries no day-boundary state to verify, and an
    # absent owner is not an active owner; neither is incoherence by itself.
    establish(db, clock(day=1), owners_for(1))
    _publish_namespace(db, "live_status", {})
    u.break_glass(
        db,
        "delete from public.campaign_state_generations "
        "where generation = (select published_generation from public.campaign_runtime where id = 1) "
        "and key = 'dm_meta'",
    )
    payload = begin_read(db)
    assert payload["coherence"]["coherent"] is True
    assert payload["coherence"]["owner_current_days"]["live_status"] is None
    assert payload["coherence"]["owner_current_days"]["dm_meta"] is None
    assert payload["current"]["dm_meta"] == {}


def test_begin_day_conductor_fails_closed_on_unparseable_owner_day(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    recap = owners_for(1)["daily_recap"]
    recap["current_day"] = "1"
    _publish_namespace(db, "daily_recap", recap)
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    runtime = bd.SqlDayBoundaryRuntime(
        db, confirmation_worker=lambda: u.confirm_mirror(db)
    )
    with pytest.raises(bd.BeginDayError) as excinfo:
        bd.open_next_day(2, runtime=runtime, finalized_store=store)
    assert "incoherent" in str(excinfo.value)


def test_begin_day_read_fails_closed_on_unverifiable_owner_day_pg17(db_pg17):
    establish(db_pg17, clock(day=1), owners_for(1))
    hooks = owners_for(1)["narrative_hooks"]
    hooks["current_day"] = "1"
    _publish_namespace(db_pg17, "narrative_hooks", hooks)
    payload = begin_read(db_pg17)
    assert payload["coherence"]["coherent"] is False


# ---------------------------------------------------------------------------
# P1-01 proof -- durable transaction boundary under default DB-API behavior
# ---------------------------------------------------------------------------


class _RecordingConnection:
    """Thin connection proxy that records explicit commit boundaries."""

    def __init__(self, connection):
        self._connection = connection
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def commit(self):
        self.commits += 1
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _BadClockRuntime(bd.SqlDayBoundaryRuntime):
    """Stages a Clock candidate the RT02 route must refuse."""

    def stage_clock(self, token, clock_value):
        super().stage_clock(token, {**clock_value, "elapsed_campaign_minutes": 50})


def _default_transaction_connection(dsn_variables, fallback):
    connection = psycopg2.connect(_first_dsn(dsn_variables, fallback))
    connection.autocommit = False
    return connection


def test_begin_day_success_is_durable_under_default_dbapi_transactions(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    worker_connection = _default_transaction_connection(
        _PG15_DSN_PRECEDENCE, _PG15_FALLBACK
    )
    try:
        probe = _RecordingConnection(worker_connection)
        runtime = bd.SqlDayBoundaryRuntime(
            probe, confirmation_worker=lambda: u.confirm_mirror(worker_connection)
        )
        packet = bd.open_next_day(
            2,
            runtime=runtime,
            finalized_store=store,
            consumers=[WeatherConsumer()],
            dispatch_rng=random.Random(11),
        )
        assert packet["mode"] == "fresh_day_boot"
        assert packet["day"] == 2
        # Publication and confirmation each crossed an explicit commit boundary
        # before Begin Day reported success.
        assert probe.commits >= 2
        # An independent connection observes the durable published generation.
        assert (
            u.scalar(db, "select published_day from public.campaign_runtime where id = 1")
            == 2
        )
        published = u.published_state(db)
        assert published["campaign_clock"]["day"] == 2
        assert len(published["day_resolution"]["rng_rolls"]) == 1
        row = u.runtime_row(db)
        assert row["runtime_published_confirmed"] is True
        assert row["save_in_progress"] is False
        assert packet["current_context"]["published_generation"] == row["published_generation"]
        # The success survives the caller discarding any lingering transaction
        # state on the Begin Day connection: nothing reported was uncommitted.
        worker_connection.rollback()
        assert (
            u.scalar(db, "select published_day from public.campaign_runtime where id = 1")
            == 2
        )
        assert u.published_state(db)["daily_recap"]["current_day"] == 2
    finally:
        worker_connection.close()


def test_begin_day_abort_under_default_transactions_leaves_day_n_durable(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    worker_connection = _default_transaction_connection(
        _PG15_DSN_PRECEDENCE, _PG15_FALLBACK
    )
    try:
        runtime = bd.SqlDayBoundaryRuntime(worker_connection, confirmation_worker=None)
        before_generation = u.scalar(
            db, "select published_generation from public.campaign_runtime where id = 1"
        )
        before_state = u.published_state(db)
        boom = RecordingConsumer("daily-boom", error=ValueError("synthetic mechanic failure"))
        with pytest.raises(bd.BeginDayError):
            bd.open_next_day(2, runtime=runtime, finalized_store=store, consumers=[boom])
        # The durable explicit abort discarded the uncommitted candidate...
        assert u.runtime_row(db)["save_in_progress"] is False
        worker_connection.rollback()
        # ...and Day 1 published truth is unchanged on an independent connection.
        assert (
            u.scalar(db, "select published_generation from public.campaign_runtime where id = 1")
            == before_generation
        )
        assert u.published_state(db) == before_state
    finally:
        worker_connection.close()


def test_begin_day_sql_failure_under_default_transactions_fails_closed(db, tmp_path):
    establish(db, clock(day=1), owners_for(1))
    _write_finalized(tmp_path, 1)
    store = bd.RepositoryFinalizedDayStore(str(tmp_path))
    worker_connection = _default_transaction_connection(
        _PG15_DSN_PRECEDENCE, _PG15_FALLBACK
    )
    try:
        runtime = _BadClockRuntime(worker_connection, confirmation_worker=None)
        before_generation = u.scalar(
            db, "select published_generation from public.campaign_runtime where id = 1"
        )
        before_state = u.published_state(db)
        with pytest.raises(bd.BeginDayError) as excinfo:
            bd.open_next_day(2, runtime=runtime, finalized_store=store)
        # The primary SQL failure is reported, not the secondary abort failure.
        assert "elapsed_campaign_minutes" in str(excinfo.value)
        # The aborted client transaction never became durable; Day 1 truth and
        # the save gateway state are unchanged on an independent connection.
        worker_connection.rollback()
        assert (
            u.scalar(db, "select published_generation from public.campaign_runtime where id = 1")
            == before_generation
        )
        assert u.published_state(db) == before_state
        assert u.runtime_row(db)["save_in_progress"] is False
    finally:
        worker_connection.close()
