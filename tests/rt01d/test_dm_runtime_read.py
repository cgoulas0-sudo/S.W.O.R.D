import psycopg2
import pytest

from rt01d_util import (
    CONFIRMED_RUNTIME,
    begin_save,
    bind_base,
    confirm,
    pending,
    publish,
    scalar,
    stage,
)


def test_generation_zero_is_unknown_safe_and_empty(db):
    result = scalar(db, "select public.dm_runtime_read()")

    assert result["mode"] == "context"
    assert result["runtime"] == {
        "generation": 0,
        "git_ref": None,
        "day": None,
        "mirror_confirmed": False,
        "mirror_confirmed_at": None,
        "last_confirmed_generation": None,
        "last_confirmed_git_ref": None,
        "fallback_freshness": "unavailable",
    }
    assert result["context"]["scene"]["status"] == "unknown"
    assert result["context"]["scene"]["next_scene_handoff"] == []
    assert result["context"]["world"]["status"] == "unknown"
    assert result["context"]["today"]["rng_rolls"] == []
    assert result["context"]["dm_index"]["committed_hidden_truths"] == []


def test_context_is_rhc_shaped_bounded_and_published_only(db):
    _published, _staging, token, _expires = begin_save(db)
    stage(
        db,
        token,
        "daily_recap",
        {
            "status": "active",
            "current_summary": {
                "next_scene_handoff": [f"handoff-{index}" for index in range(25)]
            },
        },
    )
    stage(
        db,
        token,
        "narrative_hooks",
        {
            "day_status": "active",
            "active_hooks": [
                {
                    "id": "H01",
                    "title": "A compact hook",
                    "status": "active",
                    "visibility": "meta",
                    "description": "full secret body must not expand",
                }
            ],
            "dormant_hooks": [],
            "closed_hooks_today": [],
        },
    )
    stage(
        db,
        token,
        "live_status",
        {
            "status": "active",
            "current_day": 9,
            "party_state": {"location": "camp"},
            "campaign_resources": {"rations": 4},
            "persistent_effects": ["blessed"],
        },
    )
    stage(
        db,
        token,
        "day_resolution",
        {
            "status": "resolved",
            "current_day": 9,
            "rng_rolls": [{"id": f"R{index}", "total": 17} for index in range(60)],
            "mechanical_resolutions": ["watch complete"],
        },
    )
    stage(
        db,
        token,
        "dm_meta",
        {
            "status": "active",
            "committed_hidden_truths": [
                {
                    "id": "T1",
                    "title": "Indexed truth",
                    "status": "committed",
                    "body": "secret body must not expand",
                }
            ],
            "durable_dm_plans": [],
        },
    )
    publish(db, token)

    result = scalar(db, "select public.dm_runtime_read()")
    context = result["context"]
    assert result["runtime"]["generation"] == 1
    assert result["runtime"]["git_ref"] is None
    assert result["runtime"]["mirror_confirmed"] is False
    assert len(context["scene"]["next_scene_handoff"]) == 20
    assert context["scene"]["hooks"]["active"] == [
        {
            "id": "H01",
            "title": "A compact hook",
            "status": "active",
            "visibility": "meta",
        }
    ]
    assert context["world"]["party_state"] == {"location": "camp"}
    assert context["today"]["rng_rolls"][0]["total"] == 17
    assert len(context["today"]["rng_rolls"]) == 50
    assert context["dm_index"]["committed_hidden_truths"] == [
        {"id": "T1", "title": "Indexed truth", "status": "committed"}
    ]


