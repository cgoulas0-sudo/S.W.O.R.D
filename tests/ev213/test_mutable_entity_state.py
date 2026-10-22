"""EV2-13 mutable entity-state runtime proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 + EV2-10 + EV2-11 + EV2-12.1 spine plus the forward-only EV2-13 migration.
All durable mutation goes through the real save/publication/mirror-confirmation
spine; nothing is mocked. No real RHC entity state is published: every entity is
synthetic.

Proof Matrix coverage:
  * a valid MAINRUN-owned mutable entity mutation stages + publishes the bounded
    entity-state record through the existing RT01 spine;
  * a valid published RUN-owned mutation publishes through the same spine;
  * unknown / not_applicable states are coherent and never carry entries;
  * exactly one authoritative record per mutable entity; another entity keeps its
    own record;
  * the target is absolute and replay-safe (re-applying one logical update cannot
    drift or duplicate);
  * malformed controller / state / request / entity identity fails closed before
    any staging;
  * known state requires a non-empty unique entries array; unknown/not_applicable
    forbid entries; entry values are plain scalars and only when known;
  * malformed or duplicate existing entity_state truth fails closed and is never
    canonicalized by overwrite;
  * generic SAVE stage/delete cannot bypass the validated route; the existing
    ordinary-save allowlist is preserved;
  * entity state composes with an already-authorized inventory mutation in one
    all-or-nothing save and does not mutate unrelated state;
  * an aborted mutation leaves no durable entity state;
  * generation, exact Git ref, mirror parity and confirmation remain valid after
    publication;
  * the route is service-role-only and the migration installs cleanly.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402


HERO = "character:test-hero"
BEAST = "creature:test-wolf"


# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

def _run_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _run_as_role(db, role, fn):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
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


def _mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_entity_state(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_entity_state(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _stage_error(db, token, key, value):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        ),
    )


def _delete_error(db, token, key):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)", (token, key)
        ),
    )


def _inventory_mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_owner_inventory(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _published_entity_state(db):
    return u.published_state(db).get("entity_state") or []


def _staged_entity_state(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'entity_state'",
    )
    return value or []


def _entry(attribute="location", status="known", value="Tavern"):
    entry = {"attribute": attribute, "status": status}
    if status == "known":
        entry["value"] = value
    return entry


def _known(entries=None):
    return {"status": "known", "entries": [_entry()] if entries is None else entries}


def _request(entity=HERO, controller=None, state=None):
    return {
        "entity_id": entity,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "state": _known() if state is None else state,
    }


def _inventory_request(owner=HERO, controller=None, entries=None):
    return {
        "owner_entity_id": owner,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "inventory": {
            "status": "known",
            "entries": entries if entries is not None else [],
        },
    }


def _seed_published_entity_state(db, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select published_generation, 'entity_state', %s::jsonb, now(), now() "
        "from public.campaign_runtime where id = 1 "
        "on conflict (generation, key) do update set value = excluded.value",
        (json.dumps(value),),
    )


# ---------------------------------------------------------------------------
# Happy path + record shape
# ---------------------------------------------------------------------------

def test_mainrun_mutation_publishes_bounded_entity_state(db):
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(
            state=_known(
                entries=[
                    _entry("location", "known", "The Rusty Anchor"),
                    _entry("disposition", "known", "wary"),
                ]
            )
        ),
    )

    assert result["entity_id"] == HERO
    assert result["controller"] == {"kind": "mainrun"}
    assert result["state"]["status"] == "known"
    assert result["entity_state_mutation_version"] == 1

    # Staging is invisible until the existing publication handshake completes.
    assert _published_entity_state(db) == []

    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert len(records) == 1
    assert records[0]["entity_id"] == HERO
    assert records[0]["status"] == "known"
    assert {e["attribute"] for e in records[0]["entries"]} == {"location", "disposition"}


def test_run_owned_mutation_publishes_through_existing_spine(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(
            controller={"kind": "run", "run_id": "R01"},
            state=_known(entries=[_entry("hp_band", "known", "bloodied")]),
        ),
    )
    assert result["controller"] == {"kind": "run", "run_id": "R01"}

    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert records[0]["entries"][0] == {
        "attribute": "hp_band",
        "status": "known",
        "value": "bloodied",
    }


def test_unknown_and_not_applicable_states_are_coherent(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO, state={"status": "unknown"}))
    _mutate(db, token, _request(entity=BEAST, state={"status": "not_applicable"}))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = {r["entity_id"]: r for r in _published_entity_state(db)}
    assert records[HERO] == {"entity_id": HERO, "status": "unknown"}
    assert records[BEAST] == {"entity_id": BEAST, "status": "not_applicable"}


def test_entry_status_is_independent_of_box_status(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(
            state=_known(
                entries=[
                    _entry("location", "known", "The Rusty Anchor"),
                    _entry("current_goal", "unknown"),
                    _entry("hunger", "not_applicable"),
                ]
            )
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    entries = {e["attribute"]: e for e in _published_entity_state(db)[0]["entries"]}
    assert entries["location"] == {"attribute": "location", "status": "known", "value": "The Rusty Anchor"}
    assert entries["current_goal"] == {"attribute": "current_goal", "status": "unknown"}
    assert entries["hunger"] == {"attribute": "hunger", "status": "not_applicable"}


def test_multiple_entities_keep_exactly_one_record_each(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO))
    _mutate(db, token, _request(entity=BEAST))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert sorted(r["entity_id"] for r in records) == sorted([HERO, BEAST])


def test_mutation_is_absolute_and_replay_safe(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request(state=_known(entries=[_entry("location", "known", "Camp")]))
    _mutate(db, token, request)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_entity_state(db)
    assert len(records) == 1
    assert records[0]["entries"] == [
        {"attribute": "location", "status": "known", "value": "Camp"}
    ]


def test_abort_discards_unpublished_entity_state(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request())
    u.abort_save(db, token)

    assert _published_entity_state(db) == []


# ---------------------------------------------------------------------------
# Bounded validation (fail closed before staging)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state",
    [
        None,
        "not-an-object",
        {"status": "sometimes"},
        {"status": 1},
        {"status": "known"},
        {"status": "known", "entries": []},
        {"status": "known", "entries": "nope"},
        {"status": "known", "entries": [_entry()], "extra": 1},
        {"status": "unknown", "entries": []},
        {"status": "not_applicable", "entries": [_entry()]},
        {"entries": [_entry()]},
    ],
)
def test_invalid_state_payload_fails_closed(db, state):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": HERO, "controller": {"kind": "mainrun"}, "state": state}
    err = _mutate_error(db, token, request)
    assert "entity state" in err or "status" in err or "entries" in err


@pytest.mark.parametrize(
    "entry",
    [
        {"status": "known", "value": 1},
        {"attribute": "x", "value": 1},
        {"attribute": "x", "status": "sometimes"},
        {"attribute": "", "status": "known", "value": 1},
        {"attribute": "x", "status": "known"},
        {"attribute": "x", "status": "known", "value": None},
        {"attribute": "x", "status": "known", "value": [1]},
        {"attribute": "x", "status": "known", "value": {"a": 1}},
        {"attribute": "x", "status": "unknown", "value": 1},
        {"attribute": "x", "status": "known", "value": 1, "extra": 1},
    ],
)
def test_invalid_entry_payload_fails_closed(db, entry):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _request(state=_known(entries=[entry]))
    )
    assert "entry" in err or "value" in err


def test_duplicate_entries_fail_closed_under_json_value_equality(db):
    _published, _staging, token, _expires = u.begin_save(db)
    duplicate = _entry("location", "known", "Camp")
    err = _mutate_error(db, token, _request(state=_known(entries=[duplicate, duplicate])))
    assert "unique" in err.lower()


def test_duplicate_entries_differing_only_by_integral_spelling_fail_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(
            state=_known(
                entries=[
                    _entry("count", "known", 1),
                    _entry("count", "known", 1.0),
                ]
            )
        ),
    )
    assert "unique" in err.lower()


@pytest.mark.parametrize(
    "entity",
    [
        "party:test-stash",
        "item:test-blade",
        "location:test-town",
        "character:",
        "character:Bad Slug",
        123,
        None,
    ],
)
def test_entity_must_be_a_character_or_creature_identity(db, entity):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": entity, "controller": {"kind": "mainrun"}, "state": _known()}
    err = _mutate_error(db, token, request)
    assert "entity" in err.lower()


def test_request_rejects_fields_outside_the_contract(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request()
    request["narrative"] = "ignore this"
    err = _mutate_error(db, token, request)
    assert "outside the EV2-13 contract" in err


@pytest.mark.parametrize(
    "controller",
    [
        None,
        "mainrun",
        {},
        {"kind": None},
        {"kind": 1},
        {"kind": "MAINRUN"},
        {"kind": "run"},
        {"kind": "run", "run_id": "R1"},
        {"kind": "run", "run_id": "R01", "extra": 1},
        {"kind": "mainrun", "extra": 1},
    ],
)
def test_controller_shape_is_bounded(db, controller):
    _published, _staging, token, _expires = u.begin_save(db)
    request = {"entity_id": HERO, "controller": controller, "state": _known()}
    err = _mutate_error(db, token, request)
    assert "controller" in err.lower()


def test_mutation_requires_an_active_campaign_save(db):
    err = _mutate_error(db, "not-a-real-token", _request())
    assert "lock" in err.lower()


# ---------------------------------------------------------------------------
# Malformed existing truth (never canonicalized by overwrite)
# ---------------------------------------------------------------------------

def test_malformed_existing_truth_fails_closed_even_for_unrelated_entity(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _seed_published_entity_state(
        db,
        [
            {"entity_id": BEAST, "status": "unknown", "entries": [_entry()]},
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "entity state" in err or "entries" in err


def test_duplicate_existing_records_fail_closed(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[])])
    _seed_published_entity_state(
        db,
        [
            {"entity_id": HERO, "status": "unknown"},
            {"entity_id": HERO, "status": "not_applicable"},
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(entity=HERO))
    assert "duplicate" in err.lower() or "entity_state" in err


# ---------------------------------------------------------------------------
# Bypass closure + authority
# ---------------------------------------------------------------------------

def test_generic_save_cannot_write_or_delete_the_entity_state_key(db):
    _published, _staging, token, _expires = u.begin_save(db)

    err_stage = _stage_error(db, token, "entity_state", [_known()])
    assert "mutate_entity_state" in err_stage

    err_delete = _delete_error(db, token, "entity_state")
    assert "entity_state" in err_delete


def test_existing_generic_allowed_keys_still_work_after_ev213(db):
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(db, token, "live_status", {"scene": "workshop"})
    u.publish(db, token)
    u.confirm_mirror(db)

    assert u.published_state(db).get("live_status") == {"scene": "workshop"}


def test_route_is_not_executable_by_anon_or_authenticated(db):
    _published, _staging, token, _expires = u.begin_save(db)
    for role in ("anon", "authenticated"):
        err = _error_as_role(
            db,
            role,
            lambda cur: cur.execute(
                "select public.mutate_entity_state(%s, %s::jsonb)",
                (token, json.dumps(_request())),
            ),
        )
        assert "permission denied" in err.lower()


# ---------------------------------------------------------------------------
# Composition + isolation
# ---------------------------------------------------------------------------

def test_composes_with_inventory_mutation_in_one_all_or_nothing_save(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO))
    _inventory_mutate(db, token, _inventory_request(entries=[]))
    u.publish(db, token)
    u.confirm_mirror(db)

    published = u.published_state(db)
    assert published["entity_state"][0]["entity_id"] == HERO
    assert published["inventory"][0]["entity_id"] == HERO


def test_entity_state_mutation_does_not_touch_inventory_or_custody(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO))
    u.publish(db, token)
    u.confirm_mirror(db)

    published = u.published_state(db)
    assert "inventory" not in published
    assert "item_custody" not in published


# ---------------------------------------------------------------------------
# Publication integrity
# ---------------------------------------------------------------------------

def test_publication_keeps_generation_git_ref_mirror_and_confirmation_valid(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(entity=HERO))
    u.publish(db, token)
    u.confirm_mirror(db)

    row = u.runtime_row(db)
    assert row["runtime_published_confirmed"] is True
    assert row["published_git_ref"]
    assert row["last_confirmed_generation"] == row["published_generation"]
    assert row["last_confirmed_git_ref"] == row["published_git_ref"]
    assert row["save_in_progress"] is False
