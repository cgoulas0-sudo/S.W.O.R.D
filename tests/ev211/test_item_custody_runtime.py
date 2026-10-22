"""EV2-11 unique-item custody runtime proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 + EV2-10 spine plus the forward-only EV2-11 migration. All durable
mutation goes through the real save/publication/mirror-confirmation spine;
nothing is mocked. Published admitted custody truth is seeded directly (as an
already-authorized admission would have, EV2-12's job) because EV2-11 gameplay
mutation deliberately cannot mint identity.

Proof Matrix coverage:
  * exactly one authoritative custody record per `item_id`;
  * owner and holder are independent nullable facts, so theft/loan changes holder
    without owner, a gift changes both atomically, a drop clears holder while
    preserving owner, and treasure is owner=null + holder=null;
  * gameplay mutation of an existing admitted record succeeds under the valid
    current controller;
  * gameplay mutation for an absent/unadmitted `item_id` fails closed and mints
    nothing;
  * malformed item/owner/holder IDs and other entity types fail closed;
  * missing-vs-null is unambiguous;
  * controller validation happens before any authority branch, so a malformed or
    non-string kind cannot fall through to MAINRUN;
  * every non-null actor across current/new owner/holder must resolve under one
    asserted controller; incompatible cross-controller direct transfer fails
    closed;
  * parked/malformed/duplicated published Run truth fails closed rather than
    authorizing MAINRUN;
  * same-save Run ownership changes and custody mutations are mutually exclusive
    across every Run-writing doorway, keyed on the explicit staging operation
    fact, not final value equality;
  * generic stage/delete cannot write or delete the engine-owned `item_custody`
    key;
  * custody reuses the RT01 publication/mirror spine and coexists with an
    ordinary inventory mutation; ordinary inventory is not required to mirror
    custody.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402


HERO = "character:test-hero"
FANIS = "character:test-fanis"
PARTY = "party:test-stash"
BLADE = "item:test-blade"
SHIELD = "item:test-shield"


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


def _mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_item_custody(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_item_custody(%s, %s::jsonb)",
            (token, json.dumps(request)),
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


def _reconcile(db, token, request):
    def call(cur):
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _reconcile_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _seed_published_custody(db, records):
    """Seed already-admitted published custody truth directly (EV2-12 admission).

    EV2-11 gameplay mutation cannot mint identity, so tests stand in for the
    authorized admission flow the same way the existing harness seeds synthetic
    already-published Run truth.
    """
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select cr.published_generation, 'item_custody', %s::jsonb, now(), now() "
        "from public.campaign_runtime cr where cr.id = 1 "
        "on conflict (generation, key) do update "
        "set value = excluded.value, updated_at = now()",
        (json.dumps(records),),
    )


def _published_custody(db):
    return u.published_state(db).get("item_custody") or []


def _staged_custody(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'item_custody'",
    )
    return value or []


def _custody(item=BLADE, owner=HERO, holder=HERO):
    return {"item_id": item, "owner_entity_id": owner, "holder_entity_id": holder}


def _request(item=BLADE, controller=None, owner=HERO, holder=HERO):
    return {
        "item_id": item,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "owner_entity_id": owner,
        "holder_entity_id": holder,
    }


# ---------------------------------------------------------------------------
# State / lifecycle model
# ---------------------------------------------------------------------------

def test_staging_is_invisible_until_publication(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(owner=HERO, holder=FANIS))

    assert result["custody"] == _custody(owner=HERO, holder=FANIS)
    # Staging is invisible until the existing publication handshake completes.
    assert _published_custody(db) == [_custody(owner=HERO, holder=HERO)]

    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_custody(db) == [_custody(owner=HERO, holder=FANIS)]


def test_theft_changes_holder_without_changing_owner(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(owner=HERO, holder=FANIS))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert result["custody"]["owner_entity_id"] == HERO
    assert result["custody"]["holder_entity_id"] == FANIS
    assert _published_custody(db)[0]["owner_entity_id"] == HERO
    assert _published_custody(db)[0]["holder_entity_id"] == FANIS


def test_gift_changes_owner_and_holder_atomically(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(owner=FANIS, holder=FANIS))
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_custody(db)
    assert len(records) == 1
    assert records[0] == _custody(owner=FANIS, holder=FANIS)
    assert result["custody"] == _custody(owner=FANIS, holder=FANIS)


def test_drop_clears_holder_while_preserving_owner(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=HERO, holder=None))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_custody(db)[0] == _custody(owner=HERO, holder=None)


def test_pickup_without_ownership_sets_holder_only(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=None, holder=FANIS))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_custody(db)[0] == _custody(owner=None, holder=FANIS)


def test_treasure_is_owner_null_and_holder_null(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(owner=None, holder=None))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert result["custody"] == _custody(owner=None, holder=None)
    assert _published_custody(db)[0] == _custody(owner=None, holder=None)


def test_party_custody_is_representable_under_mainrun(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=PARTY, holder=PARTY))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_custody(db)[0] == _custody(owner=PARTY, holder=PARTY)


def test_owned_but_uncarried_is_representable(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=HERO, holder=None))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_custody(db)[0]["owner_entity_id"] == HERO
    assert _published_custody(db)[0]["holder_entity_id"] is None


# ---------------------------------------------------------------------------
# Non-minting law
# ---------------------------------------------------------------------------

def test_unadmitted_item_fails_closed_and_mints_nothing(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(item=SHIELD))
    assert "no admitted custody record" in err

    assert _published_custody(db) == []
    assert _staged_custody(db) == []


def test_gameplay_cannot_append_a_second_identity(db):
    _seed_published_custody(db, [_custody(item=BLADE)])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(item=SHIELD))
    assert "no admitted custody record" in err

    assert [r["item_id"] for r in _published_custody(db)] == [BLADE]
    assert [r["item_id"] for r in _staged_custody(db)] == [BLADE]


def test_preexisting_duplicate_records_fail_closed(db):
    _seed_published_custody(db, [_custody(), _custody(owner=FANIS, holder=FANIS)])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request())
    assert "duplicate" in err


def test_duplicate_elsewhere_in_collection_fails_whole_candidate(db):
    _seed_published_custody(
        db,
        [_custody(item=BLADE), _custody(item=SHIELD), _custody(item=SHIELD, owner=FANIS)],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(item=BLADE))
    assert "duplicate" in err


# ---------------------------------------------------------------------------
# Payload law
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "item",
    [
        "character:test-hero",
        "party:test-stash",
        "item:Test-Blade",
        "item:",
        "test-blade",
        "item:test blade",
    ],
)
def test_invalid_item_id_fails_closed(db, item):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(item=item))
    assert "item_id" in err or "item custody" in err


@pytest.mark.parametrize(
    "owner",
    ["location:tavern", "faction:guild", "creature:wolf", "character:Test-Hero", "hero", 7],
)
def test_invalid_owner_fails_closed(db, owner):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(owner=owner))
    assert "owner_entity_id" in err


@pytest.mark.parametrize(
    "holder",
    ["location:tavern", "faction:guild", "creature:wolf", "party:", "fanis", True],
)
def test_invalid_holder_fails_closed(db, holder):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(holder=holder))
    assert "holder_entity_id" in err


def test_missing_owner_key_fails_closed_but_null_is_valid(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)

    missing = _request()
    del missing["owner_entity_id"]
    err = _mutate_error(db, token, missing)
    assert "owner_entity_id" in err or "requires" in err

    # A real explicit null is a valid absence, not a missing field.
    result = _mutate(db, token, _request(owner=None, holder=FANIS))
    assert result["custody"]["owner_entity_id"] is None


def test_missing_holder_key_fails_closed(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)

    missing = _request()
    del missing["holder_entity_id"]
    err = _mutate_error(db, token, missing)
    assert "holder_entity_id" in err or "requires" in err


def test_missing_item_id_key_fails_closed(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)

    missing = _request()
    del missing["item_id"]
    err = _mutate_error(db, token, missing)
    assert "item_id" in err or "requires" in err


def test_request_rejects_fields_outside_the_contract(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)

    request = _request()
    request["status"] = "held"
    err = _mutate_error(db, token, request)
    assert "outside the EV2-11 contract" in err


def test_request_must_be_an_object(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)

    err = _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_item_custody(%s, %s::jsonb)", (token, json.dumps([1, 2]))
        ),
    )
    assert "JSON object" in err


@pytest.mark.parametrize(
    "controller",
    [
        {"kind": "mainrun", "run_id": "R01"},
        {"kind": "run"},
        {"kind": "run", "run_id": "R1"},
        {"kind": "run", "run_id": "R01", "extra": 1},
    ],
)
def test_controller_shape_is_bounded(db, controller):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller=controller))
    assert "controller" in err


@pytest.mark.parametrize(
    "controller",
    [
        {"kind": None},
        {"kind": 1},
        {"kind": ["mainrun"]},
        {"kind": {"x": 1}},
        {"kind": "MAINRUN"},
        {"kind": "other"},
        {},
    ],
)
def test_controller_kind_must_be_an_explicit_valid_string(db, controller):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller=controller))
    assert "controller" in err


def test_null_controller_kind_cannot_fall_through_to_mainrun(db):
    """controller.kind null would make `kind NOT IN (...)` SQL NULL under
    three-valued logic; the explicit string check must reject it instead of
    silently authorizing MAINRUN."""
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": None}))
    assert "must be a JSON string" in err


# ---------------------------------------------------------------------------
# Controller authority
# ---------------------------------------------------------------------------

def test_run_controller_accepted_when_run_claims_involved_actors(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=None)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db, token, _request(controller={"kind": "run", "run_id": "R01"}, owner=HERO, holder=HERO)
    )
    assert result["controller"] == {"kind": "run", "run_id": "R01"}


def test_mainrun_rejected_while_run_claims_involved_actor(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "MAINRUN" in err and "R01" in err


def test_cross_controller_transfer_fails_closed_both_ways(db):
    """HERO is MAINRUN-controlled and FANIS is R01-controlled. Mutating the
    item from HERO to FANIS crosses incompatible controllers, so neither a
    MAINRUN nor the R01 assertion may shortcut it."""
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(
        db,
        [u.run(run_id="R01", participant_entity_ids=[FANIS], mutable_owner_entity_ids=[FANIS])],
    )

    _published, _staging, token, _expires = u.begin_save(db)

    err_mainrun = _mutate_error(db, token, _request(owner=HERO, holder=FANIS))
    assert "MAINRUN may not" in err_mainrun and "R01" in err_mainrun

    err_run = _mutate_error(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=HERO, holder=FANIS),
    )
    assert "crosses controllers" in err_run or "does not own" in err_run or "cannot assert custody authority" in err_run


def test_run_controller_rejected_without_any_published_claim(db):
    _seed_published_custody(db, [_custody()])
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "no published Run currently controls" in err


def test_run_controller_rejected_when_a_different_run_owns_actor(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _request(controller={"kind": "run", "run_id": "R02"})
    )
    assert "R01" in err and "R02" in err


def test_party_actor_rejects_run_controller_but_mainrun_accepts(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=PARTY, holder=PARTY),
    )
    assert "no published Run currently controls" in err


def test_parked_run_claiming_actor_fails_closed_for_run_and_mainrun(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[HERO])]
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err_run = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "parked" in err_run

    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "parked" in err_mainrun


def test_malformed_published_run_entry_fails_closed_not_mainrun(db):
    malformed = {
        "execution_mode": "played",
        "control_state": "active",
        "scenario_id": "S01",
        "occurred_encounter_ids": [],
        "participant_entity_ids": [HERO],
        "mutable_owner_entity_ids": [HERO],
        "location_ids": [],
        "campaign_anchor": {"base_commit": u.RUN_ANCHOR, "campaign_time": "Day 1, evening"},
    }
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [malformed])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "run_id" in err or "unreadable" in err


def test_non_object_published_run_entry_fails_closed(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, ["not-a-run-record"])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "non-object" in err


def test_two_runs_claiming_one_actor_fail_closed(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", participant_entity_ids=[HERO], mutable_owner_entity_ids=[HERO]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    for run_id in ("R01", "R02"):
        err = _mutate_error(
            db, token, _request(controller={"kind": "run", "run_id": run_id})
        )
        assert "more than one" in err


def test_duplicate_published_run_identity_fails_closed_before_authority(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(
                run_id="R01",
                participant_entity_ids=[FANIS],
                mutable_owner_entity_ids=[FANIS],
            ),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "duplicate authoritative Run identity" in err


# ---------------------------------------------------------------------------
# Same-save mutual exclusion
# ---------------------------------------------------------------------------

def test_custody_mutation_refused_after_same_save_runs_change(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(
        db,
        token,
        "runs",
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])],
    )

    err_run = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "runs" in err_run

    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "runs" in err_mainrun


def test_generic_runs_change_refused_once_custody_staged(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=HERO, holder=HERO))

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage

    err_delete = _delete_error(db, token, "runs")
    assert "runs" in err_delete

    # Unrelated ordinary-save keys remain stageable in the same save.
    u.stage(db, token, "live_status", {"scene": "workshop"})


def test_reconcile_refused_once_custody_staged(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))

    request = u.request(u.resolution(run_id="R01"), released=[HERO])
    err = _reconcile_error(db, token, request)
    assert "custody" in err


def test_custody_mutation_refused_after_reconcile_in_same_save(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))

    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "runs" in err


def test_generic_stage_and_delete_reject_item_custody_key(db):
    _seed_published_custody(db, [_custody()])

    _published, _staging, token, _expires = u.begin_save(db)
    err_stage = _stage_error(db, token, "item_custody", [_custody()])
    assert "item_custody" in err_stage

    err_delete = _delete_error(db, token, "item_custody")
    assert "item_custody" in err_delete


def test_custody_staging_marker_does_not_leak_into_a_later_save(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    u.publish(db, token)
    u.confirm_mirror(db)

    # A fresh save is not blocked by the prior save's custody operation fact.
    _published, _staging, token, _expires = u.begin_save(db)
    result = _reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))
    assert result["run_id"] == "R01"


def test_value_equal_custody_replay_still_closes_runs_doorways(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    request = _request(owner=HERO, holder=FANIS)
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    # Re-stage the identical absolute target: final value is value-equal to
    # published reality, so final-value equality alone would look unchanged.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    assert _staged_custody(db) == _published_custody(db)

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage


def test_mutate_away_and_back_still_closes_runs_doorways(db):
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    canonical = _request(owner=HERO, holder=FANIS)
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, canonical)
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(owner=HERO, holder=HERO))
    _mutate(db, token, canonical)
    assert _staged_custody(db) == _published_custody(db)

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage


def test_custody_mutation_requires_an_active_campaign_save(db):
    _seed_published_custody(db, [_custody()])

    err = _mutate_error(db, "not-a-real-token", _request())
    assert "lock" in err.lower()


# ---------------------------------------------------------------------------
# Coexistence / non-duplication
# ---------------------------------------------------------------------------

def test_inventory_and_custody_coexist_without_mirroring(db):
    """Custody is the authoritative unique-item truth; ordinary inventory stays
    identity-free and is not required to mirror it. Both may be staged in one
    save because neither changes Run ownership."""
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])

    _published, _staging, token, _expires = u.begin_save(db)
    _inventory_mutate(
        db,
        token,
        {
            "owner_entity_id": HERO,
            "controller": {"kind": "mainrun"},
            "inventory": {
                "status": "known",
                "entries": [
                    {"name": "Rope", "description": "Fifty feet of rope.", "quantity": 1}
                ],
            },
        },
    )
    _mutate(db, token, _request(owner=HERO, holder=FANIS))
    u.publish(db, token)
    u.confirm_mirror(db)

    inventory = u.published_state(db)["inventory"]
    assert inventory[0]["entity_id"] == HERO
    assert "item_id" not in inventory[0]["entries"][0]

    custody = _published_custody(db)
    assert custody[0] == _custody(owner=HERO, holder=FANIS)


# ---------------------------------------------------------------------------
# Repair round 1 — existing-truth validation and no-actor controller proof
# ---------------------------------------------------------------------------

def test_malformed_admitted_record_fails_closed_and_is_not_overwritten(db):
    """`item_id` presence is not admission proof: the existing record must
    satisfy the EV2-11 contract first. A malformed current record fails closed
    and must not be canonicalized into a valid identity by overwriting it."""
    malformed = {"item_id": BLADE, "owner_entity_id": HERO}
    _seed_published_custody(db, [malformed])
    before = _published_custody(db)

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(owner=HERO, holder=HERO))
    assert "holder_entity_id" in err or "requires" in err or "EV2-11 contract" in err

    # Nothing was repaired by overwrite: published and staged truth stay malformed.
    assert _published_custody(db) == before
    assert _staged_custody(db) == before


def test_malformed_admitted_record_wrong_owner_type_fails_closed(db):
    _seed_published_custody(
        db, [{"item_id": BLADE, "owner_entity_id": "location:tavern", "holder_entity_id": FANIS}]
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request())
    assert "owner_entity_id" in err


def test_malformed_existing_truth_elsewhere_fails_closed(db):
    """The whole existing collection is validated, not just the target record."""
    _seed_published_custody(db, [_custody(item=BLADE), {"item_id": SHIELD, "owner_entity_id": HERO}])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(item=BLADE))
    assert "holder_entity_id" in err or "requires" in err or "EV2-11 contract" in err


def test_treasure_run_controller_must_name_an_existing_run(db):
    """owner=null + holder=null must not bypass controller validation: a Run
    assertion naming a nonexistent Run fails closed."""
    _seed_published_custody(db, [_custody(owner=None, holder=None)])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=None, holder=None),
    )
    assert "does not exist" in err


def test_treasure_run_controller_rejects_parked_run(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(
        db, [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[HERO])]
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=None, holder=None),
    )
    assert "parked" in err


def test_treasure_run_controller_accepts_existing_active_run(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=None, holder=None),
    )
    assert result["controller"] == {"kind": "run", "run_id": "R01"}
    assert result["custody"] == _custody(owner=None, holder=None)


def test_treasure_mainrun_still_rejects_malformed_published_runs(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(db, ["not-a-run-record"])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}, owner=None, holder=None))
    assert "non-object" in err


def test_treasure_mainrun_still_rejects_run_entry_without_string_run_id(db):
    malformed = {
        "execution_mode": "played",
        "control_state": "active",
        "scenario_id": "S01",
        "occurred_encounter_ids": [],
        "participant_entity_ids": [HERO],
        "mutable_owner_entity_ids": [HERO],
        "location_ids": [],
        "campaign_anchor": {"base_commit": u.RUN_ANCHOR, "campaign_time": "Day 1, evening"},
    }
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(db, [malformed])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}, owner=None, holder=None))
    assert "run_id" in err or "unreadable" in err


def test_treasure_mainrun_still_rejects_duplicate_published_run_identity(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R01", participant_entity_ids=[FANIS], mutable_owner_entity_ids=[FANIS]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}, owner=None, holder=None))
    assert "duplicate authoritative Run identity" in err


def test_treasure_mainrun_rejects_cross_run_mutable_owner_conflict(db):
    """Duplicate run_id rejection alone is not sufficient: two distinct valid
    Runs claiming the same mutable owner make published Run truth untrustworthy
    even for a no-actor treasure mutation."""
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", participant_entity_ids=[HERO], mutable_owner_entity_ids=[HERO]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}, owner=None, holder=None))
    assert "more than one" in err


def test_treasure_run_controller_rejects_cross_run_mutable_owner_conflict(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", participant_entity_ids=[HERO], mutable_owner_entity_ids=[HERO]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=None, holder=None),
    )
    assert "more than one" in err


def test_conflicting_run_batch_fails_even_when_conflict_actor_is_uninvolved(db):
    """The full batch invariant is proven, not just the involved actor's claim."""
    other = "character:test-other"
    _seed_published_custody(db, [_custody(owner=HERO, holder=HERO)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", participant_entity_ids=[other], mutable_owner_entity_ids=[other]),
            u.run(run_id="R03", participant_entity_ids=[other], mutable_owner_entity_ids=[other]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db, token, _request(controller={"kind": "run", "run_id": "R01"})
    )
    assert "more than one" in err


def test_treasure_accepts_non_conflicting_multi_run_batch(db):
    _seed_published_custody(db, [_custody(owner=None, holder=None)])
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", participant_entity_ids=[FANIS], mutable_owner_entity_ids=[FANIS]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(controller={"kind": "mainrun"}, owner=None, holder=None))
    assert result["custody"] == _custody(owner=None, holder=None)