def test_staging_generation_never_leaks_into_context_or_lookup(db):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "live_status", {"status": "published-marker"})
    publish(db, token)
    candidate = pending(db)
    bind_base(db, candidate)
    candidate = pending(db)
    confirm(db, candidate)

    _published, _staging, next_token, _expires = begin_save(db)
    stage(db, next_token, "live_status", {"status": "future-only-marker"})

    context = scalar(db, "select public.dm_runtime_read()")
    lookup = scalar(db, "select public.dm_runtime_read('future-only-marker')")
    assert context["runtime"]["generation"] == 1
    assert context["context"]["world"]["status"] == "published-marker"
    assert lookup["runtime"]["generation"] == 1
    assert lookup["results"] == []


def test_lookup_is_bounded_deterministic_and_keeps_metadata_on_zero_hits(db):
    _published, _staging, token, _expires = begin_save(db)
    for index in range(110):
        stage(db, token, f"entry-{index:03d}", {"topic": "needle"})
    publish(db, token)

    zero = scalar(db, "select public.dm_runtime_read('absent')")
    bounded = scalar(db, "select public.dm_runtime_read('needle', 1000)")
    one = scalar(db, "select public.dm_runtime_read('needle', 0)")
    assert zero["runtime"]["generation"] == 1
    assert zero["results"] == []
    assert len(bounded["results"]) == 100
    assert len(one["results"]) == 1
    assert [item["key"] for item in bounded["results"]] == sorted(
        item["key"] for item in bounded["results"]
    )
    with pytest.raises(psycopg2.errors.RaiseException, match="query is required"):
        scalar(db, "select public.dm_runtime_lookup('   ', 20)")
    with pytest.raises(psycopg2.errors.RaiseException, match="exceeds 200"):
        scalar(db, "select public.dm_runtime_lookup(%s, 20)", ("x" * 201,))


def test_pending_and_confirmed_git_fallback_freshness_are_honest(db):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "k", {"version": 1})
    publish(db, token)
    first = pending(db)
    assert scalar(db, "select public.dm_runtime_read()")["runtime"]["fallback_freshness"] == "unavailable"
    bind_base(db, first)
    first = pending(db)
    confirm(db, first)

    confirmed = scalar(db, "select public.dm_runtime_read()")["runtime"]
    assert confirmed["git_ref"] == CONFIRMED_RUNTIME
    assert confirmed["last_confirmed_git_ref"] == CONFIRMED_RUNTIME
    assert confirmed["fallback_freshness"] == "current"

    _published, _staging, second_token, _expires = begin_save(db)
    stage(db, second_token, "k", {"version": 2})
    publish(db, second_token)
    pending_runtime = scalar(db, "select public.dm_runtime_read()")["runtime"]
    assert pending_runtime["generation"] == 2
    assert pending_runtime["git_ref"] is None
    assert pending_runtime["last_confirmed_generation"] == 1
    assert pending_runtime["last_confirmed_git_ref"] == CONFIRMED_RUNTIME
    assert pending_runtime["fallback_freshness"] == "stale"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_dm_facade_denies_client_roles(db, role):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select public.dm_runtime_read()")
        finally:
            cur.execute("reset role")


def test_dm_facade_allows_service_role(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute("select public.dm_runtime_read()")
            assert cur.fetchone()[0]["runtime"]["generation"] == 0
        finally:
            cur.execute("reset role")


def test_service_role_cannot_read_raw_staging_generation(db):
    _published, _staging, token, _expires = begin_save(db)
    stage(db, token, "future-only", {"status": "staging-marker"})

    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select * from public.campaign_state_generations")
            cur.execute("select public.dm_runtime_read('staging-marker')")
            result = cur.fetchone()[0]
            assert result["runtime"]["generation"] == 0
            assert result["results"] == []
        finally:
            cur.execute("reset role")


def test_service_role_targeted_read_cannot_bypass_runtime_metadata_envelope(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select public.dm_runtime_lookup('missing', 20)")
            cur.execute("select public.dm_runtime_read('missing', 20)")
            result = cur.fetchone()[0]
            assert result["mode"] == "lookup"
            assert result["runtime"]["generation"] == 0
            assert result["results"] == []
        finally:
            cur.execute("reset role")
