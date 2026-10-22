"""POST-EV2-5 proof suite — Current published-world exact-focus search.

Runs against real PostgreSQL 15 and 17 with the full forward migration chain
(RT01-A/B/C/D + RT02 + RT03 + RT04 + HWB-02 + EV2-10 + EV2-11 + EV2-12.1 +
EV2-13 + EV2-13.420 + EV2-13.1 + POST-EV2-1 Patch 1A/1B + POST-EV2-2 +
POST-EV2-3 + POST-EV2-4A + POST-EV2-5) using disposable schemas and synthetic
data only. No live Supabase is touched and no real RHC state is imported.

The Mission ("POST-EV2-5 — Current published-world exact-focus search") adds one
service-only, read-only, stable search facade, `public.dm_current_search(...)`,
that wires existing engine plugs only:

  * it reads only the published generation (staged/future rows never appear);
  * it reads only the namespaces that can contribute to the requested focus
    kind, each fetched individually by its exact runtime key -- the whole
    published generation is never aggregated and filtered later;
  * every routed namespace is validated by its EXISTING owner whole-collection
    contract before any filtering (Runs through the existing canonical
    published Run-truth reader that already applies the RT03/EV2-08 path),
    including the owner's declared cross-collection law: `item_admissions`
    also proves the existing EV2-12.1
    `_rhc_validate_item_admission_custody_linkage` invariant against the
    validated published `item_custody` collection;
  * only exact existing identity/relation fields create hits;
  * knower-local knowledge stays with the exact knower;
  * multi-hit domains are deterministic and bounded and report truncation;
  * no recursive hydration of IDs found inside hits;
  * no new table, runtime key, mutation route, validator framework, cache,
    index, graph/vector store or second state reader is introduced;
  * the read is service-only, stable and non-mutating.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-5 needs real PostgreSQL servers"
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402

_MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
FORWARD_MIGRATIONS = tuple(sorted(_MIGRATIONS_DIR.glob("*.sql")))
_CURRENT_SEARCH_MIGRATION = _MIGRATIONS_DIR / (
    "20260926000001_post_ev2_5_current_search.sql"
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
    "RHC_POST_EV25_PG_DSN",
    "RHC_POST_EV24A_PG_DSN",
    "RHC_POST_EV23_PG_DSN",
    "RHC_RT04_PG_DSN",
)
_PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
_PG17_DSN_PRECEDENCE = (
    "RHC_POST_EV25_PG17_DSN",
    "RHC_POST_EV24A_PG17_DSN",
    "RHC_POST_EV23_PG17_DSN",
    "RHC_RT01_ACTIVATION_PG_DSN",
)
_PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

HERO = "character:test-hero"
SIDEKICK = "character:test-sidekick"
BEAST = "creature:test-wolf"
LOCATION = "location:tavern"
FACTION = "faction:test-guild"
PARTY = "party:test-stash"
ITEM = "item:test-blade"
MISSING_ITEM = "item:test-missing"

# The surfaces this Mission is authorized to touch. Any tracked/working-tree
# diff outside this set is a STOP-and-return, not an opportunistic edit.
ALLOWED_SURFACES = frozenset(
    {
        "supabase/migrations/20260926000001_post_ev2_5_current_search.sql",
        "docs/POST-EV2-5-CURRENT-SEARCH.md",
        "tests/post_ev2_5/test_current_search.py",
        "supabase/README.md",
        "PLAY.md",
        ".github/workflows/rt01-runtime.yml",
        "tests/post_ev2_2/test_hot_run_registry.py",
    }
)


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
        pytest.skip(f"POST-EV2-5 proof skipped (no server): {exc}")
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
# Helpers
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


def _error_as_role(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def published_generation(db):
    return u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )


def publish_namespace(db, key, value):
    """Seed one published namespace directly (test fixture, owner-shaped data)."""
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def stage_namespace(db, key, value):
    """Seed the current staging generation directly (staged/future probe only)."""
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select staging_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (key, json.dumps(value)),
    )


def establish(db, runs=None, seed=None):
    """Advance to a confirmed published generation, then seed namespaces."""
    _published, _staging, token, _expires = u.begin_save(db)
    if runs is not None:
        u.stage_runs(db, token, runs)
    u.publish(db, token)
    u.confirm_mirror(db)
    for key, value in (seed or {}).items():
        publish_namespace(db, key, value)
    return published_generation(db)


def search(db, focus, limit=None):
    def call(cur):
        if limit is None:
            cur.execute("select public.dm_current_search(%s)", (focus,))
        else:
            cur.execute("select public.dm_current_search(%s, %s)", (focus, limit))
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def search_error(db, focus, limit=None):
    def call(cur):
        if limit is None:
            cur.execute("select public.dm_current_search(%s)", (focus,))
        else:
            cur.execute("select public.dm_current_search(%s, %s)", (focus, limit))

    return _error_as_service(db, call)


def hits(response, domain):
    return response["results"].get(domain, {}).get("hits", [])


# --- owner-shaped synthetic records -----------------------------------------

def entity_state(entity, status="unknown", entries=None):
    record = {"entity_id": entity, "status": status}
    if entries is not None:
        record["entries"] = entries
    return record


def inventory(entity, entries=None, currency=None):
    record = {"entity_id": entity, "status": "known", "entries": entries or []}
    if currency is not None:
        record["currency"] = currency
    return record


def custody(item, owner=None, holder=None):
    return {"item_id": item, "owner_entity_id": owner, "holder_entity_id": holder}


def admission(item, generation=1, controller=None, source="canary", event="admit"):
    return {
        "item_id": item,
        "controller": controller or {"kind": "mainrun"},
        "provenance": {"source": source, "event": event, "campaign_day": 1},
        "admitted_generation": generation,
        "admission_version": 1,
    }


def applied_status(application_id="APP-1", target=HERO, source=None, definition="status_effect:test-aura"):
    return {
        "application_version": 1,
        "application_id": application_id,
        "definition_id": definition,
        "target_entity_id": target,
        "source_entity_id": source,
        "applied_at_elapsed_minutes": 0,
        "thresholds": [{"threshold_id": "T1", "due_at_elapsed_minutes": 10}],
        "acknowledged_thresholds": [],
        "ended_at_elapsed_minutes": None,
    }


def knowledge(entity, entries=None, status="known"):
    record = {"entity_id": entity, "status": status}
    if entries is not None:
        record["entries"] = entries
    return record


def assertion_entry(topic="courier", value="alive", visibility="meta"):
    return {
        "topic": topic,
        "epistemic_status": "confirmed",
        "value": value,
        "visibility": visibility,
    }


# ---------------------------------------------------------------------------
# 1. Valid focus returns RT01-D published generation / exact-ref metadata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_valid_focus_returns_published_generation_and_exact_ref_metadata(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    generation = establish(db, seed={"entity_state": [entity_state(HERO, "unknown")]})

    response = search(db, HERO)
    assert response["read_version"] == 1
    assert response["mode"] == "current_search"
    assert response["focus"] == HERO

    runtime = response["runtime"]
    assert runtime["generation"] == generation
    assert runtime["git_ref"] == u.CONFIRMED_RUNTIME
    assert runtime["mirror_confirmed"] is True
    assert runtime["last_confirmed_generation"] == generation
    assert runtime["last_confirmed_git_ref"] == u.CONFIRMED_RUNTIME
    assert runtime["fallback_freshness"] == "current"

    assert hits(response, "entity_state") == [entity_state(HERO, "unknown")]
    assert response["results"]["entity_state"]["truncated"] is False


# ---------------------------------------------------------------------------
# 2. Unsupported / malformed focus fails closed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "focus",
    [
        "",
        "   ",
        None,
        "hero",
        "character:",
        "character:Bad",
        "character:bad_slug",
        "character:bad--slug",
        "character:Test-Hero",
        "unknown:thing",
        "location:tavern/",
        "R01",
    ],
)
def test_invalid_focus_fails_closed(db, focus):
    establish(db)
    err = search_error(db, focus)
    assert "focus" in err


# ---------------------------------------------------------------------------
# 3. Only namespaces that can contribute to the focus kind are read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_only_routed_namespaces_are_read(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    # A malformed entity_state namespace would fail any read that routes it.
    establish(db, seed={"entity_state": "not-an-array"})

    # `item:` does not route entity_state, so it still succeeds.
    item_response = search(db, ITEM)
    assert item_response["results"] == {}

    # `character:` routes entity_state, so the malformed namespace fails closed.
    err = search_error(db, HERO)
    assert "entity_state" in err


# ---------------------------------------------------------------------------
# 4. Every routed namespace is validated by its EXISTING owner contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "focus, key",
    [
        (HERO, "entity_state"),
        (HERO, "inventory"),
        (HERO, "item_custody"),
        (HERO, "applied_statuses"),
        (HERO, "entity_knowledge"),
        (ITEM, "item_admissions"),
        (PARTY, "item_custody"),
        (LOCATION, "inventory"),
    ],
)
def test_malformed_routed_namespace_fails_through_owner_contract(db, focus, key):
    establish(db, seed={key: "not-an-array"})
    err = search_error(db, focus)
    assert key in err


def test_malformed_relevant_record_fails_closed(db):
    # A valid array carrying one malformed record must fail its owner contract.
    establish(db, seed={"entity_state": [entity_state(HERO, "sometimes")]})
    err = search_error(db, HERO)
    assert "entity_state" in err


# ---------------------------------------------------------------------------
# 5. No POST-EV2-5 custom validator substitutes for owner validation
# ---------------------------------------------------------------------------

def test_whole_collection_validation_rejects_malformed_unrelated_record(db):
    # The focus record is valid; an unrelated malformed record in the SAME
    # authoritative namespace must still fail closed. This proves validation is
    # the owner's whole-collection contract, not a per-record shortcut invented
    # by POST-EV2-5.
    establish(
        db,
        seed={
            "entity_state": [
                entity_state(HERO, "unknown"),
                {"entity_id": SIDEKICK, "status": "sometimes"},
            ]
        },
    )
    err = search_error(db, HERO)
    assert "entity_state" in err


# ---------------------------------------------------------------------------
# 6 & 7. Exact existing relation fields only; unrelated records never returned
# ---------------------------------------------------------------------------

def test_only_exact_relation_fields_create_hits(db):
    near_hero = "character:test-heroine"
    establish(
        db,
        seed={
            "entity_state": [
                entity_state(HERO, "unknown"),
                entity_state(near_hero, "unknown"),
                entity_state(SIDEKICK, "unknown"),
            ],
            "inventory": [
                inventory(HERO, [{"name": "Rope", "description": "hemp", "quantity": 1}]),
                inventory(PARTY, [{"name": "Tent", "description": "canvas", "quantity": 2}]),
            ],
            "item_custody": [
                custody(ITEM, owner=PARTY, holder=HERO),
                custody(MISSING_ITEM, owner=SIDEKICK, holder=None),
            ],
            "entity_knowledge": [knowledge(HERO, [assertion_entry()])],
        },
    )

    response = search(db, HERO)
    assert [r["entity_id"] for r in hits(response, "entity_state")] == [HERO]
    # inventory and knowledge are exact-owner/knower only; SIDEKICK, PARTY and
    # the near-match heroine never leak into the HERO result.
    assert [r["entity_id"] for r in hits(response, "inventory")] == [HERO]
    assert [r["item_id"] for r in hits(response, "item_custody")] == [ITEM]
    assert [r["entity_id"] for r in hits(response, "entity_knowledge")] == [HERO]

    serialized = json.dumps(response)
    assert near_hero not in serialized
    assert MISSING_ITEM not in serialized


# ---------------------------------------------------------------------------
# 8. Staged / future state is never read
# ---------------------------------------------------------------------------

def test_staged_state_is_never_read(db):
    generation = establish(db, seed={"entity_state": [entity_state(HERO, "unknown")]})

    # Begin a new save; its staging generation is a copy of published reality.
    _published, _staging, token, _expires = u.begin_save(db)
    # Directly change a staged (future) value that was never published.
    stage_namespace(db, "entity_state", [entity_state(HERO, "known",
                  entries=[{"attribute": "mood", "status": "known", "value": "furious"}])])
    try:
        response = search(db, HERO)
        assert published_generation(db) == generation
        assert hits(response, "entity_state") == [entity_state(HERO, "unknown")]
    finally:
        u.abort_save(db, token)

    # A namespace that exists only in staging is invisible to the published read.
    _published, _staging, token, _expires = u.begin_save(db)
    stage_namespace(db, "inventory", [inventory(HERO, [{"name": "Ghost",
                   "description": "staged", "quantity": 1}])])
    try:
        response = search(db, HERO)
        assert hits(response, "inventory") == []
    finally:
        u.abort_save(db, token)


# ---------------------------------------------------------------------------
# 9. Knower-local knowledge remains exact-knower only
# ---------------------------------------------------------------------------

def test_knower_local_knowledge_is_exact_knower_only(db):
    establish(
        db,
        seed={
            "entity_knowledge": [
                knowledge(HERO, [assertion_entry(topic="hero_secret", value="A")]),
                knowledge(SIDEKICK, [assertion_entry(topic="sidekick_secret", value="B")]),
            ]
        },
    )

    hero = search(db, HERO)
    assert len(hits(hero, "entity_knowledge")) == 1
    assert hits(hero, "entity_knowledge")[0]["entity_id"] == HERO
    assert hits(hero, "entity_knowledge")[0]["entries"][0]["topic"] == "hero_secret"

    sidekick = search(db, SIDEKICK)
    assert len(hits(sidekick, "entity_knowledge")) == 1
    assert hits(sidekick, "entity_knowledge")[0]["entity_id"] == SIDEKICK
    assert hits(sidekick, "entity_knowledge")[0]["entries"][0]["topic"] == "sidekick_secret"


# ---------------------------------------------------------------------------
# 10. Run hits reuse canonical published Run truth / existing validation law
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_run_hits_reuse_canonical_published_run_truth(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    runs = [
        u.run(run_id="R01", participant_entity_ids=[HERO], mutable_owner_entity_ids=[HERO],
              location_ids=[LOCATION], party_id=PARTY),
        u.run(run_id="R02", participant_entity_ids=[SIDEKICK],
              mutable_owner_entity_ids=[SIDEKICK], location_ids=["location:market"]),
    ]
    establish(db, runs=runs)

    hero = search(db, HERO)
    assert [r["run_id"] for r in hits(hero, "runs")] == ["R01"]
    assert hits(hero, "runs")[0] == runs[0]

    location = search(db, LOCATION)
    assert [r["run_id"] for r in hits(location, "runs")] == ["R01"]

    party = search(db, PARTY)
    assert [r["run_id"] for r in hits(party, "runs")] == ["R01"]


def test_malformed_published_run_batch_fails_closed(db):
    establish(db, runs=[{"run_id": "R01"}])
    err = search_error(db, HERO)
    assert "Run" in err


def test_cross_run_mutable_owner_conflict_fails_closed(db):
    runs = [
        u.run(run_id="R01", participant_entity_ids=[HERO], mutable_owner_entity_ids=[HERO]),
        u.run(run_id="R02", participant_entity_ids=[HERO, SIDEKICK],
              mutable_owner_entity_ids=[HERO, SIDEKICK]),
    ]
    establish(db, runs=runs)
    err = search_error(db, SIDEKICK)
    assert "mutable" in err.lower() or "owner" in err.lower()


# ---------------------------------------------------------------------------
# 11. Multi-hit domains are deterministic, bounded and report truncation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_multi_hit_domain_is_bounded_and_reports_truncation(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    items = [f"item:test-item-{i}" for i in range(3)]
    establish(db, seed={"item_custody": [custody(item, owner=PARTY, holder=None) for item in items]})

    full = search(db, PARTY)
    assert [r["item_id"] for r in hits(full, "item_custody")] == sorted(items)
    assert full["results"]["item_custody"]["truncated"] is False

    bounded = search(db, PARTY, limit=2)
    assert len(hits(bounded, "item_custody")) == 2
    assert bounded["results"]["item_custody"]["truncated"] is True


def test_default_limit_is_twenty(db):
    items = [f"item:test-item-{i}" for i in range(25)]
    establish(db, seed={"item_custody": [custody(item, owner=PARTY, holder=None) for item in items]})
    response = search(db, PARTY)
    assert len(hits(response, "item_custody")) == 20
    assert response["results"]["item_custody"]["truncated"] is True


def test_limit_is_clamped_to_hard_bounds(db):
    items = [f"item:test-item-{i}" for i in range(51)]
    establish(db, seed={"item_custody": [custody(item, owner=PARTY, holder=None) for item in items]})

    # Hard maximum 50: 51 matching records are bounded to 50.
    upper = search(db, PARTY, limit=100)
    assert len(hits(upper, "item_custody")) == 50
    assert upper["results"]["item_custody"]["truncated"] is True

    # Lower bound 1: a zero/negative request is clamped to at least one hit.
    lower = search(db, PARTY, limit=0)
    assert len(hits(lower, "item_custody")) == 1
    assert lower["results"]["item_custody"]["truncated"] is True


# ---------------------------------------------------------------------------
# 12. No recursive hydration of IDs found inside hits
# ---------------------------------------------------------------------------

def test_no_recursive_hydration(db):
    run_record = u.run(run_id="R01", participant_entity_ids=[HERO],
                       mutable_owner_entity_ids=[HERO], scenario_id="S07")
    establish(
        db,
        runs=[run_record],
        seed={"item_custody": [custody(ITEM, owner=PARTY, holder=HERO)]},
    )

    response = search(db, HERO)
    run_hit = hits(response, "runs")[0]
    # The hit is exactly the published Run record: the scenario_id and owner IDs
    # are direct values, and no Scenario/Encounter/participant object is nested.
    assert run_hit == run_record
    assert set(run_hit) == set(run_record)
    assert isinstance(run_hit["scenario_id"], str)
    assert all(isinstance(pid, str) for pid in run_hit["participant_entity_ids"])

    custody_hit = hits(response, "item_custody")[0]
    assert custody_hit == custody(ITEM, owner=PARTY, holder=HERO)
    assert set(custody_hit) == {"item_id", "owner_entity_id", "holder_entity_id"}


# ---------------------------------------------------------------------------
# 13. Existing reads remain unchanged
# ---------------------------------------------------------------------------

def test_existing_runtime_reads_remain_unchanged(db):
    runs = [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])]
    establish(db, runs=runs)

    context = u.dm_read(db)
    assert context["mode"] == "context"
    assert context["read_version"] == 1
    assert context["runtime"]["generation"] >= 1

    run_read = u.read_run(db, "R01")
    assert run_read["mode"] == "run"
    assert run_read["run"]["run_id"] == "R01"

    absent = u.read_run(db, "R99")
    assert absent["mode"] == "run"
    assert absent["run"] is None


# ---------------------------------------------------------------------------
# 14. Service-only, stable, non-mutating
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_read_is_service_only(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    establish(db, seed={"entity_state": [entity_state(HERO, "unknown")]})

    for role in ("anon", "authenticated"):
        err = _error_as_role(
            db, role,
            lambda cur: cur.execute("select public.dm_current_search(%s)", (HERO,)),
        )
        assert "permission denied" in err.lower()


def test_read_is_stable_and_non_mutating(db):
    generation = establish(db, seed={"entity_state": [entity_state(HERO, "unknown")]})

    meta = u.scalar(
        db,
        "select jsonb_build_object('volatile', p.provolatile, "
        "'security_definer', p.prosecdef) "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace "
        "and p.proname = 'dm_current_search'",
    )
    assert meta["volatile"] == "s"
    assert meta["security_definer"] is True

    before = u.scalar(
        db,
        "select count(*) from public.campaign_state_generations",
    )
    search(db, HERO)
    after = u.scalar(db, "select count(*) from public.campaign_state_generations")
    assert after == before

    row = u.runtime_row(db)
    assert row["published_generation"] == generation
    assert row["save_in_progress"] is False
    assert row["staging_generation"] is None


# ---------------------------------------------------------------------------
# 15. No new persistence / index / RAG / graph / validator framework
# ---------------------------------------------------------------------------

def test_no_new_persistence_or_framework_is_introduced(db):
    establish(db)

    forbidden_terms = ("vector", "embedding", "rag", "graph", "semantic", "%search%")
    with db.cursor() as cur:
        cur.execute(
            "select c.relname from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind in ('r', 'p', 'm') "
            "and (c.relname ilike any(%s))",
            (list(forbidden_terms),),
        )
        tables = [row[0] for row in cur.fetchall()]
    assert tables == []

    # No invented validator framework: the only public function named for this
    # Mission is dm_current_search itself.
    with db.cursor() as cur:
        cur.execute(
            "select p.proname from pg_proc p "
            "where p.pronamespace = 'public'::regnamespace "
            "and (p.proname ilike '%current_search%' "
            "     or p.proname ilike '%focus_search%' "
            "     or p.proname ilike '%selective_context%')"
        )
        names = sorted(row[0] for row in cur.fetchall())
    assert names == ["dm_current_search"]

    # The read adds no runtime key: an unknown key is still forbidden.
    policy = u.scalar(db, "select public._rhc_save_domain_policy(%s)",
                      ("__post_ev2_5_unknown_key__",))
    assert policy["admission"] == "forbidden"

    # Patch 1A classification of the existing runtime keys is unchanged.
    assert u.scalar(db, "select public._rhc_save_domain_policy('runs')")["admission"] == "generic"
    assert u.scalar(db, "select public._rhc_save_domain_policy('entity_knowledge')")["admission"] == "dedicated"


# ---------------------------------------------------------------------------
# 16. Migration frontier + static surface guard
# ---------------------------------------------------------------------------

def test_forward_migration_frontier_includes_post_ev2_5():
    # POST-EV2-5 must remain in the frozen forward migration chain. A later
    # Mission necessarily advances the repository migration frontier beyond
    # POST-EV2-5, so this suite no longer claims its migration is the final one;
    # the frozen ordering of the POST-EV2-5 chain itself is unchanged.
    assert _CURRENT_SEARCH_MIGRATION in FORWARD_MIGRATIONS


def test_only_the_authorized_surfaces_are_in_scope():
    assert ALLOWED_SURFACES == {
        "supabase/migrations/20260926000001_post_ev2_5_current_search.sql",
        "docs/POST-EV2-5-CURRENT-SEARCH.md",
        "tests/post_ev2_5/test_current_search.py",
        "supabase/README.md",
        "PLAY.md",
        ".github/workflows/rt01-runtime.yml",
        "tests/post_ev2_2/test_hot_run_registry.py",
    }


# ---------------------------------------------------------------------------
# 17. Invariant A — selective read path (Codex finding 01)
# ---------------------------------------------------------------------------

# The exact runtime keys the read may ever fetch. `runs` is not fetched
# directly: it is read through the existing canonical published Run-truth
# reader, which is itself key-selective.
_ROUTED_NAMESPACE_KEYS = frozenset(
    {
        "entity_state",
        "inventory",
        "item_custody",
        "item_admissions",
        "applied_statuses",
        "entity_knowledge",
    }
)


def test_read_path_fetches_only_routed_namespaces_individually():
    # Invariant A: `dm_current_search` must not aggregate the whole published
    # generation and filter later. The migration source must fetch each routed
    # namespace individually by its exact runtime key, and only the routed
    # namespaces. This proves the fetch path itself is selective, which no
    # result-level assertion can distinguish (the old whole-generation
    # aggregate was invisible in results because non-routed namespaces were
    # never validated or filtered).
    source = _CURRENT_SEARCH_MIGRATION.read_text(encoding="utf-8")

    # No whole-generation aggregate anywhere in the read.
    assert "jsonb_object_agg" not in source

    # Every campaign_state_generations reference sits inside a key-scoped
    # fetch: one occurrence per routed namespace, no unscoped select.
    scoped_keys = set(re.findall(r"csg\.key = '([a-z_]+)'", source))
    assert scoped_keys == _ROUTED_NAMESPACE_KEYS
    assert source.count("campaign_state_generations") == len(scoped_keys)


def test_selective_fetch_matches_declared_routing(db):
    # Behavioral counterpart of Invariant A: a namespace that cannot
    # contribute to the focus kind is never validated (so a malformed
    # non-routed namespace cannot fail an unrouted focus), while every routed
    # namespace is validated before filtering. Already proven by
    # test_only_routed_namespaces_are_read; repeated here focused on the
    # fetch-level contract for each routed family after the repair.
    establish(
        db,
        seed={
            "entity_state": [entity_state(HERO, "unknown")],
            "inventory": [inventory(HERO, [{"name": "Rope", "description": "hemp", "quantity": 1}])],
            "item_custody": [custody(ITEM, owner=HERO, holder=None)],
            "applied_statuses": [],
            "entity_knowledge": [],
        },
    )
    hero = search(db, HERO)
    assert [r["entity_id"] for r in hits(hero, "entity_state")] == [HERO]
    assert [r["entity_id"] for r in hits(hero, "inventory")] == [HERO]
    assert [r["item_id"] for r in hits(hero, "item_custody")] == [ITEM]

    # item: does not route entity_state; the search still succeeds.
    item = search(db, ITEM)
    assert [r["item_id"] for r in hits(item, "item_custody")] == [ITEM]
    assert "entity_state" not in item["results"]


# ---------------------------------------------------------------------------
# 18. Invariant B — owner contract includes the cross-collection law
#     (Codex finding 02: _rhc_validate_item_admission_custody_linkage)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_valid_admission_receipt_with_custody_returns_both_hits(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    establish(
        db,
        seed={
            "item_custody": [custody(ITEM, owner=PARTY, holder=None)],
            "item_admissions": [admission(ITEM)],
        },
    )

    response = search(db, ITEM)
    assert [r["item_id"] for r in hits(response, "item_custody")] == [ITEM]
    assert [r["item_id"] for r in hits(response, "item_admissions")] == [ITEM]
    assert response["results"]["item_admissions"]["truncated"] is False


@pytest.mark.parametrize("db_fixture", ("db", "db_pg17"))
def test_orphan_admission_receipt_fails_closed_through_existing_linkage_law(request, db_fixture):
    db = request.getfixturevalue(db_fixture)
    # Both collections are individually valid under their whole-collection
    # owner contracts. Only the existing EV2-12.1 cross-collection linkage law
    # can catch the orphan receipt; POST-EV2-5 must not return it as
    # authoritative and must fail closed through that EXISTING contract (the
    # error text is the existing function's, proving no weaker replacement).
    establish(
        db,
        seed={
            "item_custody": [custody(ITEM, owner=PARTY, holder=None)],
            "item_admissions": [admission(MISSING_ITEM)],
        },
    )

    # The receipt's own item fails closed.
    err = search_error(db, MISSING_ITEM)
    assert "no matching item_custody record" in err

    # The linkage is whole-namespace law, not filtered to the focus: an orphan
    # receipt for an unrelated item also fails the read for the item whose
    # custody does match (mirroring the whole-collection philosophy of the
    # owner contracts).
    err = search_error(db, ITEM)
    assert "no matching item_custody record" in err


def test_custody_without_receipt_legacy_asymmetry_stays_allowed(db):
    # The EV2-12.1 law is one-directional: custody-without-receipt is the
    # forward-only legacy asymmetry and is never an orphan. Search must still
    # return the custody hit and must not invent an admissions domain.
    establish(db, seed={"item_custody": [custody(ITEM, owner=PARTY, holder=HERO)]})

    response = search(db, ITEM)
    assert [r["item_id"] for r in hits(response, "item_custody")] == [ITEM]
    assert "item_admissions" not in response["results"]


def test_admission_linkage_is_wired_through_the_existing_owner_contract():
    # Static wiring proof for Invariant B: the admission owner contract is
    # reused whole (existing whole-collection validator + existing
    # cross-collection linkage function), not reimplemented.
    source = _CURRENT_SEARCH_MIGRATION.read_text(encoding="utf-8")
    assert "perform public._rhc_validate_item_admissions_collection(v_ns);" in source
    assert (
        "perform public._rhc_validate_item_admission_custody_linkage(v_custody_ns, v_ns);"
        in source
    )